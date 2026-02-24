import asyncio
from typing import List, Dict, Any, Optional
from loguru import logger
from ..protocols.base import Tag, DataType, TagReading
from ..protocols.fins_client import FINSClient
from ..protocols.modbus_client import ModbusTCPClient
from .connection_manager import ConnectionManager
import time

class TagDiscovery:
    """Auto-discover tags by scanning PLC memory"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.conn_manager = connection_manager
    
    async def discover_tags(
        self,
        device_id: str,
        memory_area: str = "DM",
        start_address: int = 0,
        count: int = 100,
        data_type: str = "uint16",
        sample_interval: float = 1.0,
        samples: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Auto-discover active tags by scanning memory range.
        
        Args:
            device_id: Device identifier
            memory_area: Memory area to scan (DM, CIO, WR, etc.)
            start_address: Starting address
            count: Number of addresses to scan
            data_type: Data type to read (uint16, int16, float32, etc.)
            sample_interval: Time between samples (seconds)
            samples: Number of samples to detect changes
        
        Returns:
            List of discovered tags with metadata
        """
        connection = self.conn_manager.get_connection(device_id)
        if not connection:
            raise ValueError(f"Device {device_id} not connected")
        
        logger.info(
            f"Starting tag discovery: {memory_area}{start_address}-"
            f"{start_address + count - 1} ({count} addresses)"
        )
        
        discovered_tags = []
        
        # Determine protocol-specific scanning
        if isinstance(connection.client, FINSClient):
            discovered_tags = await self._discover_fins_tags(
                connection.client,
                memory_area,
                start_address,
                count,
                DataType(data_type),
                sample_interval,
                samples
            )
        elif isinstance(connection.client, ModbusTCPClient):
            discovered_tags = await self._discover_modbus_tags(
                connection.client,
                start_address,
                count,
                DataType(data_type),
                sample_interval,
                samples
            )
        else:
            raise ValueError(f"Protocol {connection.protocol} not supported for discovery")
        
        logger.info(f"✓ Discovered {len(discovered_tags)} active tags")
        return discovered_tags
    
    async def _discover_fins_tags(
        self,
        client: FINSClient,
        memory_area: str,
        start_address: int,
        count: int,
        data_type: DataType,
        sample_interval: float,
        samples: int
    ) -> List[Dict[str, Any]]:
        """Discover FINS tags by sampling memory range"""
        
        discovered = []
        
        # Create temporary tags for scanning
        scan_tags = []
        for offset in range(count):
            address = start_address + offset
            tag = Tag(
                name=f"{memory_area}{address}",
                address=f"{memory_area}{address}",
                data_type=data_type,
                access="R"
            )
            scan_tags.append(tag)
        
        # Sample tags multiple times
        logger.info(f"Taking {samples} samples with {sample_interval}s interval...")
        all_samples = []
        
        for sample_num in range(samples):
            logger.info(f"Sample {sample_num + 1}/{samples}...")
            sample_readings = await client.read_multiple(scan_tags)
            all_samples.append(sample_readings)
            
            if sample_num < samples - 1:
                await asyncio.sleep(sample_interval)
        
        # Analyze samples to find active/changing tags
        for tag_idx, tag in enumerate(scan_tags):
            values = [
                sample[tag_idx].value 
                for sample in all_samples 
                if sample[tag_idx].quality == "good"
            ]
            
            if not values:
                continue
            
            # Check if tag has valid data
            is_active = any(v is not None and v != 0 for v in values)
            is_changing = len(set(values)) > 1
            
            if is_active or is_changing:
                tag_info = {
                    "name": tag.name,
                    "address": tag.address,
                    "data_type": data_type.value,
                    "memory_area": memory_area,
                    "current_value": values[-1],
                    "min_value": min(values),
                    "max_value": max(values),
                    "is_changing": is_changing,
                    "change_rate": self._calculate_change_rate(values),
                    "suggested_access": "R",  # Default to read-only
                    "confidence": "high" if is_changing else "medium"
                }
                discovered.append(tag_info)
                logger.debug(
                    f"✓ {tag.name}: {values[-1]} "
                    f"(changing={is_changing}, range={min(values)}-{max(values)})"
                )
        
        return discovered
    
    async def _discover_modbus_tags(
        self,
        client: ModbusTCPClient,
        start_address: int,
        count: int,
        data_type: DataType,
        sample_interval: float,
        samples: int
    ) -> List[Dict[str, Any]]:
        """Discover Modbus tags by sampling register range"""
        
        discovered = []
        
        # Modbus holding registers (40000 range)
        scan_tags = []
        for offset in range(count):
            address = 40001 + start_address + offset
            tag = Tag(
                name=f"HR_{start_address + offset}",
                address=str(address),
                data_type=data_type,
                access="R"
            )
            scan_tags.append(tag)
        
        # Sample multiple times
        logger.info(f"Taking {samples} samples with {sample_interval}s interval...")
        all_samples = []
        
        for sample_num in range(samples):
            logger.info(f"Sample {sample_num + 1}/{samples}...")
            sample_readings = await client.read_multiple(scan_tags)
            all_samples.append(sample_readings)
            
            if sample_num < samples - 1:
                await asyncio.sleep(sample_interval)
        
        # Analyze samples
        for tag_idx, tag in enumerate(scan_tags):
            values = [
                sample[tag_idx].value 
                for sample in all_samples 
                if sample[tag_idx].quality == "good"
            ]
            
            if not values:
                continue
            
            is_active = any(v is not None and v != 0 for v in values)
            is_changing = len(set(values)) > 1
            
            if is_active or is_changing:
                tag_info = {
                    "name": tag.name,
                    "address": tag.address,
                    "data_type": data_type.value,
                    "current_value": values[-1],
                    "min_value": min(values),
                    "max_value": max(values),
                    "is_changing": is_changing,
                    "change_rate": self._calculate_change_rate(values),
                    "suggested_access": "RW",
                    "confidence": "high" if is_changing else "medium"
                }
                discovered.append(tag_info)
        
        return discovered
    
    def _calculate_change_rate(self, values: List[Any]) -> float:
        """Calculate how often values change"""
        if len(values) < 2:
            return 0.0
        
        changes = sum(
            1 for i in range(1, len(values)) 
            if values[i] != values[i-1]
        )
        return changes / (len(values) - 1)
    
    async def discover_and_classify(
        self,
        device_id: str,
        memory_ranges: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Discover tags across multiple memory ranges and classify them.
        
        Args:
            device_id: Device ID
            memory_ranges: List of ranges to scan
                Example: [
                    {"area": "DM", "start": 0, "count": 100, "type": "uint16"},
                    {"area": "DM", "start": 1000, "count": 50, "type": "float32"}
                ]
        
        Returns:
            Classified tags by category
        """
        all_tags = []
        
        for range_spec in memory_ranges:
            tags = await self.discover_tags(
                device_id=device_id,
                memory_area=range_spec.get("area", "DM"),
                start_address=range_spec["start"],
                count=range_spec["count"],
                data_type=range_spec.get("type", "uint16")
            )
            all_tags.extend(tags)
        
        # Classify tags
        classified = {
            "sensors": [],      # Changing values (likely sensors)
            "setpoints": [],    # Static non-zero (likely setpoints)
            "statuses": [],     # Boolean-like (0/1 values)
            "counters": [],     # Incrementing values
            "unknown": []       # Everything else
        }
        
        for tag in all_tags:
            if tag["is_changing"]:
                if tag["change_rate"] > 0.5:
                    # Rapidly changing = sensor
                    classified["sensors"].append(tag)
                elif self._looks_like_counter(tag):
                    classified["counters"].append(tag)
                else:
                    classified["sensors"].append(tag)
            elif tag["max_value"] == 1 and tag["min_value"] == 0:
                # Binary values = status
                classified["statuses"].append(tag)
            elif tag["current_value"] != 0:
                # Static non-zero = setpoint
                classified["setpoints"].append(tag)
            else:
                classified["unknown"].append(tag)
        
        return classified
    
    def _looks_like_counter(self, tag: Dict[str, Any]) -> bool:
        """Check if tag looks like a counter (always increasing)"""
        # Simple heuristic: large value range suggests counter
        value_range = tag["max_value"] - tag["min_value"]
        return value_range > 100 and tag["min_value"] >= 0

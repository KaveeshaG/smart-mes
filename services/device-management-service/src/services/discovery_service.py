from typing import List
import time
import asyncio
from ..infrastructure.device_profiler import DeviceProfiler
from ..schemas.discovery_schema import (
    ScanResponse, 
    BatchScanResponse,
    DiscoveredDeviceSchema
)
from loguru import logger

class DiscoveryService:
    def __init__(self):
        self.profiler = DeviceProfiler()
    
    async def scan_network(self, subnet: str) -> ScanResponse:
        start_time = time.time()
        logger.info(f"Starting discovery scan: {subnet}")
        
        try:
            devices = await self.profiler.profile_subnet(subnet)
            
            device_schemas = [
                DiscoveredDeviceSchema(
                    ip_address=d.ip_address,
                    mac_address=d.mac_address,
                    hostname=d.hostname,
                    open_ports=d.open_ports or [],
                    response_time_ms=d.response_time_ms,
                    device_type=d.device_type.value,
                    vendor=d.vendor,
                    supported_protocols=[p.value for p in (d.supported_protocols or [])],
                    identification_confidence=d.identification_confidence
                )
                for d in devices
            ]
            
            duration = time.time() - start_time
            
            response = ScanResponse(
                total_hosts_scanned=256,
                devices_found=len(devices),
                scan_duration_seconds=round(duration, 2),
                devices=device_schemas
            )
            
            logger.info(f"Scan complete: {len(devices)} devices in {duration:.1f}s")
            return response
            
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            raise
    
    async def scan_multiple_networks(self, subnets: List[str]) -> BatchScanResponse:
        start_time = time.time()
        logger.info(f"Starting batch scan of {len(subnets)} subnets")
        
        try:
            tasks = [self.scan_network(subnet) for subnet in subnets]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            devices_by_subnet = {}
            all_devices = []
            total_hosts = 0
            
            for subnet, result in zip(subnets, results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to scan {subnet}: {result}")
                    devices_by_subnet[subnet] = []
                else:
                    devices_by_subnet[subnet] = result.devices
                    all_devices.extend(result.devices)
                    total_hosts += result.total_hosts_scanned
            
            duration = time.time() - start_time
            
            response = BatchScanResponse(
                total_subnets_scanned=len(subnets),
                total_hosts_scanned=total_hosts,
                total_devices_found=len(all_devices),
                scan_duration_seconds=round(duration, 2),
                devices_by_subnet={
                    subnet: [d.model_dump() for d in devices]
                    for subnet, devices in devices_by_subnet.items()
                },
                all_devices=all_devices
            )
            
            logger.info(
                f"Batch scan complete: {len(all_devices)} devices "
                f"across {len(subnets)} subnets in {duration:.1f}s"
            )
            return response
            
        except Exception as e:
            logger.error(f"Batch scan failed: {e}")
            raise

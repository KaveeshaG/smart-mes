from typing import Dict, List, Optional
from .network_scanner import NetworkScanner
from .port_scanner import PortScanner
from .protocol_prober import ProtocolProber
from ..models.domain.device import DiscoveredDevice, DeviceType, Protocol
from loguru import logger

class DeviceProfiler:
    """Orchestrates device discovery and profiling."""
    
    def __init__(self):
        self.network_scanner = NetworkScanner()
        self.port_scanner = PortScanner()
        self.protocol_prober = ProtocolProber()
    
    async def profile_subnet(self, subnet: str) -> List[DiscoveredDevice]:
        """Complete discovery workflow for a subnet."""
        discovered_devices = []
        
        logger.info(f"Step 1/3: Scanning network {subnet}")
        hosts = await self.network_scanner.scan_subnet(subnet)
        logger.info(f"Found {len(hosts)} active hosts")
        
        for host in hosts:
            try:
                device = await self._profile_single_device(host)
                if device:
                    discovered_devices.append(device)
            except Exception as e:
                logger.error(f"Failed to profile {host['ip']}: {e}")
        
        logger.info(f"Profiled {len(discovered_devices)} devices")
        return discovered_devices
    
    async def _profile_single_device(self, host: Dict) -> Optional[DiscoveredDevice]:
        """Profile a single host."""
        ip = host['ip']
        logger.debug(f"Profiling device: {ip}")
        
        open_ports = await self.port_scanner.scan_ports(ip)
        
        if not open_ports:
            logger.debug(f"{ip}: No industrial ports open")
            return None
        
        probe_result = await self.protocol_prober.probe_device(ip, open_ports)
        
        if not probe_result['supported_protocols']:
            logger.debug(f"{ip}: No recognized protocols")
            return None
        
        hostname = host.get('hostname')
        if not hostname:
            hostname = await self.network_scanner.resolve_hostname(ip)
        
        device = DiscoveredDevice(
            ip_address=ip,
            mac_address=host.get('mac'),
            hostname=hostname,
            open_ports=open_ports,
            device_type=DeviceType(probe_result.get('device_type', 'Unknown')),
            vendor=probe_result.get('vendor'),
            supported_protocols=[
                Protocol(p) for p in probe_result['supported_protocols']
            ],
            identification_confidence=probe_result['confidence']
        )
        
        logger.info(f"✓ {ip}: {device.device_type} | {device.supported_protocols}")
        return device

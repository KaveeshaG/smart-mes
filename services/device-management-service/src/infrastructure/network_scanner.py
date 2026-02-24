import asyncio
import subprocess
from typing import List, Dict, Optional
from ipaddress import IPv4Network
from loguru import logger
import platform

class NetworkScanner:
    """Performs ICMP ping sweep to discover active hosts."""
    
    def __init__(self, timeout: int = 2):
        self.timeout = timeout
    
    async def scan_subnet(self, subnet: str) -> List[Dict[str, str]]:
        """Scan subnet and return list of active hosts."""
        network = IPv4Network(subnet, strict=False)
        logger.info(f"Starting subnet scan: {network} ({network.num_addresses} hosts)")
        
        hosts = list(network.hosts())
        tasks = [self._ping_host(str(ip)) for ip in hosts]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        devices = [
            {'ip': str(hosts[i]), 'mac': None, 'hostname': None}
            for i, alive in enumerate(results)
            if alive is True
        ]
        
        logger.info(f"Ping scan found {len(devices)} devices")
        return devices
    
    async def _ping_host(self, ip: str) -> bool:
        """Async ping using subprocess."""
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', '-W', str(self.timeout), ip]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(process.wait(), timeout=self.timeout + 1)
            return process.returncode == 0
        except asyncio.TimeoutError:
            return False
        except Exception as e:
            logger.debug(f"Ping failed for {ip}: {e}")
            return False
    
    async def resolve_hostname(self, ip: str) -> Optional[str]:
        """Reverse DNS lookup"""
        try:
            process = await asyncio.create_subprocess_exec(
                'nslookup', ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(), 
                timeout=2
            )
            
            output = stdout.decode()
            if 'name =' in output:
                return output.split('name =')[1].strip().split('\n')[0]
            return None
        except:
            return None

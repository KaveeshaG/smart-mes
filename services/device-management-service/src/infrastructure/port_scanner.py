import asyncio
from typing import List
from loguru import logger

class PortScanner:
    """TCP port scanner for identifying industrial protocols."""
    
    COMMON_INDUSTRIAL_PORTS = [
        9600,   # FINS (Omron)
        502,    # Modbus TCP
        4840,   # OPC UA
        44818,  # EtherNet/IP
        102,    # Siemens S7
        2222,   # EtherNet/IP (alternate)
    ]
    
    def __init__(self, timeout: float = 3.0):
        self.timeout = timeout
    
    async def scan_ports(
        self, 
        ip: str, 
        ports: List[int] = None
    ) -> List[int]:
        """Scan TCP ports on a given IP."""
        if ports is None:
            ports = self.COMMON_INDUSTRIAL_PORTS
        
        logger.debug(f"Scanning {len(ports)} ports on {ip}")
        
        tasks = [self._check_port(ip, port) for port in ports]
        results = await asyncio.gather(*tasks)
        
        open_ports = [port for port, is_open in zip(ports, results) if is_open]
        logger.debug(f"{ip}: Open ports: {open_ports}")
        
        return open_ports
    
    async def _check_port(self, ip: str, port: int) -> bool:
        """Check if a TCP port is open."""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=self.timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return False

from typing import Optional
from .base import ProtocolClient
from .fins_client import FINSClient
from .modbus_client import ModbusTCPClient
from loguru import logger

class ProtocolFactory:
    """Factory for creating protocol clients"""
    
    @staticmethod
    def create_client(protocol: str) -> Optional[ProtocolClient]:
        """
        Create protocol client by name.
        
        Args:
            protocol: Protocol name (fins, modbus_tcp, opc_ua)
        
        Returns:
            Protocol client instance
        """
        protocol = protocol.lower()
        
        if protocol == 'fins':
            logger.info("Creating FINS client")
            return FINSClient()
        elif protocol in ['modbus_tcp', 'modbus']:
            logger.info("Creating Modbus TCP client")
            return ModbusTCPClient()
        # elif protocol == 'opc_ua':
        #     return OPCUAClient()  # Future implementation
        else:
            logger.error(f"Unknown protocol: {protocol}")
            return None

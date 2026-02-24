from typing import Optional, List, Dict
from loguru import logger
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
import asyncio
import struct

class ProtocolProber:
    """Identifies industrial protocols by handshake validation."""
    
    async def probe_device(self, ip: str, open_ports: List[int]) -> Dict:
        """Probe all detected protocols on a device."""
        results = {
            'supported_protocols': [],
            'vendor': None,
            'device_type': None,
            'confidence': 0.0,
            'details': {}
        }
        
        # FINS probe (Omron)
        if 9600 in open_ports:
            fins_result = await self.probe_fins(ip)
            if fins_result['is_valid']:
                results['supported_protocols'].append('fins')
                results['vendor'] = 'Omron'
                results['device_type'] = 'PLC'
                results['confidence'] = fins_result['confidence']
                results['details']['fins'] = fins_result
        
        # Modbus TCP probe
        if 502 in open_ports:
            modbus_result = await self.probe_modbus_tcp(ip)
            if modbus_result['is_valid']:
                results['supported_protocols'].append('modbus_tcp')
                if not results['vendor']:
                    results['vendor'] = modbus_result.get('vendor')
                if not results['device_type']:
                    results['device_type'] = 'PLC'
                results['confidence'] = max(results['confidence'], modbus_result['confidence'])
                results['details']['modbus'] = modbus_result
        
        return results
    
    async def probe_fins(self, ip: str, port: int = 9600) -> Dict:
        """Validate FINS connectivity (Omron protocol)."""
        result = {
            'is_valid': False,
            'vendor': 'Omron',
            'port': port,
            'confidence': 0.0,
            'error': None,
            'fins_info': {}
        }
        
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=5.0
            )
            
            # FINS TCP handshake frame
            fins_handshake = bytearray([
                0x46, 0x49, 0x4E, 0x53,  # 'FINS' header
                0x00, 0x00, 0x00, 0x0C,  # Length (12 bytes)
                0x00, 0x00, 0x00, 0x00,  # Command (0 = node address)
                0x00, 0x00, 0x00, 0x00,  # Error code
                0x00, 0x00, 0x00, 0x00   # Client node
            ])
            
            writer.write(fins_handshake)
            await writer.drain()
            
            response = await asyncio.wait_for(
                reader.read(1024),
                timeout=3.0
            )
            
            if len(response) >= 8 and response[0:4] == b'FINS':
                result['is_valid'] = True
                result['confidence'] = 0.95
                result['fins_info'] = {
                    'response_length': len(response),
                    'header': response[0:4].decode('ascii')
                }
                logger.info(f"✓ FINS protocol detected on {ip}:{port}")
            else:
                result['error'] = "Invalid FINS response"
            
            writer.close()
            await writer.wait_closed()
            
        except asyncio.TimeoutError:
            result['error'] = "Timeout during FINS handshake"
        except ConnectionRefusedError:
            result['error'] = "Connection refused"
        except Exception as e:
            result['error'] = f"FINS probe error: {e}"
        
        return result
    
    async def probe_modbus_tcp(
        self, 
        ip: str, 
        port: int = 502,
        unit_id: int = 1
    ) -> Dict:
        """Validate Modbus TCP connectivity."""
        result = {
            'is_valid': False,
            'vendor': None,
            'unit_id': unit_id,
            'confidence': 0.0,
            'error': None
        }
        
        client = AsyncModbusTcpClient(
            host=ip,
            port=port,
            timeout=3.0
        )
        
        try:
            connected = await asyncio.wait_for(
                client.connect(), 
                timeout=5.0
            )
            
            if not connected:
                result['error'] = "Connection refused"
                return result
            
            response = await client.read_holding_registers(
                address=0, 
                count=1, 
                slave=unit_id
            )
            
            if not response.isError():
                result['is_valid'] = True
                result['confidence'] = 0.9
                logger.info(f"✓ Modbus TCP detected on {ip}:{port}")
            else:
                result['is_valid'] = True
                result['confidence'] = 0.5
                result['error'] = f"Modbus error: {response}"
            
            client.close()
            
        except asyncio.TimeoutError:
            result['error'] = "Timeout during Modbus handshake"
        except ModbusException as e:
            result['error'] = f"Modbus exception: {e}"
        except Exception as e:
            result['error'] = f"Unexpected error: {e}"
        
        return result

import asyncio
from typing import Any, List, Optional
from loguru import logger
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from .base import ProtocolClient, Tag, TagReading, DataType
import time
import struct

class ModbusTCPClient(ProtocolClient):
    """
    Modbus TCP Protocol Client.
    
    Address Format:
    - 0xxxx: Coils (Read/Write)
    - 1xxxx: Discrete Inputs (Read-only)
    - 3xxxx: Input Registers (Read-only)
    - 4xxxx: Holding Registers (Read/Write)
    """
    
    def __init__(self):
        self.client = None
        self._connected = False
        self.ip = None
        self.port = None
        self.unit_id = 1
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self.client is not None and self.client.connected
    
    async def connect(self, ip: str, port: int = 502, **kwargs) -> bool:
        """Connect to Modbus TCP device"""
        try:
            self.ip = ip
            self.port = port
            self.unit_id = kwargs.get('unit_id', 1)
            
            self.client = AsyncModbusTcpClient(
                host=ip,
                port=port,
                timeout=kwargs.get('timeout', 3.0)
            )
            
            connected = await asyncio.wait_for(
                self.client.connect(),
                timeout=5.0
            )
            
            if connected:
                self._connected = True
                logger.info(f"✓ Modbus TCP connected to {ip}:{port} (unit={self.unit_id})")
                return True
            else:
                logger.error(f"Failed to connect to {ip}:{port}")
                return False
                
        except Exception as e:
            logger.error(f"Modbus connection error: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close Modbus connection"""
        if self.client:
            self.client.close()
        self._connected = False
    
    async def read_tag(self, tag: Tag) -> TagReading:
        """Read single tag from Modbus device"""
        if not self._connected:
            raise RuntimeError("Not connected to device")
        
        address, function_code = self._parse_address(tag.address)
        
        try:
            if function_code == 'coil':
                response = await self.client.read_coils(
                    address=address,
                    count=1,
                    slave=self.unit_id
                )
                if not response.isError():
                    value = bool(response.bits[0])
                else:
                    raise RuntimeError(f"Modbus error: {response}")
                    
            elif function_code == 'discrete_input':
                response = await self.client.read_discrete_inputs(
                    address=address,
                    count=1,
                    slave=self.unit_id
                )
                if not response.isError():
                    value = bool(response.bits[0])
                else:
                    raise RuntimeError(f"Modbus error: {response}")
                    
            elif function_code == 'input_register':
                word_count = self._get_word_count(tag.data_type)
                response = await self.client.read_input_registers(
                    address=address,
                    count=word_count,
                    slave=self.unit_id
                )
                if not response.isError():
                    value = self._decode_registers(response.registers, tag.data_type)
                else:
                    raise RuntimeError(f"Modbus error: {response}")
                    
            elif function_code == 'holding_register':
                word_count = self._get_word_count(tag.data_type)
                response = await self.client.read_holding_registers(
                    address=address,
                    count=word_count,
                    slave=self.unit_id
                )
                if not response.isError():
                    value = self._decode_registers(response.registers, tag.data_type)
                else:
                    raise RuntimeError(f"Modbus error: {response}")
            else:
                raise ValueError(f"Unknown function code: {function_code}")
            
            return TagReading(
                tag_name=tag.name,
                value=value,
                timestamp=time.time(),
                quality="good"
            )
            
        except Exception as e:
            logger.error(f"Failed to read {tag.name}: {e}")
            return TagReading(
                tag_name=tag.name,
                value=None,
                timestamp=time.time(),
                quality="bad"
            )
    
    async def write_tag(self, tag: Tag, value: Any) -> bool:
        """Write single tag to Modbus device"""
        if not self._connected:
            raise RuntimeError("Not connected to device")

        if "W" not in tag.access:
            raise ValueError(f"Tag {tag.name} is read-only (access='{tag.access}')")

        address, function_code = self._parse_address(tag.address)
        
        try:
            if function_code == 'coil':
                response = await self.client.write_coil(
                    address=address,
                    value=bool(value),
                    slave=self.unit_id
                )
                return not response.isError()
                
            elif function_code == 'holding_register':
                registers = self._encode_registers(value, tag.data_type)
                if len(registers) == 1:
                    response = await self.client.write_register(
                        address=address,
                        value=registers[0],
                        slave=self.unit_id
                    )
                else:
                    response = await self.client.write_registers(
                        address=address,
                        values=registers,
                        slave=self.unit_id
                    )
                return not response.isError()
            else:
                raise ValueError(f"Cannot write to {function_code}")
                
        except Exception as e:
            logger.error(f"Failed to write {tag.name}: {e}")
            return False
    
    async def change_plc_mode(self, run: bool, **kwargs) -> bool:
        """Change PLC mode via a control register (holding register).

        For Modbus PLCs that lack native RUN/STOP commands, a designated
        holding register is used as a 'Run Enable' flag.  The PLC ladder
        program must check this register to allow or block execution.

        kwargs:
            control_register: Modbus address string, e.g. "40100"
        """
        if not self._connected:
            raise RuntimeError("Not connected to device")

        control_register = kwargs.get("control_register")
        if not control_register:
            raise ValueError(
                "No control_register configured for this Modbus device. "
                "Set the Run Enable Register address in device settings."
            )

        address, function_code = self._parse_address(str(control_register))

        if function_code == "coil":
            value = run
            response = await self.client.write_coil(
                address=address, value=bool(value), slave=self.unit_id
            )
        elif function_code == "holding_register":
            value = 1 if run else 0
            response = await self.client.write_register(
                address=address, value=value, slave=self.unit_id
            )
        else:
            raise ValueError(
                f"Control register {control_register} must be a coil (0xxxx) "
                f"or holding register (4xxxx)"
            )

        success = not response.isError()
        mode_label = "RUN (1)" if run else "STOP (0)"
        if success:
            logger.info(
                f"✓ Modbus control register {control_register} set to {mode_label}"
            )
        else:
            logger.error(
                f"✗ Failed to write {mode_label} to control register {control_register}"
            )
        return success

    async def read_multiple(self, tags: List[Tag]) -> List[TagReading]:
        """Read multiple tags"""
        readings = []
        for tag in tags:
            reading = await self.read_tag(tag)
            readings.append(reading)
        return readings
    
    def _parse_address(self, address: str) -> tuple:
        """
        Parse Modbus address.
        
        Format:
        - 0xxxx: Coils
        - 1xxxx: Discrete Inputs
        - 3xxxx: Input Registers
        - 4xxxx: Holding Registers
        """
        addr = int(address)
        
        if 1 <= addr <= 9999:
            return addr - 1, 'coil'
        elif 10001 <= addr <= 19999:
            return addr - 10001, 'discrete_input'
        elif 30001 <= addr <= 39999:
            return addr - 30001, 'input_register'
        elif 40001 <= addr <= 49999:
            return addr - 40001, 'holding_register'
        else:
            # Assume holding register if no prefix
            return addr, 'holding_register'
    
    def _get_word_count(self, data_type: DataType) -> int:
        """Get register count for data type"""
        if data_type in [DataType.BOOL, DataType.INT16, DataType.UINT16]:
            return 1
        elif data_type in [DataType.INT32, DataType.UINT32, DataType.FLOAT32]:
            return 2
        return 1
    
    def _decode_registers(self, registers: List[int], data_type: DataType) -> Any:
        """Decode Modbus registers to value"""
        if data_type == DataType.INT16:
            return struct.unpack('>h', struct.pack('>H', registers[0]))[0]
        elif data_type == DataType.UINT16:
            return registers[0]
        elif data_type == DataType.INT32:
            bytes_val = struct.pack('>HH', registers[0], registers[1])
            return struct.unpack('>i', bytes_val)[0]
        elif data_type == DataType.UINT32:
            bytes_val = struct.pack('>HH', registers[0], registers[1])
            return struct.unpack('>I', bytes_val)[0]
        elif data_type == DataType.FLOAT32:
            bytes_val = struct.pack('>HH', registers[0], registers[1])
            return struct.unpack('>f', bytes_val)[0]
        elif data_type == DataType.BOOL:
            return bool(registers[0])
        return registers[0]
    
    def _encode_registers(self, value: Any, data_type: DataType) -> List[int]:
        """Encode value to Modbus registers"""
        if data_type == DataType.INT16:
            packed = struct.pack('>h', int(value))
            return [struct.unpack('>H', packed)[0]]
        elif data_type == DataType.UINT16:
            return [int(value)]
        elif data_type == DataType.INT32:
            packed = struct.pack('>i', int(value))
            return list(struct.unpack('>HH', packed))
        elif data_type == DataType.UINT32:
            packed = struct.pack('>I', int(value))
            return list(struct.unpack('>HH', packed))
        elif data_type == DataType.FLOAT32:
            packed = struct.pack('>f', float(value))
            return list(struct.unpack('>HH', packed))
        elif data_type == DataType.BOOL:
            return [1 if value else 0]
        return [int(value)]

import asyncio
import struct
from typing import Any, List, Optional, Tuple
from loguru import logger
from .base import ProtocolClient, Tag, TagReading, DataType
import time

class FINSClient(ProtocolClient):
    """
    Omron FINS Protocol Client for CP2E PLC.
    
    Memory Areas:
    - CIO: 0x30 (I/O and Work Relays)
    - WR:  0x31 (Work Relays)
    - HR:  0x32 (Holding Relays)
    - AR:  0x33 (Auxiliary Relays)
    - DM:  0x02 (Data Memory)
    - EM:  0x0A (Extended Memory)
    
    Address Formats:
    - Word: "DM1000", "CIO100"
    - Bit: "CIO0.00", "CIO100.05", "WR10.03"
    """
    
    MEMORY_AREAS = {
        'CIO': 0x30,
        'WR': 0x31,
        'HR': 0x32,
        'AR': 0x33,
        'DM': 0x02,
        'EM': 0x0A,
    }
    
    def __init__(self):
        self.reader = None
        self.writer = None
        self._connected = False
        self._local_node = 0x00
        self._remote_node = 0x00
        self._sid = 0x00
        self.ip = None
        self.port = None
    
    @property
    def is_connected(self) -> bool:
        return (
            self._connected
            and self.writer is not None
            and not self.writer.is_closing()
        )
    
    async def connect(self, ip: str, port: int = 9600, **kwargs) -> bool:
        """Connect to Omron PLC via FINS/TCP."""
        try:
            self.ip = ip
            self.port = port
            
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=5.0
            )
            
            # FINS/TCP handshake
            handshake = bytearray([
                0x46, 0x49, 0x4E, 0x53,
                0x00, 0x00, 0x00, 0x0C,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00
            ])
            
            self.writer.write(handshake)
            await self.writer.drain()
            
            response = await asyncio.wait_for(
                self.reader.read(24),
                timeout=3.0
            )
            
            if len(response) >= 24 and response[0:4] == b'FINS':
                self._local_node = response[19]
                self._remote_node = response[23]
                self._connected = True
                logger.info(
                    f"✓ FINS connected to {ip}:{port} "
                    f"(local={self._local_node}, remote={self._remote_node})"
                )
                return True
            else:
                logger.error("Invalid FINS handshake response")
                return False
                
        except Exception as e:
            logger.error(f"FINS connection error: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close FINS connection"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self._connected = False
    
    async def read_tag(self, tag: Tag) -> TagReading:
        """Read single tag from PLC."""
        if not self._connected:
            raise RuntimeError("Not connected to PLC")
        
        area_str, address, bit = self._parse_address(tag.address)
        area_code = self.MEMORY_AREAS.get(area_str.upper())
        
        if area_code is None:
            raise ValueError(f"Invalid memory area: {area_str}")
        
        # Determine if bit or word access
        if bit is not None:
            # Bit access
            command = self._build_read_bit_command(area_code, address, bit)
            response = await self._send_command(command)
            value = self._parse_read_bit_response(response)
        else:
            # Word access
            word_count = self._get_word_count(tag.data_type)
            command = self._build_read_command(area_code, address, word_count)
            response = await self._send_command(command)
            value = self._parse_read_response(response, tag.data_type)
        
        return TagReading(
            tag_name=tag.name,
            value=value,
            timestamp=time.time(),
            quality="good"
        )
    
    async def write_tag(self, tag: Tag, value: Any) -> bool:
        """Write single tag to PLC"""
        if not self._connected:
            raise RuntimeError("Not connected to PLC")

        if "W" not in tag.access:
            raise ValueError(f"Tag {tag.name} is read-only (access='{tag.access}')")

        area_str, address, bit = self._parse_address(tag.address)
        area_code = self.MEMORY_AREAS.get(area_str.upper())
        
        if bit is not None:
            # Bit write
            command = self._build_write_bit_command(area_code, address, bit, bool(value))
        else:
            # Word write
            command = self._build_write_command(area_code, address, value, tag.data_type)
        
        response = await self._send_command(command)
        return self._check_write_response(response)
    
    async def change_plc_mode(self, run: bool) -> bool:
        """Switch PLC between RUN and PROGRAM mode using FINS commands 0401/0402."""
        if not self._connected:
            raise RuntimeError("Not connected to PLC")

        if run:
            command = self._build_run_command()
            logger.info(f"Sending FINS RUN command to {self.ip}:{self.port}")
        else:
            command = self._build_stop_command()
            logger.info(f"Sending FINS STOP command to {self.ip}:{self.port}")

        response = await self._send_command(command)
        success = self._check_write_response(response)

        if success:
            logger.info(f"✓ PLC mode changed to {'RUN' if run else 'PROGRAM/STOP'}")
        else:
            logger.error(f"✗ Failed to change PLC mode to {'RUN' if run else 'PROGRAM/STOP'}")

        return success

    def _build_run_command(self) -> bytearray:
        """Build FINS command 0401 — switch PLC to RUN mode."""
        self._sid = (self._sid + 1) % 256

        # Data: program number (FFFF = all programs) + mode (04 = RUN)
        command = bytearray([
            0x46, 0x49, 0x4E, 0x53,  # FINS magic
            0x00, 0x00, 0x00, 0x17,  # Length = 23 (8 + 10 + 2 + 3)
            0x00, 0x00, 0x00, 0x02,  # Command type (FINS frame)
            0x00, 0x00, 0x00, 0x00,  # Error code

            0x80, 0x00, 0x02,                    # ICF, RSV, GCT
            0x00, self._remote_node, 0x00,       # DNA, DA1, DA2
            0x00, self._local_node, 0x00,        # SNA, SA1, SA2
            self._sid,                           # SID

            0x04, 0x01,              # RUN command

            0xFF, 0xFF,              # Program number (all)
            0x04,                    # Mode: 04 = RUN
        ])

        return command

    def _build_stop_command(self) -> bytearray:
        """Build FINS command 0402 — switch PLC to PROGRAM/STOP mode."""
        self._sid = (self._sid + 1) % 256

        command = bytearray([
            0x46, 0x49, 0x4E, 0x53,  # FINS magic
            0x00, 0x00, 0x00, 0x14,  # Length = 20 (8 + 10 + 2)
            0x00, 0x00, 0x00, 0x02,  # Command type (FINS frame)
            0x00, 0x00, 0x00, 0x00,  # Error code

            0x80, 0x00, 0x02,                    # ICF, RSV, GCT
            0x00, self._remote_node, 0x00,       # DNA, DA1, DA2
            0x00, self._local_node, 0x00,        # SNA, SA1, SA2
            self._sid,                           # SID

            0x04, 0x02,              # STOP command
        ])

        return command

    async def read_multiple(self, tags: List[Tag]) -> List[TagReading]:
        """Read multiple tags sequentially"""
        readings = []
        for tag in tags:
            try:
                reading = await self.read_tag(tag)
                readings.append(reading)
            except Exception as e:
                logger.error(f"Failed to read {tag.name}: {e}")
                readings.append(TagReading(
                    tag_name=tag.name,
                    value=None,
                    timestamp=time.time(),
                    quality="bad"
                ))
        return readings
    
    def _parse_address(self, address: str) -> Tuple[str, int, Optional[int]]:
        """
        Parse address string.
        
        Examples:
        - "DM1000" -> ("DM", 1000, None)
        - "CIO100" -> ("CIO", 100, None)
        - "CIO0.05" -> ("CIO", 0, 5)
        - "CIO100.03" -> ("CIO", 100, 3)
        """
        import re
        
        # Try bit format first (e.g., CIO100.05)
        match = re.match(r'([A-Z]+)(\d+)\.(\d+)', address.upper())
        if match:
            area = match.group(1)
            word = int(match.group(2))
            bit = int(match.group(3))
            return area, word, bit
        
        # Word format (e.g., DM1000)
        match = re.match(r'([A-Z]+)(\d+)', address.upper())
        if not match:
            raise ValueError(f"Invalid address format: {address}")
        
        area = match.group(1)
        word = int(match.group(2))
        return area, word, None
    
    def _get_word_count(self, data_type: DataType) -> int:
        """Get word count for data type"""
        if data_type in [DataType.BOOL, DataType.INT16, DataType.UINT16]:
            return 1
        elif data_type in [DataType.INT32, DataType.UINT32, DataType.FLOAT32]:
            return 2
        return 1
    
    def _build_read_command(
        self, 
        area_code: int, 
        address: int, 
        word_count: int
    ) -> bytearray:
        """Build FINS memory area read command"""
        self._sid = (self._sid + 1) % 256
        
        command = bytearray([
            0x46, 0x49, 0x4E, 0x53,
            0x00, 0x00, 0x00, 0x1A,
            0x00, 0x00, 0x00, 0x02,
            0x00, 0x00, 0x00, 0x00,
            
            0x80, 0x00, 0x02,
            0x00, self._remote_node, 0x00,
            0x00, self._local_node, 0x00,
            self._sid,
            
            0x01, 0x01,  # Read command
            
            area_code,
            (address >> 8) & 0xFF,
            address & 0xFF,
            0x00,  # Bit position (0 for word)
            (word_count >> 8) & 0xFF,
            word_count & 0xFF,
        ])
        
        return command
    
    def _build_read_bit_command(
        self,
        area_code: int,
        address: int,
        bit: int
    ) -> bytearray:
        """Build FINS bit read command"""
        self._sid = (self._sid + 1) % 256
        
        command = bytearray([
            0x46, 0x49, 0x4E, 0x53,
            0x00, 0x00, 0x00, 0x1A,
            0x00, 0x00, 0x00, 0x02,
            0x00, 0x00, 0x00, 0x00,
            
            0x80, 0x00, 0x02,
            0x00, self._remote_node, 0x00,
            0x00, self._local_node, 0x00,
            self._sid,
            
            0x01, 0x01,  # Read command
            
            area_code,
            (address >> 8) & 0xFF,
            address & 0xFF,
            bit & 0xFF,  # Bit position
            0x00, 0x01,  # Read 1 bit
        ])
        
        return command
    
    def _build_write_command(
        self,
        area_code: int,
        address: int,
        value: Any,
        data_type: DataType
    ) -> bytearray:
        """Build FINS memory area write command"""
        self._sid = (self._sid + 1) % 256
        
        value_bytes = self._encode_value(value, data_type)
        word_count = len(value_bytes) // 2
        
        command = bytearray([
            0x46, 0x49, 0x4E, 0x53,
            0x00, 0x00, 0x00, 0x1A + len(value_bytes),
            0x00, 0x00, 0x00, 0x02,
            0x00, 0x00, 0x00, 0x00,
            
            0x80, 0x00, 0x02,
            0x00, self._remote_node, 0x00,
            0x00, self._local_node, 0x00,
            self._sid,
            
            0x01, 0x02,  # Write command
            
            area_code,
            (address >> 8) & 0xFF,
            address & 0xFF,
            0x00,
            (word_count >> 8) & 0xFF,
            word_count & 0xFF,
        ])
        
        command.extend(value_bytes)
        return command
    
    def _build_write_bit_command(
        self,
        area_code: int,
        address: int,
        bit: int,
        value: bool
    ) -> bytearray:
        """Build FINS bit write command"""
        self._sid = (self._sid + 1) % 256
        
        command = bytearray([
            0x46, 0x49, 0x4E, 0x53,
            0x00, 0x00, 0x00, 0x1B,
            0x00, 0x00, 0x00, 0x02,
            0x00, 0x00, 0x00, 0x00,
            
            0x80, 0x00, 0x02,
            0x00, self._remote_node, 0x00,
            0x00, self._local_node, 0x00,
            self._sid,
            
            0x01, 0x02,  # Write command
            
            area_code,
            (address >> 8) & 0xFF,
            address & 0xFF,
            bit & 0xFF,
            0x00, 0x01,  # Write 1 bit
            0x01 if value else 0x00  # Value
        ])
        
        return command
    
    def _encode_value(self, value: Any, data_type: DataType) -> bytearray:
        """Encode value to FINS byte format"""
        if data_type == DataType.INT16:
            return bytearray(struct.pack('>h', int(value)))
        elif data_type == DataType.UINT16:
            return bytearray(struct.pack('>H', int(value)))
        elif data_type == DataType.INT32:
            return bytearray(struct.pack('>i', int(value)))
        elif data_type == DataType.UINT32:
            return bytearray(struct.pack('>I', int(value)))
        elif data_type == DataType.FLOAT32:
            return bytearray(struct.pack('>f', float(value)))
        elif data_type == DataType.BOOL:
            return bytearray([0x00, 0x01 if value else 0x00])
        raise ValueError(f"Unsupported data type: {data_type}")
    
    async def _send_command(self, command: bytearray) -> bytearray:
        """Send FINS command and receive response"""
        self.writer.write(command)
        await self.writer.drain()
        
        header = await asyncio.wait_for(
            self.reader.read(16),
            timeout=3.0
        )
        
        if len(header) < 16:
            raise RuntimeError("Incomplete FINS response")
        
        data_length = struct.unpack('>I', header[4:8])[0]
        remaining = data_length - 8
        data = await asyncio.wait_for(
            self.reader.read(remaining),
            timeout=3.0
        )
        
        return header + data
    
    def _parse_read_response(
        self, 
        response: bytearray, 
        data_type: DataType
    ) -> Any:
        """Parse FINS read response"""
        if len(response) < 30:
            raise RuntimeError("Invalid FINS response")
        
        end_code = struct.unpack('>H', response[28:30])[0]
        if end_code != 0:
            raise RuntimeError(f"FINS error code: {end_code:04X}")
        
        data = response[30:]
        
        if data_type == DataType.INT16:
            return struct.unpack('>h', data[0:2])[0]
        elif data_type == DataType.UINT16:
            return struct.unpack('>H', data[0:2])[0]
        elif data_type == DataType.INT32:
            return struct.unpack('>i', data[0:4])[0]
        elif data_type == DataType.UINT32:
            return struct.unpack('>I', data[0:4])[0]
        elif data_type == DataType.FLOAT32:
            return struct.unpack('>f', data[0:4])[0]
        elif data_type == DataType.BOOL:
            return bool(data[1])
        return struct.unpack('>H', data[0:2])[0]
    
    def _parse_read_bit_response(self, response: bytearray) -> bool:
        """Parse FINS bit read response"""
        if len(response) < 31:
            raise RuntimeError("Invalid FINS response")
        
        end_code = struct.unpack('>H', response[28:30])[0]
        if end_code != 0:
            raise RuntimeError(f"FINS error code: {end_code:04X}")
        
        # Bit value is in byte 30
        return bool(response[30] & 0x01)
    
    def _check_write_response(self, response: bytearray) -> bool:
        """Check if write was successful"""
        if len(response) < 30:
            return False
        end_code = struct.unpack('>H', response[28:30])[0]
        return end_code == 0

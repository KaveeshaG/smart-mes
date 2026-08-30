import asyncio
from typing import Dict, Optional, List
from uuid import UUID
from loguru import logger
from ..protocols.protocol_factory import ProtocolFactory
from ..protocols.base import ProtocolClient, Tag
from ..models.connection import DeviceConnection

class ConnectionManager:
    """Manages active PLC connections"""

    def __init__(self):
        self._connections: Dict[str, DeviceConnection] = {}

    async def connect_device(
        self,
        device_id: str,
        ip_address: str,
        port: int,
        protocol: str,
        **kwargs
    ) -> bool:
        """Establish connection to a device"""

        if device_id in self._connections:
            logger.info(f"Device {device_id} already connected")
            return True

        client = ProtocolFactory.create_client(protocol)
        if not client:
            logger.error(f"Failed to create client for protocol: {protocol}")
            return False

        success = await client.connect(ip_address, port, **kwargs)
        if not success:
            logger.error(f"Failed to connect to {ip_address}:{port}")
            return False

        connection = DeviceConnection(
            device_id=device_id,
            ip_address=ip_address,
            port=port,
            protocol=protocol,
            client=client,
            connect_kwargs=dict(kwargs),
        )

        self._connections[device_id] = connection
        logger.info(f"Connected to device {device_id} at {ip_address}:{port}")
        return True

    async def connect_with_retry(
        self,
        device_id: str,
        ip_address: str,
        port: int,
        protocol: str,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        **kwargs,
    ) -> bool:
        """Connect with exponential backoff retries."""
        delay = retry_delay
        for attempt in range(1, max_retries + 1):
            success = await self.connect_device(device_id, ip_address, port, protocol, **kwargs)
            if success:
                return True
            if attempt < max_retries:
                logger.warning(
                    f"Connection attempt {attempt}/{max_retries} failed for "
                    f"{ip_address}:{port}, retrying in {delay:.0f}s..."
                )
                await asyncio.sleep(delay)
                delay *= 2  # exponential backoff: 5s, 10s, 20s
        logger.error(
            f"All {max_retries} connection attempts failed for {ip_address}:{port}"
        )
        return False

    async def ensure_connected(
        self,
        device_id: str,
        ip_address: str,
        port: int,
        protocol: str,
        **kwargs,
    ) -> bool:
        """Check connection health; reconnect with retry if dead."""
        if self.is_connected(device_id):
            return True

        # Clean up stale entry if present
        if device_id in self._connections:
            logger.info(f"Cleaning up stale connection for device {device_id}")
            try:
                await self._connections[device_id].client.disconnect()
            except Exception:
                pass
            del self._connections[device_id]

        return await self.connect_with_retry(device_id, ip_address, port, protocol, **kwargs)

    async def disconnect_device(self, device_id: str) -> bool:
        """Disconnect from a device"""
        if device_id not in self._connections:
            return False

        connection = self._connections[device_id]
        await connection.client.disconnect()
        del self._connections[device_id]

        logger.info(f"Disconnected from device {device_id}")
        return True

    def get_connection(self, device_id: str) -> Optional[DeviceConnection]:
        """Get active connection"""
        return self._connections.get(device_id)

    def is_connected(self, device_id: str) -> bool:
        """Check if device is connected (cached flag — use probe_device for accuracy)."""
        connection = self._connections.get(device_id)
        return connection is not None and connection.client.is_connected

    async def probe_device(self, device_id: str) -> bool:
        """Actively probe the device. If unreachable, attempts one reconnect using
        the original connection params. Returns True if the device is reachable."""
        connection = self._connections.get(device_id)
        if connection is None:
            return False

        alive = await connection.client.probe()
        if alive:
            return True

        # Probe failed — device may have gone offline temporarily. Try to reconnect.
        logger.info(
            f"[{device_id}] offline — reconnecting to "
            f"{connection.ip_address}:{connection.port} ({connection.protocol})"
        )
        saved_tags = dict(connection.tags or {})
        try:
            await connection.client.disconnect()
        except Exception:
            pass
        self._connections.pop(device_id, None)

        success = await self.connect_device(
            device_id=device_id,
            ip_address=connection.ip_address,
            port=connection.port,
            protocol=connection.protocol,
            **connection.connect_kwargs,
        )

        if success and saved_tags:
            self.register_tags(device_id, list(saved_tags.values()))

        return success

    def register_tags(self, device_id: str, tags: List[Tag]) -> None:
        """Register tags for a device"""
        connection = self._connections.get(device_id)
        if connection:
            connection.tags = {tag.name: tag for tag in tags}
            logger.info(f"Registered {len(tags)} tags for device {device_id}")

    def get_tag(self, device_id: str, tag_name: str) -> Optional[Tag]:
        """Get tag configuration"""
        connection = self._connections.get(device_id)
        if connection and connection.tags:
            return connection.tags.get(tag_name)
        return None

    async def shutdown(self):
        """Disconnect all devices"""
        logger.info("Shutting down all connections...")
        for device_id in list(self._connections.keys()):
            await self.disconnect_device(device_id)

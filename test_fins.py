#!/usr/bin/env python3
import asyncio
import socket

async def test_fins_connection():
    ip = '192.168.250.1'
    port = 9600
    
    print(f"Testing FINS connection to {ip}:{port}...")
    
    try:
        # Connect
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=5.0
        )
        print(f"✓ Connected to {ip}:{port}")
        
        # FINS handshake
        fins_handshake = bytearray([
            0x46, 0x49, 0x4E, 0x53,  # 'FINS'
            0x00, 0x00, 0x00, 0x0C,  # Length
            0x00, 0x00, 0x00, 0x00,  # Command
            0x00, 0x00, 0x00, 0x00,  # Error
            0x00, 0x00, 0x00, 0x00   # Client node
        ])
        
        print(f"Sending FINS handshake...")
        writer.write(fins_handshake)
        await writer.drain()
        
        # Read response
        response = await asyncio.wait_for(
            reader.read(1024),
            timeout=3.0
        )
        
        print(f"✓ Received response ({len(response)} bytes)")
        print(f"Response header: {response[0:4]}")
        
        if response[0:4] == b'FINS':
            print("✓ Valid FINS response!")
            print("✓ Omron CP2E detected successfully")
        else:
            print("✗ Invalid FINS response")
        
        writer.close()
        await writer.wait_closed()
        
    except asyncio.TimeoutError:
        print("✗ Timeout - PLC not responding")
    except ConnectionRefusedError:
        print("✗ Connection refused - Check IP and port")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_fins_connection())

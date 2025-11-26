# Discovery

The framework provides discovery implementations for common network protocols, making it easy to find devices automatically.

## Discovery Classes

| Class | Protocol | Use Case | Package |
|-------|----------|----------|---------|
| **SSDPDiscovery** | UPnP/SSDP | Smart TVs, media renderers | `ssdpy` |
| **SDDPDiscovery** | SDDP | Samsung TVs | `sddp-discovery-protocol` |
| **MDNSDiscovery** | mDNS/Bonjour | Apple devices, Chromecast | `zeroconf` |
| **NetworkScanDiscovery** | TCP/IP scan | Active probing | Built-in |
| **BaseDiscovery** | Custom | Library-specific discovery | Built-in |

## Basic Discovery

All discovery classes return `DiscoveredDevice` objects:

```python
@dataclass
class DiscoveredDevice:
    identifier: str       # Unique ID (MAC, serial, etc.)
    name: str            # Human-readable name
    address: str         # IP address or connection string
    extra_data: dict | None  # Protocol-specific data
```

## SSDP Discovery

For UPnP/SSDP devices (media renderers, smart TVs):

```python
from ucapi_framework.discovery import SSDPDiscovery, DiscoveredDevice

class MyS SDPDiscovery(SSDPDiscovery):
    def __init__(self):
        super().__init__(
            search_target="urn:schemas-upnp-org:device:MediaRenderer:1",
            timeout=5
        )
    
    def parse_ssdp_device(self, raw_device: dict) -> DiscoveredDevice | None:
        """Convert SSDP response to DiscoveredDevice."""
        try:
            # Extract location URL
            location = raw_device.get("location", "")
            if not location:
                return None
            
            # Parse IP from location
            from urllib.parse import urlparse
            parsed = urlparse(location)
            host = parsed.hostname
            
            return DiscoveredDevice(
                identifier=raw_device.get("usn", ""),
                name=raw_device.get("server", "Unknown Device"),
                address=host,
                extra_data={"location": location}
            )
        except Exception:
            return None

# Use in setup flow
discovery = MySSDPDiscovery()
devices = await discovery.discover()
```

## SDDP Discovery

For SDDP devices (Samsung TVs):

```python
from ucapi_framework.discovery import SDDPDiscovery, DiscoveredDevice

class MySDDPDiscovery(SDDPDiscovery):
    def __init__(self):
        super().__init__(
            search_pattern=b"NOTIFY * HTTP/1.1",
            timeout=5
        )
    
    def parse_sddp_response(
        self, data: bytes, addr: tuple[str, int]
    ) -> DiscoveredDevice | None:
        """Parse SDDP response."""
        try:
            message = data.decode('utf-8')
            
            # Parse headers
            lines = message.split('\r\n')
            headers = {}
            for line in lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip().upper()] = value.strip()
            
            return DiscoveredDevice(
                identifier=headers.get('USN', ''),
                name=headers.get('SERVER', 'Samsung TV'),
                address=addr[0],
                extra_data=headers
            )
        except Exception:
            return None
```

## mDNS Discovery

For mDNS/Bonjour devices (Chromecast, Apple TV):

```python
from ucapi_framework.discovery import MDNSDiscovery, DiscoveredDevice
from zeroconf import ServiceInfo

class MyMDNSDiscovery(MDNSDiscovery):
    def __init__(self):
        super().__init__(
            service_type="_googlecast._tcp.local.",
            timeout=5
        )
    
    def parse_mdns_service(
        self, service_info: ServiceInfo
    ) -> DiscoveredDevice | None:
        """Parse mDNS service info."""
        if not service_info.addresses:
            return None
        
        # Get first IPv4 address
        import socket
        address = socket.inet_ntoa(service_info.addresses[0])
        
        # Extract name and properties
        name = service_info.name.replace(f".{self.service_type}", "")
        properties = {
            k.decode(): v.decode() if isinstance(v, bytes) else v
            for k, v in service_info.properties.items()
        }
        
        return DiscoveredDevice(
            identifier=service_info.name,
            name=name,
            address=address,
            extra_data=properties
        )
```

## Network Scan Discovery

For devices that don't support standard discovery:

```python
from ucapi_framework.discovery import NetworkScanDiscovery, DiscoveredDevice

class MyNetworkScanDiscovery(NetworkScanDiscovery):
    def __init__(self):
        super().__init__(
            ip_range="192.168.1.0/24",
            ports=[8080, 9000],
            timeout=10
        )
    
    async def probe_device(
        self, ip: str, port: int
    ) -> DiscoveredDevice | None:
        """Probe IP:port for device."""
        try:
            # Try to connect and identify device
            url = f"http://{ip}:{port}/api/info"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=2) as response:
                    if response.status == 200:
                        data = await response.json()
                        return DiscoveredDevice(
                            identifier=data["id"],
                            name=data["name"],
                            address=ip,
                            extra_data={"port": port}
                        )
        except Exception:
            pass
        
        return None
```

## Custom Discovery

For devices with library-specific discovery:

```python
from ucapi_framework import BaseDiscovery, DiscoveredDevice

class MyCustomDiscovery(BaseDiscovery):
    async def discover(self) -> list[DiscoveredDevice]:
        """Call library discovery and convert results."""
        import my_device_library
        
        # Call library's discovery
        raw_devices = await my_device_library.discover()
        
        # Convert to DiscoveredDevice
        self._discovered_devices.clear()
        for raw in raw_devices:
            device = DiscoveredDevice(
                identifier=raw.serial_number,
                name=raw.friendly_name,
                address=raw.ip_address,
                extra_data={"model": raw.model}
            )
            self._discovered_devices.append(device)
        
        return self._discovered_devices
```

## Using Discovery in Setup Flow

Integrate discovery into your setup flow:

```python
from ucapi_framework import BaseSetupFlow

class MySetupFlow(BaseSetupFlow[MyDeviceConfig]):
    async def discover_devices(self) -> list[DiscoveredDevice]:
        """Run discovery."""
        if self._discovery:
            return await self._discovery.discover()
        return []
    
    async def prepare_input_from_discovery(
        self, device: DiscoveredDevice
    ) -> dict:
        """Convert discovered device to input values."""
        return {
            "identifier": device.identifier,
            "name": device.name,
            "host": device.address,
        }

# Create setup flow with discovery
discovery = MySSDPDiscovery()
setup_flow = MySetupFlow(config_manager, discovery=discovery)
```

## No Discovery

If your integration doesn't support discovery, simply pass `None`:

```python
setup_flow = MySetupFlow(config_manager, discovery=None)
```

The setup flow will skip discovery and go straight to manual entry.

## Best Practices

1. **Timeout appropriately** - Balance thoroughness with user experience
2. **Filter results** - Return only compatible devices
3. **Handle errors gracefully** - Discovery can fail for many reasons
4. **Provide fallback** - Always support manual entry
5. **Cache results** - Don't re-discover on every attempt

```python
class MySSDPDiscovery(SSDPDiscovery):
    def __init__(self):
        super().__init__(
            search_target="urn:my-device:1",
            timeout=5,
            device_filter=self._is_compatible  # Filter function
        )
    
    def _is_compatible(self, raw_device: dict) -> bool:
        """Check if device is compatible."""
        model = raw_device.get("server", "")
        return "MyDevice" in model
```

See the [API Reference](../api/discovery.md) for complete documentation.

# Getting Started

This guide will walk you through creating your first Unfolded Circle Remote integration using the UCAPI Framework.

## Installation

Install the framework using pip or uv:

=== "uv"
    ```bash
    uv add ucapi-framework
    ```

=== "pip"
    ```bash
    pip install ucapi-framework
    ```

## Project Structure

A typical integration has this structure:

```
my-integration/
├── intg-mydevice/
│   ├── __init__.py
│   ├── driver.py          # Driver implementation
│   ├── device.py          # Device interface
│   ├── setup_flow.py      # Setup flow
│   └── config.py          # Configuration dataclass
├── pyproject.toml
└── README.md
```

## Quick Example: REST API Device

Let's build a simple integration for a device with a REST API.

### 1. Define Your Configuration

```python
# config.py
from dataclasses import dataclass

@dataclass
class MyDeviceConfig:
    """Device configuration."""
    identifier: str
    name: str
    host: str
    api_key: str = ""
```

### 2. Implement Your Device

```python
# device.py
from ucapi_framework import StatelessHTTPDevice
import aiohttp

class MyDevice(StatelessHTTPDevice):
    """Device implementation."""
    
    @property
    def identifier(self) -> str:
        return self._device_config.identifier
    
    @property
    def name(self) -> str:
        return self._device_config.name
    
    @property
    def address(self) -> str:
        return self._device_config.host
    
    @property
    def log_id(self) -> str:
        return f"MyDevice[{self.identifier}]"
    
    async def verify_connection(self) -> None:
        """Verify device is reachable."""
        url = f"http://{self.address}/api/status"
        headers = {"Authorization": f"Bearer {self._device_config.api_key}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
    
    async def send_command(self, command: str) -> None:
        """Send a command to the device."""
        url = f"http://{self.address}/api/command"
        headers = {"Authorization": f"Bearer {self._device_config.api_key}"}
        data = {"command": command}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as response:
                response.raise_for_status()
```

### 3. Create Your Driver

```python
# driver.py
from ucapi_framework import BaseIntegrationDriver
from ucapi import EntityTypes, media_player
from .device import MyDevice
from .config import MyDeviceConfig

class MyIntegrationDriver(BaseIntegrationDriver[MyDevice, MyDeviceConfig]):
    """Integration driver."""
```

### 4. Implement Setup Flow

```python
# setup_flow.py
from ucapi_framework import BaseSetupFlow
from ucapi.api_definitions import RequestUserInput
from .config import MyDeviceConfig

class MySetupFlow(BaseSetupFlow[MyDeviceConfig]):
    """Setup flow for manual device entry."""
    
    def get_manual_entry_form(self) -> RequestUserInput:
        """Return the manual entry form."""
        return RequestUserInput(
            title="Add Device",
            settings=[
                {
                    "id": "host",
                    "label": {"en": "Device IP Address", "de": "Geräte-IP-Adresse"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "name",
                    "label": {"en": "Device Name", "de": "Gerätename"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "api_key",
                    "label": {"en": "API Key", "de": "API-Schlüssel"},
                    "field": {"text": {"value": ""}},
                },
            ],
        )
    
    async def query_device(self, input_values: dict) -> MyDeviceConfig:
        """Create device config from user input."""
        return MyDeviceConfig(
            identifier=input_values.get("identifier", input_values["host"].replace(".", "_")),
            name=input_values["name"],
            host=input_values["host"],
            api_key=input_values.get("api_key", ""),
        )
```

### 5. Wire It All Up

```python
# __init__.py
import asyncio
import logging
from ucapi import IntegrationAPI

from .driver import MyIntegrationDriver
from .setup_flow import MySetupFlow
from .config import MyDeviceConfig
from ucapi_framework import BaseConfigManager

_LOG = logging.getLogger(__name__)

async def main():
    """Main entry point."""
    loop = asyncio.get_running_loop()
    
    # Create configuration manager
    config_manager = BaseConfigManager[MyDeviceConfig](
        data_path="./config",
    )
    
    # Create driver
    driver = MyIntegrationDriver()
    driver.config_manager = config_manager
    
    # Wire up config callbacks
    config_manager._add_handler = driver.on_device_added
    config_manager._remove_handler = driver.on_device_removed
    
    # Create setup flow
    setup_flow = MySetupFlow(config_manager, discovery=None)
    
    # Register with API
    api = driver.api
    api.register_setup_handler(setup_flow.create_handler())
    
    # Start integration
    await api.init("mydevice.json", MySetupFlow)
    
    _LOG.info("Integration started")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
```

## Next Steps

Now that you have a basic integration:

1. **Add Discovery** - Implement [device discovery](guide/discovery.md) if your devices support it
2. **Add Entities** - Create entity classes for your device capabilities
3. **Handle Events** - Override event handlers for custom behavior
4. **Add Polling** - Use `PollingDevice` if your device needs state polling
5. **Add WebSocket** - Use `WebSocketDevice` for real-time updates

Check out the [User Guide](guide/setup-flow.md) for detailed information on each component!

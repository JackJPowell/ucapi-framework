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
│   ├── driver.py          # Driver implementation
│   ├── device.py          # Device interface
│   ├── setup_flow.py      # Setup flow
│   └── config.py          # Configuration dataclass
│   └── media_player.py    # Media Player Entity
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

### 3. Create Your Entities

For simple integrations, you often don't need to create your own driver class - you can use `BaseIntegrationDriver` directly in your main function (see step 5). However, you do need to define entity classes:

```python
# entities.py
from ucapi import MediaPlayer, media_player
from ucapi_framework import create_entity_id, EntityTypes, Entity

class MyMediaPlayer(MediaPlayer, Entity):
    """Media player entity for MyDevice."""
    
    def __init__(self, device_config, device):
        """Initialize the media player entity."""
        entity_id = create_entity_id(
            EntityTypes.MEDIA_PLAYER,
            device_config.identifier,
            "player"
        )
        
        super().__init__(
            entity_id,
            device_config.name,
            features=[
                media_player.Features.ON_OFF,
                media_player.Features.VOLUME,
                media_player.Features.VOLUME_UP_DOWN,
            ],
            attributes={
                media_player.Attributes.STATE: media_player.States.UNKNOWN,
                media_player.Attributes.VOLUME: 0,
            },
            cmd_handler=self.handle_command,
        )
        self._device = device
        self._device_config = device_config
    
    async def handle_command(self, entity_id: str, cmd_id: str, params: dict | None) -> None:
        """Handle entity commands."""
        if cmd_id == media_player.Commands.ON:
            await self._device.send_command("power_on")
        elif cmd_id == media_player.Commands.OFF:
            await self._device.send_command("power_off")
        elif cmd_id == media_player.Commands.VOLUME:
            await self._device.send_command(f"volume_{params['volume']}")
        # ... handle other commands
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
# __main__.py
import asyncio
import logging
import ucapi

from ucapi_framework import BaseIntegrationDriver, BaseConfigManager
from .device import MyDevice
from .entities import MyMediaPlayer
from .setup_flow import MySetupFlow
from .config import MyDeviceConfig

_LOG = logging.getLogger(__name__)

async def main():
    """Main entry point."""
    logging.basicConfig(level=logging.INFO)
    
    driver = BaseIntegrationDriver(
        device_class=MyDevice,
        entity_classes=[MyMediaPlayer],
    )
    # Initialize configuration manager with device callbacks
    driver.config_manager = BaseConfigManager(
        get_config_path(driver.api.config_dir_path),
        driver.on_device_added,
        driver.on_device_removed,
        config_class=MyDeviceConfig,
    )

    # Connect to all configured PowerView hubs
    await driver.register_all_configured_devices()

    setup_handler = PowerviewSetupFlow.create_handler(driver, None)
    await driver.api.init("driver.json", setup_handler)

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())

```

**Key Points:**

- **No custom driver class needed**: For simple integrations, use `BaseIntegrationDriver` directly
- **Entity classes list**: Pass your entity classes to `entity_classes` parameter
- **Automatic entity creation**: The driver creates entity instances automatically for each device
- **Config manager callbacks**: Use `add_listener` and `remove_listener` to wire up device lifecycle events

## Next Steps

Now that you have a basic integration:

1. **Add Discovery** - Implement [device discovery](guide/discovery.md) if your devices support it
2. **Add Multiple Entities** - Use [factory functions](guide/advanced-entity-patterns.md#factory-functions-for-dynamic-entities) for creating multiple entities
3. **Customize Entity Behavior** - Use the [Entity ABC](guide/advanced-entity-patterns.md#entity-abc-for-per-entity-customization) for per-entity state mapping and attribute filtering
4. **Handle Events** - Override event handlers for custom behavior (see [Driver Integration](guide/driver.md))
5. **Add Polling** - Use `PollingDevice` if your device needs state polling
6. **Add WebSocket** - Use `WebSocketDevice` for real-time updates
7. **Hub-based Integrations** - Learn about [hub-based discovery patterns](guide/advanced-entity-patterns.md#hub-based-discovery-pattern) for devices that expose multiple entities

Check out the [User Guide](guide/setup-flow.md) for detailed information on each component!

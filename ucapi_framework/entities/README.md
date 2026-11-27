# Entity Subclasses with Built-in State Management

This folder contains entity subclasses that manage their own state internally, eliminating the need for devices to track entity state via `get_device_attributes()`.

## Philosophy

**Before**: Devices tracked state, entities retrieved it via `get_device_attributes()`

**Now**: Entities track their own state using property-based accessors

This provides a more natural separation of concerns where:

- **Devices** handle communication with physical/remote devices
- **Entities** manage their presentation state for the Remote

## Available Entity Classes

### MediaPlayerEntity

Full-featured MediaPlayer with state management for all media player attributes.

**Example**:

```python
from ucapi_framework.entities import MediaPlayerEntity

class MyMediaPlayer(MediaPlayerEntity):
    def __init__(self, device_config, device):
        super().__init__(
            f"media_player.{device_config.id}",
            device_config.name,
            features=[...],
            attributes={...}
        )
        self._device = device
    
    async def handle_command(self, entity_id, cmd_id, params):
        if cmd_id == media_player.Commands.ON:
            await self._device.turn_on()
            self.set_state(media_player.States.ON)  # State managed by entity!
```

## Coming Soon

- `ClimateEntity` - Climate control with temperature, fan mode, etc.
- `CoverEntity` - Covers/blinds with position and tilt
- `LightEntity` - Lights with brightness, color, etc.
- `SwitchEntity` - Simple on/off switches
- Additional entity types...

## Documentation

See [Entity State Management Guide](../../docs/guide/entity-state-management.md) for comprehensive usage examples and patterns.

# MediaPlayerEntity Usage Guide

The `MediaPlayerEntity` class provides built-in state management for MediaPlayer entities, eliminating the need for devices to track entity state via `get_device_attributes()`.

## Key Concept: Entity-Managed State

Instead of storing state on the device and retrieving it with `get_device_attributes()`, entities now manage their own state internally using the existing `self.attributes` dictionary that all ucapi entities have:

- **Property getters** for read-only access (e.g., `entity.state`, `entity.volume`)
- **Setter methods** for updates (e.g., `entity.set_state()`, `entity.set_volume()`)
- **Bulk update method** for efficient multi-attribute updates (`entity.set_attributes()`)
- **State storage** in `self.attributes` dict - the same dict used by ucapi entities

This matches your existing pattern:

```python
self.attributes[Attributes.SOURCE] = source
self.update(self.attributes)
```


## Benefits

1. **Natural separation of concerns**: Entities manage their own state
2. **No device boilerplate**: No need to implement `get_device_attributes()`
3. **Type-safe**: IDE autocomplete and type checking for all attributes
4. **Explicit control**: Choose when to push updates to Remote with `update` parameter
5. **Still overridable**: Subclasses can override any method or property
6. **Consistent with ucapi**: Uses the existing `self.attributes` dict pattern

## Basic Usage

```python
from ucapi import media_player
from ucapi_framework.entities import MediaPlayerEntity

class MyMediaPlayer(MediaPlayerEntity):
    def __init__(self, device_config, device):
        entity_id = f"media_player.{device_config.id}"
        super().__init__(
            entity_id,
            device_config.name,
            features=[
                media_player.Features.ON_OFF,
                media_player.Features.VOLUME,
                media_player.Features.MEDIA_TITLE,
            ],
            attributes={
                media_player.Attributes.STATE: media_player.States.UNKNOWN
            }
        )
        self._device = device

    async def handle_command(self, entity_id, cmd_id, params):
        """Handle commands from the Remote."""
        if cmd_id == media_player.Commands.ON:
            await self._device.turn_on()
            # Update state - automatically pushes to Remote
            self.set_state(media_player.States.ON)
            
        elif cmd_id == media_player.Commands.OFF:
            await self._device.turn_off()
            self.set_state(media_player.States.OFF)
            
        elif cmd_id == media_player.Commands.VOLUME:
            await self._device.set_volume(params['volume'])
            self.set_volume(params['volume'])

        return ucapi.StatusCodes.OK
```

## Reading State

All attributes have read-only property getters that access `self.attributes`:

```python
# Check current state
if entity.state == media_player.States.PLAYING:
    print(f"Now playing: {entity.media_title}")

# Access any attribute
print(f"Volume: {entity.volume}")
print(f"Muted: {entity.muted}")
print(f"Source: {entity.source}")
print(f"Available sources: {entity.source_list}")

# Direct access to attributes dict also works
state = entity.attributes.get(media_player.Attributes.STATE)
```

## Updating Single Attributes

Each attribute has a setter method that updates `self.attributes` with optional `update` parameter:

```python
# Update state and push to Remote (default)
entity.set_state(media_player.States.PLAYING)

# Update volume without pushing to Remote
entity.set_volume(75, update=False)

# Later, push all changes at once
entity.update(entity.attributes)

# Or use the traditional pattern
entity.attributes[media_player.Attributes.VOLUME] = 75
entity.update(entity.attributes)
```

## Updating Multiple Attributes Efficiently

Use `set_attributes()` to update multiple attributes with a single Remote update:

```python
# Efficient: Single update call for all changes
entity.set_attributes(
    state=media_player.States.PLAYING,
    volume=50,
    muted=False,
    media_title="Song Title",
    media_artist="Artist Name",
    media_album="Album Name",
    source="Spotify",
)

# Or without pushing to Remote yet
entity.set_attributes(
    state=media_player.States.PLAYING,
    volume=50,
    media_title="Song Title",
    update=False  # Don't push yet
)
# Later...
entity.update({...})  # Push when ready
```

## Device Update Pattern

When your device receives state updates, update the entity directly:

```python
class MyDevice(BaseDeviceInterface):
    def __init__(self, device_config, driver=None):
        super().__init__(device_config, driver=driver)
        self.entity = None  # Will be set after entity creation
        
    async def on_state_update(self, state_data):
        """Handle state updates from the device."""
        if self.entity:
            # Update entity state directly
            self.entity.set_attributes(
                state=self.map_state(state_data['status']),
                volume=state_data.get('volume'),
                media_title=state_data.get('track_title'),
                media_artist=state_data.get('track_artist'),
            )
```

## Controlling When Updates Are Sent

### Pattern 1: Immediate Updates (Default)

```python
# Each setter immediately pushes to Remote
self.set_state(media_player.States.PLAYING)  # Update sent
self.set_volume(75)                           # Update sent
self.set_media_title("Song")                  # Update sent
# Result: 3 separate update calls to Remote
```

### Pattern 2: Batched Updates (Recommended for multiple changes)

```python
# Set attributes without updates
entity.set_state(media_player.States.PLAYING, update=False)
entity.set_volume(75, update=False)
entity.set_media_title("Song", update=False)

# Single update call
entity.update(entity.attributes)
# Result: 1 update call to Remote
```

### Pattern 3: Bulk Update (Most Efficient)

```python
# Single call, single update
self.set_attributes(
    state=media_player.States.PLAYING,
    volume=75,
    media_title="Song",
)
# Result: 1 update call to Remote
```

## Advanced: Overriding Behavior

You can override any getter or setter for custom behavior:

```python
class CustomMediaPlayer(MediaPlayerEntity):
    def set_state(self, value, *, update=True):
        """Add custom logic before setting state."""
        # Custom validation
        if value == media_player.States.PLAYING and not self._device.is_ready:
            value = media_player.States.BUFFERING
        
        # Call parent implementation
        super().set_state(value, update=update)
    
    @property
    def volume(self):
        """Override getter to return scaled volume."""
        # Device uses 0-255, Remote uses 0-100
        if self._volume is not None:
            return int(self._volume * 100 / 255)
        return None
    
    def set_volume(self, value, *, update=True):
        """Override setter to scale volume."""
        # Convert 0-100 to 0-255 for device
        if value is not None:
            scaled_value = int(value * 255 / 100)
            self._volume = scaled_value
        else:
            self._volume = None
            
        if update:
            # Use original value for Remote (0-100)
            self.update({media_player.Attributes.VOLUME: value})
```

## Migration from get_device_attributes()

### Before (Device-Managed State)

```python
# Old pattern: Device tracks state
class MyDevice(BaseDeviceInterface):
    def __init__(self, device_config):
        super().__init__(device_config)
        self.state = media_player.States.UNKNOWN
        self.volume = 0
        self.media_title = None
    
    def get_device_attributes(self, entity_id):
        """Return entity attributes."""
        return {
            media_player.Attributes.STATE: self.state,
            media_player.Attributes.VOLUME: self.volume,
            media_player.Attributes.MEDIA_TITLE: self.media_title,
        }

class MyMediaPlayer(media_player.MediaPlayer):
    def __init__(self, device_config, device):
        self._device = device
        super().__init__(...)
    
    async def handle_command(self, entity_id, cmd_id, params):
        if cmd_id == media_player.Commands.VOLUME:
            await self._device.set_volume(params['volume'])
            # Update device state
            self._device.volume = params['volume']
            # Trigger refresh
            await self._driver.refresh_entity_state(entity_id)
```

### After (Entity-Managed State)

```python
# New pattern: Entity tracks state
class MyDevice(BaseDeviceInterface):
    def __init__(self, device_config):
        super().__init__(device_config)
        # No state tracking needed!

class MyMediaPlayer(MediaPlayerEntity):
    def __init__(self, device_config, device):
        self._device = device
        super().__init__(...)
    
    async def handle_command(self, entity_id, cmd_id, params):
        if cmd_id == media_player.Commands.VOLUME:
            await self._device.set_volume(params['volume'])
            # Update entity state directly - no device involvement!
            self.set_volume(params['volume'])
```

## Available Attributes

All MediaPlayer attributes are supported:

- `state` - Playback state (States enum)
- `volume` - Volume level (0-100)
- `muted` - Mute status (bool)
- `media_duration` - Media duration in seconds
- `media_position` - Current position in seconds
- `media_position_updated_at` - Position update timestamp
- `media_type` - Media type (e.g., 'music', 'video')
- `media_image_url` - Artwork URL
- `media_title` - Track/show title
- `media_artist` - Artist name
- `media_album` - Album name
- `repeat` - Repeat mode (RepeatMode enum)
- `shuffle` - Shuffle status (bool)
- `source` - Current input source
- `source_list` - Available sources (list)
- `sound_mode` - Current sound mode
- `sound_mode_list` - Available sound modes (list)

## Next Steps

This pattern will be extended to other entity types:

- `ClimateEntity`
- `CoverEntity`
- `LightEntity`
- `SwitchEntity`
- etc.

Each will follow the same pattern: property getters for reading, setter methods for writing, and optional `update` parameter for control.

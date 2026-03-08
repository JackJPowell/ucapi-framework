# Driver Integration

The driver is the central coordinator of your integration, managing device lifecycle, entity registration, and Remote events.

## Core Responsibilities

The `BaseIntegrationDriver` handles:

- ✅ Remote Two event handling (connect, disconnect, standby)
- ✅ Entity subscription and registration management
- ✅ Device lifecycle (add, remove, connect, disconnect)
- ✅ State propagation from devices to entities
- ✅ Event routing and coordination

## How State Flows

With the coordinator pattern, state flows in one direction:

```
Device              Entity                  Remote Two
──────              ──────                  ──────────
push_update()  →    sync_state()  →         update_attributes()
                    self.update({...})
```

1. The device detects a state change and calls `push_update()`
2. Every entity subscribed to that device has `sync_state()` called automatically
3. The entity reads raw values from the device and calls `self.update({...fresh dict...})`
4. The framework diffs against the last-pushed state and sends only changed attributes to the Remote

The driver wires the device and entities together at subscription time. You don't need to manage this manually.

## Minimal Setup

Most integrations work with just the constructor:

```python
from ucapi_framework import BaseIntegrationDriver

class MyDriver(BaseIntegrationDriver[MyDevice, MyDeviceConfig]):
    def __init__(self):
        super().__init__(
            device_class=MyDevice,
            entity_classes=[MyMediaPlayer, MyRemote],
        )
```

The framework automatically:

- Creates entity instances when a device is subscribed to
- Wires device lifecycle events (connected, disconnected, error)
- Calls `sync_state()` on reconnect for coordinator entities
- Propagates legacy `on_device_update` attribute dicts for non-coordinator entities

## Hub-Based Dynamic Entities

For integrations where the set of entities is discovered at runtime (hubs, bridges, multi-zone devices), use factory lambdas in `entity_classes` and set `require_connection_before_registry=True`:

```python
class MyHubDriver(BaseIntegrationDriver[SmartHub, SmartHubConfig]):
    def __init__(self):
        super().__init__(
            device_class=SmartHub,
            entity_classes=[
                lambda cfg, dev: [HubLight(cfg, light, dev) for light in dev.lights],
                lambda cfg, dev: [HubCover(cfg, cover, dev) for cover in dev.covers],
                lambda cfg, dev: [HubScene(cfg, scene, dev) for scene in dev.scenes],
            ],
            require_connection_before_registry=True,
        )
```

When `require_connection_before_registry=True`:

1. The device connects first
2. The device's `connect()` populates its entity lists (e.g., `dev.lights`, `dev.covers`)
3. The framework calls the factory lambdas to create entity instances
4. Entities are registered with the Remote

Each lambda receives `(device_config, device)` and returns a single entity or a list. The return type is `Entity | list[Entity]`.

## Overridable Methods

The driver provides sensible defaults for all common patterns. Override only what you need.

### `create_entities()` — Override for Advanced Cases

**Default behavior:** Calls each item in `entity_classes`. If the item is a class, calls `entity_class(device_config, device)`. If it's a callable (lambda/factory), calls it with `(device_config, device)`.

**Override when:** You need logic that can't fit in a lambda — for example, async entity initialization or conditional creation based on external state.

```python
def create_entities(self, device_config: MyConfig, device: MyDevice) -> list[Entity]:
    entities = []
    if device.supports_playback:
        entities.append(MyMediaPlayer(device_config, device))
    if device.supports_remote:
        entities.append(MyRemote(device_config, device))
    return entities
```

### `map_device_state()` — Override for Custom State Enums

**Default behavior:** Maps common state strings to `media_player.States`:

- `"ON"`, `"MENU"`, `"IDLE"`, `"ACTIVE"`, `"READY"` → `States.ON`
- `"OFF"`, `"POWER_OFF"`, `"STOPPED"` → `States.OFF`
- `"PLAYING"`, `"PLAY"`, `"SEEKING"` → `States.PLAYING`
- `"PAUSED"`, `"PAUSE"` → `States.PAUSED`
- `"STANDBY"`, `"SLEEP"` → `States.STANDBY`
- `"BUFFERING"`, `"LOADING"` → `States.BUFFERING`
- Everything else → `States.UNKNOWN`

!!! note
    If your entity uses `sync_state()` (coordinator pattern), it calls `self.map_entity_states()` on the entity — not this driver method. `map_device_state()` is used by the legacy `on_device_update` path.

**Override when** you have device-specific state enums:

```python
def map_device_state(self, device_state) -> media_player.States:
    if isinstance(device_state, MyDeviceState):
        match device_state:
            case MyDeviceState.POWERED_ON:
                return media_player.States.ON
            case MyDeviceState.POWERED_OFF:
                return media_player.States.OFF
            case _:
                return media_player.States.UNKNOWN
    return super().map_device_state(device_state)
```

### `device_from_entity_id()` — Override for Custom Entity ID Formats

**Default behavior:** Parses standard format `"entity_type.device_id"` or `"entity_type.device_id.sub_device_id"`. Returns the second segment.

```python
device_id = driver.device_from_entity_id("media_player.receiver_123")
# Returns "receiver_123"

device_id = driver.device_from_entity_id("light.hub_1.bedroom")
# Returns "hub_1"
```

**Raises `ValueError`** if the entity ID doesn't contain the expected separator.

**Override when** your entity IDs use a non-standard format:

```python
def device_from_entity_id(self, entity_id: str) -> str | None:
    # For PSN-style: entity_id IS the device_id
    return entity_id
```

### `entity_type_from_entity_id()` and `sub_device_from_entity_id()`

Same parsing conventions as `device_from_entity_id()`. Override together if you use a custom entity ID format.

```python
entity_type = driver.entity_type_from_entity_id("light.hub_1.bedroom")
# Returns "light"

sub_device = driver.sub_device_from_entity_id("light.hub_1.bedroom")
# Returns "bedroom"

sub_device = driver.sub_device_from_entity_id("media_player.receiver_123")
# Returns None (no sub-device in 2-part format)
```

All three raise `ValueError` if the separator is missing. They return `None` only for empty input or a missing sub-device (which is valid).

### `on_device_update()` — Legacy Attribute Routing

**Default behavior:** Routes attribute dicts from `DeviceEvents.UPDATE` to the correct entity by `entity_id`. Supports all entity types.

This method is used by the **legacy pattern** where devices emit `(entity_id, attributes_dict)`:

```python
# Legacy device emitting attribute dicts (still supported)
self.events.emit(DeviceEvents.UPDATE, entity_id, {
    "state": "PLAYING",
    "volume": 50,
})
```

With the coordinator pattern, `on_device_update` is not called for entities that override `sync_state()` — those entities handle their own updates via `push_update()`.

**Override when** you need custom attribute transformation:

```python
async def on_device_update(
    self, entity_id: str | None = None, update: dict | None = None
) -> None:
    if update and "power_state" in update:
        update["state"] = "ON" if update["power_state"] else "OFF"
    await super().on_device_update(entity_id, update)
```

## Event Handlers

### Device Events

Override these to add custom logic around device lifecycle events:

```python
async def on_device_connected(self, device_id: str) -> None:
    await super().on_device_connected(device_id)
    _LOG.info("Device %s is now online", device_id)

async def on_device_disconnected(self, device_id: str) -> None:
    await super().on_device_disconnected(device_id)
    # Mark entities unavailable
    for entity in self._get_framework_entities_for_device(device_id):
        entity.set_unavailable()

async def on_device_connection_error(self, device_id: str, message: str) -> None:
    await super().on_device_connection_error(device_id, message)
    _LOG.error("Device %s error: %s", device_id, message)
```

### Remote Events

Override these to customize Remote Two event handling:

```python
async def on_r2_connect_cmd(self) -> None:
    await super().on_r2_connect_cmd()

async def on_r2_disconnect_cmd(self) -> None:
    await super().on_r2_disconnect_cmd()

async def on_r2_enter_standby(self) -> None:
    await super().on_r2_enter_standby()

async def on_r2_exit_standby(self) -> None:
    await super().on_r2_exit_standby()
```

## Entity ID Helpers

Use `create_entity_id()` to build consistent entity IDs:

```python
from ucapi_framework import create_entity_id
from ucapi import EntityTypes

# Simple: "media_player.receiver_123"
entity_id = create_entity_id(EntityTypes.MEDIA_PLAYER, "receiver_123")

# With sub-device: "light.hub_1.bedroom"
entity_id = create_entity_id(EntityTypes.LIGHT, "hub_1", "bedroom")
```

And parse them back using the driver methods:

```python
driver.entity_type_from_entity_id("light.hub_1.bedroom")  # "light"
driver.device_from_entity_id("light.hub_1.bedroom")        # "hub_1"
driver.sub_device_from_entity_id("light.hub_1.bedroom")    # "bedroom"
```

## Complete Example

A full coordinator-pattern driver for a hub device:

```python
from ucapi_framework import BaseIntegrationDriver, create_entity_id
from ucapi import EntityTypes
import logging

_LOG = logging.getLogger(__name__)

class SmartHubDriver(BaseIntegrationDriver[SmartHub, SmartHubConfig]):
    def __init__(self):
        super().__init__(
            device_class=SmartHub,
            entity_classes=[
                # Factory lambdas — called after device connects and populates its lists
                lambda cfg, dev: [HubLight(cfg, light, dev) for light in dev.lights],
                lambda cfg, dev: [HubCover(cfg, cover, dev) for cover in dev.covers],
            ],
            require_connection_before_registry=True,
        )

    async def on_device_connected(self, device_id: str) -> None:
        await super().on_device_connected(device_id)
        _LOG.info("Hub %s connected with %d devices", device_id,
                  len(self._device_instances.get(device_id).lights or []))

    async def on_device_disconnected(self, device_id: str) -> None:
        await super().on_device_disconnected(device_id)
        for entity in self._get_framework_entities_for_device(device_id):
            entity.set_unavailable()
```

And the corresponding entity (one per hub device):

```python
from ucapi import light
from ucapi_framework import Entity, create_entity_id, EntityTypes

class HubLight(light.Light, Entity):
    def __init__(self, hub_config, light_info, hub):
        self._hub = hub
        self._light_id = light_info.id
        entity_id = create_entity_id(EntityTypes.LIGHT, hub_config.identifier, light_info.id)

        super().__init__(
            entity_id,
            light_info.name,
            features=[light.Features.ON_OFF, light.Features.DIM],
            attributes={
                light.Attributes.STATE: light.States.UNKNOWN,
                light.Attributes.BRIGHTNESS: 0,
            },
            cmd_handler=self.handle_command,
        )

        # Subscribe to hub — sync_state() fires on every hub.push_update()
        self.subscribe_to_device(hub)

    async def sync_state(self) -> None:
        """Read this light's state from the hub and push to Remote."""
        light_state = self._hub.get_light(self._light_id)
        if light_state is None:
            return
        self.update({
            light.Attributes.STATE: light.States.ON if light_state.on else light.States.OFF,
            light.Attributes.BRIGHTNESS: light_state.brightness,
        })

    async def handle_command(self, entity, cmd_id, params):
        match cmd_id:
            case light.Commands.ON:
                await self._hub.set_light(self._light_id, on=True)
            case light.Commands.OFF:
                await self._hub.set_light(self._light_id, on=False)
            case light.Commands.BRIGHTNESS:
                await self._hub.set_light(self._light_id, brightness=params["brightness"])
```

See the [API Reference](../api/driver.md) for complete documentation of all methods and event handlers.

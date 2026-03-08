# Migration Guide: Converting to ucapi-framework

This guide helps you migrate an existing Unfolded Circle integration to use the ucapi-framework. We'll cover both migrating from raw ucapi code and upgrading between framework versions.

## Table of Contents

- [Why Migrate?](#why-migrate)
- [Migration Overview](#migration-overview)
- [Step-by-Step Migration](#step-by-step-migration)
  - [1. Configuration Management](#1-configuration-management)
  - [2. Device Implementation](#2-device-implementation)
  - [3. Entity Implementation](#3-entity-implementation)
  - [4. Setup Flow](#4-setup-flow)
  - [5. Driver Integration](#5-driver-integration)
- [Upgrading to 1.9+: The Coordinator Pattern](#upgrading-to-19-the-coordinator-pattern)
- [Common Patterns](#common-patterns)
- [Testing Your Migration](#testing-your-migration)

## Why Migrate?

**Before ucapi-framework:**
- ~1500 lines of boilerplate per integration
- Manual configuration management with dict manipulation
- Global state management with module-level variables
- Repetitive event handler wiring
- Copy-paste setup flow code
- Manual device lifecycle management
- Entity and device state tightly coupled

**After ucapi-framework:**
- ~400 lines of integration-specific code
- Type-safe configuration with dataclasses
- Clean OOP design with proper encapsulation
- Automatic event handler wiring
- Reusable setup flow base class
- Automatic device lifecycle management
- Clear separation of concerns between device and entity

**Code Reduction:** ~70% less code to write and maintain!

## Migration Overview

The migration follows these steps:

1. **Configuration** — Replace dict-based config with typed dataclass + `BaseConfigManager`
2. **Device** — Inherit from a device base class; device knows nothing about entities
3. **Entities** — Inherit from framework `Entity`; entity subscribes to the device and owns its own state
4. **Setup Flow** — Inherit from `BaseSetupFlow`, implement required methods
5. **Driver** — Inherit from `BaseIntegrationDriver`, remove global state


## Step-by-Step Migration

### 1. Configuration Management

#### Before: Dict-Based Configuration (~80 lines)

```python
# config.py - Old approach
import json, os
from typing import TypedDict

class MyDevice(TypedDict):
    identifier: str
    name: str
    host: str

devices: dict[str, MyDevice] = {}
_config_path = os.path.join(os.path.dirname(__file__), "config.json")

def _load() -> bool:
    global devices
    if not os.path.exists(_config_path):
        return True
    with open(_config_path) as f:
        data = json.load(f)
        devices = {k: MyDevice(**v) for k, v in data.items()}
    return True

def add_device(device: MyDevice) -> bool:
    devices[device["identifier"]] = device
    return _store()

def remove_device(identifier: str) -> bool:
    if identifier in devices:
        devices.pop(identifier)
        return _store()
    return False
```

**Problems:** ~80 lines of boilerplate, global mutable state, manual JSON serialization.

#### After: BaseConfigManager with Dataclass (~5 lines)

```python
# config.py - New approach
from dataclasses import dataclass
from ucapi_framework import BaseConfigManager

@dataclass
class MyDeviceConfig:
    identifier: str
    name: str
    host: str

class MyConfigManager(BaseConfigManager[MyDeviceConfig]):
    pass
```

**Usage Comparison:**

```python
# Old:
import config
device = config.get_device(device_id)
config.add_device(new_device)

# New:
config = MyConfigManager("config.json", MyDeviceConfig)
device = config.get(device_id)
config.add_or_update(new_device)
```

---

### 2. Device Implementation

The framework enforces a key principle: **the device knows nothing about entities**. It stores raw hardware state (power, volume, input source — whatever your device has) and signals that something changed. Entities subscribe to those signals and translate them into ucapi attributes.

#### Before: Device Emitting Entity-Specific Attributes

```python
# device.py - Old approach
class MyDevice:
    async def _process_update(self, data):
        self.state = data["power"]
        # Emitting entity ID + ucapi attribute dict — tightly coupled to entity type!
        self.events.emit(
            "UPDATE",
            self.identifier,
            {
                media_player.Attributes.STATE: data["power"],
                media_player.Attributes.VOLUME: data["volume"],
            }
        )
```

**Problem:** The device has to know about ucapi entity attribute keys, which means changing entity types (e.g., adding a second entity) requires modifying the device. The device and entity are tightly coupled.

#### After: Device Stores Raw State and Calls `push_update()`

```python
# device.py - New approach
from ucapi_framework import WebSocketDevice, DeviceEvents
import json

class MyDevice(WebSocketDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(device_config, config_manager=config_manager)
        # Raw device state — plain Python values, no ucapi attributes
        self.power: str = "OFF"
        self.volume: int = 0
        self.source: str = ""

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

    async def handle_message(self, message: str) -> None:
        """Process incoming message, update state, then notify subscribers."""
        data = json.loads(message)
        self.power = data.get("power", self.power)
        self.volume = data.get("volume", self.volume)
        self.source = data.get("source", self.source)
        # Signal "something changed" — no entity IDs, no attribute keys
        self.push_update()

    async def establish_connection(self) -> None:
        """Called by the framework after the connection is established."""
        # Fetch current state so entities have something to sync on connect
        state = await self._fetch_state()
        self.power = state["power"]
        self.volume = state["volume"]
        self.push_update()  # Push initial state to all subscribed entities
```

`push_update()` emits `DeviceEvents.UPDATE` with no arguments. Every entity that subscribed via `subscribe_to_device(device)` will have its `sync_state()` called automatically.

---

### 3. Entity Implementation

Entities are responsible for translating device state into ucapi attributes. This is the **coordinator pattern** — the entity _coordinates_ state between the device and the Remote.

#### Before: Entity as a Passive Attribute Store

```python
# media_player.py - Old approach
# Entity state was updated externally by the driver routing attribute dicts.
# Entity had no awareness of the device — driver handled everything.
class MyMediaPlayer(MediaPlayer):
    def __init__(self, device_config, device):
        super().__init__(
            identifier=device_config.identifier,
            ...
            attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN},
        )
        self._device = device
        # No sync_state(), no subscribe_to_device() — driver pushed state in
```

#### After: Entity Subscribes and Owns Its State

```python
# media_player.py - New approach
from ucapi import media_player
from ucapi_framework import Entity, create_entity_id, EntityTypes

class MyMediaPlayer(media_player.MediaPlayer, Entity):
    """Media player that subscribes to its device and manages its own state."""

    def __init__(self, device_config, device):
        self._device = device
        entity_id = create_entity_id(EntityTypes.MEDIA_PLAYER, device_config.identifier)

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

        # Wire entity to device: sync_state() is called on every push_update()
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """
        Translate device state into ucapi attributes and push to Remote.

        Called automatically when the device calls push_update().
        Always pass a FRESH dict or dataclass — never mutate self.attributes.
        Change-filtering compares the incoming dict against the last-pushed state,
        so mutating self.attributes first defeats filtering entirely.
        """
        self.update({
            media_player.Attributes.STATE: self.map_entity_states(self._device.power),
            media_player.Attributes.VOLUME: self._device.volume,
            media_player.Attributes.SOURCE: self._device.source,
        })

    async def handle_command(self, entity, cmd_id, params):
        """Handle commands from the Remote."""
        match cmd_id:
            case media_player.Commands.ON:
                await self._device.power_on()
            case media_player.Commands.OFF:
                await self._device.power_off()
            case media_player.Commands.VOLUME:
                await self._device.set_volume(params["volume"])
```

**The three key methods at a glance:**

| Method | Called in | What it does |
|---|---|---|
| `subscribe_to_device(device)` | Entity `__init__` | Wires `sync_state()` to the device's `UPDATE` events |
| `push_update()` | Device, after state changes | Emits `DeviceEvents.UPDATE` — triggers all subscribed entities |
| `sync_state()` | Entity (override required) | Reads device state, calls `self.update({...fresh dict...})` |

---

### 4. Setup Flow

#### Before: Manual State Machine (~200 lines)

```python
class MySetupFlow:
    def __init__(self):
        self._setup_step = "START"

    async def handle_setup_request(self, msg):
        if msg.reconfigure:
            return await self._show_configuration_mode()
        config.clear()
        return await self._show_manual_entry()

    async def handle_user_data_response(self, msg):
        if self._setup_step == "CONFIGURATION_MODE":
            return await self._handle_configuration_action(msg)
        elif self._setup_step == "MANUAL_ENTRY":
            return await self._handle_manual_entry_response(msg)
        # ... hundreds more lines
```

#### After: Inherit BaseSetupFlow (~30 lines)

```python
from ucapi_framework import BaseSetupFlow
from ucapi import IntegrationSetupError, RequestUserInput, SetupError

class MySetupFlow(BaseSetupFlow[MyDeviceConfig]):

    def get_manual_entry_form(self) -> RequestUserInput:
        """Define the manual entry form fields."""
        return RequestUserInput(
            {"en": "Add Device"},
            [
                {"id": "name", "label": {"en": "Name"}, "field": {"text": {"value": ""}}},
                {"id": "host", "label": {"en": "IP Address"}, "field": {"text": {"value": ""}}},
            ],
        )

    async def query_device(self, input_values):
        """Validate and create device config from user input."""
        host = input_values.get("host", "").strip()
        if not host:
            return SetupError(error_type=IntegrationSetupError.CONNECTION_REFUSED)

        return MyDeviceConfig(
            identifier=host,
            name=input_values.get("name", host),
            host=host,
        )
```

**You get for free:** Configuration mode (add/update/remove/reset), backup/restore, duplicate detection, pre-discovery screens, multi-screen flows, migration support.

---

### 5. Driver Integration

#### Before: Global State and Manual Wiring (~300 lines)

```python
# driver.py - Old approach
_configured_devices: dict[str, MyDevice] = {}

@api.listens_to(ucapi.Events.CONNECT)
async def on_r2_connect_cmd():
    for device in _configured_devices.values():
        await device.connect()

@api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
async def on_subscribe_entities(entity_ids):
    for entity_id in entity_ids:
        device_config = config.get_device(entity_id)
        device = MyDevice(device_config)
        device.events.on("UPDATE", _on_device_update)
        _configured_devices[entity_id] = device
        # ... manual entity creation, registration, state sync, etc.
```

#### After: Inherit BaseIntegrationDriver (~5 lines)

```python
from ucapi_framework import BaseIntegrationDriver

class MyDriver(BaseIntegrationDriver[MyDevice, MyDeviceConfig]):
    def __init__(self):
        super().__init__(
            device_class=MyDevice,
            entity_classes=[MyMediaPlayer],
        )
```

For hub devices where entities are discovered at runtime, use factory lambdas:

```python
class MyHubDriver(BaseIntegrationDriver[MyHub, MyHubConfig]):
    def __init__(self):
        super().__init__(
            device_class=MyHub,
            entity_classes=[
                lambda cfg, dev: [MyLight(cfg, info, dev) for info in dev.lights],
                lambda cfg, dev: [MyCover(cfg, info, dev) for info in dev.covers],
                lambda cfg, dev: [MyScene(cfg, info, dev) for info in dev.scenes],
            ],
            require_connection_before_registry=True,
        )
```

---

## Upgrading to 1.9+: The Coordinator Pattern

Version 1.9 introduced the **coordinator pattern** — a fundamental shift in how device state flows to entities. Here are the three key changes.

### Change 1: Entities Own Their State via `sync_state()`

**Old pattern (legacy, still works via `on_device_update`):**

```python
# Device emits entity ID + attribute dict
device.events.emit(DeviceEvents.UPDATE, entity_id, {
    media_player.Attributes.STATE: media_player.States.PLAYING,
    media_player.Attributes.VOLUME: 50,
})
# Driver routes this to the right entity automatically
```

**New pattern (coordinator):**

```python
# Device stores raw state and signals "something changed"
class MyDevice(WebSocketDevice):
    async def handle_message(self, msg):
        self.state = msg["state"]
        self.volume = msg["volume"]
        self.push_update()  # No args, no entity awareness

# Entity subscribes and translates
class MyMediaPlayer(media_player.MediaPlayer, Entity):
    def __init__(self, cfg, device):
        ...
        self.subscribe_to_device(device)  # Wire to device

    async def sync_state(self) -> None:
        self.update({
            media_player.Attributes.STATE: self.map_entity_states(self._device.state),
            media_player.Attributes.VOLUME: self._device.volume,
        })
```

### Change 2: Always Pass a Fresh Dict to `update()`

The framework filters unchanged attributes before pushing to the Remote. For this to work, `update()` must receive a **new dict** each time — not `self.attributes`.

**Wrong — breaks change filtering:**

```python
async def sync_state(self):
    # BAD: the framework stores attributes by reference.
    # self.attributes IS configured_entities.attributes — comparing an object to itself
    # always produces an empty diff, so nothing ever gets sent to the Remote.
    self.attributes[media_player.Attributes.STATE] = media_player.States.PLAYING
    self.update(self.attributes)
```

**Correct — fresh dict or dataclass:**

```python
async def sync_state(self):
    # GOOD: new dict each call — framework diffs against last-pushed state correctly
    self.update({
        media_player.Attributes.STATE: media_player.States.PLAYING,
        media_player.Attributes.VOLUME: self._device.volume,
    })

    # Or with a typed dataclass (None values are automatically filtered):
    # from ucapi_framework.helpers import MediaPlayerAttributes
    # self.update(MediaPlayerAttributes(
    #     state=media_player.States.PLAYING,
    #     volume=self._device.volume,
    # ))
```

### Change 3: Call `push_update()` After Connecting

`on_device_connected` no longer calls `sync_state()` for coordinator-pattern entities. Instead, call `push_update()` at the end of your device's connection setup so entities receive their initial state.

```python
class MyDevice(WebSocketDevice):
    async def establish_connection(self) -> None:
        """Called by the framework after the connection is established."""
        # Fetch current state from device
        state = await self._fetch_initial_state()
        self.power = state["power"]
        self.volume = state["volume"]
        # Push to all subscribed entities
        self.push_update()
```

---

## Common Patterns

### Hub with Dynamic Entities

Use `require_connection_before_registry=True` when the hub must be connected before you know what entities exist. The framework will connect the device first, then register entities:

```python
class SmartHubDriver(BaseIntegrationDriver[SmartHub, SmartHubConfig]):
    def __init__(self):
        super().__init__(
            device_class=SmartHub,
            entity_classes=[
                lambda cfg, dev: [HubLight(cfg, light, dev) for light in dev.lights],
                lambda cfg, dev: [HubCover(cfg, cover, dev) for cover in dev.covers],
            ],
            require_connection_before_registry=True,
        )
```

### Marking Entities Unavailable on Disconnect

Override `on_device_disconnected` in your driver, or subscribe to `DeviceEvents.ERROR` in the entity:

```python
class MyDriver(BaseIntegrationDriver[MyDevice, MyDeviceConfig]):
    async def on_device_disconnected(self, device_id: str) -> None:
        await super().on_device_disconnected(device_id)
        for entity in self._get_framework_entities_for_device(device_id):
            entity.set_unavailable()
```

### Pre-Discovery Credentials

Use `get_pre_discovery_screen()` to collect API keys or server addresses before discovery runs:

```python
class MySetupFlow(BaseSetupFlow[MyDeviceConfig]):
    async def get_pre_discovery_screen(self):
        return RequestUserInput(
            {"en": "API Configuration"},
            [{"id": "api_key", "label": {"en": "API Key"}, "field": {"text": {"value": ""}}}],
        )

    async def discover_devices(self):
        api_key = self._pre_discovery_data.get("api_key")
        return await MyDiscovery.run(api_key=api_key)
```

### Multi-Screen Setup

Return `RequestUserInput` from `query_device()` after storing the partial config:

```python
async def query_device(self, input_values):
    device = await MyDevice.fetch_info(input_values["host"])
    if not device:
        return SetupError(error_type=IntegrationSetupError.NOT_FOUND)

    # Store partial config, show next screen
    self._pending_device_config = MyDeviceConfig(
        identifier=device.id,
        name=device.name,
        host=input_values["host"],
    )
    return RequestUserInput(
        {"en": "Select Zone"},
        [{"id": "zone", "label": {"en": "Zone"}, "field": {"dropdown": {"items": device.zones}}}],
    )

async def handle_additional_configuration_response(self, msg):
    self._pending_device_config.zone = msg.input_values["zone"]
    return None  # Save and complete
```

---

## Testing Your Migration

### Testing `sync_state()`

```python
import pytest
from unittest.mock import MagicMock, AsyncMock
from myintegration.config import MyDeviceConfig
from myintegration.device import MyDevice
from myintegration.media_player import MyMediaPlayer

@pytest.fixture
def device_config():
    return MyDeviceConfig(identifier="test123", name="Test Device", host="192.168.1.100")

async def test_sync_state_maps_device_state(device_config):
    """Entity reads from device and pushes fresh dict to Remote."""
    device = MyDevice(device_config)
    device.power = "PLAYING"
    device.volume = 42

    # Mock the API so update() doesn't fail
    entity = MyMediaPlayer(device_config, device)
    entity._api = MagicMock()
    entity._api.configured_entities.contains.return_value = True
    entity._api.configured_entities.get.return_value = MagicMock(attributes={})
    entity._api.configured_entities.update_attributes = MagicMock()

    await entity.sync_state()

    entity._api.configured_entities.update_attributes.assert_called_once()
    args = entity._api.configured_entities.update_attributes.call_args[0]
    assert media_player.Attributes.STATE in args[1]
    assert args[1][media_player.Attributes.STATE] == media_player.States.PLAYING
```

### Migration Checklist

- [ ] Configuration converted to dataclass + `BaseConfigManager`
- [ ] Device inherits from appropriate base class
- [ ] Device stores raw state (not ucapi attribute keys)
- [ ] Device calls `push_update()` after state changes (no args)
- [ ] Device calls `push_update()` at end of `establish_connection()` / `connect()`
- [ ] Entity inherits from both the ucapi entity class and framework `Entity`
- [ ] Entity calls `subscribe_to_device(device)` in `__init__`
- [ ] Entity overrides `sync_state()` and passes a **fresh dict or dataclass** to `update()`
- [ ] Entity does NOT call `self.attributes[...] = ...; self.update(self.attributes)`
- [ ] Setup flow inherits from `BaseSetupFlow` and implements `get_manual_entry_form()` + `query_device()`
- [ ] Driver inherits from `BaseIntegrationDriver`
- [ ] All global state removed
- [ ] Factory lambdas used for hub-based dynamic entity creation (not `create_entities()` override)
- [ ] Tests verify `sync_state()` reads from device and calls `update()` with a fresh dict

## Need Help?

- Review inline docstrings in `ucapi_framework` modules — they include detailed examples
- See the [Device Patterns](guide/device-patterns.md) guide for connection class details
- See the [Driver Guide](guide/driver.md) for driver configuration
- Open an issue on GitHub for questions

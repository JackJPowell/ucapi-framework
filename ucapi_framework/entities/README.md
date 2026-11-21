# Entity Subclasses with Built-in State Management

This folder contains entity subclasses that manage their own state internally, eliminating the need for devices to track entity state via `get_device_attributes()`.

## Philosophy

**Before**: Devices tracked state, entities retrieved it via `get_device_attributes()`

**Now**: Entities track their own state using property-based accessors

This provides a more natural separation of concerns where:

- **Devices** handle communication with physical/remote devices
- **Entities** manage their presentation state for the Remote

## Available Entity Classes

### WebViewEntity

Requires the ucapi release containing webview support and Remote firmware 2.14.0
or newer. Import protocol definitions from `ucapi.webview`:

```python
from ucapi import webview
from ucapi_framework import WebViewEntity, WebViewAttributes

dashboard = WebViewEntity(
    "webview.home.energy",
    "Energy dashboard",
    options={
        webview.Options.URL: "https://dashboard.example.com/energy",
        webview.Options.USER_AGENT: webview.UserAgent.DESKTOP,
        webview.Options.ZOOM: 70,
        webview.Options.RELOAD_INTERVAL: 60,
    },
)
# After the framework registers the entity and assigns its API:
dashboard.set_state(webview.States.UNAVAILABLE, update=True)
dashboard.update(WebViewAttributes(STATE=webview.States.ON))
```

Use a factory in `entity_classes` to construct a web view for each device:

```python
entity_classes=[
    lambda cfg, dev: WebViewEntity(
        f"webview.{cfg.identifier}.dashboard",
        "Dashboard",
        options={webview.Options.URL: f"https://{cfg.address}/dashboard"},
    ),
]
```

State is optional and omitted by default, allowing Core to determine availability.
`WebViewAttributes()` sends no state. Setters default to local updates
(`update=False`). Driver disconnection and connection errors don't automatically
mark web views unavailable, because the Remote loads their pages directly. Report
`UNAVAILABLE` explicitly if your integration knows the web server is unreachable.
Only `ON`, `UNKNOWN` and `UNAVAILABLE` are valid web view states.

Options are passed through to ucapi and validated by Core. They include the required
absolute HTTP(S) `url`, authentication, TLS exceptions, cookies, user agent, zoom,
background color, navigation controls, reload interval and physical button mappings.
Put credentials in `auth` or `cookies`, rather than the URL. These options belong
to the entity definition; `update()` and `WebViewAttributes` only update state.
To change options, publish the complete updated entity definition using the
Integration API's `entity_available` event.

Web views have no features or device classes and need no command handler.
`open`, `reload`, `clear_cache` and `clear_data` execute on the Remote UI. The ucapi
capability check only includes web views in `available_entities` when the Remote
explicitly reports support, including when capability discovery fails. Keep this
check when customizing entity advertisement, because older firmware rejects the
entire response if it contains a web view.

### NumberEntity

Requires ucapi 0.7.1. Import the protocol definitions from `ucapi.number` and
the framework class from `ucapi_framework`:

```python
from ucapi import number
from ucapi_framework import NumberEntity, NumberAttributes

bass = NumberEntity(
    "number.amp.bass",
    "Bass",
    features=[],
    attributes={number.Attributes.VALUE: 0},
    device_class=number.DeviceClasses.AUDIO_LEVEL,
    options={number.Options.MIN: -10, number.Options.MAX: 10,
             number.Options.STEP: 0.5},
)
# After the framework registers the entity and assigns its API:
bass.set_value(2.5, update=True)
bass.update(NumberAttributes(STATE=number.States.ON, VALUE=3))
bass.set_attributes(value=None, update=True)  # Explicitly report an unknown value.
```

`NumberAttributes` follows the existing dataclass convention: `None` fields are
omitted. To clear a value, use `set_value(None, update=True)`,
`set_attributes(value=None, update=True)`, or `update({"value": None})`.
Setters default to local updates (`update=False`).

Range, step, precision, unit, display mode and readability are static constructor
options. Implement `set_value`, `increment`, and `decrement` in your integration's
command handler; the framework does not change the device value automatically.

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

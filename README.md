[![Tests](https://github.com/jackjpowell/ucapi-framework/actions/workflows/test.yml/badge.svg)](https://github.com/jackjpowell/ucapi-framework/actions/workflows/test.yml)
[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee&nbsp;☕-FFDD00?logo=buy-me-a-coffee&logoColor=white&labelColor=grey)](https://buymeacoffee.com/jackpowell)

# UCAPI Framework

A framework for building Unfolded Circle Remote integrations that handles the repetitive parts of integration development so you can focus on what's important.

## What This Solves

Building an Unfolded Circle Remote integration typically involves:
- Writing 200+ lines of setup flow routing logic
- Manually managing configuration updates and persistence
- Implementing device lifecycle management (connect/disconnect/reconnect)
- Wiring up Remote event handlers
- Managing global state for devices and entities
- Handling entity registration and state synchronization

This framework provides tested implementations of all these patterns, reducing a simple integration from ~1500 lines of boilerplate to ~400 lines of device-specific code. It even adds features, like back and restore, for free.

## Core Features

### Standard Setup Flow with Extension Points

The setup flow handles the common pattern: configuration mode → discovery/manual entry → device selection. But every integration has unique needs, so there are extension points at key moments:

- **Pre-discovery screens** - Collect API credentials or server addresses before running discovery
- **Post-selection screens** - Gather device-specific settings after the user picks a device
- **Custom discovery fields** - Add extra fields to the discovery screen (zones, profiles, etc.)

The framework handles all the routing, state management, duplicate checking, and configuration persistence. You just implement the screens you need.

**Reduction**: Setup flow code goes from ~200 lines to ~50 lines.

### Device Connection Patterns

Five base classes cover the common connection patterns:

**StatelessHTTPDevice** - For REST APIs. You implement `verify_connection()` to test reachability. No connection management needed.

**PollingDevice** - For devices that need periodic state checks. You set a poll interval and implement `poll_device()`. Automatic reconnection on errors.

**WebSocketDevice** - For WebSocket connections. You implement `create_websocket()` and `handle_message()`. Framework manages the connection lifecycle, reconnection, and cleanup.

**ExternalClientDevice** - For third-party libraries that manage their own connections (Z-Wave JS, MQTT clients, etc.). You implement `create_client()`, `connect_client()`, and `check_client_connected()`. Framework provides watchdog monitoring and auto-reconnection.

**PersistentConnectionDevice** - For TCP, serial, or custom protocols. You implement `establish_connection()`, `maintain_connection()`, and `close_connection()`. Framework handles the receive loop and error recovery.

All connection management, error handling, reconnection logic, and cleanup happens automatically.

**Reduction**: Device implementation goes from ~100 lines of connection boilerplate to ~30 lines of business logic.

### Configuration Management

Configuration is just a dataclass. The framework handles JSON serialization, CRUD operations, and persistence:

```python
@dataclass
class MyDeviceConfig:
    device_id: str
    name: str
    host: str

config = BaseDeviceManager("config.json", MyDeviceConfig)
```

You get full CRUD operations: `add_or_update()`, `get()`, `remove()`, `all()`, `clear()`. Plus automatic backup/restore functionality for free. The framework handles all the file I/O, error handling, and atomic writes.

Full type safety means IDE autocomplete works everywhere. No more dict manipulation or manual JSON handling.

**Reduction**: Configuration management goes from ~80 lines to ~15 lines.

### Driver Integration

The driver coordinates everything - device lifecycle, entity management, and Remote events. **Most integrations work with just the defaults** - no overrides needed!

The framework provides sensible defaults for:

- **`create_entities()`** - Creates one entity per entity type automatically
- **`map_device_state()`** - Maps common state strings (ON, OFF, PLAYING, etc.)
- **`device_from_entity_id()`** - Parses standard entity ID format
- **`get_entity_ids_for_device()`** - Queries and filters entities by device

**Override only what you need**: Custom state enums? Override `map_device_state()`. Conditional entity creation? Override `create_entities()`. Custom entity ID format? Override `device_from_entity_id()` too.

Everything else is automatic. The framework handles Remote connection events (connect, disconnect, standby), entity subscriptions, device lifecycle management, and state synchronization.

Device events (like state changes) automatically propagate to entity state updates. The framework maintains the connection between your devices and your remote.

**Reduction**: Driver code goes from ~300 lines to ~50 lines (or less!).

### Discovery (Optional)

If your devices support network discovery, the framework provides implementations for common protocols:

**SSDPDiscovery** - For UPnP/SSDP devices. Define your service type and implement `parse_ssdp_device()` to convert SSDP responses into `DiscoveredDevice` objects.

**SDDPDiscovery** - For SDDP devices (Samsung TVs). Same pattern: define search pattern and implement `parse_sddp_device()`.

**MDNSDiscovery** - For mDNS/Bonjour devices. Define service type and implement `parse_mdns_service()` to convert service info into device configs.

**NetworkScanDiscovery** - For devices that need active probing. Scans local network ranges and calls your `probe_device()` method for each IP.

For integrations where your device library has its own discovery mechanism, simply inherit from `BaseDiscovery` and implement the `discover()` method to call your library's discovery and convert results to `DiscoveredDevice` format.

All discovery classes handle the protocol details, timeouts, and error handling. Dependencies are lazy-loaded, so you only install what you use (ssdpy, sddp-discovery-protocol, zeroconf, etc.). If your integration doesn't support discovery, just return an empty list from `discover_devices()` and focus on manual entry.

### Event System

The driver base class automatically wires up Remote events (connect, disconnect, standby, subscribe/unsubscribe) with sensible defaults. You can override any of them, but the defaults handle most cases.

Device events (state changes, errors) automatically propagate to entity state updates. You just emit events from your device and the framework keeps the Remote in sync.

## How It Works

You inherit from base classes and override only what you need:

**Driver** - Usually works with defaults! Override only if you need custom state mapping or conditional entity creation.

**Device** - Implement your connection pattern (verify, poll, handle messages, etc.).

**Setup Flow** - Define how to discover devices and create configurations from user input.

**Config** - Just a dataclass.

The framework provides sensible defaults for common patterns. You override only what's specific to your integration. Everything else is handled automatically: lifecycle management, event routing, state synchronization, configuration persistence, error handling, and reconnection logic.

## Architecture

The framework is layered:

```
Your Integration (device logic, API calls, protocol handling)
         ↓
BaseIntegrationDriver (lifecycle, events, entity management)
         ↓
Device Interfaces (connection patterns, error handling)
         ↓
Setup Flow + Config Manager (user interaction, persistence)
```

Each layer handles its responsibility and provides clean extension points. You only touch the top layer.

## Generic Type System

The framework uses bounded generics (`DeviceT`, `ConfigT`) so your IDE knows exactly what types you're working with:

```python
class MyDriver(BaseIntegrationDriver[MyDevice, MyDeviceConfig]):
    def get_device(self, device_id: str) -> MyDevice | None:
        device = super().get_device(device_id)
        # IDE knows device is MyDevice, full autocomplete available
```

No casting, no generic types, just full type safety throughout.

## Discovery Support

Optional discovery implementations for common protocols:

- **SSDPDiscovery** - For UPnP/SSDP devices
- **SDDPDiscovery** - For SDDP devices (Samsung TVs)
- **MDNSDiscovery** - For mDNS/Bonjour devices
- **NetworkScanDiscovery** - For scanning IP ranges
- **BaseDiscovery** - For custom discovery (inherit and implement `discover()`)

Lazy imports mean you only need the dependencies if you use them.

## Real-World Example

See the PSN integration in this repository:

- `intg-psn/driver.py` - 90 lines (was 300)
- `intg-psn/psn.py` - 140 lines (was 240)
- `intg-psn/setup_flow.py` - 50 lines (was 250)
- `intg-psn/config.py` - 15 lines (was 95)

Total: ~295 lines of integration code vs ~885 lines previously. And the new code is type-safe, testable, and maintainable.

## Migration

If you have an existing integration, see [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for step-by-step instructions with before/after examples.

## Requirements

- Python 3.11+
- ucapi
- pyee

Optional (only if you use them):
- aiohttp (for HTTP devices)
- websockets (for WebSocket devices)
- ssdpy (for SSDP discovery)
- zeroconf (for mDNS discovery)

## Documentation

Full documentation is available at [https://jackjpowell.github.io/ucapi-framework/](https://jackjpowell.github.io/ucapi-framework/)

To build documentation locally:

```bash
# Install documentation dependencies
uv sync --group docs

# Serve documentation locally
mkdocs serve
```

Visit <http://127.0.0.1:8000> to view the docs.

## License

Mozilla Public License Version 2.0

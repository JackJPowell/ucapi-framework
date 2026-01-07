"""
Base integration driver for Unfolded Circle Remote integrations.

Provides common event handlers and device lifecycle management.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any, Generic, TypeVar

import ucapi
import ucapi.api as uc
from ucapi import (
    Entity,
    EntityTypes,
    button,
    climate,
    cover,
    light,
    media_player,
    remote,
    sensor,
    switch,
    voice_assistant,
)

from ucapi_framework.config import BaseConfigManager
from .device import BaseDeviceInterface, DeviceEvents

# Type variables for generic device and entity types
DeviceT = TypeVar("DeviceT", bound=BaseDeviceInterface)  # Device interface type
ConfigT = TypeVar("ConfigT")  # Device configuration type (any object with attributes)

_LOG = logging.getLogger(__name__)

# Common attribute names for device configuration extraction
_DEVICE_ID_ATTRIBUTES = ("identifier", "id", "device_id")
_DEVICE_NAME_ATTRIBUTES = ("name", "friendly_name", "device_name")
_DEVICE_ADDRESS_ATTRIBUTES = (
    "address",
    "host_address",
    "ip_address",
    "device_address",
    "host",
)


def _get_first_valid_attr(obj: Any, *attrs: str) -> str | None:
    """
    Get the first valid attribute value from an object.

    Helper function to extract configuration values by trying multiple
    common attribute names in order.

    :param obj: Object to inspect
    :param attrs: Attribute names to try in order
    :return: String value of first found attribute, or None
    """
    for attr in attrs:
        if hasattr(obj, attr):
            value = getattr(obj, attr)
            if value:
                return str(value)
    return None


def create_entity_id(
    entity_type: EntityTypes | str, device_id: str, sub_device_id: str | None = None
) -> str:
    """
    Create a unique entity identifier for the given device and entity type.

    Entity IDs follow the format:
    - Simple: "{entity_type}.{device_id}"
    - With sub-device: "{entity_type}.{device_id}.{sub_device_id}"

    Use the optional sub_device_id parameter for devices that expose multiple entities
    of the same type, such as a hub with multiple lights or zones.

    Examples:
        >>> create_entity_id(EntityTypes.MEDIA_PLAYER, "device_123")
        'media_player.device_123'
        >>> create_entity_id(EntityTypes.LIGHT, "hub_1", "light_bedroom")
        'light.hub_1.light_bedroom'
        >>> create_entity_id("media_player", "receiver_abc", "zone_2")
        'media_player.receiver_abc.zone_2'

    :param entity_type: The entity type (EntityTypes enum or string)
    :param device_id: The device identifier (hub or parent device)
    :param sub_device_id: Optional sub-device identifier (e.g., light ID, zone ID)
    :return: Entity identifier in the format "entity_type.device_id" or "entity_type.device_id.sub_device_id"
    """
    type_str = (
        entity_type.value if isinstance(entity_type, EntityTypes) else entity_type
    )

    if sub_device_id:
        return f"{type_str}.{device_id}.{sub_device_id}"
    return f"{type_str}.{device_id}"


class BaseIntegrationDriver(Generic[DeviceT, ConfigT]):
    """
    Base class for Remote Two integration drivers.

    Handles common patterns like:
    - Event listeners (connect, disconnect, standby, subscribe/unsubscribe)
    - Device lifecycle management
    - Entity registration and updates
    - State propagation from devices to entities

    Type Parameters:
        DeviceT: The device interface class (e.g., YamahaAVR)
        ConfigT: The device configuration class (e.g., YamahaDevice)
    """

    def __init__(
        self,
        device_class: type[DeviceT],
        entity_classes: list[type[Entity]] | type[Entity],
        require_connection_before_registry: bool = False,
        loop: asyncio.AbstractEventLoop | None = None,
        driver_id: str | None = None,
    ):
        """
        Initialize the integration driver.

        :param device_class: The device interface class to instantiate
        :param entity_classes: Entity class or list of entity classes (e.g., MediaPlayer, Light)
                               Single entity class will be converted to a list
        :param require_connection_before_registry: If True, ensure device connection
                                                   before subscribing to entities and re-register
                                                   available entities after connection. Useful for hub-based
                                                   integrations that populate entities dynamically on connection.
        :param loop: The asyncio event loop (optional, defaults to asyncio.get_running_loop())
        :param driver_id: Optional driver/integration ID. Used for entity ID migration to automatically
                         fetch the current version from the Remote, eliminating manual entry during upgrades.
        """
        self._loop = loop if loop is not None else asyncio.get_event_loop()
        self.api = uc.IntegrationAPI(self._loop)
        self._device_class = device_class
        self._require_connection_before_registry = require_connection_before_registry
        self.driver_id = driver_id

        # Allow passing a single entity class or a list
        if isinstance(entity_classes, type):
            self._entity_classes = [entity_classes]
        else:
            self._entity_classes = entity_classes

        self._configured_devices: dict[str, DeviceT] = {}
        self._config_manager = None  # Set via config_manager property
        self.entity_id_separator = "."  # Default separator for entity IDs
        self._setup_event_handlers()

    @property
    def config_manager(self) -> BaseConfigManager | None:
        """
        Get the configuration manager.

        :return: The configuration manager instance
        """
        return self._config_manager

    @config_manager.setter
    def config_manager(self, value: BaseConfigManager | None) -> None:
        """
        Set the configuration manager.

        :param value: The configuration manager instance (BaseConfigManager)
        """
        self._config_manager = value

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """
        Get the asyncio event loop.

        :return: The asyncio event loop instance
        """
        return self._loop

    async def register_all_configured_devices(self, connect: bool = False) -> None:
        """
        Register all devices from the configuration manager.

        This method iterates over all devices in the config manager and registers
        them with the driver. When require_connection_before_registry is True,
        it uses async_add_configured_device() which waits for connection before
        registering entities.

        Call this method during driver initialization after setting the config_manager.

        Example:
            driver = MyDriver(device_class=MyDevice, entity_classes=[EntityTypes.MEDIA_PLAYER])
            driver.config_manager = my_config_manager
        :param connect: Whether to connect devices after adding them (default: False).
                         Only applies when require_connection_before_registry=False.
                         When require_connection_before_registry=True, devices are always connected.

        :param connect: Whether to connect devices after adding them (default: False)
        """
        if self._config_manager is None:
            _LOG.warning("Cannot register devices: config_manager is not set")
            return

        for device_config in self._config_manager.all():
            if self._require_connection_before_registry:
                await self.async_add_configured_device(device_config)
            else:
                self.add_configured_device(device_config, connect=connect)

    def _setup_event_handlers(self) -> None:
        """Register all event handlers with the API."""
        self.api.listens_to(ucapi.Events.CONNECT)(self.on_r2_connect_cmd)
        self.api.listens_to(ucapi.Events.DISCONNECT)(self.on_r2_disconnect_cmd)
        self.api.listens_to(ucapi.Events.ENTER_STANDBY)(self.on_r2_enter_standby)
        self.api.listens_to(ucapi.Events.EXIT_STANDBY)(self.on_r2_exit_standby)
        self.api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)(self.on_subscribe_entities)
        self.api.listens_to(ucapi.Events.UNSUBSCRIBE_ENTITIES)(
            self.on_unsubscribe_entities
        )

    # ========================================================================
    # Remote Two Event Handlers (can be overridden)
    # ========================================================================

    async def on_r2_connect_cmd(self) -> None:
        """
        Handle Remote Two connect command.

        Default implementation: connects all configured devices and sets integration state.
        Override to add custom logic before/after device connections.

        Example:
            async def on_r2_connect_cmd(self) -> None:
                await super().on_r2_connect_cmd()
                # Custom logic after connect
        """
        _LOG.debug("Client connect command: connecting device(s)")
        await self.api.set_device_state(ucapi.DeviceStates.CONNECTED)
        for device in self._configured_devices.values():
            # start background task
            self._loop.create_task(device.connect())

    async def on_r2_disconnect_cmd(self) -> None:
        """
        Handle Remote Two disconnect command.

        Default implementation: disconnects all configured devices.
        Override to add custom disconnect logic.
        """
        _LOG.debug("Client disconnect command: disconnecting device(s)")
        for device in self._configured_devices.values():
            # start background task
            self._loop.create_task(device.disconnect())

    async def on_r2_enter_standby(self) -> None:
        """
        Handle Remote Two entering standby mode.

        Default implementation: disconnects all devices to save resources.
        Override to customize standby behavior.
        """
        _LOG.debug("Enter standby event: disconnecting device(s)")
        for device in self._configured_devices.values():
            await device.disconnect()

    async def on_r2_exit_standby(self) -> None:
        """
        Handle Remote Two exiting standby mode.

        Default implementation: reconnects all configured devices.
        Override to customize wake behavior.
        """
        _LOG.debug("Exit standby event: connecting device(s)")
        for device in self._configured_devices.values():
            # start background task
            self._loop.create_task(device.connect())

    async def on_subscribe_entities(self, entity_ids: list[str]) -> None:
        """
        Handle entity subscription events.

        Default implementation handles two scenarios:

        **Standard integrations** (require_connection_before_registry=False):
        - Adds devices for subscribed entities (with background connect)
        - Calls refresh_entity_state() for each entity

        **Hub-based integrations** (require_connection_before_registry=True):
        - If device not configured: adds device, connects, then calls async_register_available_entities()
        - If device configured but not connected: connects with retries, then calls async_register_available_entities()
        - Calls refresh_entity_state() for each entity

        Override refresh_entity_state() for custom state refresh logic.
        Override async_register_available_entities() for hub-based entity population.

        :param entity_ids: List of entity identifiers being subscribed
        """
        _LOG.debug("Subscribe entities event: %s", entity_ids)

        if not entity_ids:
            return

        device_id = self.device_from_entity_id(entity_ids[0])
        if device_id is None:
            _LOG.error("Could not extract device_id from entity_id: %s", entity_ids[0])
            return

        # Path 1: Hub-based integrations that need connection before entity registration
        if self._require_connection_before_registry:
            # Check if device is already configured
            if device_id not in self._configured_devices:
                # Device not configured - add it and connect
                device_config = self.get_device_config(device_id)
                if device_config:
                    # Add device without registering entities yet (connect=False, register=False)
                    self._add_device_instance(device_config)
                else:
                    _LOG.error(
                        "Failed to subscribe entity: no device config found for %s",
                        device_id,
                    )
                    return

            # Get the device and ensure it's connected
            device = self._configured_devices.get(device_id)
            if device and not device.is_connected:
                # Connect with retries
                if not await self._ensure_device_connected(device_id):
                    _LOG.error(
                        "Failed to connect to device %s for entity subscription",
                        device_id,
                    )
                    return

                # After successful connection, register entities from the hub (async)
                await self.async_register_available_entities(
                    self.get_device_config(device_id), device
                )

        # Path 2: Standard integrations - add devices for entities that aren't configured yet
        else:
            for entity_id in entity_ids:
                eid_device_id = self.device_from_entity_id(entity_id)
                if eid_device_id is None:
                    continue

                # Check if device is already configured
                if eid_device_id in self._configured_devices:
                    continue

                # Device not configured yet, add it with background connect
                device_config = self.get_device_config(eid_device_id)
                if device_config:
                    self.add_configured_device(device_config, connect=True)
                else:
                    _LOG.error(
                        "Failed to subscribe entity %s: no device config found",
                        entity_id,
                    )

        # Refresh each entity's state
        for entity_id in entity_ids:
            await self.refresh_entity_state(entity_id)

    async def on_unsubscribe_entities(self, entity_ids: list[str]) -> None:
        """
        Handle entity unsubscription events.

        Default implementation: disconnects and cleans up devices when all their
        entities are unsubscribed. Override to customize cleanup behavior.

        :param entity_ids: List of entity identifiers being unsubscribed
        """
        _LOG.debug("Unsubscribe entities event: %s", entity_ids)

        # Track which devices need to be checked
        devices_to_check = set()

        for entity_id in entity_ids:
            device_id = self.device_from_entity_id(entity_id)
            if device_id is not None and device_id in self._configured_devices:
                devices_to_check.add(device_id)

        # For each device, check if any of its entities are still configured
        for device_id in devices_to_check:
            device_entities = self.get_entity_ids_for_device(device_id)
            any_entity_configured = any(
                self.api.configured_entities.get(entity_id) is not None
                for entity_id in device_entities
            )

            if not any_entity_configured:
                # No entities are configured anymore, disconnect and cleanup
                device = self._configured_devices.get(device_id)
                if device:
                    _LOG.info(
                        "No entities configured for device '%s', disconnecting and cleaning up",
                        device_id,
                    )
                    await device.disconnect()
                    device.events.remove_all_listeners()
                    self._configured_devices.pop(device_id, None)

    async def _ensure_device_connected(self, device_id: str) -> bool:
        """
        Ensure device is connected, with retry logic.

        This helper method attempts to connect to the device with up to 3 retries.
        The device must already exist in _configured_devices.

        :param device_id: Device identifier
        :return: True if device is connected, False otherwise
        """
        device = self._configured_devices.get(device_id)

        if not device:
            _LOG.error("Device %s not found in configured devices", device_id)
            return False

        # Check if already connected
        if device.is_connected:
            _LOG.debug("Device %s already connected", device_id)
            return True

        # Attempt connection with retries
        for attempt in range(1, 4):
            _LOG.debug(
                "Device %s not connected, attempting to connect (%d/3)",
                device_id,
                attempt,
            )
            if await device.connect():
                _LOG.info("Device %s connected successfully", device_id)
                return True

            await device.disconnect()
            await asyncio.sleep(0.5)

        _LOG.error("Failed to connect to device %s after 3 attempts", device_id)
        return False

    async def refresh_entity_state(self, entity_id: str) -> None:
        """
        Refresh state for a single entity.

        Default implementation: Updates STATE attribute based on device connection state.
        For media_player entities, uses map_device_state(). For other entity types,
        sets STATE to AVAILABLE if connected, UNAVAILABLE otherwise.

        **Device Attribute Hook**: Override `get_device_attributes(entity_id)` in your device
        class to provide additional attributes beyond STATE. The method should return a
        dict[Attributes, Any] with entity-specific attributes (e.g., SOURCE_LIST, SOUND_MODE_LIST,
        VOLUME, BRIGHTNESS, etc.). These will be merged with STATE before updating.

        The default implementation in BaseDeviceInterface returns an empty dict.

        Example device implementation:
            def get_device_attributes(self, entity_id: str) -> dict:
                return {
                    media_player.Attributes.SOURCE_LIST: list(self.source_list),
                    media_player.Attributes.SOUND_MODE_LIST: list(self.sound_mode_list),
                    media_player.Attributes.VOLUME: self.volume,
                }

        **Override this** to implement integration-specific state refresh logic,
        especially for hub-based integrations that need to query device data.

        Example for hub-based integration:
            async def refresh_entity_state(self, entity_id: str) -> None:
                device_id = self.device_from_entity_id(entity_id)
                device = self._configured_devices.get(device_id)
                if not device:
                    return

                entity_type = self.entity_type_from_entity_id(entity_id)
                sub_device_id = self.sub_device_from_entity_id(entity_id)

                match entity_type:
                    case EntityTypes.LIGHT.value:
                        light = next(
                            (l for l in device.lights if l.device_id == sub_device_id),
                            None
                        )
                        if light:
                            self.api.configured_entities.update_attributes(
                                entity_id,
                                {
                                    "state": "ON" if light.current_state > 0 else "OFF",
                                    "brightness": int(light.current_state * 255 / 100),
                                }
                            )
                    case EntityTypes.BUTTON.value:
                        scene = next(
                            (s for s in device.scenes if s.scene_id == sub_entity_id),
                            None
                        )
                        if scene:
                            self.api.configured_entities.update_attributes(
                                entity_id, {"state": "AVAILABLE"}
                            )

        :param entity_id: Entity identifier
        """
        device_id = self.device_from_entity_id(entity_id)
        if device_id is None:
            return

        device = self._configured_devices.get(device_id)
        if device is None:
            _LOG.warning("Device %s not found for entity %s", device_id, entity_id)
            return

        configured_entity = self.api.configured_entities.get(entity_id)
        if configured_entity is None:
            _LOG.debug("Entity %s is not configured, ignoring", entity_id)
            return

        # Default state refresh based on device connection and entity type
        if not device.is_connected or device.state is None:
            state = media_player.States.UNAVAILABLE
        else:
            # For media_player entities, use the device state mapping
            if configured_entity.entity_type == EntityTypes.MEDIA_PLAYER:
                state = self.map_device_state(device.state)
            else:
                # For other entity types, just mark as available
                state = button.States.AVAILABLE

        # Allow device to provide additional attributes beyond STATE
        # Device can implement get_device_attributes(entity_id) -> dict[Attributes, Any]
        attributes = {}
        if hasattr(device, "get_device_attributes"):
            device_attrs = device.get_device_attributes(entity_id)
            if device_attrs:
                attributes.update(device_attrs)

        # Update the appropriate STATE attribute based on entity type
        match configured_entity.entity_type:
            case EntityTypes.BUTTON:
                # Merge STATE with device-provided attributes (STATE takes precedence if device provided it)
                if button.Attributes.STATE not in attributes:
                    attributes[button.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)
            case EntityTypes.CLIMATE:
                if climate.Attributes.STATE not in attributes:
                    attributes[climate.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)
            case EntityTypes.COVER:
                if cover.Attributes.STATE not in attributes:
                    attributes[cover.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)
            case EntityTypes.LIGHT:
                if light.Attributes.STATE not in attributes:
                    attributes[light.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)
            case EntityTypes.MEDIA_PLAYER:
                if media_player.Attributes.STATE not in attributes:
                    attributes[media_player.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)
            case EntityTypes.REMOTE:
                if remote.Attributes.STATE not in attributes:
                    attributes[remote.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)
            case EntityTypes.SENSOR:
                if sensor.Attributes.STATE not in attributes:
                    attributes[sensor.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)
            case EntityTypes.SWITCH:
                if switch.Attributes.STATE not in attributes:
                    attributes[switch.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)
            case EntityTypes.IR_EMITTER:  # Remote shares the same states as IR Emitter
                if remote.Attributes.STATE not in attributes:
                    attributes[remote.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)
            case EntityTypes.VOICE_ASSISTANT:
                if voice_assistant.Attributes.STATE not in attributes:
                    attributes[voice_assistant.Attributes.STATE] = state
                self.api.configured_entities.update_attributes(entity_id, attributes)

    # ========================================================================
    # Device Lifecycle Management
    # ========================================================================

    def add_configured_device(
        self, device_config: ConfigT, connect: bool = True
    ) -> None:
        """
        Add and configure a device (non-blocking).

        This method adds a device to the configured devices list and registers
        its available entities. If connect=True, it will start a background
        connection task (non-blocking).

        Use this for normal device addition where you don't need to wait for
        connection to complete. For hub-based integrations that need to wait
        for connection before registering entities, use async_add_configured_device().

        :param device_config: Device configuration
        :param connect: Whether to initiate connection immediately (as background task)
        """
        device = self._add_device_instance(device_config)

        if connect:
            # start background connection task (non-blocking)
            self._loop.create_task(device.connect())

        self.register_available_entities(device_config, device)

    async def async_add_configured_device(self, device_config: ConfigT) -> bool:
        """
        Add and configure a device, waiting for connection to complete (async).

        This method is designed for hub-based integrations where you need to:
        1. Add the device
        2. Wait for connection to establish
        3. Register entities (which may be populated from the hub during connection)

        Use this when require_connection_before_registry=True or when you need
        to ensure the device is connected before proceeding.

        :param device_config: Device configuration
        :return: True if device was added and connected successfully, False otherwise
        """
        device = self._add_device_instance(device_config)
        device_id = self.get_device_id(device_config)

        # Always connect and wait for completion
        _LOG.debug("Connecting to device %s", device_id)
        if not await device.connect():
            _LOG.error("Failed to connect to device %s", device_id)
            return False

        # Register entities after successful connection
        # For hub-based integrations, this allows the device to populate
        # its entity list during connection
        await self.async_register_available_entities(device_config, device)
        return True

    def setup_device_event_handlers(self, device: DeviceT) -> None:
        """
        Attach event handlers to device.

        Override this method to add custom event handlers. Call super() first
        to register the default handlers, then add your custom ones.

        :param device: Device instance
        """
        device.events.on(DeviceEvents.CONNECTED, self.on_device_connected)
        device.events.on(DeviceEvents.DISCONNECTED, self.on_device_disconnected)
        device.events.on(DeviceEvents.ERROR, self.on_device_connection_error)
        device.events.on(DeviceEvents.UPDATE, self.on_device_update)

    def register_available_entities(
        self, device_config: ConfigT, device: DeviceT
    ) -> None:
        """
        Register available entities for a device.

        Override this method to customize entity registration logic. Call super()
        to use the default implementation that calls create_entities().

        :param device_config: Device configuration
        :param device: Device instance
        """
        device_id = self.get_device_id(device_config)
        _LOG.info("Registering available entities for %s", device_id)

        entities = self.create_entities(device_config, device)

        for entity in entities:
            if self.api.available_entities.contains(entity.id):
                self.api.available_entities.remove(entity.id)
            self.api.available_entities.add(entity)

    async def async_register_available_entities(
        self, device_config: ConfigT, device: DeviceT
    ) -> None:
        """
        Register available entities for a device (async version).

        **For hub-based integrations** (require_connection_before_registry=True):
        Override this method to populate entities that are discovered from the hub
        after connection. This is called after a successful device connection.

        Default implementation:
        - If require_connection_before_registry=True: logs a warning that you should
          override this method, then falls back to register_available_entities()
        - If require_connection_before_registry=False: calls register_available_entities()

        Example for hub-based integration:
            async def async_register_available_entities(
                self, device_config: ConfigT, device: DeviceT
            ) -> None:
                # Query hub for available devices/entities
                for light in device.lights:
                    entity = ucapi.light.Light(
                        identifier=f"{device.device_id}-light-{light.device_id}",
                        name=light.name,
                        features=[...],
                        cmd_handler=...
                    )
                    if not self.api.available_entities.contains(entity.id):
                        self.api.available_entities.add(entity)

        :param device_config: Device configuration
        :param device: Device instance
        """
        if self._require_connection_before_registry:
            _LOG.warning(
                "async_register_available_entities() called but not overridden. "
                "When using require_connection_before_registry=True, you should "
                "override this method to register entities discovered from the hub. "
                "Falling back to synchronous register_available_entities()."
            )

        self.register_available_entities(device_config, device)

    def _add_device_instance(self, device_config: ConfigT) -> DeviceT:
        """
        Add a device instance without connecting or registering entities.

        This is a low-level helper used by hub-based integrations that need
        to add a device, connect, and then register entities in sequence.

        :param device_config: Device configuration
        :return: The created device instance
        """
        device_id = self.get_device_id(device_config)

        if device_id in self._configured_devices:
            _LOG.debug(
                "Device %s already exists, returning existing instance", device_id
            )
            return self._configured_devices[device_id]

        _LOG.info(
            "Adding device instance: %s (%s)",
            device_id,
            self.get_device_name(device_config),
        )
        device = self._device_class(
            device_config, loop=self._loop, config_manager=self._config_manager
        )
        self.setup_device_event_handlers(device)
        self._configured_devices[device_id] = device

        return device

    # ========================================================================
    # Device Event Handlers (can be overridden)
    # ========================================================================

    async def on_device_connected(self, device_id: str) -> None:
        """
        Handle device connection.

        :param device_id: Device identifier
        """
        _LOG.debug("Device connected: %s", device_id)

        if device_id not in self._configured_devices:
            _LOG.warning("Device %s is not configured", device_id)
            return

        await self.api.set_device_state(ucapi.DeviceStates.CONNECTED)

        device = self._configured_devices[device_id]
        state = (
            self.map_device_state(device.state)
            if device.state
            else media_player.States.UNKNOWN
        )

        for entity_id in self.get_entity_ids_for_device(device_id):
            configured_entity = self.api.configured_entities.get(entity_id)
            if configured_entity is None:
                _LOG.debug("Entity %s is not configured, ignoring", entity_id)
                continue

            # Update STATE attribute for the appropriate entity type
            match configured_entity.entity_type:
                case EntityTypes.BUTTON:
                    self.api.configured_entities.update_attributes(
                        entity_id, {button.Attributes.STATE: state}
                    )
                case EntityTypes.CLIMATE:
                    self.api.configured_entities.update_attributes(
                        entity_id, {climate.Attributes.STATE: state}
                    )
                case EntityTypes.COVER:
                    self.api.configured_entities.update_attributes(
                        entity_id, {cover.Attributes.STATE: state}
                    )
                case EntityTypes.LIGHT:
                    self.api.configured_entities.update_attributes(
                        entity_id, {light.Attributes.STATE: state}
                    )
                case EntityTypes.MEDIA_PLAYER:
                    self.api.configured_entities.update_attributes(
                        entity_id, {media_player.Attributes.STATE: state}
                    )
                case EntityTypes.REMOTE:
                    self.api.configured_entities.update_attributes(
                        entity_id, {remote.Attributes.STATE: state}
                    )
                case EntityTypes.SENSOR:
                    self.api.configured_entities.update_attributes(
                        entity_id, {sensor.Attributes.STATE: state}
                    )
                case EntityTypes.SWITCH:
                    self.api.configured_entities.update_attributes(
                        entity_id, {switch.Attributes.STATE: state}
                    )
                case (
                    EntityTypes.IR_EMITTER
                ):  # Remote shares the same states as IR Emitter
                    self.api.configured_entities.update_attributes(
                        entity_id, {remote.Attributes.STATE: state}
                    )
                case EntityTypes.VOICE_ASSISTANT:
                    self.api.configured_entities.update_attributes(
                        entity_id, {voice_assistant.Attributes.STATE: state}
                    )

    async def on_device_disconnected(self, device_id: str) -> None:
        """
        Handle device disconnection.

        :param device_id: Device identifier
        """
        _LOG.debug("Device disconnected: %s", device_id)

        for entity_id in self.get_entity_ids_for_device(device_id):
            configured_entity = self.api.configured_entities.get(entity_id)
            if configured_entity is None:
                continue

            # Update STATE attribute for the appropriate entity type
            match configured_entity.entity_type:
                case EntityTypes.BUTTON:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {button.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.CLIMATE:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {climate.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.COVER:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {cover.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.LIGHT:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {light.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.MEDIA_PLAYER:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {
                            media_player.Attributes.STATE: media_player.States.UNAVAILABLE
                        },
                    )
                case EntityTypes.REMOTE:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {remote.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.SENSOR:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {sensor.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.SWITCH:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {switch.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case (
                    EntityTypes.IR_EMITTER
                ):  # Remote shares the same states as IR Emitter
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {remote.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.VOICE_ASSISTANT:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {
                            voice_assistant.Attributes.STATE: media_player.States.UNAVAILABLE
                        },
                    )

    async def on_device_connection_error(self, device_id: str, message: str) -> None:
        """
        Handle device connection error.

        :param device_id: Device identifier
        :param message: Error message
        """
        _LOG.error("[%s] Connection error: %s", device_id, message)

        for entity_id in self.get_entity_ids_for_device(device_id):
            configured_entity = self.api.configured_entities.get(entity_id)
            if configured_entity is None:
                continue

            # Update STATE attribute for the appropriate entity type
            match configured_entity.entity_type:
                case EntityTypes.BUTTON:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {button.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.CLIMATE:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {climate.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.COVER:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {cover.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.LIGHT:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {light.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.MEDIA_PLAYER:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {
                            media_player.Attributes.STATE: media_player.States.UNAVAILABLE
                        },
                    )
                case EntityTypes.REMOTE:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {remote.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.SENSOR:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {sensor.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.SWITCH:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {switch.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case (
                    EntityTypes.IR_EMITTER
                ):  # Remote shares the same states as IR Emitter
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {remote.Attributes.STATE: media_player.States.UNAVAILABLE},
                    )
                case EntityTypes.VOICE_ASSISTANT:
                    self.api.configured_entities.update_attributes(
                        entity_id,
                        {
                            voice_assistant.Attributes.STATE: media_player.States.UNAVAILABLE
                        },
                    )

    async def on_device_update(
        self,
        entity_id: str,
        update: dict[str, Any] | None,
        clear_media_when_off: bool = True,
    ) -> None:
        """
        Handle device state updates.

        Default implementation extracts entity-type-specific attributes from the
        update dict and updates configured/available entities accordingly.
        Override this method to customize update handling or add state mapping.

        :param device_id: Device identifier
        :param update: Dictionary containing updated properties
        :param clear_media_when_off: If True, clears all media player attributes when state is OFF
        """
        if update is None:
            _LOG.warning("[%s] Received None update, skipping", entity_id)
            return

        # Process update for each entity belonging to this device
        configured_entity = self.api.configured_entities.get(entity_id)
        if configured_entity is None:
            # Try available entities if not in configured
            configured_entity = self.api.available_entities.get(entity_id)
            if configured_entity is None:
                _LOG.debug(
                    "[%s] Entity not found in configured or available entities, skipping",
                    entity_id,
                )
                return

        _LOG.debug("[%s] Device update: %s", entity_id, update)
        attributes: dict[str, Any] = {}

        match configured_entity.entity_type:
            case EntityTypes.BUTTON:
                # Button entities: STATE
                if button.Attributes.STATE.value in update:
                    state = self.map_device_state(update[button.Attributes.STATE.value])
                    attributes[button.Attributes.STATE] = state

            case EntityTypes.CLIMATE:
                # Climate entities: STATE, CURRENT_TEMPERATURE, TARGET_TEMPERATURE,
                # TARGET_TEMPERATURE_HIGH, TARGET_TEMPERATURE_LOW, FAN_MODE
                for attr in [
                    climate.Attributes.STATE,
                    climate.Attributes.CURRENT_TEMPERATURE,
                    climate.Attributes.TARGET_TEMPERATURE,
                    climate.Attributes.TARGET_TEMPERATURE_HIGH,
                    climate.Attributes.TARGET_TEMPERATURE_LOW,
                    climate.Attributes.FAN_MODE,
                ]:
                    if attr.value in update:
                        value = update[attr.value]
                        # Apply state mapping for STATE attribute
                        if attr == climate.Attributes.STATE:
                            value = self.map_device_state(value)
                        attributes[attr] = value

            case EntityTypes.COVER:
                # Cover entities: STATE, POSITION, TILT_POSITION
                for attr in [
                    cover.Attributes.STATE,
                    cover.Attributes.POSITION,
                    cover.Attributes.TILT_POSITION,
                ]:
                    if attr.value in update:
                        value = update[attr.value]
                        # Apply state mapping for STATE attribute
                        if attr == cover.Attributes.STATE:
                            value = self.map_device_state(value)
                        attributes[attr] = value

            case EntityTypes.LIGHT:
                # Light entities: STATE, HUE, SATURATION, BRIGHTNESS, COLOR_TEMPERATURE
                for attr in [
                    light.Attributes.STATE,
                    light.Attributes.HUE,
                    light.Attributes.SATURATION,
                    light.Attributes.BRIGHTNESS,
                    light.Attributes.COLOR_TEMPERATURE,
                ]:
                    if attr.value in update:
                        value = update[attr.value]
                        # Apply state mapping for STATE attribute
                        if attr == light.Attributes.STATE:
                            value = self.map_device_state(value)
                        attributes[attr] = value

            case EntityTypes.MEDIA_PLAYER:
                # Media player entities: STATE, VOLUME, MUTED, MEDIA_DURATION,
                # MEDIA_POSITION, MEDIA_TYPE, MEDIA_IMAGE_URL, MEDIA_TITLE,
                # MEDIA_ARTIST, MEDIA_ALBUM, REPEAT, SHUFFLE, SOURCE, SOURCE_LIST,
                # SOUND_MODE, SOUND_MODE_LIST

                # Check if state is being updated and is OFF
                state_value = None
                if media_player.Attributes.STATE.value in update:
                    state_value = self.map_device_state(
                        update[media_player.Attributes.STATE.value]
                    )
                    attributes[media_player.Attributes.STATE] = state_value

                # If clear_media_when_off is True and state is OFF, clear all media attributes
                if clear_media_when_off and state_value == media_player.States.OFF:
                    # Clear all media-related attributes (use empty strings for string fields, 0 for numbers)
                    attributes[media_player.Attributes.MEDIA_DURATION] = 0
                    attributes[media_player.Attributes.MEDIA_POSITION] = 0
                    attributes[media_player.Attributes.MEDIA_TYPE] = ""
                    attributes[media_player.Attributes.MEDIA_IMAGE_URL] = ""
                    attributes[media_player.Attributes.MEDIA_TITLE] = ""
                    attributes[media_player.Attributes.MEDIA_ARTIST] = ""
                    attributes[media_player.Attributes.MEDIA_ALBUM] = ""
                    attributes[media_player.Attributes.SOURCE] = ""
                    attributes[media_player.Attributes.SOUND_MODE] = ""
                else:
                    # Process remaining attributes normally
                    for attr in [
                        media_player.Attributes.VOLUME,
                        media_player.Attributes.MUTED,
                        media_player.Attributes.MEDIA_DURATION,
                        media_player.Attributes.MEDIA_POSITION,
                        media_player.Attributes.MEDIA_POSITION_UPDATED_AT,
                        media_player.Attributes.MEDIA_TYPE,
                        media_player.Attributes.MEDIA_IMAGE_URL,
                        media_player.Attributes.MEDIA_TITLE,
                        media_player.Attributes.MEDIA_ARTIST,
                        media_player.Attributes.MEDIA_ALBUM,
                        media_player.Attributes.REPEAT,
                        media_player.Attributes.SHUFFLE,
                        media_player.Attributes.SOURCE,
                        media_player.Attributes.SOURCE_LIST,
                        media_player.Attributes.SOUND_MODE,
                        media_player.Attributes.SOUND_MODE_LIST,
                    ]:
                        if attr.value in update:
                            attributes[attr] = update[attr.value]

            case EntityTypes.REMOTE:
                # Remote entities: STATE
                if remote.Attributes.STATE.value in update:
                    state = self.map_device_state(update[remote.Attributes.STATE.value])
                    attributes[remote.Attributes.STATE] = state

            case EntityTypes.SENSOR:
                # Sensor entities: STATE, VALUE, UNIT
                for attr in [
                    sensor.Attributes.STATE,
                    sensor.Attributes.VALUE,
                    sensor.Attributes.UNIT,
                ]:
                    if attr.value in update:
                        value = update[attr.value]
                        # Apply state mapping for STATE attribute
                        if attr == sensor.Attributes.STATE:
                            value = self.map_device_state(value)
                        attributes[attr] = value

            case EntityTypes.SWITCH:
                # Switch entities: STATE
                if switch.Attributes.STATE.value in update:
                    state = self.map_device_state(update[switch.Attributes.STATE.value])
                    attributes[switch.Attributes.STATE] = state

            case EntityTypes.IR_EMITTER:
                # IR Emitter entities: STATE (Shares same state mapping as Remote)
                if remote.Attributes.STATE.value in update:
                    state = self.map_device_state(update[remote.Attributes.STATE.value])
                    attributes[remote.Attributes.STATE] = state

            case EntityTypes.VOICE_ASSISTANT:
                # Voice Assistant entities: STATE
                if voice_assistant.Attributes.STATE.value in update:
                    state = self.map_device_state(
                        update[voice_assistant.Attributes.STATE.value]
                    )
                    attributes[voice_assistant.Attributes.STATE] = state

            case _:
                # Unknown entity type - log warning
                _LOG.warning(
                    "[%s] Unknown entity type: %s for entity %s",
                    entity_id,
                    configured_entity.entity_type,
                    entity_id,
                )

        # Update entity attributes if any were found
        if attributes:
            if self.api.configured_entities.contains(entity_id):
                self.api.configured_entities.update_attributes(entity_id, attributes)
            elif self.api.available_entities.contains(entity_id):
                self.api.available_entities.update_attributes(entity_id, attributes)
            _LOG.debug(
                "[%s] Updated entity %s with attributes: %s",
                entity_id,
                entity_id,
                attributes,
            )

    def get_device_config(self, device_id: str) -> ConfigT | None:
        """
        Get device configuration for the given device ID.

        Default implementation: checks _configured_devices first, then falls
        back to self._config_manager.get() if config manager is available.
        Override this if your integration uses a different config structure.

        :param device_id: Device identifier
        :return: Device configuration or None
        """
        # First check if device is already configured
        device = self._configured_devices.get(device_id)
        if device:
            return device.device_config

        # Fall back to stored configuration if available
        if self._config_manager and hasattr(self._config_manager, "get"):
            return self._config_manager.get(device_id)

        return None

    def get_device_id(self, device_config: ConfigT) -> str:
        """
        Extract device ID from device configuration.

        Default implementation: tries common attribute names (identifier, id, device_id).
        Override this if your config uses a different attribute name.

        :param device_config: Device configuration
        :return: Device identifier
        :raises AttributeError: If no valid ID attribute is found
        """
        value = _get_first_valid_attr(device_config, *_DEVICE_ID_ATTRIBUTES)
        if value:
            return value

        raise AttributeError(
            f"Device config {type(device_config).__name__} has no 'identifier', 'id', or 'device_id' attribute. "
            f"Override get_device_id() to specify which attribute to use."
        )

    def get_device_name(self, device_config: ConfigT) -> str:
        """
        Extract device name from device configuration.

        Default implementation: tries common attribute names (name, friendly_name, device_name).
        Override this if your config uses a different attribute name.

        :param device_config: Device configuration
        :return: Device name
        :raises AttributeError: If no valid name attribute is found
        """
        value = _get_first_valid_attr(device_config, *_DEVICE_NAME_ATTRIBUTES)
        if value:
            return value

        raise AttributeError(
            f"Device config {type(device_config).__name__} has no 'name', 'friendly_name', or 'device_name' attribute. "
            f"Override get_device_name() to specify which attribute to use."
        )

    def get_device_address(self, device_config: ConfigT) -> str:
        """
        Extract device address from device configuration.

        Default implementation: tries common attribute names (address, host_address, ip_address, device_address, host).
        Override this if your config uses a different attribute name.

        :param device_config: Device configuration
        :return: Device address
        :raises AttributeError: If no valid address attribute is found
        """
        value = _get_first_valid_attr(device_config, *_DEVICE_ADDRESS_ATTRIBUTES)
        if value:
            return value

        raise AttributeError(
            f"Device config {type(device_config).__name__} has no 'address', 'host_address', 'ip_address', 'device_address', or 'host' attribute. "
            f"Override get_device_address() to specify which attribute to use."
        )

    def create_entities(self, device_config: ConfigT, device: DeviceT) -> list[Entity]:
        """
        Create entity instances for a device.

        DEFAULT IMPLEMENTATION: Creates one instance per entity class passed to __init__,
        calling each as: entity_class(device_config, device)

        This works automatically for simple integrations. Override this method only when you need:
        - Variable entity counts (e.g., multi-zone receivers)
        - Hub-based discovery with runtime entity creation
        - Conditional entity creation based on device capabilities
        - Custom parameters beyond (device_config, device)

        Example - Multi-zone receiver:
            def create_entities(self, device_config, device):
                entities = []
                for zone in device_config.zones:
                    entities.append(AnthemMediaPlayer(
                        entity_id=f"media_player.{device_config.id}_zone_{zone.id}",
                        device=device,
                        device_config=device_config,
                        zone_config=zone  # Custom parameter
                    ))
                return entities

        Example - Conditional creation:
            def create_entities(self, device_config, device):
                entities = []
                if device.supports_playback:
                    entities.append(YamahaMediaPlayer(device_config, device))
                if device.supports_remote:
                    entities.append(YamahaRemote(device_config, device))
                return entities

        :param device_config: Device configuration
        :param device: Device instance
        :return: List of entity instances (MediaPlayer, Remote, etc.)
        """
        # Default: instantiate from entity_classes
        return [
            entity_class(device_config, device) for entity_class in self._entity_classes
        ]

    def map_device_state(self, device_state: Any) -> media_player.States:
        """
        Map device-specific state to ucapi media player state.

        DEFAULT IMPLEMENTATION: Converts device_state to uppercase string and maps
        common state values to media_player.States:

        - UNAVAILABLE → UNAVAILABLE
        - UNKNOWN → UNKNOWN
        - ON, MENU, IDLE, ACTIVE, READY → ON
        - OFF, POWER_OFF, POWERED_OFF → OFF
        - PLAYING, PLAY → PLAYING
        - PAUSED, PAUSE → PAUSED
        - STANDBY, SLEEP → STANDBY
        - BUFFERING, LOADING → BUFFERING
        - Everything else → UNKNOWN

        Override this method if you need:
        - Different state mappings
        - Device-specific state enum handling
        - Complex state logic

        Example override:
            def map_device_state(self, device_state):
                if isinstance(device_state, MyDeviceState):
                    match device_state:
                        case MyDeviceState.POWERED_ON:
                            return media_player.States.ON
                        case MyDeviceState.POWERED_OFF:
                            return media_player.States.OFF
                        case _:
                            return media_player.States.UNKNOWN
                return super().map_device_state(device_state)

        :param device_state: Device-specific state (string, enum, or any object with __str__)
        :return: Media player state
        """
        if device_state is None:
            return media_player.States.UNKNOWN

        # If already a media_player.States enum, return it directly
        if isinstance(device_state, media_player.States):
            return device_state

        # Convert to uppercase string for comparison
        state_str = str(device_state).upper()

        match state_str:
            case "UNAVAILABLE":
                return media_player.States.UNAVAILABLE
            case "UNKNOWN":
                return media_player.States.UNKNOWN
            case "ON" | "MENU" | "IDLE" | "ACTIVE" | "READY":
                return media_player.States.ON
            case "OFF" | "POWER_OFF" | "POWERED_OFF" | "STOPPED":
                return media_player.States.OFF
            case "PLAYING" | "PLAY" | "SEEKING":
                return media_player.States.PLAYING
            case "PAUSED" | "PAUSE":
                return media_player.States.PAUSED
            case "STANDBY" | "SLEEP":
                return media_player.States.STANDBY
            case "BUFFERING" | "LOADING":
                return media_player.States.BUFFERING
            case _:
                return media_player.States.UNKNOWN

    # ========================================================================
    # Entity ID Methods (should be overridden together if custom format used)
    # ========================================================================

    def entity_type_from_entity_id(self, entity_id: str) -> str | None:
        """
        Extract entity type from entity identifier.

        DEFAULT IMPLEMENTATION: Parses entity IDs using the configured separator
        (defaults to "."). Returns the entity type (first part before the separator):
        - "media_player.device_123" → returns "media_player"
        - "light.hub_1.light_bedroom" → returns "light"

        If you use a custom entity ID format that doesn't use the standard separator,
        either:
        1. Set `driver.entity_id_separator` to your custom separator, OR
        2. Override this method to parse your custom format

        Example with custom separator:
            def __init__(self, ...):
                super().__init__(...)
                self.entity_id_separator = "_"  # Use underscore instead of period

        Example custom override:
            def entity_type_from_entity_id(self, entity_id: str) -> str | None:
                # For PSN, all entities are media players
                return "media_player"

        :param entity_id: Entity identifier (e.g., "media_player.device_123")
        :return: Entity type string or None
        :raises ValueError: If entity_id doesn't contain the expected separator
        """
        if not entity_id:
            return None

        # Check if separator exists in entity_id
        if self.entity_id_separator not in entity_id:
            raise ValueError(
                f"Entity ID '{entity_id}' does not contain the expected separator "
                f"'{self.entity_id_separator}'. Either your entity IDs are not using the "
                f"standard format, or you need to set driver.entity_id_separator to match "
                f"your format, or override entity_type_from_entity_id() to parse your custom format."
            )

        # Split on separator: "entity_type.device_id" or "entity_type.device_id.entity_id"
        parts = entity_id.split(self.entity_id_separator)

        # First part is always the entity_type
        return parts[0] if parts else None

    def device_from_entity_id(self, entity_id: str) -> str | None:
        """
        Extract device identifier from entity identifier.

        DEFAULT IMPLEMENTATION: Parses entity IDs using the configured separator
        (defaults to "."). Handles both formats:
        - Simple: "entity_type.device_id" → returns "device_id"
        - With sub-entity: "entity_type.device_id.entity_id" → returns "device_id"

        If you use a custom entity ID format that doesn't use the standard separator,
        either:
        1. Set `driver.entity_id_separator` to your custom separator, OR
        2. Override this method to parse your custom format

        Example with custom separator:
            def __init__(self, ...):
                super().__init__(...)
                self.entity_id_separator = "_"  # Use underscore instead of period

        Example custom override:
            def device_from_entity_id(self, entity_id: str) -> str | None:
                # For PSN, entity_id IS the device_id
                return entity_id

        :param entity_id: Entity identifier (e.g., "media_player.device_123")
        :return: Device identifier or None
        :raises ValueError: If entity_id doesn't contain the expected separator
        """
        if not entity_id:
            return None

        # Check if separator exists in entity_id
        if self.entity_id_separator not in entity_id:
            raise ValueError(
                f"Entity ID '{entity_id}' does not contain the expected separator "
                f"'{self.entity_id_separator}'. Either your entity IDs are not using the "
                f"standard format, or you need to set driver.entity_id_separator to match "
                f"your format, or override device_from_entity_id() to parse your custom format."
            )

        # Split on separator: "entity_type.device_id" or "entity_type.device_id.entity_id"
        parts = entity_id.split(self.entity_id_separator)

        if len(parts) < 2:
            return None

        # Second part is always the device_id
        return parts[1]

    def sub_device_from_entity_id(self, entity_id: str) -> str | None:
        """
        Extract sub-device identifier from entity identifier (if present).

        DEFAULT IMPLEMENTATION: Parses entity IDs using the configured separator
        (defaults to "."). Returns the sub-device ID (third part) if present, None otherwise:
        - Simple: "entity_type.device_id" → returns None (no sub-device)
        - With sub-device: "entity_type.device_id.sub_device_id" → returns "sub_device_id"

        If you use a custom entity ID format that doesn't use the standard separator,
        either:
        1. Set `driver.entity_id_separator` to your custom separator, OR
        2. Override this method to parse your custom format

        Example with custom separator:
            def __init__(self, ...):
                super().__init__(...)
                self.entity_id_separator = "_"  # Use underscore instead of period

        Example custom override:
            def sub_device_from_entity_id(self, entity_id: str) -> str | None:
                # For custom format: "deviceid_zonename"
                if "_" in entity_id:
                    return entity_id.split("_", 1)[1]  # Returns "zone1", "zone2"
                return None

        :param entity_id: Entity identifier (e.g., "light.hub_1.bedroom")
        :return: Sub-device identifier or None
        :raises ValueError: If entity_id doesn't contain the expected separator
        """
        if not entity_id:
            return None

        # Check if separator exists in entity_id
        if self.entity_id_separator not in entity_id:
            raise ValueError(
                f"Entity ID '{entity_id}' does not contain the expected separator "
                f"'{self.entity_id_separator}'. Either your entity IDs are not using the "
                f"standard format, or you need to set driver.entity_id_separator to match "
                f"your format, or override sub_device_from_entity_id() to parse your custom format."
            )

        # Split on separator: "entity_type.device_id" or "entity_type.device_id.sub_device_id"
        parts = entity_id.split(
            self.entity_id_separator, 2
        )  # Split into at most 3 parts

        # Return everything after the second separator if present, None otherwise
        if len(parts) >= 3:
            return parts[2]  # This will be "sub_device_id" or "sub.device.with.dots"

        return None

    def get_entity_ids_for_device(self, device_id: str) -> list[str]:
        """
        Get all entity identifiers for a device.

        DEFAULT IMPLEMENTATION: Queries all registered entities from the API and
        filters them by device_id using device_from_entity_id().

        This works automatically with the standard entity ID format from create_entity_id().
        For integrations using custom entity ID formats, this will work as long as
        device_from_entity_id() is properly overridden to parse your custom format.

        Override this method only if you need:
        - Performance optimization for integrations with many entities
        - Special filtering logic beyond device_id matching
        - Caching or pre-computed entity lists

        Example override for performance:
            def get_entity_ids_for_device(self, device_id: str) -> list[str]:
                # Cache entity IDs per device for faster lookups
                if device_id not in self._entity_cache:
                    self._entity_cache[device_id] = [
                        f"media_player.{device_id}",
                        f"remote.{device_id}",
                    ]
                return self._entity_cache[device_id]

        :param device_id: Device identifier
        :return: List of entity identifiers for this device
        """
        # Query all entities (both available and configured) and filter by device_id
        entity_ids = set()  # Use set to avoid duplicates

        # Check available entities
        for entity in self.api.available_entities.get_all():
            entity_device_id = self.device_from_entity_id(entity["entity_id"])
            if entity_device_id == device_id:
                entity_ids.add(entity["entity_id"])

        # Check configured entities
        for entity in self.api.configured_entities.get_all():
            entity_device_id = self.device_from_entity_id(entity["entity_id"])
            if entity_device_id == device_id:
                entity_ids.add(entity["entity_id"])

        return list(entity_ids)

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def remove_device(self, device_id: str) -> None:
        """
        Remove a configured device.

        :param device_id: Device identifier
        """
        if device_id in self._configured_devices:
            _LOG.info("Removing device %s", device_id)
            device = self._configured_devices.pop(device_id)
            device.events.remove_all_listeners()

            # Remove all associated entities
            for entity_id in self.get_entity_ids_for_device(device_id):
                self.api.configured_entities.remove(entity_id)
                self.api.available_entities.remove(entity_id)
        else:
            _LOG.warning("Device %s not found in configured devices", device_id)

    def clear_devices(self) -> None:
        """Remove all configured devices."""
        _LOG.info("Clearing all configured devices")
        for device in self._configured_devices.values():
            device.events.remove_all_listeners()
        self._configured_devices.clear()
        self.api.configured_entities.clear()
        self.api.available_entities.clear()

    # ========================================================================
    # Configuration Change Callbacks (can be overridden)
    # ========================================================================

    def on_device_added(self, device_config: ConfigT | None) -> None:
        """
        Handle a newly added device in the configuration.

        Default implementation:
        - If require_connection_before_registry=True: schedules async_add_configured_device
          as a background task (connects and registers entities after connection)
        - Otherwise: adds the device without connecting

        Override if you need custom behavior.

        :param device_config: Device configuration that was added
        """
        _LOG.debug("Device added: %s", self.get_device_id(device_config))

        if self._require_connection_before_registry:
            # Schedule async device addition as a background task
            self._loop.create_task(self.async_add_configured_device(device_config))
        else:
            self.add_configured_device(device_config, connect=False)

    def on_device_removed(self, device_config: ConfigT | None) -> None:
        """
        Handle a removed device in the configuration.

        Default implementation: Removes the device or clears all if None.
        Override if you need custom behavior.

        :param device_config: Device configuration that was removed, or None to clear all
        """
        if device_config is None:
            _LOG.debug("Configuration cleared, removing all devices")
            self.clear_devices()
        else:
            device_id = self.get_device_id(device_config)
            _LOG.debug("Device removed: %s", device_id)
            self.remove_device(device_id)

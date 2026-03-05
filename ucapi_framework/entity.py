"""
Common entity interface for UC API integrations.

:copyright: (c) 2025 by Unfolded Circle ApS.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from abc import ABC
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any, cast
from ucapi import (
    IntegrationAPI,
    button,
    climate,
    cover,
    ir_emitter,
    light,
    media_player,
    remote,
    select,
    sensor,
    switch,
    voice_assistant,
)
from .helpers import EntityAttributes

if TYPE_CHECKING:
    from .device import BaseDeviceInterface

# Mapping from ucapi entity classes to their Attributes enums
_ENTITY_ATTRIBUTES_MAP = {
    button.Button: button.Attributes,
    climate.Climate: climate.Attributes,
    cover.Cover: cover.Attributes,
    ir_emitter.IREmitter: ir_emitter.Attributes,
    light.Light: light.Attributes,
    media_player.MediaPlayer: media_player.Attributes,
    remote.Remote: remote.Attributes,
    select.Select: select.Attributes,
    sensor.Sensor: sensor.Attributes,
    switch.Switch: switch.Attributes,
    voice_assistant.VoiceAssistant: voice_assistant.Attributes,
}


def map_state_to_media_player(device_state: Any) -> media_player.States:
    """
    Map a device-specific state to media_player.States.

    This helper function provides the default state mapping logic used by both
    Entity.map_entity_states() and BaseIntegrationDriver.map_device_state().

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


# pylint: disable=R0903
class Entity(ABC):
    """
    Common interface for entities with custom behavior.

    This ABC provides optional per-entity customization of state mapping and
    attribute updates. Entities inheriting from this class will automatically
    use their custom methods when the driver processes updates.

    **Usage Pattern**:

        from dataclasses import dataclass
        from ucapi import media_player
        from ucapi_framework import Entity

        @dataclass
        class MediaPlayerAttributes:
            STATE: media_player.States = media_player.States.UNKNOWN
            VOLUME: int = 0
            MUTED: bool = False

        class MyMediaPlayer(media_player.MediaPlayer, Entity):
            def __init__(self, device_config, device):
                # Initialize ucapi entity
                entity_id = create_entity_id(device.id, "media_player")
                media_player.MediaPlayer.__init__(
                    self, entity_id, device.name, features, attributes
                )

                # Framework sets self._api automatically after construction
                self._device = device

                # Create attributes dataclass for easy state management
                self.attrs = MediaPlayerAttributes()

            def sync_from_device(self):
                \"\"\"Map device state to entity attributes.\"\"\"
                self.attrs.STATE = self.map_entity_states(self._device.state)
                self.attrs.VOLUME = self._device.volume
                self.attrs.MUTED = self._device.is_muted

            async def handle_command(self, entity_id, cmd_id, params):
                \"\"\"Handle commands and sync state.\"\"\"
                if cmd_id == media_player.Commands.ON:
                    await self._device.turn_on()
                    self.sync_from_device()
                    self.update_from_dataclass(self.attrs)  # Auto-filters changes!

    The framework automatically sets `self._api` after entity construction.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize the Entity with cooperative multiple inheritance support.

        This uses *args/**kwargs to support MRO chain traversal when Entity
        is mixed with ucapi entity classes that have their own __init__ signatures.
        """
        # Pass all args/kwargs up the MRO chain (to ucapi.Entity or others)
        super().__init__(*args, **kwargs)

        # Initialize framework-specific attributes
        self._entity_id: str | None = None

    _api: IntegrationAPI

    @property
    def _framework_entity_id(self) -> str:
        """Get the entity ID (lazy initialization from ucapi.Entity parent)."""
        # Use getattr to handle case where __init__ wasn't called due to MRO
        entity_id = getattr(self, "_entity_id", None)
        if entity_id is None:
            # Access the id from the ucapi.Entity parent class
            if hasattr(self, "id"):
                self._entity_id = self.id  # type: ignore[assignment]
                return self._entity_id  # type: ignore[return-value]
            else:
                raise RuntimeError(
                    "Entity ID not available. Ensure entity is properly initialized."
                )
        return entity_id  # type: ignore[return-value]

    def update_attributes(self, update: dict[str, Any], *, force: bool = False) -> None:
        """
        Update the entity attributes from the given device update.

        :param update: dictionary containing the updated properties.
        :param force: if True, update attributes even if they haven't changed.
        """
        # Skip entirely if this entity is not configured on the Remote.
        if not self._api.configured_entities.contains(self._framework_entity_id):
            return

        # Strip None values - they represent attributes that have never been set
        # and should not be sent to the Remote. Empty strings and False are valid.
        update = {k: v for k, v in update.items() if v is not None}

        if force:
            attributes = update
            # Even with force=True, skip if update is empty
            if not attributes:
                return
        else:
            attributes = self.filter_changed_attributes(update)
            # Skip if no attributes changed
            if not attributes:
                return

        self._api.configured_entities.update_attributes(
            self._framework_entity_id, attributes
        )

    def update(
        self, attributes: EntityAttributes | dict[str, Any], *, force: bool = False
    ) -> None:
        """
        Update entity attributes from a dataclass or dictionary.

        Provides a unified interface for updating entity attributes regardless of whether
        you're using dataclasses (recommended) or plain dictionaries. When using a dataclass,
        None values are automatically filtered out. All updates filter unchanged values
        unless force=True.

        Args:
            attributes: An EntityAttributes dataclass instance (e.g., MediaPlayerAttributes)
                       or a dict of attribute key-value pairs.
            force: If True, update all attributes even if unchanged. Default False.

        Raises:
            TypeError: If attributes is neither a dataclass nor a dict.

        Example with dataclass (recommended):
            ```python
            from ucapi_framework import MediaPlayerAttributes
            from ucapi import media_player

            # In your device
            self.attrs = MediaPlayerAttributes(
                STATE=media_player.States.PLAYING,
                VOLUME=50
            )

            # In your entity - clean and simple
            self.update(self._device.attrs)
            ```

        Example with dict:
            ```python
            from ucapi import media_player

            # Also works with plain dicts
            self.update({
                media_player.Attributes.STATE: media_player.States.PLAYING,
                media_player.Attributes.VOLUME: 50
            })
            ```
        """
        # Handle dict directly
        if isinstance(attributes, dict):
            self.update_attributes(cast(dict[str, Any], attributes), force=force)
            return

        # Handle dataclass
        if not is_dataclass(attributes):
            msg = f"Expected a dataclass or dict, got {type(attributes).__name__}"
            raise TypeError(msg)

        # Convert dataclass to dict and filter out None values
        attrs_dict = {k: v for k, v in asdict(attributes).items() if v is not None}

        # Convert string keys to Attribute enum objects
        # The dataclass field names match the Attribute enum member names
        # Walk MRO to find the first ucapi entity class and get its Attributes enum
        attributes_enum = None
        for base in self.__class__.__mro__:
            if base in _ENTITY_ATTRIBUTES_MAP:
                attributes_enum = _ENTITY_ATTRIBUTES_MAP[base]
                break

        if attributes_enum:
            # Convert string keys to enum objects
            attrs = {}
            for key, value in attrs_dict.items():
                try:
                    # Look up the enum member by name
                    attrs[attributes_enum[key]] = value
                except KeyError:
                    # If the key doesn't exist in the enum, skip it
                    # (allows for extra fields in dataclass that aren't in ucapi)
                    pass
        else:
            # Fallback: use string keys as-is (shouldn't happen for ucapi entities)
            attrs = attrs_dict

        self.update_attributes(attrs, force=force)

    def set_unavailable(self) -> None:
        """
        Mark this entity as unavailable on the Remote.

        Sets ``Attributes.STATE`` to ``States.UNAVAILABLE`` for the entity type
        and pushes the update immediately. Works for all ucapi entity types
        (button, climate, cover, light, media_player, remote, select, etc.).

        Example::

            def on_device_disconnected(self):
                self.set_unavailable()
        """
        # All ucapi States enums share the same UNAVAILABLE string value,
        # so media_player.States.UNAVAILABLE works as a proxy for all entity types.
        self.update({media_player.Attributes.STATE: media_player.States.UNAVAILABLE})

    def subscribe_to_device(self, device: "BaseDeviceInterface") -> None:
        """
        Subscribe to device UPDATE events.

        Registers ``sync_state()`` as a listener on the device's UPDATE event.
        Call this in ``__init__`` to wire the entity to its device — after that,
        every ``DeviceEvents.UPDATE`` emission will automatically invoke
        ``sync_state()`` on this entity.

        The framework also calls ``sync_state()`` directly during
        ``on_device_connected`` and ``refresh_entity_state``, so subscription
        handles the push-notification path while the driver handles the
        poll/reconnect path.

        :param device: Device instance to subscribe to.

        Example::

            class MyLight(LightEntity):
                def __init__(self, config, device):
                    super().__init__(...)
                    self._device = device
                    self.subscribe_to_device(device)

                async def sync_state(self) -> None:
                    self.update({
                        light.Attributes.STATE: self.map_entity_states(self._device.state),
                        light.Attributes.BRIGHTNESS: self._device.brightness,
                    })
        """
        from .device import DeviceEvents  # local import to avoid circular dependency

        device.events.on(DeviceEvents.UPDATE, self._handle_device_update)

    async def _handle_device_update(self, *_args: Any, **_kwargs: Any) -> None:
        """Internal handler wired to DeviceEvents.UPDATE by subscribe_to_device."""
        await self.sync_state()

    async def sync_state(self) -> None:
        """
        Sync entity state from device to Remote.

        Override this method to read current values from ``self._device`` and call
        ``self.update()`` with a **fresh dict or dataclass** — do not mutate
        ``self.attributes`` directly, as that would defeat change-filtering.

        The framework calls this method automatically in two situations:

        - **Device reconnect** — after ``on_device_connected``, the driver calls
          ``sync_state()`` on each configured entity for the device.
        - **Device UPDATE event** — if the entity has subscribed via
          ``subscribe_to_device()``, ``sync_state()`` is called on every
          ``DeviceEvents.UPDATE`` emission.

        The default implementation is a no-op. Override it when the entity
        manages its own state (i.e. the developer is not using the driver's
        default ``on_device_update`` attribute-routing logic).

        Example with dict::

            async def sync_state(self) -> None:
                self.update({
                    light.Attributes.STATE: self.map_entity_states(self._device.state),
                    light.Attributes.BRIGHTNESS: self._device.brightness,
                })

        Example with dataclass (recommended)::

            async def sync_state(self) -> None:
                self.update(LightAttributes(
                    STATE=self.map_entity_states(self._device.state),
                    BRIGHTNESS=self._device.brightness,
                ))
        """
        # No-op by default. Subclasses override to pull from device and push to Remote.

    def filter_changed_attributes(self, update: dict[str, Any]) -> dict[str, Any]:
        """
        Filter the given attributes and return only the changed values.

        Compares each attribute in the update dict with the currently stored
        entity state in configured_entities and only returns attributes that
        have actually changed.

        :param update: dictionary containing the updated properties.
        :return: dictionary containing only the changed attributes.
        """
        configured_entity = self._api.configured_entities.get(self._framework_entity_id)
        if not configured_entity:
            # Entity not found, return all attributes
            return update

        # Get current attributes from the configured entity
        current_attributes = configured_entity.attributes or {}

        # Return only changed values
        return {
            key: value
            for key, value in update.items()
            if current_attributes.get(key) != value
        }

    def map_entity_states(self, device_state: Any) -> Any:
        """
        Convert a device-specific state to a UC API entity state.

        DEFAULT IMPLEMENTATION: Uses map_state_to_media_player() helper to convert
        device_state to uppercase string and map common state values to media_player.States:

        - UNAVAILABLE → UNAVAILABLE
        - UNKNOWN → UNKNOWN
        - ON, MENU, IDLE, ACTIVE, READY → ON
        - OFF, POWER_OFF, POWERED_OFF, STOPPED → OFF
        - PLAYING, PLAY, SEEKING → PLAYING
        - PAUSED, PAUSE → PAUSED
        - STANDBY, SLEEP → STANDBY
        - BUFFERING, LOADING → BUFFERING
        - Everything else → UNKNOWN

        Override this method per entity type to customize state mapping for your device.

        Example override:
            class MyCustomMediaPlayer(MediaPlayer, Entity):
                def map_entity_states(self, device_state):
                    if isinstance(device_state, MyDeviceState):
                        match device_state:
                            case MyDeviceState.POWERED_ON:
                                return media_player.States.ON
                            case MyDeviceState.POWERED_OFF:
                                return media_player.States.OFF
                            case _:
                                return media_player.States.UNKNOWN
                    return super().map_entity_states(device_state)

        :param device_state: Device-specific state (string, enum, or any object with __str__)
        :return: UC API entity state (typically media_player.States)
        """
        return map_state_to_media_player(device_state)

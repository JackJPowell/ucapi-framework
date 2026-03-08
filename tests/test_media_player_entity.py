"""Tests for MediaPlayerEntity with built-in state management."""

import asyncio
import pytest
from unittest.mock import MagicMock
from ucapi import media_player
from ucapi_framework import MediaPlayerEntity
from ucapi_framework.device import BaseDeviceInterface, DeviceEvents


def _make_api(initial_state=media_player.States.UNKNOWN):
    """Return a mock API whose configured_entities.contains returns True."""
    api = MagicMock()
    api.configured_entities.contains.return_value = True
    api.configured_entities.get.return_value = MagicMock(
        attributes={media_player.Attributes.STATE: initial_state}
    )
    return api


def _make_entity(mock_api=None, extra_attrs=None):
    """Create a MediaPlayerEntity wired to a mock API."""
    attrs = {media_player.Attributes.STATE: media_player.States.UNKNOWN}
    if extra_attrs:
        attrs.update(extra_attrs)
    entity = MediaPlayerEntity(
        "media_player.test",
        "Test Player",
        features=[media_player.Features.ON_OFF, media_player.Features.VOLUME],
        attributes=attrs,
    )
    entity._api = mock_api or _make_api()  # noqa: SLF001
    return entity


class TestMediaPlayerEntity:
    """Test MediaPlayerEntity state management."""

    @pytest.fixture
    def mock_api(self):
        return _make_api()

    @pytest.fixture
    def entity(self, mock_api):
        return _make_entity(mock_api)

    # ------------------------------------------------------------------
    # Property getters — all attributes
    # ------------------------------------------------------------------

    def test_initial_state(self, entity):
        """All unset properties return None; initial state is UNKNOWN."""
        assert entity.state == media_player.States.UNKNOWN
        assert entity.volume is None
        assert entity.muted is None
        assert entity.media_duration is None
        assert entity.media_position is None
        assert entity.media_position_updated_at is None
        assert entity.media_type is None
        assert entity.media_image_url is None
        assert entity.media_title is None
        assert entity.media_artist is None
        assert entity.media_album is None
        assert entity.repeat is None
        assert entity.shuffle is None
        assert entity.source is None
        assert entity.source_list is None
        assert entity.sound_mode is None
        assert entity.sound_mode_list is None

    def test_property_getters_are_read_only(self, entity):
        """Property setters must not exist — direct assignment raises AttributeError."""
        with pytest.raises(AttributeError):
            entity.state = media_player.States.PLAYING  # type: ignore[misc]

    # ------------------------------------------------------------------
    # set_state
    # ------------------------------------------------------------------

    def test_set_state_with_update(self, entity, mock_api):
        """set_state(update=True) pushes STATE to Remote."""
        entity.set_state(media_player.States.PLAYING, update=True)

        assert entity.state == media_player.States.PLAYING
        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "media_player.test"
        assert attributes[media_player.Attributes.STATE] == media_player.States.PLAYING

    def test_set_state_without_update(self, entity, mock_api):
        """set_state(update=False) updates local state but does not push."""
        entity.set_state(media_player.States.PLAYING, update=False)
        assert entity.state == media_player.States.PLAYING
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_state_all_states(self, entity):
        """set_state accepts every States enum value."""
        for state in media_player.States:
            entity.set_state(state, update=False)
            assert entity.state == state

    def test_set_state_none(self, entity, mock_api):
        """set_state(None) clears the state property."""
        entity.set_state(None, update=False)
        assert entity.state is None

    # ------------------------------------------------------------------
    # Individual setters — update=True and update=False paths
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("value,update", [(75, True), (0, False), (100, True)])
    def test_set_volume(self, entity, mock_api, value, update):
        entity.set_volume(value, update=update)
        assert entity.volume == value
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize(
        "value,update", [(True, True), (False, True), (True, False)]
    )
    def test_set_muted(self, entity, mock_api, value, update):
        entity.set_muted(value, update=update)
        assert entity.muted is value
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_media_duration(self, entity, mock_api, update):
        entity.set_media_duration(300, update=update)
        assert entity.media_duration == 300
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_media_position(self, entity, mock_api, update):
        entity.set_media_position(120, update=update)
        assert entity.media_position == 120
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_media_position_updated_at(self, entity, mock_api, update):
        entity.set_media_position_updated_at("2025-01-01T12:00:00Z", update=update)
        assert entity.media_position_updated_at == "2025-01-01T12:00:00Z"
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_media_type(self, entity, mock_api, update):
        entity.set_media_type("music", update=update)
        assert entity.media_type == "music"
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_media_image_url(self, entity, mock_api, update):
        entity.set_media_image_url("https://example.com/art.jpg", update=update)
        assert entity.media_image_url == "https://example.com/art.jpg"
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_media_title(self, entity, mock_api, update):
        entity.set_media_title("Test Song", update=update)
        assert entity.media_title == "Test Song"
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_media_artist(self, entity, mock_api, update):
        entity.set_media_artist("Test Artist", update=update)
        assert entity.media_artist == "Test Artist"
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_media_album(self, entity, mock_api, update):
        entity.set_media_album("Test Album", update=update)
        assert entity.media_album == "Test Album"
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_repeat(self, entity, mock_api, update):
        entity.set_repeat(media_player.RepeatMode.ALL, update=update)
        assert entity.repeat == media_player.RepeatMode.ALL
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("value,update", [(True, True), (False, False)])
    def test_set_shuffle(self, entity, mock_api, value, update):
        entity.set_shuffle(value, update=update)
        assert entity.shuffle is value
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_source(self, entity, mock_api, update):
        entity.set_source("Spotify", update=update)
        assert entity.source == "Spotify"
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_source_list(self, entity, mock_api, update):
        sources = ["HDMI 1", "HDMI 2", "Bluetooth"]
        entity.set_source_list(sources, update=update)
        assert entity.source_list == sources
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_sound_mode(self, entity, mock_api, update):
        entity.set_sound_mode("Stereo", update=update)
        assert entity.sound_mode == "Stereo"
        assert mock_api.configured_entities.update_attributes.called == update

    @pytest.mark.parametrize("update", [True, False])
    def test_set_sound_mode_list(self, entity, mock_api, update):
        modes = ["Stereo", "Surround", "Night"]
        entity.set_sound_mode_list(modes, update=update)
        assert entity.sound_mode_list == modes
        assert mock_api.configured_entities.update_attributes.called == update

    # ------------------------------------------------------------------
    # set_attributes bulk helper
    # ------------------------------------------------------------------

    def test_set_attributes_bulk_update(self, entity, mock_api):
        """set_attributes() batches multiple attributes into a single Remote push."""
        entity.set_attributes(
            state=media_player.States.PLAYING,
            volume=50,
            muted=False,
            media_title="Song Title",
            media_artist="Artist Name",
            update=True,
        )

        assert entity.state == media_player.States.PLAYING
        assert entity.volume == 50
        assert entity.muted is False
        assert entity.media_title == "Song Title"
        assert entity.media_artist == "Artist Name"

        # Exactly one Remote push for all changes
        assert mock_api.configured_entities.update_attributes.call_count == 1

    def test_set_attributes_without_update(self, entity, mock_api):
        """set_attributes(update=False) updates local state but does not push."""
        entity.set_attributes(
            state=media_player.States.PLAYING, volume=50, update=False
        )
        assert entity.state == media_player.States.PLAYING
        assert entity.volume == 50
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_ignores_none_values(self, entity, mock_api):
        """set_attributes() skips None kwargs — they don't overwrite existing values."""
        entity.set_attributes(
            state=media_player.States.PLAYING, volume=None, update=True
        )
        assert entity.state == media_player.States.PLAYING
        assert entity.volume is None
        # Only STATE should have been pushed
        call_args = mock_api.configured_entities.update_attributes.call_args
        _, attributes = call_args[0]
        assert len(attributes) == 1
        assert media_player.Attributes.STATE in attributes

    def test_set_attributes_all_fields(self, entity, mock_api):
        """set_attributes() covers every supported attribute in one call."""
        entity.set_attributes(
            state=media_player.States.PLAYING,
            volume=75,
            muted=False,
            media_duration=300,
            media_position=120,
            media_position_updated_at="2025-01-01T12:00:00Z",
            media_type="music",
            media_image_url="https://example.com/art.jpg",
            media_title="Test Song",
            media_artist="Test Artist",
            media_album="Test Album",
            repeat=media_player.RepeatMode.ALL,
            shuffle=True,
            source="Spotify",
            source_list=["Spotify", "Bluetooth"],
            sound_mode="Stereo",
            sound_mode_list=["Stereo", "Surround"],
            update=True,
        )

        assert entity.state == media_player.States.PLAYING
        assert entity.volume == 75
        assert entity.muted is False
        assert entity.media_duration == 300
        assert entity.media_position == 120
        assert entity.media_position_updated_at == "2025-01-01T12:00:00Z"
        assert entity.media_type == "music"
        assert entity.media_image_url == "https://example.com/art.jpg"
        assert entity.media_title == "Test Song"
        assert entity.media_artist == "Test Artist"
        assert entity.media_album == "Test Album"
        assert entity.repeat == media_player.RepeatMode.ALL
        assert entity.shuffle is True
        assert entity.source == "Spotify"
        assert entity.source_list == ["Spotify", "Bluetooth"]
        assert entity.sound_mode == "Stereo"
        assert entity.sound_mode_list == ["Stereo", "Surround"]

        # All in a single Remote push
        assert mock_api.configured_entities.update_attributes.call_count == 1

    # ------------------------------------------------------------------
    # set_unavailable
    # ------------------------------------------------------------------

    def test_set_unavailable(self, entity, mock_api):
        """set_unavailable() pushes STATE=UNAVAILABLE to the Remote."""
        entity.set_unavailable()

        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "media_player.test"
        assert (
            attributes[media_player.Attributes.STATE] == media_player.States.UNAVAILABLE
        )

    def test_set_unavailable_does_not_change_other_state(self, entity, mock_api):
        """set_unavailable() only marks STATE; volume and title are not cleared."""
        entity.set_volume(50, update=False)
        entity.set_media_title("Track", update=False)
        mock_api.configured_entities.update_attributes.reset_mock()

        entity.set_unavailable()

        # Local attributes still hold previous values
        assert entity.volume == 50
        assert entity.media_title == "Track"
        # But only UNAVAILABLE state was pushed
        call_args = mock_api.configured_entities.update_attributes.call_args
        _, attributes = call_args[0]
        assert attributes == {
            media_player.Attributes.STATE: media_player.States.UNAVAILABLE
        }


class TestMediaPlayerEntityCoordinator:
    """Test coordinator pattern — sync_state, subscribe_to_device."""

    def _make_device(self):
        """Return a minimal mock device backed by a real AsyncIOEventEmitter."""
        from pyee.asyncio import AsyncIOEventEmitter

        device = MagicMock(spec=BaseDeviceInterface)
        device.events = AsyncIOEventEmitter()
        device.power = True
        device.volume = 42
        device.muted = False
        device.title = "Coordinator Track"
        return device

    @pytest.mark.asyncio
    async def test_sync_state_called_on_push_update(self):
        """subscribe_to_device() wires sync_state() to fire on every push_update()."""
        device = self._make_device()
        api = _make_api()
        sync_calls = []

        class TrackingPlayer(MediaPlayerEntity):
            def __init__(self):
                super().__init__(
                    "media_player.coord",
                    "Coord Player",
                    features=[media_player.Features.ON_OFF],
                    attributes={
                        media_player.Attributes.STATE: media_player.States.UNKNOWN
                    },
                )
                self._device = device
                self.subscribe_to_device(device)

            async def sync_state(self):
                sync_calls.append(True)
                self.set_state(
                    media_player.States.ON
                    if self._device.power
                    else media_player.States.OFF,
                    update=False,
                )

        entity = TrackingPlayer()
        entity._api = api  # noqa: SLF001

        assert len(sync_calls) == 0

        # Simulate what push_update() does: emit UPDATE with no args
        device.events.emit(DeviceEvents.UPDATE)
        await asyncio.sleep(0)  # flush the async handler scheduled by pyee

        assert len(sync_calls) == 1
        assert entity.state == media_player.States.ON

    @pytest.mark.asyncio
    async def test_sync_state_multiple_pushes(self):
        """sync_state() is called once per push_update() emission."""
        device = self._make_device()
        api = _make_api()
        sync_calls = []

        class CountingPlayer(MediaPlayerEntity):
            def __init__(self):
                super().__init__(
                    "media_player.counting",
                    "Counting Player",
                    features=[],
                    attributes={
                        media_player.Attributes.STATE: media_player.States.UNKNOWN
                    },
                )
                self._dev = device
                self.subscribe_to_device(device)

            async def sync_state(self):
                sync_calls.append(self._dev.volume)

        entity = CountingPlayer()
        entity._api = api  # noqa: SLF001

        for vol in [10, 20, 30]:
            device.volume = vol
            device.events.emit(DeviceEvents.UPDATE)
            await asyncio.sleep(0)  # flush handler before changing volume again

        assert sync_calls == [10, 20, 30]

    @pytest.mark.asyncio
    async def test_default_sync_state_is_noop(self):
        """The base MediaPlayerEntity.sync_state() is a no-op coroutine."""
        import inspect

        entity = _make_entity()
        result = entity.sync_state()
        assert inspect.iscoroutine(result)
        await result  # must be awaitable without raising


class TestMediaPlayerEntityInheritance:
    """Test that MediaPlayerEntity can be subclassed and overridden."""

    def test_custom_set_state(self):
        """set_state can be overridden to inject custom logic."""

        class CustomMediaPlayer(MediaPlayerEntity):
            def __init__(self):
                super().__init__(
                    "media_player.custom",
                    "Custom Player",
                    features=[],
                    attributes={},
                )
                self.custom_set_state_called = False

            def set_state(self, value, *, update=False):
                self.custom_set_state_called = True
                super().set_state(value, update=update)

        entity = CustomMediaPlayer()
        entity._api = _make_api()  # noqa: SLF001

        entity.set_state(media_player.States.PLAYING, update=False)
        assert entity.custom_set_state_called is True
        assert entity.state == media_player.States.PLAYING

    def test_custom_property_getter(self):
        """Property getters can be overridden to return computed values."""

        class CustomMediaPlayer(MediaPlayerEntity):
            def __init__(self):
                super().__init__(
                    "media_player.custom",
                    "Custom Player",
                    features=[],
                    attributes={},
                )

            @property
            def state(self):
                return media_player.States.PLAYING

        entity = CustomMediaPlayer()
        assert entity.state == media_player.States.PLAYING

    def test_map_entity_states_default(self):
        """map_entity_states() maps common strings to media_player.States."""
        entity = _make_entity()
        assert entity.map_entity_states("PLAYING") == media_player.States.PLAYING
        assert entity.map_entity_states("PAUSED") == media_player.States.PAUSED
        assert entity.map_entity_states("OFF") == media_player.States.OFF
        assert entity.map_entity_states("ON") == media_player.States.ON
        assert entity.map_entity_states("STANDBY") == media_player.States.STANDBY
        assert entity.map_entity_states("BUFFERING") == media_player.States.BUFFERING
        assert entity.map_entity_states("UNKNOWN_STATE") == media_player.States.UNKNOWN
        assert entity.map_entity_states(None) == media_player.States.UNKNOWN

    def test_map_entity_states_passthrough(self):
        """map_entity_states() passes through existing States enum values unchanged."""
        entity = _make_entity()
        assert (
            entity.map_entity_states(media_player.States.PLAYING)
            == media_player.States.PLAYING
        )
        assert (
            entity.map_entity_states(media_player.States.UNAVAILABLE)
            == media_player.States.UNAVAILABLE
        )

    def test_map_entity_states_override(self):
        """map_entity_states() can be overridden for device-specific state enums."""
        from enum import Enum

        class DeviceState(Enum):
            POWERED_ON = "powered_on"
            POWERED_OFF = "powered_off"

        class CustomPlayer(MediaPlayerEntity):
            def __init__(self):
                super().__init__(
                    "media_player.custom", "Custom", features=[], attributes={}
                )

            def map_entity_states(self, device_state):
                if isinstance(device_state, DeviceState):
                    return (
                        media_player.States.ON
                        if device_state == DeviceState.POWERED_ON
                        else media_player.States.OFF
                    )
                return super().map_entity_states(device_state)

        entity = CustomPlayer()
        assert (
            entity.map_entity_states(DeviceState.POWERED_ON) == media_player.States.ON
        )
        assert (
            entity.map_entity_states(DeviceState.POWERED_OFF) == media_player.States.OFF
        )
        # Falls through to default for unknown types
        assert entity.map_entity_states("PLAYING") == media_player.States.PLAYING

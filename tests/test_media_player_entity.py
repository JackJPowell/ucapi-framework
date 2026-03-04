"""Tests for MediaPlayerEntity with built-in state management."""

import pytest
from unittest.mock import MagicMock
from ucapi import media_player
from ucapi_framework import MediaPlayerEntity


class TestMediaPlayerEntity:
    """Test MediaPlayerEntity state management."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API for testing."""
        api = MagicMock()
        api.configured_entities.get.return_value = MagicMock(
            attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN}
        )
        return api

    @pytest.fixture
    def entity(self, mock_api):
        """Create a MediaPlayerEntity for testing."""
        entity = MediaPlayerEntity(
            "media_player.test",
            "Test Player",
            features=[media_player.Features.ON_OFF, media_player.Features.VOLUME],
            attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN},
        )
        entity._api = mock_api  # noqa: SLF001
        return entity

    def test_initial_state(self, entity):
        """Test initial state from constructor attributes."""
        # State was set to UNKNOWN in constructor
        assert entity.state == media_player.States.UNKNOWN
        # These were not set, so should be None
        assert entity.volume is None
        assert entity.muted is None

    def test_set_state_with_update(self, entity, mock_api):
        """Test set_state() calls entity.update() by default."""
        entity.set_state(media_player.States.PLAYING, update=True)

        # Verify internal state was updated
        assert entity.state == media_player.States.PLAYING

        # Verify update was called
        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "media_player.test"
        assert media_player.Attributes.STATE in attributes
        assert attributes[media_player.Attributes.STATE] == media_player.States.PLAYING

    def test_set_state_without_update(self, entity, mock_api):
        """Test set_state(update=False) does not call entity.update()."""
        entity.set_state(media_player.States.PLAYING, update=False)

        # Verify internal state was updated
        assert entity.state == media_player.States.PLAYING

        # Verify update was NOT called
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_volume(self, entity, mock_api):
        """Test set_volume() updates state and calls update."""
        entity.set_volume(75, update=True)

        assert entity.volume == 75
        assert mock_api.configured_entities.update_attributes.called

    def test_set_muted(self, entity, mock_api):
        """Test set_muted() updates state and calls update."""
        entity.set_muted(True, update=True)

        assert entity.muted is True
        assert mock_api.configured_entities.update_attributes.called

    def test_set_media_title(self, entity, mock_api):
        """Test set_media_title() updates state and calls update."""
        entity.set_media_title("Test Song", update=True)

        assert entity.media_title == "Test Song"
        assert mock_api.configured_entities.update_attributes.called

    def test_set_media_artist(self, entity, mock_api):
        """Test set_media_artist() updates state and calls update."""
        entity.set_media_artist("Test Artist", update=True)

        assert entity.media_artist == "Test Artist"
        assert mock_api.configured_entities.update_attributes.called

    def test_set_source_list(self, entity, mock_api):
        """Test set_source_list() updates state and calls update."""
        sources = ["HDMI 1", "HDMI 2", "Bluetooth"]
        entity.set_source_list(sources, update=True)

        assert entity.source_list == sources
        assert mock_api.configured_entities.update_attributes.called

    def test_set_attributes_bulk_update(self, entity, mock_api):
        """Test set_attributes() updates multiple attributes with single update call."""
        entity.set_attributes(
            state=media_player.States.PLAYING,
            volume=50,
            muted=False,
            media_title="Song Title",
            media_artist="Artist Name",
            update=True,
        )

        # Verify all internal state was updated
        assert entity.state == media_player.States.PLAYING
        assert entity.volume == 50
        assert entity.muted is False
        assert entity.media_title == "Song Title"
        assert entity.media_artist == "Artist Name"

        # Verify update was called only once
        assert mock_api.configured_entities.update_attributes.call_count == 1

        # Verify all attributes were included in the update
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "media_player.test"
        assert len(attributes) == 5
        assert attributes[media_player.Attributes.STATE] == media_player.States.PLAYING
        assert attributes[media_player.Attributes.VOLUME] == 50
        assert attributes[media_player.Attributes.MUTED] is False
        assert attributes[media_player.Attributes.MEDIA_TITLE] == "Song Title"
        assert attributes[media_player.Attributes.MEDIA_ARTIST] == "Artist Name"

    def test_set_attributes_without_update(self, entity, mock_api):
        """Test set_attributes(update=False) does not call entity.update()."""
        entity.set_attributes(
            state=media_player.States.PLAYING, volume=50, update=False
        )

        # Verify internal state was updated
        assert entity.state == media_player.States.PLAYING
        assert entity.volume == 50

        # Verify update was NOT called
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_ignores_none_values(self, entity, mock_api):
        """Test set_attributes() ignores None values."""
        entity.set_attributes(
            state=media_player.States.PLAYING, volume=None, update=True
        )

        # Only state should be in internal storage
        assert entity.state == media_player.States.PLAYING
        assert entity.volume is None

        # Verify only state was included in update
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert len(attributes) == 1
        assert media_player.Attributes.STATE in attributes

    def test_property_getters_are_read_only(self, entity):
        """Test that property getters cannot be set directly."""
        # This should raise AttributeError
        with pytest.raises(AttributeError):
            entity.state = media_player.States.PLAYING  # type: ignore[misc]

    def test_all_media_attributes(self, entity, mock_api):
        """Test setting all media-related attributes."""
        entity.set_attributes(
            state=media_player.States.PLAYING,
            volume=75,
            muted=False,
            media_duration=300,
            media_position=120,
            media_type="music",
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

        # Verify all attributes
        assert entity.state == media_player.States.PLAYING
        assert entity.volume == 75
        assert entity.muted is False
        assert entity.media_duration == 300
        assert entity.media_position == 120
        assert entity.media_type == "music"
        assert entity.media_title == "Test Song"
        assert entity.media_artist == "Test Artist"
        assert entity.media_album == "Test Album"
        assert entity.repeat == media_player.RepeatMode.ALL
        assert entity.shuffle is True
        assert entity.source == "Spotify"
        assert entity.source_list == ["Spotify", "Bluetooth"]
        assert entity.sound_mode == "Stereo"
        assert entity.sound_mode_list == ["Stereo", "Surround"]

        # Verify single update call
        assert mock_api.configured_entities.update_attributes.call_count == 1


class TestMediaPlayerEntityInheritance:
    """Test that MediaPlayerEntity can be subclassed and overridden."""

    def test_custom_set_state(self):
        """Test that set_state can be overridden."""

        class CustomMediaPlayer(MediaPlayerEntity):
            def __init__(self):
                super().__init__(
                    "media_player.custom",
                    "Custom Player",
                    features=[],
                    attributes={},
                )
                self.custom_set_state_called = False

            def set_state(self, value, *, update=True):
                """Override set_state to add custom logic."""
                self.custom_set_state_called = True
                super().set_state(value, update=update)

        entity = CustomMediaPlayer()
        entity._api = MagicMock()  # noqa: SLF001
        entity._api.configured_entities.get.return_value = entity  # noqa: SLF001

        entity.set_state(media_player.States.PLAYING, update=False)
        assert entity.custom_set_state_called is True
        assert entity.state == media_player.States.PLAYING

    def test_custom_property_getter(self):
        """Test that property getters can be overridden."""

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
                """Override state getter to always return PLAYING."""
                return media_player.States.PLAYING

        entity = CustomMediaPlayer()
        # Even if internal state is None, getter returns PLAYING
        assert entity.state == media_player.States.PLAYING

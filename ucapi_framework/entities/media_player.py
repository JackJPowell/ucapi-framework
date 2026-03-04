"""
MediaPlayer entity with built-in state management.

Provides a MediaPlayer entity subclass that manages its own state internally
using property getters and setter methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import media_player
from ucapi_framework.entity import Entity


class MediaPlayerEntity(media_player.MediaPlayer, Entity):
    """
    MediaPlayer entity with built-in state management.

    This class extends the base MediaPlayer entity to provide built-in state tracking
    and management. Instead of requiring devices to track state via get_device_attributes(),
    entities now manage their own state internally.

    **State Management Pattern**:
    - Each attribute has a property getter (e.g., `entity.state`)
    - Each attribute has a setter method (e.g., `entity.set_state(States.PLAYING)`)
    - Setter methods accept an optional `update` parameter to control whether
      `entity.update()` is called automatically (default: True)
    - Properties are still overridable by subclasses for custom behavior

    **Example Usage**:

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
                    ],
                )
                self._device = device

            async def handle_command(self, entity_id, cmd_id, params):
                if cmd_id == media_player.Commands.ON:
                    await self._device.turn_on()
                    # Update state - automatically calls entity.update()
                    self.set_state(media_player.States.ON)

                elif cmd_id == media_player.Commands.VOLUME:
                    await self._device.set_volume(params['volume'])
                    # Update volume without triggering entity.update()
                    self.set_volume(params['volume'], update=False)
                    # Then update state and trigger one update
                    self.set_state(media_player.States.PLAYING)
        ```

    **Benefits**:
    - Natural separation of concerns (entity manages its own state)
    - No need for get_device_attributes() on devices
    - Type-safe state access with IDE autocomplete
    - Explicit control over when updates are sent to Remote
    - Still fully overridable for custom behavior
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize MediaPlayer entity with state tracking.

        Accepts the same parameters as ucapi.media_player.MediaPlayer.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getters (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> media_player.States | None:
        """Get current playback state."""
        return self.attributes.get(media_player.Attributes.STATE)

    @property
    def volume(self) -> int | None:
        """Get current volume level (0-100)."""
        return self.attributes.get(media_player.Attributes.VOLUME)

    @property
    def muted(self) -> bool | None:
        """Get mute status."""
        return self.attributes.get(media_player.Attributes.MUTED)

    @property
    def media_duration(self) -> int | None:
        """Get media duration in seconds."""
        return self.attributes.get(media_player.Attributes.MEDIA_DURATION)

    @property
    def media_position(self) -> int | None:
        """Get current media position in seconds."""
        return self.attributes.get(media_player.Attributes.MEDIA_POSITION)

    @property
    def media_position_updated_at(self) -> str | None:
        """Get timestamp when media position was last updated."""
        return self.attributes.get(media_player.Attributes.MEDIA_POSITION_UPDATED_AT)

    @property
    def media_type(self) -> str | None:
        """Get media type (e.g., 'music', 'video')."""
        return self.attributes.get(media_player.Attributes.MEDIA_TYPE)

    @property
    def media_image_url(self) -> str | None:
        """Get URL of media artwork/thumbnail."""
        return self.attributes.get(media_player.Attributes.MEDIA_IMAGE_URL)

    @property
    def media_title(self) -> str | None:
        """Get media title."""
        return self.attributes.get(media_player.Attributes.MEDIA_TITLE)

    @property
    def media_artist(self) -> str | None:
        """Get media artist name."""
        return self.attributes.get(media_player.Attributes.MEDIA_ARTIST)

    @property
    def media_album(self) -> str | None:
        """Get media album name."""
        return self.attributes.get(media_player.Attributes.MEDIA_ALBUM)

    @property
    def repeat(self) -> media_player.RepeatMode | None:
        """Get repeat mode."""
        return self.attributes.get(media_player.Attributes.REPEAT)

    @property
    def shuffle(self) -> bool | None:
        """Get shuffle status."""
        return self.attributes.get(media_player.Attributes.SHUFFLE)

    @property
    def source(self) -> str | None:
        """Get current input source."""
        return self.attributes.get(media_player.Attributes.SOURCE)

    @property
    def source_list(self) -> list[str] | None:
        """Get list of available input sources."""
        return self.attributes.get(media_player.Attributes.SOURCE_LIST)

    @property
    def sound_mode(self) -> str | None:
        """Get current sound mode."""
        return self.attributes.get(media_player.Attributes.SOUND_MODE)

    @property
    def sound_mode_list(self) -> list[str] | None:
        """Get list of available sound modes."""
        return self.attributes.get(media_player.Attributes.SOUND_MODE_LIST)

    # ========================================================================
    # Setter Methods (with optional auto-update, overridable)
    # ========================================================================

    def set_state(
        self, value: media_player.States | None, *, update: bool = False
    ) -> None:
        """
        Set playback state.

        :param value: New state value
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

    def set_volume(self, value: int | None, *, update: bool = False) -> None:
        """
        Set volume level.

        :param value: Volume level (0-100)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.VOLUME] = value
        if update:
            self.update(self.attributes)

    def set_muted(self, value: bool | None, *, update: bool = False) -> None:
        """
        Set mute status.

        :param value: Mute status
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.MUTED] = value
        if update:
            self.update(self.attributes)

    def set_media_duration(self, value: int | None, *, update: bool = False) -> None:
        """
        Set media duration.

        :param value: Duration in seconds
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.MEDIA_DURATION] = value
        if update:
            self.update(self.attributes)

    def set_media_position(self, value: int | None, *, update: bool = False) -> None:
        """
        Set media position.

        :param value: Position in seconds
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.MEDIA_POSITION] = value
        if update:
            self.update(self.attributes)

    def set_media_position_updated_at(
        self, value: str | None, *, update: bool = False
    ) -> None:
        """
        Set media position update timestamp.

        :param value: Timestamp string
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.MEDIA_POSITION_UPDATED_AT] = value
        if update:
            self.update(self.attributes)

    def set_media_type(self, value: str | None, *, update: bool = False) -> None:
        """
        Set media type.

        :param value: Media type (e.g., 'music', 'video')
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.MEDIA_TYPE] = value
        if update:
            self.update(self.attributes)

    def set_media_image_url(self, value: str | None, *, update: bool = False) -> None:
        """
        Set media artwork URL.

        :param value: URL of media artwork/thumbnail
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.MEDIA_IMAGE_URL] = value
        if update:
            self.update(self.attributes)

    def set_media_title(self, value: str | None, *, update: bool = False) -> None:
        """
        Set media title.

        :param value: Media title
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.MEDIA_TITLE] = value
        if update:
            self.update(self.attributes)

    def set_media_artist(self, value: str | None, *, update: bool = False) -> None:
        """
        Set media artist.

        :param value: Artist name
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.MEDIA_ARTIST] = value
        if update:
            self.update(self.attributes)

    def set_media_album(self, value: str | None, *, update: bool = False) -> None:
        """
        Set media album.

        :param value: Album name
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.MEDIA_ALBUM] = value
        if update:
            self.update(self.attributes)

    def set_repeat(
        self, value: media_player.RepeatMode | None, *, update: bool = False
    ) -> None:
        """
        Set repeat mode.

        :param value: Repeat mode
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.REPEAT] = value
        if update:
            self.update(self.attributes)

    def set_shuffle(self, value: bool | None, *, update: bool = False) -> None:
        """
        Set shuffle status.

        :param value: Shuffle status
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.SHUFFLE] = value
        if update:
            self.update(self.attributes)

    def set_source(self, value: str | None, *, update: bool = False) -> None:
        """
        Set input source.

        :param value: Source name
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.SOURCE] = value
        if update:
            self.update(self.attributes)

    def set_source_list(self, value: list[str] | None, *, update: bool = False) -> None:
        """
        Set available input sources.

        :param value: List of source names
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.SOURCE_LIST] = value
        if update:
            self.update(self.attributes)

    def set_sound_mode(self, value: str | None, *, update: bool = False) -> None:
        """
        Set sound mode.

        :param value: Sound mode name
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.SOUND_MODE] = value
        if update:
            self.update(self.attributes)

    def set_sound_mode_list(
        self, value: list[str] | None, *, update: bool = False
    ) -> None:
        """
        Set available sound modes.

        :param value: List of sound mode names
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[media_player.Attributes.SOUND_MODE_LIST] = value
        if update:
            self.update(self.attributes)

    # ========================================================================
    # Bulk Update Helper
    # ========================================================================

    def set_attributes(
        self,
        *,
        state: media_player.States | None = None,
        volume: int | None = None,
        muted: bool | None = None,
        media_duration: int | None = None,
        media_position: int | None = None,
        media_position_updated_at: str | None = None,
        media_type: str | None = None,
        media_image_url: str | None = None,
        media_title: str | None = None,
        media_artist: str | None = None,
        media_album: str | None = None,
        repeat: media_player.RepeatMode | None = None,
        shuffle: bool | None = None,
        source: str | None = None,
        source_list: list[str] | None = None,
        sound_mode: str | None = None,
        sound_mode_list: list[str] | None = None,
        update: bool = False,
    ) -> None:
        """
        Update multiple attributes at once.

        This is more efficient than calling individual setters when updating
        multiple attributes, as it only triggers one entity.update() call.

        **Example**:
            ```python
            # Update multiple attributes efficiently
            entity.set_attributes(
                state=media_player.States.PLAYING,
                volume=50,
                media_title="Song Title",
                media_artist="Artist Name",
                update=True  # Single update call for all changes
            )
            ```

        :param state: Playback state
        :param volume: Volume level (0-100)
        :param muted: Mute status
        :param media_duration: Media duration in seconds
        :param media_position: Media position in seconds
        :param media_position_updated_at: Position update timestamp
        :param media_type: Media type
        :param media_image_url: Media artwork URL
        :param media_title: Media title
        :param media_artist: Media artist
        :param media_album: Media album
        :param repeat: Repeat mode
        :param shuffle: Shuffle status
        :param source: Input source
        :param source_list: Available input sources
        :param sound_mode: Sound mode
        :param sound_mode_list: Available sound modes
        :param update: If True, call entity.update() once after setting all attributes (default: True)
        """
        # Update attributes dict with non-None values
        if state is not None:
            self.attributes[media_player.Attributes.STATE] = state

        if volume is not None:
            self.attributes[media_player.Attributes.VOLUME] = volume

        if muted is not None:
            self.attributes[media_player.Attributes.MUTED] = muted

        if media_duration is not None:
            self.attributes[media_player.Attributes.MEDIA_DURATION] = media_duration

        if media_position is not None:
            self.attributes[media_player.Attributes.MEDIA_POSITION] = media_position

        if media_position_updated_at is not None:
            self.attributes[media_player.Attributes.MEDIA_POSITION_UPDATED_AT] = (
                media_position_updated_at
            )

        if media_type is not None:
            self.attributes[media_player.Attributes.MEDIA_TYPE] = media_type

        if media_image_url is not None:
            self.attributes[media_player.Attributes.MEDIA_IMAGE_URL] = media_image_url

        if media_title is not None:
            self.attributes[media_player.Attributes.MEDIA_TITLE] = media_title

        if media_artist is not None:
            self.attributes[media_player.Attributes.MEDIA_ARTIST] = media_artist

        if media_album is not None:
            self.attributes[media_player.Attributes.MEDIA_ALBUM] = media_album

        if repeat is not None:
            self.attributes[media_player.Attributes.REPEAT] = repeat

        if shuffle is not None:
            self.attributes[media_player.Attributes.SHUFFLE] = shuffle

        if source is not None:
            self.attributes[media_player.Attributes.SOURCE] = source

        if source_list is not None:
            self.attributes[media_player.Attributes.SOURCE_LIST] = source_list

        if sound_mode is not None:
            self.attributes[media_player.Attributes.SOUND_MODE] = sound_mode

        if sound_mode_list is not None:
            self.attributes[media_player.Attributes.SOUND_MODE_LIST] = sound_mode_list

        # Trigger update if requested
        if update:
            self.update(self.attributes)

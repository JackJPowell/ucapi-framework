"""
Cover entity with built-in state management.

Provides a Cover entity subclass that manages its own state internally
using property getters and setter methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import cover
from ucapi_framework.entity import Entity


class CoverEntity(cover.Cover, Entity):
    """
    Cover entity with built-in state management.

    This class extends the base Cover entity to provide built-in state tracking
    and management. State is stored directly in the existing ``self.attributes``
    dict that all ucapi entities have.

    **State Management Pattern**:
    - Each attribute has a property getter (e.g., ``entity.state``)
    - Each attribute has a setter method (e.g., ``entity.set_state(States.OPEN)``)
    - Setter methods accept an optional ``update`` parameter to control whether
      ``entity.update()`` is called automatically (default: True)
    - Properties are still overridable by subclasses for custom behavior

    **Example Usage**:

        ```python
        from ucapi import cover
        from ucapi_framework.entities import CoverEntity

        class MyBlind(CoverEntity):
            def __init__(self, device_config, device):
                entity_id = f"cover.{device_config.id}"
                super().__init__(
                    entity_id,
                    device_config.name,
                    features=[
                        cover.Features.OPEN,
                        cover.Features.CLOSE,
                        cover.Features.POSITION,
                    ],
                    attributes={
                        cover.Attributes.STATE: cover.States.CLOSED,
                        cover.Attributes.POSITION: 0,
                    },
                )
                self._device = device

            async def handle_command(self, entity_id, cmd_id, params):
                if cmd_id == cover.Commands.OPEN:
                    await self._device.open()
                    self.set_state(cover.States.OPENING)

                elif cmd_id == cover.Commands.SET_POSITION:
                    await self._device.set_position(params['position'])
                    self.set_position(params['position'])
        ```
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize Cover entity with state tracking.

        Accepts the same parameters as ucapi.cover.Cover.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getters (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> cover.States | None:
        """Get current cover state (OPEN, CLOSED, OPENING, CLOSING, etc.)."""
        return self.attributes.get(cover.Attributes.STATE)

    @property
    def position(self) -> int | None:
        """Get current position (0=closed, 100=fully open)."""
        return self.attributes.get(cover.Attributes.POSITION)

    @property
    def tilt_position(self) -> int | None:
        """Get current tilt position (0=closed, 100=fully open)."""
        return self.attributes.get(cover.Attributes.TILT_POSITION)

    # ========================================================================
    # Setter Methods (with optional auto-update, overridable)
    # ========================================================================

    def set_state(self, value: cover.States | None, *, update: bool = False) -> None:
        """
        Set cover state.

        :param value: New state value
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[cover.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

    def set_position(self, value: int | None, *, update: bool = False) -> None:
        """
        Set cover position.

        :param value: Position (0=closed, 100=fully open)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[cover.Attributes.POSITION] = value
        if update:
            self.update(self.attributes)

    def set_tilt_position(self, value: int | None, *, update: bool = False) -> None:
        """
        Set cover tilt position.

        :param value: Tilt position (0=closed, 100=fully open)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[cover.Attributes.TILT_POSITION] = value
        if update:
            self.update(self.attributes)

    # ========================================================================
    # Bulk Update Helper
    # ========================================================================

    def set_attributes(
        self,
        *,
        state: cover.States | None = None,
        position: int | None = None,
        tilt_position: int | None = None,
        update: bool = False,
    ) -> None:
        """
        Update multiple attributes at once with a single Remote update call.

        Only non-``None`` arguments are written into ``self.attributes``.

        :param state: Cover state
        :param position: Position (0=closed, 100=fully open)
        :param tilt_position: Tilt position (0=closed, 100=fully open)
        :param update: If True, call entity.update() once after all changes (default: True)
        """
        if state is not None:
            self.attributes[cover.Attributes.STATE] = state
        if position is not None:
            self.attributes[cover.Attributes.POSITION] = position
        if tilt_position is not None:
            self.attributes[cover.Attributes.TILT_POSITION] = tilt_position

        if update:
            self.update(self.attributes)

"""
Button entity with built-in state management.

Provides a Button entity subclass that manages its own state internally
using a property getter and setter method.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import button
from ucapi_framework.entity import Entity


class ButtonEntity(button.Button, Entity):
    """
    Button entity with built-in state management.

    This class extends the base Button entity to provide built-in state tracking
    and management. State is stored directly in the existing ``self.attributes``
    dict that all ucapi entities have.

    A Button entity has a single attribute: STATE (AVAILABLE or UNAVAILABLE).

    **State Management Pattern**:
    - A property getter provides read access (e.g., ``entity.state``)
    - A setter method handles updates (e.g., ``entity.set_state(States.AVAILABLE)``)
    - The setter accepts an optional ``update`` parameter to control whether
      ``entity.update()`` is called automatically (default: True)
    - The property is overridable by subclasses for custom behavior

    **Example Usage**:

        ```python
        from ucapi import button
        from ucapi_framework.entities import ButtonEntity

        class MyButton(ButtonEntity):
            def __init__(self, device_config, device):
                entity_id = f"button.{device_config.id}"
                super().__init__(
                    entity_id,
                    device_config.name,
                    features=[button.Features.PRESS],
                    attributes={button.Attributes.STATE: button.States.AVAILABLE},
                )
                self._device = device

            async def handle_command(self, entity_id, cmd_id, params):
                if cmd_id == button.Commands.PUSH:
                    await self._device.press()
                    # State stays AVAILABLE after a press
        ```
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize Button entity with state tracking.

        Accepts the same parameters as ucapi.button.Button:
        ``identifier``, ``name``, optional ``area``, optional ``cmd_handler``.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getter (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> button.States | None:
        """Get current availability state (AVAILABLE or UNAVAILABLE)."""
        return self.attributes.get(button.Attributes.STATE)

    # ========================================================================
    # Setter Method (with optional auto-update, overridable)
    # ========================================================================

    def set_state(self, value: button.States | None, *, update: bool = False) -> None:
        """
        Set availability state.

        :param value: New state value (AVAILABLE or UNAVAILABLE)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[button.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

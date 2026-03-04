"""
Switch entity with built-in state management.

Provides a Switch entity subclass that manages its own state internally
using property getters and setter methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import switch
from ucapi_framework.entity import Entity


class SwitchEntity(switch.Switch, Entity):
    """
    Switch entity with built-in state management.

    This class extends the base Switch entity to provide built-in state tracking
    and management. State is stored directly in the existing ``self.attributes``
    dict that all ucapi entities have.

    **State Management Pattern**:
    - The state attribute has a property getter (e.g., ``entity.state``)
    - The state attribute has a setter method (e.g., ``entity.set_state(States.ON)``)
    - Setter methods accept an optional ``update`` parameter to control whether
      ``entity.update()`` is called automatically (default: True)
    - Properties are still overridable by subclasses for custom behavior

    **Example Usage**:

        ```python
        from ucapi import switch
        from ucapi_framework.entities import SwitchEntity

        class MySwitch(SwitchEntity):
            def __init__(self, device_config, device):
                entity_id = f"switch.{device_config.id}"
                super().__init__(
                    entity_id,
                    device_config.name,
                    features=[
                        switch.Features.ON_OFF,
                        switch.Features.TOGGLE,
                    ],
                    attributes={
                        switch.Attributes.STATE: switch.States.OFF,
                    },
                    device_class=switch.DeviceClasses.SWITCH,
                )
                self._device = device

            async def handle_command(self, entity_id, cmd_id, params):
                if cmd_id == switch.Commands.ON:
                    await self._device.turn_on()
                    self.set_state(switch.States.ON)
                elif cmd_id == switch.Commands.OFF:
                    await self._device.turn_off()
                    self.set_state(switch.States.OFF)
                elif cmd_id == switch.Commands.TOGGLE:
                    await self._device.toggle()
                    new_state = switch.States.OFF if self.state == switch.States.ON else switch.States.ON
                    self.set_state(new_state)
        ```
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize Switch entity with state tracking.

        Accepts the same parameters as ucapi.switch.Switch.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getters (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> switch.States | None:
        """Get current on/off state."""
        return self.attributes.get(switch.Attributes.STATE)

    # ========================================================================
    # Setter Methods (with optional auto-update, overridable)
    # ========================================================================

    def set_state(self, value: switch.States | None, *, update: bool = False) -> None:
        """
        Set on/off state.

        :param value: New state value (ON, OFF, UNAVAILABLE, UNKNOWN)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[switch.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

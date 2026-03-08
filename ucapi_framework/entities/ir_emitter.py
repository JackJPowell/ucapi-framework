"""
IR Emitter entity with built-in state management.

Provides an IREmitter entity subclass that manages its own state internally
using property getters and setter methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import ir_emitter
from ucapi_framework.entity import Entity


class IREmitterEntity(ir_emitter.IREmitter, Entity):
    """
    IR Emitter entity with built-in state management.

    This class extends the base IREmitter entity to provide built-in state tracking
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
        from ucapi import ir_emitter
        from ucapi_framework.entities import IREmitterEntity

        class MyIRBlaster(IREmitterEntity):
            def __init__(self, device_config, device):
                entity_id = f"ir_emitter.{device_config.id}"
                super().__init__(
                    entity_id,
                    device_config.name,
                    features=[ir_emitter.Features.SEND_IR],
                    attributes={
                        ir_emitter.Attributes.STATE: ir_emitter.States.ON,
                    },
                )
                self._device = device

            async def handle_command(self, entity_id, cmd_id, params):
                if cmd_id == ir_emitter.Commands.SEND_IR:
                    await self._device.send_ir(params)
        ```
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize IREmitter entity with state tracking.

        Accepts the same parameters as ucapi.ir_emitter.IREmitter.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getters (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> ir_emitter.States | None:
        """Get current on/off state."""
        return self.attributes.get(ir_emitter.Attributes.STATE)

    # ========================================================================
    # Setter Methods (with optional auto-update, overridable)
    # ========================================================================

    def set_state(
        self, value: ir_emitter.States | None, *, update: bool = False
    ) -> None:
        """
        Set on/off state.

        :param value: New state value (ON, UNAVAILABLE, UNKNOWN)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[ir_emitter.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

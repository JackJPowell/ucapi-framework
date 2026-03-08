"""
Voice Assistant entity with built-in state management.

Provides a VoiceAssistant entity subclass that manages its own state internally
using property getters and setter methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import voice_assistant
from ucapi_framework.entity import Entity


class VoiceAssistantEntity(voice_assistant.VoiceAssistant, Entity):
    """
    Voice Assistant entity with built-in state management.

    This class extends the base VoiceAssistant entity to provide built-in state
    tracking and management. State is stored directly in the existing
    ``self.attributes`` dict that all ucapi entities have.

    **State Management Pattern**:
    - The state attribute has a property getter (e.g., ``entity.state``)
    - The state attribute has a setter method (e.g., ``entity.set_state(States.ON)``)
    - Setter methods accept an optional ``update`` parameter to control whether
      ``entity.update()`` is called automatically (default: True)
    - Properties are still overridable by subclasses for custom behavior

    **Example Usage**:

        ```python
        from ucapi import voice_assistant
        from ucapi_framework.entities import VoiceAssistantEntity

        class MyVoiceAssistant(VoiceAssistantEntity):
            def __init__(self, device_config, device):
                entity_id = f"voice_assistant.{device_config.id}"
                super().__init__(
                    entity_id,
                    device_config.name,
                    features=[
                        voice_assistant.Features.TRANSCRIPTION,
                        voice_assistant.Features.RESPONSE_TEXT,
                    ],
                    attributes={
                        voice_assistant.Attributes.STATE: voice_assistant.States.OFF,
                    },
                )
                self._device = device

            async def handle_command(self, entity_id, cmd_id, params):
                if cmd_id == voice_assistant.Commands.VOICE_START:
                    await self._device.start_listening()
                    self.set_state(voice_assistant.States.ON)
        ```
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize VoiceAssistant entity with state tracking.

        Accepts the same parameters as ucapi.voice_assistant.VoiceAssistant.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getters (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> voice_assistant.States | None:
        """Get current on/off state."""
        return self.attributes.get(voice_assistant.Attributes.STATE)

    # ========================================================================
    # Setter Methods (with optional auto-update, overridable)
    # ========================================================================

    def set_state(
        self, value: voice_assistant.States | None, *, update: bool = False
    ) -> None:
        """
        Set on/off state.

        :param value: New state value (ON, OFF, UNAVAILABLE, UNKNOWN)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[voice_assistant.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

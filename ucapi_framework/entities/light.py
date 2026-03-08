"""
Light entity with built-in state management.

Provides a Light entity subclass that manages its own state internally
using property getters and setter methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import light
from ucapi_framework.entity import Entity


class LightEntity(light.Light, Entity):
    """
    Light entity with built-in state management.

    This class extends the base Light entity to provide built-in state tracking
    and management. State is stored directly in the existing ``self.attributes``
    dict that all ucapi entities have.

    **State Management Pattern**:
    - Each attribute has a property getter (e.g., ``entity.state``)
    - Each attribute has a setter method (e.g., ``entity.set_state(States.ON)``)
    - Setter methods accept an optional ``update`` parameter to control whether
      ``entity.update()`` is called automatically (default: True)
    - Properties are still overridable by subclasses for custom behavior

    **Example Usage**:

        ```python
        from ucapi import light
        from ucapi_framework.entities import LightEntity

        class MyLight(LightEntity):
            def __init__(self, device_config, device):
                entity_id = f"light.{device_config.id}"
                super().__init__(
                    entity_id,
                    device_config.name,
                    features=[
                        light.Features.ON_OFF,
                        light.Features.DIM,
                        light.Features.COLOR_TEMPERATURE,
                    ],
                    attributes={
                        light.Attributes.STATE: light.States.OFF,
                        light.Attributes.BRIGHTNESS: 0,
                    },
                )
                self._device = device

            async def handle_command(self, entity_id, cmd_id, params):
                if cmd_id == light.Commands.ON:
                    await self._device.turn_on()
                    self.set_state(light.States.ON)

                elif cmd_id == light.Commands.SET_BRIGHTNESS:
                    await self._device.set_brightness(params['brightness'])
                    self.set_brightness(params['brightness'])
        ```
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize Light entity with state tracking.

        Accepts the same parameters as ucapi.light.Light.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getters (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> light.States | None:
        """Get current on/off state."""
        return self.attributes.get(light.Attributes.STATE)

    @property
    def hue(self) -> int | None:
        """Get current hue value (0-360)."""
        return self.attributes.get(light.Attributes.HUE)

    @property
    def saturation(self) -> int | None:
        """Get current saturation value (0-100)."""
        return self.attributes.get(light.Attributes.SATURATION)

    @property
    def brightness(self) -> int | None:
        """Get current brightness value (0-100)."""
        return self.attributes.get(light.Attributes.BRIGHTNESS)

    @property
    def color_temperature(self) -> int | None:
        """Get current color temperature in Kelvin."""
        return self.attributes.get(light.Attributes.COLOR_TEMPERATURE)

    # ========================================================================
    # Setter Methods (with optional auto-update, overridable)
    # ========================================================================

    def set_state(self, value: light.States | None, *, update: bool = False) -> None:
        """
        Set on/off state.

        :param value: New state value
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[light.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

    def set_hue(self, value: int | None, *, update: bool = False) -> None:
        """
        Set hue value.

        :param value: Hue (0-360)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[light.Attributes.HUE] = value
        if update:
            self.update(self.attributes)

    def set_saturation(self, value: int | None, *, update: bool = False) -> None:
        """
        Set saturation value.

        :param value: Saturation (0-100)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[light.Attributes.SATURATION] = value
        if update:
            self.update(self.attributes)

    def set_brightness(self, value: int | None, *, update: bool = False) -> None:
        """
        Set brightness value.

        :param value: Brightness (0-100)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[light.Attributes.BRIGHTNESS] = value
        if update:
            self.update(self.attributes)

    def set_color_temperature(self, value: int | None, *, update: bool = False) -> None:
        """
        Set color temperature.

        :param value: Color temperature in Kelvin
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[light.Attributes.COLOR_TEMPERATURE] = value
        if update:
            self.update(self.attributes)

    # ========================================================================
    # Bulk Update Helper
    # ========================================================================

    def set_attributes(
        self,
        *,
        state: light.States | None = None,
        hue: int | None = None,
        saturation: int | None = None,
        brightness: int | None = None,
        color_temperature: int | None = None,
        update: bool = False,
    ) -> None:
        """
        Update multiple attributes at once with a single Remote update call.

        Only non-``None`` arguments are written into ``self.attributes``.

        :param state: On/off state
        :param hue: Hue (0-360)
        :param saturation: Saturation (0-100)
        :param brightness: Brightness (0-100)
        :param color_temperature: Color temperature in Kelvin
        :param update: If True, call entity.update() once after all changes (default: True)
        """
        if state is not None:
            self.attributes[light.Attributes.STATE] = state
        if hue is not None:
            self.attributes[light.Attributes.HUE] = hue
        if saturation is not None:
            self.attributes[light.Attributes.SATURATION] = saturation
        if brightness is not None:
            self.attributes[light.Attributes.BRIGHTNESS] = brightness
        if color_temperature is not None:
            self.attributes[light.Attributes.COLOR_TEMPERATURE] = color_temperature

        if update:
            self.update(self.attributes)

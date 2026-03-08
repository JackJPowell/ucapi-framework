"""
Climate entity with built-in state management.

Provides a Climate entity subclass that manages its own state internally
using property getters and setter methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import climate
from ucapi_framework.entity import Entity


class ClimateEntity(climate.Climate, Entity):
    """
    Climate entity with built-in state management.

    This class extends the base Climate entity to provide built-in state tracking
    and management. State is stored directly in the existing ``self.attributes``
    dict that all ucapi entities have.

    **State Management Pattern**:
    - Each attribute has a property getter (e.g., ``entity.state``)
    - Each attribute has a setter method (e.g., ``entity.set_state(States.HEAT)``)
    - Setter methods accept an optional ``update`` parameter to control whether
      ``entity.update()`` is called automatically (default: True)
    - Properties are still overridable by subclasses for custom behavior

    **Example Usage**:

        ```python
        from ucapi import climate
        from ucapi_framework.entities import ClimateEntity

        class MyThermostat(ClimateEntity):
            def __init__(self, device_config, device):
                entity_id = f"climate.{device_config.id}"
                super().__init__(
                    entity_id,
                    device_config.name,
                    features=[
                        climate.Features.ON_OFF,
                        climate.Features.HEAT,
                        climate.Features.CURRENT_TEMPERATURE,
                        climate.Features.TARGET_TEMPERATURE,
                    ],
                    attributes={
                        climate.Attributes.STATE: climate.States.OFF,
                        climate.Attributes.CURRENT_TEMPERATURE: 20.0,
                        climate.Attributes.TARGET_TEMPERATURE: 21.0,
                    },
                )
                self._device = device

            async def handle_command(self, entity_id, cmd_id, params):
                if cmd_id == climate.Commands.ON:
                    await self._device.turn_on()
                    self.set_state(climate.States.HEAT)
                elif cmd_id == climate.Commands.TARGET_TEMPERATURE:
                    await self._device.set_temperature(params["temperature"])
                    self.set_target_temperature(params["temperature"])
        ```
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize Climate entity with state tracking.

        Accepts the same parameters as ucapi.climate.Climate.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getters (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> climate.States | None:
        """Get current climate state (OFF, HEAT, COOL, HEAT_COOL, FAN, AUTO)."""
        return self.attributes.get(climate.Attributes.STATE)

    @property
    def current_temperature(self) -> float | None:
        """Get current measured temperature."""
        return self.attributes.get(climate.Attributes.CURRENT_TEMPERATURE)

    @property
    def target_temperature(self) -> float | None:
        """Get target temperature."""
        return self.attributes.get(climate.Attributes.TARGET_TEMPERATURE)

    @property
    def target_temperature_high(self) -> float | None:
        """Get upper bound of target temperature range."""
        return self.attributes.get(climate.Attributes.TARGET_TEMPERATURE_HIGH)

    @property
    def target_temperature_low(self) -> float | None:
        """Get lower bound of target temperature range."""
        return self.attributes.get(climate.Attributes.TARGET_TEMPERATURE_LOW)

    @property
    def fan_mode(self) -> str | None:
        """Get current fan mode."""
        return self.attributes.get(climate.Attributes.FAN_MODE)

    # ========================================================================
    # Setter Methods (with optional auto-update, overridable)
    # ========================================================================

    def set_state(self, value: climate.States | None, *, update: bool = False) -> None:
        """
        Set climate state.

        :param value: New state value (OFF, HEAT, COOL, HEAT_COOL, FAN, AUTO)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[climate.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

    def set_current_temperature(
        self, value: float | None, *, update: bool = False
    ) -> None:
        """
        Set current measured temperature.

        :param value: Current temperature value
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[climate.Attributes.CURRENT_TEMPERATURE] = value
        if update:
            self.update(self.attributes)

    def set_target_temperature(
        self, value: float | None, *, update: bool = False
    ) -> None:
        """
        Set target temperature.

        :param value: Target temperature value
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[climate.Attributes.TARGET_TEMPERATURE] = value
        if update:
            self.update(self.attributes)

    def set_target_temperature_high(
        self, value: float | None, *, update: bool = False
    ) -> None:
        """
        Set upper bound of target temperature range.

        :param value: High target temperature value
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[climate.Attributes.TARGET_TEMPERATURE_HIGH] = value
        if update:
            self.update(self.attributes)

    def set_target_temperature_low(
        self, value: float | None, *, update: bool = False
    ) -> None:
        """
        Set lower bound of target temperature range.

        :param value: Low target temperature value
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[climate.Attributes.TARGET_TEMPERATURE_LOW] = value
        if update:
            self.update(self.attributes)

    def set_fan_mode(self, value: str | None, *, update: bool = False) -> None:
        """
        Set fan mode.

        :param value: Fan mode string
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[climate.Attributes.FAN_MODE] = value
        if update:
            self.update(self.attributes)

    # ========================================================================
    # Bulk Update Helper
    # ========================================================================

    def set_attributes(
        self,
        *,
        state: climate.States | None = None,
        current_temperature: float | None = None,
        target_temperature: float | None = None,
        target_temperature_high: float | None = None,
        target_temperature_low: float | None = None,
        fan_mode: str | None = None,
        update: bool = False,
    ) -> None:
        """
        Update multiple attributes at once with a single Remote update call.

        Only non-``None`` arguments are written into ``self.attributes``.

        :param state: Climate state
        :param current_temperature: Current measured temperature
        :param target_temperature: Target temperature
        :param target_temperature_high: Upper bound of target temperature range
        :param target_temperature_low: Lower bound of target temperature range
        :param fan_mode: Fan mode string
        :param update: If True, call entity.update() once after all changes (default: True)
        """
        if state is not None:
            self.attributes[climate.Attributes.STATE] = state
        if current_temperature is not None:
            self.attributes[climate.Attributes.CURRENT_TEMPERATURE] = (
                current_temperature
            )
        if target_temperature is not None:
            self.attributes[climate.Attributes.TARGET_TEMPERATURE] = target_temperature
        if target_temperature_high is not None:
            self.attributes[climate.Attributes.TARGET_TEMPERATURE_HIGH] = (
                target_temperature_high
            )
        if target_temperature_low is not None:
            self.attributes[climate.Attributes.TARGET_TEMPERATURE_LOW] = (
                target_temperature_low
            )
        if fan_mode is not None:
            self.attributes[climate.Attributes.FAN_MODE] = fan_mode

        if update:
            self.update(self.attributes)

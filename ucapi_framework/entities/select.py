"""
Select entity with built-in state management.

Provides a Select entity subclass that manages its own state internally
using property getters and setter methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import select
from ucapi_framework.entity import Entity


class SelectEntity(select.Select, Entity):
    """
    Select entity with built-in state management.

    This class extends the base Select entity to provide built-in state tracking
    and management. State is stored directly in the existing ``self.attributes``
    dict that all ucapi entities have.

    **State Management Pattern**:
    - Each attribute has a property getter (e.g., ``entity.current_option``)
    - Each attribute has a setter method (e.g., ``entity.set_current_option("Mode A")``)
    - Setter methods accept an optional ``update`` parameter to control whether
      ``entity.update()`` is called automatically (default: True)
    - Properties are still overridable by subclasses for custom behavior

    Note: ``select.Select.__init__`` does not accept ``features`` — ucapi handles
    that internally. Pass only ``identifier``, ``name``, ``attributes``, and
    optional ``area`` / ``cmd_handler``.

    **Example Usage**:

        ```python
        from ucapi import select
        from ucapi_framework.entities import SelectEntity

        class MyInputSelect(SelectEntity):
            def __init__(self, device_config, device):
                entity_id = f"select.{device_config.id}"
                super().__init__(
                    entity_id,
                    device_config.name,
                    attributes={
                        select.Attributes.STATE: select.States.ON,
                        select.Attributes.CURRENT_OPTION: "HDMI 1",
                        select.Attributes.OPTIONS: ["HDMI 1", "HDMI 2", "HDMI 3"],
                    },
                )
                self._device = device

            async def handle_command(self, entity_id, cmd_id, params):
                if cmd_id == select.Commands.SELECT_OPTION:
                    await self._device.select_input(params["option"])
                    self.set_current_option(params["option"])
        ```
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize Select entity with state tracking.

        Accepts the same parameters as ucapi.select.Select.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getters (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> select.States | None:
        """Get current state (ON, UNAVAILABLE, UNKNOWN)."""
        return self.attributes.get(select.Attributes.STATE)

    @property
    def current_option(self) -> str | None:
        """Get the currently selected option."""
        return self.attributes.get(select.Attributes.CURRENT_OPTION)

    @property
    def options(self) -> list[str] | None:
        """Get the list of available options."""
        return self.attributes.get(select.Attributes.OPTIONS)

    @options.setter
    def options(self, _value: object) -> None:
        """
        Discard the entity-level ``options`` assignment from ucapi's Entity.__init__
        (which stores config/options dicts, not the select options list).
        The select options list is managed via ``self.attributes`` and ``set_options()``.
        """

    # ========================================================================
    # Setter Methods (with optional auto-update, overridable)
    # ========================================================================

    def set_state(self, value: select.States | None, *, update: bool = False) -> None:
        """
        Set entity state.

        :param value: New state value (ON, UNAVAILABLE, UNKNOWN)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[select.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

    def set_current_option(self, value: str | None, *, update: bool = False) -> None:
        """
        Set the currently selected option.

        :param value: Option string
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[select.Attributes.CURRENT_OPTION] = value
        if update:
            self.update(self.attributes)

    def set_options(self, value: list[str] | None, *, update: bool = False) -> None:
        """
        Set the list of available options.

        :param value: List of option strings
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[select.Attributes.OPTIONS] = value
        if update:
            self.update(self.attributes)

    # ========================================================================
    # Bulk Update Helper
    # ========================================================================

    def set_attributes(
        self,
        *,
        state: select.States | None = None,
        current_option: str | None = None,
        options: list[str] | None = None,
        update: bool = False,
    ) -> None:
        """
        Update multiple attributes at once with a single Remote update call.

        Only non-``None`` arguments are written into ``self.attributes``.

        :param state: Entity state
        :param current_option: Currently selected option
        :param options: List of available options
        :param update: If True, call entity.update() once after all changes (default: True)
        """
        if state is not None:
            self.attributes[select.Attributes.STATE] = state
        if current_option is not None:
            self.attributes[select.Attributes.CURRENT_OPTION] = current_option
        if options is not None:
            self.attributes[select.Attributes.OPTIONS] = options

        if update:
            self.update(self.attributes)

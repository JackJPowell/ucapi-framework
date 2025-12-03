"""
Base setup flow for Unfolded Circle Remote integrations.

Provides reusable setup flow logic for device configuration.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Generic, TypeVar

from ucapi import (
    AbortDriverSetup,
    DriverSetupRequest,
    IntegrationSetupError,
    RequestUserInput,
    SetupAction,
    SetupComplete,
    SetupDriver,
    SetupError,
    UserDataResponse,
)

from ucapi_framework.driver import BaseIntegrationDriver

from .discovery import DiscoveredDevice, BaseDiscovery
from .config import BaseConfigManager

_LOG = logging.getLogger(__name__)

# Type variable for device configuration
ConfigT = TypeVar("ConfigT")


class SetupSteps(IntEnum):
    """Enumeration of setup steps to keep track of user data responses."""

    INIT = 0
    CONFIGURATION_MODE = 1
    RESTORE_PROMPT = 2
    PRE_DISCOVERY = 3
    DISCOVER = 4
    DEVICE_CHOICE = 5
    MANUAL_ENTRY = 6
    BACKUP = 7
    RESTORE = 8


class BaseSetupFlow(ABC, Generic[ConfigT]):
    """
    Base class for integration setup flows.

    Handles common patterns:
    - Configuration mode (add/update/remove/reset)
    - Device discovery with manual fallback
    - Device creation and validation
    - State machine management

    Type Parameters:
        ConfigT: The device configuration class
    """

    def __init__(
        self,
        config_manager: BaseConfigManager,
        *,
        discovery: BaseDiscovery | None = None,
    ):
        """
        Initialize the setup flow.

        Child classes typically don't need to override __init__ - the discovery
        instance is set automatically by create_handler().

        :param config_manager: Device configuration manager instance
        :param discovery: Discovery instance for auto-discovery.
                         Pass None if the device does not support discovery.
                         This is typically instantiated in your driver's main() and
                         passed via create_handler().
        """
        self.config = config_manager
        self.discovery = discovery
        self._setup_step = SetupSteps.INIT
        self._add_mode = False
        self._pending_device_config: ConfigT | None = None  # For multi-screen flows
        self._pre_discovery_data: dict[
            str, Any
        ] = {}  # Store data from pre-discovery screens

    @classmethod
    def create_handler(
        cls, driver: BaseIntegrationDriver, discovery: BaseDiscovery | None = None
    ):
        """
        Create a setup handler function with the given configuration.

        This is a convenience factory method that creates a closure containing
        the setup flow instance, suitable for passing to IntegrationAPI.init().

        Example usage in driver's main():
            discovery = MyDiscovery(api_key="...", timeout=30)
            setup_handler = MySetupFlow.create_handler(driver, discovery=discovery)
            api.init("driver-name", setup_handler=setup_handler)

        :param driver: The driver instance. The config_manager will be
                      retrieved from driver.config_manager.
        :param discovery: Optional initialized discovery instance for auto-discovery.
                         Pass None if the device does not support discovery.
        :return: Async function that handles SetupDriver messages
        """
        setup_flow = None

        async def driver_setup_handler(msg: SetupDriver):
            """Handle driver setup requests."""
            nonlocal setup_flow

            if setup_flow is None:
                if driver.config_manager is None:
                    raise ValueError(
                        "Driver's config_manager must be set before creating setup handler"
                    )
                _LOG.info("Creating new %s instance", cls.__name__)
                setup_flow = cls(driver.config_manager, discovery=discovery)

            return await setup_flow.handle_driver_setup(msg)

        return driver_setup_handler

    async def handle_driver_setup(self, msg: SetupDriver) -> SetupAction:
        """
        Main dispatcher for setup requests.

        :param msg: Setup driver request object
        :return: Setup action on how to continue
        """
        if isinstance(msg, DriverSetupRequest):
            self._setup_step = SetupSteps.INIT
            self._add_mode = False
            return await self._handle_driver_setup_request(msg)

        if isinstance(msg, UserDataResponse):
            _LOG.debug("User data response: %s", msg)
            return await self._handle_user_data_response(msg)

        if isinstance(msg, AbortDriverSetup):
            _LOG.info("Setup was aborted with code: %s", msg.error)
            self._setup_step = SetupSteps.INIT

        return SetupError()

    async def _handle_driver_setup_request(
        self, msg: DriverSetupRequest
    ) -> RequestUserInput | SetupError:
        """
        Handle initial setup request.

        :param msg: Driver setup request
        :return: Setup action
        """
        reconfigure = msg.reconfigure
        _LOG.debug("Starting driver setup, reconfigure=%s", reconfigure)

        if reconfigure:
            self._setup_step = SetupSteps.CONFIGURATION_MODE
            return await self._build_configuration_mode_screen()

        # Initial setup - clear configuration and ask about restore
        self.config.clear()
        self._pre_discovery_data = {}

        # Ask if user wants to restore from backup
        self._setup_step = SetupSteps.RESTORE_PROMPT
        return await self._build_restore_prompt_screen()

    async def _handle_user_data_response(self, msg: UserDataResponse) -> SetupAction:
        """
        Route user data responses to appropriate handlers.

        :param msg: User data response
        :return: Setup action
        """
        # Check if we're in an additional configuration flow
        if self._pending_device_config is not None:
            return await self._handle_additional_configuration_response(msg)

        if (
            self._setup_step == SetupSteps.CONFIGURATION_MODE
            and "action" in msg.input_values
        ):
            return await self._handle_configuration_mode(msg)

        if self._setup_step == SetupSteps.RESTORE_PROMPT:
            return await self._handle_restore_prompt_response(msg)

        if self._setup_step == SetupSteps.PRE_DISCOVERY:
            return await self._handle_pre_discovery_response(msg)

        if self._setup_step == SetupSteps.DISCOVER and "choice" in msg.input_values:
            choice = msg.input_values["choice"]
            if choice == "manual":
                return await self._handle_manual_entry()
            return await self._handle_device_selection(msg)

        if self._setup_step == SetupSteps.MANUAL_ENTRY:
            return await self._handle_manual_entry_response(msg)

        if self._setup_step == SetupSteps.BACKUP:
            # User has seen the backup, complete setup
            _LOG.info("Backup completed, finishing setup")
            return SetupComplete()

        if self._setup_step == SetupSteps.RESTORE:
            return await self._handle_restore_response(msg)

        _LOG.error("No handler for user input in step: %s", self._setup_step)
        return SetupError()

    async def _build_configuration_mode_screen(self) -> RequestUserInput:
        """
        Build the configuration mode screen.

        Shows configured devices and available actions (add/update/remove/reset).
        """
        dropdown_devices = []
        for device in self.config.all():
            device_id = self.get_device_id(device)
            device_name = self.get_device_name(device)
            dropdown_devices.append({"id": device_id, "label": {"en": device_name}})

        dropdown_actions = [
            {
                "id": "add",
                "label": {"en": "Add a new device"},
            },
        ]

        # Add update/remove/reset/backup/restore actions if devices exist
        if dropdown_devices:
            dropdown_actions.extend(
                [
                    {
                        "id": "update",
                        "label": {"en": "Update information for selected device"},
                    },
                    {
                        "id": "remove",
                        "label": {"en": "Remove selected device"},
                    },
                    {
                        "id": "reset",
                        "label": {"en": "Reset configuration and reconfigure"},
                    },
                    {
                        "id": "backup",
                        "label": {"en": "Backup configuration to clipboard"},
                    },
                    {
                        "id": "restore",
                        "label": {"en": "Restore configuration from backup"},
                    },
                ]
            )
        else:
            # Dummy entry if no devices
            dropdown_devices.append({"id": "", "label": {"en": "---"}})
            # Still allow restore even if no devices
            dropdown_actions.append(
                {
                    "id": "restore",
                    "label": {"en": "Restore configuration from backup"},
                }
            )

        return RequestUserInput(
            {"en": "Configuration mode"},
            [
                {
                    "field": {
                        "dropdown": {
                            "value": dropdown_devices[0]["id"],
                            "items": dropdown_devices,
                        }
                    },
                    "id": "choice",
                    "label": {"en": "Configured Devices"},
                },
                {
                    "field": {
                        "dropdown": {
                            "value": dropdown_actions[0]["id"],
                            "items": dropdown_actions,
                        }
                    },
                    "id": "action",
                    "label": {"en": "Action"},
                },
            ],
        )

    async def _handle_configuration_mode(self, msg: UserDataResponse) -> SetupAction:
        """
        Process configuration mode action selection.

        :param msg: User data response
        :return: Setup action
        """
        action = msg.input_values["action"]

        # Workaround for web-configurator not picking up first response
        await asyncio.sleep(1)

        match action:
            case "add":
                self._add_mode = True
                self._pre_discovery_data = {}

                # Check if pre-discovery screen is needed
                pre_discovery_screen = await self.get_pre_discovery_screen()
                if pre_discovery_screen is not None:
                    self._setup_step = SetupSteps.PRE_DISCOVERY
                    return pre_discovery_screen

                self._setup_step = SetupSteps.DISCOVER
                return await self._handle_discovery()

            case "update":
                choice = msg.input_values["choice"]
                if not self.config.remove(choice):
                    _LOG.warning("Could not update device: %s", choice)
                    return SetupError(error_type=IntegrationSetupError.OTHER)

                self._pre_discovery_data = {}

                # Check if pre-discovery screen is needed
                pre_discovery_screen = await self.get_pre_discovery_screen()
                if pre_discovery_screen is not None:
                    self._setup_step = SetupSteps.PRE_DISCOVERY
                    return pre_discovery_screen

                self._setup_step = SetupSteps.DISCOVER
                return await self._handle_discovery()

            case "remove":
                choice = msg.input_values["choice"]
                if not self.config.remove(choice):
                    _LOG.warning("Could not remove device: %s", choice)
                    return SetupError(error_type=IntegrationSetupError.OTHER)
                self.config.store()
                return SetupComplete()

            case "reset":
                self.config.clear()
                self._pre_discovery_data = {}

                # Ask if user wants to restore from backup
                self._setup_step = SetupSteps.RESTORE_PROMPT
                return await self._build_restore_prompt_screen()

            case "backup":
                return await self._handle_backup()

            case "restore":
                return await self._handle_restore()

            case _:
                _LOG.error("Invalid configuration action: %s", action)
                return SetupError(error_type=IntegrationSetupError.OTHER)

    async def _handle_pre_discovery_response(
        self, msg: UserDataResponse
    ) -> SetupAction:
        """
        Internal handler for pre-discovery screens.

        Automatically stores input values in self._pre_discovery_data, then calls
        the overridable handle_pre_discovery_response and proceeds to discovery
        if it returns None, or shows another screen if returned.

        :param msg: User data response
        :return: Setup action
        """
        try:
            # Automatically store all input values
            self._pre_discovery_data.update(msg.input_values)
            _LOG.debug(
                "Pre-discovery data collected: %s", list(msg.input_values.keys())
            )

            # Call the overridable method
            result = await self.handle_pre_discovery_response(msg)

            # If it returns a screen, show it
            if result is not None:
                return result

            # If it returns None, proceed to discovery
            self._setup_step = SetupSteps.DISCOVER
            return await self._handle_discovery()

        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("Error in pre-discovery configuration: %s", err)
            self._pre_discovery_data = {}
            return SetupError(error_type=IntegrationSetupError.OTHER)

    async def _handle_discovery(self) -> RequestUserInput:
        """
        Handle device discovery.

        Attempts auto-discovery if available, otherwise shows manual entry.
        """
        self._setup_step = SetupSteps.DISCOVER

        if self.discovery is None:
            # No discovery available, go straight to manual entry
            return await self._handle_manual_entry()

        # Attempt discovery (results are stored in self.discovery.devices)
        discovered_devices = await self.discover_devices()

        if discovered_devices:
            _LOG.debug("Found %d device(s)", len(discovered_devices))
            return await self.get_discovered_devices_screen(discovered_devices)

        # No devices found, show manual entry
        return await self._handle_manual_entry()

    async def _finalize_device_setup(
        self, device_config: ConfigT, input_values: dict[str, Any]
    ) -> SetupComplete | SetupError | RequestUserInput:
        """
        Common logic to finalize device setup after creation.

        Checks for duplicates, handles additional configuration screens,
        and saves the device configuration.

        :param device_config: Device configuration to finalize
        :param input_values: User input values from the previous screen
        :return: Setup action
        """
        # Check for duplicates in add mode
        if self._add_mode and self.config.contains(self.get_device_id(device_config)):
            _LOG.warning(
                "Device already configured: %s", self.get_device_id(device_config)
            )
            return SetupError(error_type=IntegrationSetupError.OTHER)

        # Store pending config and check if additional configuration needed
        self._pending_device_config = device_config
        additional_screen = await self.get_additional_configuration_screen(
            device_config, input_values
        )
        if additional_screen is not None:
            return additional_screen

        # No additional screens, save and complete
        self.config.add_or_update(self._pending_device_config)
        self._pending_device_config = None

        await asyncio.sleep(1)
        _LOG.info("Setup completed for %s", self.get_device_name(device_config))
        return SetupComplete()

    async def _handle_device_selection(
        self, msg: UserDataResponse
    ) -> SetupComplete | SetupError | RequestUserInput:
        """
        Handle user selecting a discovered device.

        Converts discovered device data to input_values format and calls query_device,
        just like manual entry does. Falls back to manual entry if device not found.

        :param msg: User data response
        :return: Setup action
        """
        device_id = msg.input_values.get("choice")
        if not device_id:
            _LOG.warning("No device selected, showing manual entry")
            return await self._handle_manual_entry()

        # Look up the discovered device
        discovered = self.get_discovered_devices(device_id)
        if not discovered:
            _LOG.info(
                "Discovered device not found: %s, showing manual entry", device_id
            )
            return await self._handle_manual_entry()

        # Convert discovered device to input_values format
        try:
            input_values = await self.prepare_input_from_discovery(
                discovered, msg.input_values
            )

            # Call query_device just like manual entry does
            result = await self.query_device(input_values)

            # Check if the result is an error or screen to display
            if isinstance(result, (SetupError, RequestUserInput)):
                return result

            # Otherwise it's a device config - proceed with finalization
            return await self._finalize_device_setup(result, msg.input_values)

        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("Setup error: %s", err)
            self._pending_device_config = None
            return SetupError(error_type=IntegrationSetupError.NOT_FOUND)

    async def _handle_manual_entry(self) -> RequestUserInput:
        """Show manual entry form."""
        self._setup_step = SetupSteps.MANUAL_ENTRY
        return self.get_manual_entry_form()

    async def _handle_manual_entry_response(
        self, msg: UserDataResponse
    ) -> SetupComplete | SetupError | RequestUserInput:
        """
        Handle manual entry form submission.

        Merges pre-discovery data with manual entry input before calling query_device.

        :param msg: User data response
        :return: Setup action
        """
        try:
            # Merge pre-discovery data with manual entry input
            # Manual entry values take precedence over pre-discovery
            combined_input = {**self._pre_discovery_data, **msg.input_values}

            result = await self.query_device(combined_input)

            # Check if the result is an error or screen to display
            if isinstance(result, (SetupError, RequestUserInput)):
                return result

            # Otherwise it's a device config - proceed with finalization
            return await self._finalize_device_setup(result, msg.input_values)

        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("Setup error: %s", err)
            self._pending_device_config = None
            return SetupError(error_type=IntegrationSetupError.NOT_FOUND)

    async def _handle_additional_configuration_response(
        self, msg: UserDataResponse
    ) -> SetupAction:
        """
        Internal handler for additional configuration screens.

        Automatically populates self._pending_device_config from msg.input_values
        where field names match config attributes, then calls the overridable
        handle_additional_configuration_response and finalizes setup based on
        what it returns.

        :param msg: User data response
        :return: Setup action
        """
        try:
            # Automatically populate pending config from input values
            self._auto_populate_config(msg.input_values)

            # Call the overridable method
            result = await self.handle_additional_configuration_response(msg)

            # If it returns a RequestUserInput, show it
            if isinstance(result, RequestUserInput):
                return result

            # If it returns SetupError, cleanup and return it
            if isinstance(result, SetupError):
                self._pending_device_config = None
                return result

            # If it returns a device config (ConfigT), replace pending and save
            # This allows returning a new/modified device config to complete setup
            if result is not None and not isinstance(result, SetupComplete):
                # Validate that it's an instance, not a type/class
                if isinstance(result, type):
                    _LOG.error(
                        "handle_additional_configuration_response returned a class (%s) instead of an instance. "
                        "Did you forget to instantiate the device config? "
                        "Use: return MyDeviceConfig(...) instead of: return MyDeviceConfig",
                        result.__name__,
                    )
                    self._pending_device_config = None
                    return SetupError(error_type=IntegrationSetupError.OTHER)

                # User returned a device config instance - use it as the final config
                self._pending_device_config = result

            # At this point: result is None, SetupComplete, or we just set pending_device_config
            if self._pending_device_config is None:
                _LOG.error("Pending device config is None during finalization")
                return SetupError(error_type=IntegrationSetupError.OTHER)

            # Debug logging
            _LOG.debug(
                "Saving device config: type=%s, is_instance=%s",
                type(self._pending_device_config).__name__,
                not isinstance(self._pending_device_config, type),
            )

            # Save the device and complete
            self.config.add_or_update(self._pending_device_config)
            device_name = self.get_device_name(self._pending_device_config)
            self._pending_device_config = None

            await asyncio.sleep(1)
            _LOG.info("Setup completed for %s", device_name)
            return SetupComplete()

        except Exception as err:  # pylint: disable=broad-except
            import traceback

            _LOG.error("Error in additional configuration: %s", err)
            _LOG.error("Error details: %s", traceback.format_exc())
            if self._pending_device_config is not None:
                _LOG.error(
                    "Pending device config type: %s, repr: %s",
                    type(self._pending_device_config),
                    repr(self._pending_device_config)[:200],
                )
            self._pending_device_config = None
            return SetupError(error_type=IntegrationSetupError.OTHER)

    async def _build_restore_prompt_screen(self) -> RequestUserInput:
        """
        Build the restore prompt screen for initial setup.

        This screen asks users if they want to restore from a backup
        before proceeding with normal setup flow.
        """
        prompt_text = await self.get_restore_prompt_text()

        return RequestUserInput(
            {"en": "Restore Configuration?"},
            [
                {
                    "id": "info",
                    "label": {"en": "Integration Upgrade"},
                    "field": {"label": {"value": {"en": prompt_text}}},
                },
                {
                    "id": "restore_from_backup",
                    "label": {"en": "Restore from backup"},
                    "field": {"checkbox": {"value": False}},
                },
            ],
        )

    async def _handle_restore_prompt_response(
        self, msg: UserDataResponse
    ) -> SetupAction:
        """
        Handle response from restore prompt screen.

        If user wants to restore, show restore screen.
        Otherwise, continue with normal setup flow.

        :param msg: User data response
        :return: Setup action
        """
        restore_requested = (
            str(msg.input_values.get("restore_from_backup", False)).strip().lower()
            == "true"
        )

        if restore_requested:
            _LOG.info("User requested restore from backup")
            return await self._handle_restore()

        _LOG.debug("User skipped restore, continuing with normal setup")

        # Continue with normal flow - check if pre-discovery screen is needed
        pre_discovery_screen = await self.get_pre_discovery_screen()
        if pre_discovery_screen is not None:
            self._setup_step = SetupSteps.PRE_DISCOVERY
            return pre_discovery_screen

        # No pre-discovery needed, go straight to discovery
        self._setup_step = SetupSteps.DISCOVER
        return await self._handle_discovery()

    async def _handle_backup(self) -> RequestUserInput:
        """
        Handle backup configuration request.

        Reads the configuration JSON and displays it to the user for copying.
        """
        _LOG.info("Backing up configuration")
        self._setup_step = SetupSteps.BACKUP

        try:
            # Get the configuration as JSON string
            config_json = self.config.get_backup_json()

            return RequestUserInput(
                {"en": "Configuration Backup"},
                [
                    {
                        "id": "info",
                        "label": {"en": "Configuration Backup"},
                        "field": {
                            "label": {
                                "value": {
                                    "en": "Copy the configuration data below and save it in a safe place. "
                                    "You can use this to restore your configuration after an integration update."
                                }
                            }
                        },
                    },
                    {
                        "id": "backup_data",
                        "label": {"en": "Configuration Data (copy this)"},
                        "field": {"textarea": {"value": config_json}},
                    },
                ],
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("Backup error: %s", err)
            return SetupError(error_type=IntegrationSetupError.OTHER)

    async def _handle_restore(self) -> RequestUserInput:
        """
        Handle restore configuration request.

        Prompts the user to paste their backup JSON.
        """
        _LOG.info("Starting configuration restore")
        self._setup_step = SetupSteps.RESTORE

        return RequestUserInput(
            {"en": "Restore Configuration"},
            [
                {
                    "id": "info",
                    "label": {"en": "Restore Configuration"},
                    "field": {
                        "label": {
                            "value": {
                                "en": "Paste the configuration backup data below to restore your devices."
                            }
                        }
                    },
                },
                {
                    "id": "restore_data",
                    "label": {"en": "Configuration Backup Data"},
                    "field": {"textarea": {"value": ""}},
                },
            ],
        )

    async def _handle_restore_response(
        self, msg: UserDataResponse
    ) -> SetupComplete | SetupError:
        """
        Handle restore configuration form submission.

        :param msg: User data response containing backup JSON
        :return: Setup action
        """
        try:
            restore_data = msg.input_values.get("restore_data", "").strip()

            if not restore_data:
                _LOG.error("No restore data provided")
                return SetupError(error_type=IntegrationSetupError.OTHER)

            # Restore the configuration from JSON
            success = self.config.restore_from_backup_json(restore_data)

            if not success:
                _LOG.error("Failed to restore configuration")
                return SetupError(error_type=IntegrationSetupError.OTHER)

            await asyncio.sleep(1)
            _LOG.info("Configuration restored successfully")
            return SetupComplete()

        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("Restore error: %s", err)
            return SetupError(error_type=IntegrationSetupError.OTHER)

    def _auto_populate_config(self, input_values: dict[str, Any]) -> None:
        """
        Automatically populate pending device config from input values.

        Matches field names from input_values to attributes on self._pending_device_config
        and automatically sets them. This eliminates the need for manual field mapping
        in most cases.

        Only populates attributes that:
        1. Exist on the pending device config
        2. Are present in input_values
        3. Are not None in input_values

        :param input_values: User input values from form submission
        """
        if self._pending_device_config is None:
            _LOG.warning("Cannot auto-populate: _pending_device_config is None")
            return

        populated_fields = []
        for field_name, value in input_values.items():
            # Skip None values and internal fields
            if value is None or field_name.startswith("_"):
                continue

            # Check if the config has this attribute
            if hasattr(self._pending_device_config, field_name):
                try:
                    setattr(self._pending_device_config, field_name, value)
                    populated_fields.append(field_name)
                except AttributeError:
                    # Attribute might be read-only or a property
                    _LOG.debug(
                        "Could not set attribute '%s' on %s (may be read-only)",
                        field_name,
                        type(self._pending_device_config).__name__,
                    )

        if populated_fields:
            _LOG.debug(
                "Auto-populated %s fields: %s",
                type(self._pending_device_config).__name__,
                ", ".join(populated_fields),
            )

    # ========================================================================
    # Abstract Methods (Must be implemented by subclasses)
    # ========================================================================

    @abstractmethod
    async def query_device(
        self, input_values: dict[str, Any]
    ) -> ConfigT | SetupError | RequestUserInput:
        """
        Query and validate device using collected information.

        This method is called after the user provides device information (via manual entry
        or discovery). This is where you typically have enough info to query the device,
        validate connectivity, fetch additional data, or perform authentication.

        Based on the query results, you can:
        - Return a complete device config to finish setup
        - Show additional screens to collect more information
        - Return an error if validation fails

        This method can return:
        - **ConfigT**: A valid device configuration - if no additional screens needed, setup completes.
                      If you need additional screens, DON'T return the config - store it in
                      self._pending_device_config and return RequestUserInput instead.
        - **SetupError**: An error to abort the setup with an error message
        - **RequestUserInput**: A screen to display for additional configuration or validation.
                               **IMPORTANT:** To show additional screens after this one, you MUST
                               set self._pending_device_config BEFORE returning RequestUserInput.
                               The response will then route to handle_additional_configuration_response().

        Example - Simple case (no additional screens):
            async def query_device(self, input_values):
                # Query the device to validate connectivity
                device_info = await self.api.get_device_info(input_values["host"])

                if not device_info:
                    return SetupError(error_type=IntegrationSetupError.CONNECTION_REFUSED)

                # Just return the config - setup completes automatically
                return MyDeviceConfig(
                    identifier=device_info["id"],
                    name=input_values["name"],
                    address=input_values["host"],
                    port=int(input_values.get("port", 8080)),
                    version=device_info["version"]
                )

        Example - With validation:
            async def query_device(self, input_values):
                host = input_values.get("host", "").strip()
                if not host:
                    return SetupError(error_type=IntegrationSetupError.CONNECTION_REFUSED)

                # Test connection
                if not await self.api.test_connection(host):
                    return SetupError(error_type=IntegrationSetupError.CONNECTION_REFUSED)

                return MyDeviceConfig(
                    identifier=host,
                    name=input_values.get("name", host),
                    address=host
                )

        Example - Multi-screen flow (query device, then show additional options):
            async def query_device(self, input_values):
                # Query the device API to validate and fetch available options
                auth_response = await self.api.authenticate(
                    input_values["host"],
                    input_values["token"]
                )

                if not auth_response["valid"]:
                    return SetupError(error_type=IntegrationSetupError.AUTHORIZATION_ERROR)

                # IMPORTANT: Store config in _pending_device_config for multi-screen flows
                self._pending_device_config = MyDeviceConfig(
                    identifier=input_values["host"],
                    name=input_values["name"],
                    token=auth_response["token"],
                    available_servers=auth_response["servers"]  # Data needed for next screen
                )

                # Return screen - response will route to handle_additional_configuration_response
                return RequestUserInput(
                    {"en": "Select Server"},
                    [{"id": "server", "label": {"en": "Server"},
                      "field": {"dropdown": {"items": self._build_server_dropdown()}}}]
                )

            async def handle_additional_configuration_response(self, msg):
                # Access stored config and new input
                self._pending_device_config.server = msg.input_values["server"]
                return None  # Save and complete (or return modified config)

        Example - Re-display form with validation error:
            async def query_device(self, input_values):
                host = input_values.get("host", "").strip()
                if not host:
                    # Show the form again with error (no _pending_device_config set)
                    return RequestUserInput(
                        {"en": "Invalid Input"},
                        [
                            {"id": "error", "label": {"en": "Error"},
                             "field": {"label": {"value": {"en": "Host is required"}}}},
                            # ... rest of the form fields
                        ]
                    )

                return MyDeviceConfig(identifier=host, name=host, address=host)

        :param input_values: User input values from the manual entry form.
                            Also includes self._pre_discovery_data if pre-discovery screens were shown.
        :return: Device configuration, SetupError, or RequestUserInput to re-display form
        """

    @abstractmethod
    def get_manual_entry_form(self) -> RequestUserInput:
        """
        Get the manual entry form.

        :return: RequestUserInput with manual entry fields
        """

    # ========================================================================
    # Discovery Methods (Override if discovery is supported)
    # ========================================================================

    async def discover_devices(self) -> list[DiscoveredDevice]:
        """
        Perform device discovery.

        DEFAULT IMPLEMENTATION: Calls self.discovery.discover() if available.

        If a discovery_class was passed to __init__, this method will call its
        discover() method and return the results. If no discovery_class was provided
        (None), this returns an empty list and the setup flow will skip discovery.

        :return: List of discovered devices, or empty list if discovery not supported
        """
        if self.discovery is None:
            _LOG.info(
                "%s: No discovery class provided - using manual entry only",
                self.__class__.__name__,
            )
            return []

        _LOG.debug(
            "%s: Running discovery using %s",
            self.__class__.__name__,
            type(self.discovery).__name__,
        )

        try:
            devices = await self.discovery.discover()
            # Store devices in discovery instance for later lookup
            self.discovery._discovered_devices = devices
            _LOG.info(
                "%s: Discovered %d device(s)", self.__class__.__name__, len(devices)
            )
            return devices
        except Exception as err:  # pylint: disable=broad-except
            _LOG.info("%s: Discovery failed: %s", self.__class__.__name__, err)
            return []

    async def prepare_input_from_discovery(
        self, discovered: DiscoveredDevice, additional_input: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Convert discovered device data to input_values format for query_device.

        **You must override this method if you provide a discovery_class.**

        This method transforms a discovered device into the same input_values format
        that manual entry produces. This allows query_device() to work uniformly for
        both discovery and manual entry paths.

        The returned dictionary should match the field names from your manual entry form,
        so query_device() can process both sources identically.

        DEFAULT IMPLEMENTATION: Returns a basic dictionary with common fields.
        Override this to customize the mapping for your integration.

        :param discovered: The discovered device selected by the user
        :param additional_input: Additional user input from the discovery screen
                                (e.g., from get_additional_discovery_fields)
        :return: Dictionary of input values in the same format as manual entry

        Example - Basic mapping:
            async def prepare_input_from_discovery(self, discovered, additional_input):
                return {
                    "identifier": discovered.identifier,
                    "address": discovered.address,
                    "name": discovered.name,
                    "port": discovered.extra_data.get("port", 8080),
                    # Include any additional fields from discovery screen
                    **additional_input
                }

        Example - With data transformation:
            async def prepare_input_from_discovery(self, discovered, additional_input):
                # Extract specific data from extra_data
                return {
                    "identifier": discovered.identifier,
                    "address": discovered.address,
                    "name": additional_input.get("name", discovered.name),  # Allow override
                    "model": discovered.extra_data.get("model"),
                    "firmware": discovered.extra_data.get("version"),
                }

        Example - With filtering:
            async def prepare_input_from_discovery(self, discovered, additional_input):
                # Only include relevant additional input fields
                return {
                    "identifier": discovered.identifier,
                    "address": discovered.address,
                    "name": discovered.name,
                    # Only include specific additional fields, not "choice"
                    "zone": additional_input.get("zone", 1),
                    "volume_step": additional_input.get("volume_step", 5),
                }
        """
        # Default implementation: basic mapping with additional input merged in
        input_values = {
            "identifier": discovered.identifier,
            "address": discovered.address,
            "name": discovered.name,
        }

        # Merge additional input, filtering out internal fields
        for key, value in additional_input.items():
            if not key.startswith("_") and key not in ("choice",):
                input_values[key] = value

        return input_values

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def get_discovered_devices(
        self, identifier: str | None = None
    ) -> list[DiscoveredDevice] | DiscoveredDevice | None:
        """
        Get discovered devices from the last discovery run.

        This is a convenience method that returns devices found by the framework's
        automatic discovery. Use this in your create_device_from_discovery()
        implementation to access device details.

        This is equivalent to accessing self.discovery.devices directly.

        :param identifier: Optional device identifier to look up a specific device.
                          If provided, returns the matching DiscoveredDevice or None.
                          If omitted, returns the full list of devices.
        :return: If identifier provided: DiscoveredDevice or None
                If no identifier: List of all discovered devices (empty if none found)

        Example - Get specific device:
            async def create_device_from_discovery(self, device_id, additional_data):
                discovered = self.get_discovered_devices(device_id)
                if not discovered:
                    return SetupError(error_type=IntegrationSetupError.NOT_FOUND)

                return MyDeviceConfig(
                    identifier=discovered.identifier,
                    name=discovered.name,
                    address=discovered.address,
                    port=discovered.extra_data.get("port", 80)
                )

        Example - Get all devices:
            async def create_device_from_discovery(self, device_id, additional_data):
                for device in self.get_discovered_devices():
                    if device.identifier == device_id:
                        return MyDeviceConfig.from_discovered(device)
                return SetupError(error_type=IntegrationSetupError.NOT_FOUND)
        """
        if self.discovery is None:
            return None if identifier else []

        if identifier is not None:
            # Look up specific device
            return next(
                (d for d in self.discovery.devices if d.identifier == identifier),
                None,
            )

        # Return all devices
        return self.discovery.devices

    # ========================================================================
    # Optional Override Methods
    # ========================================================================

    def get_device_id(self, device_config: ConfigT) -> str:
        """
        Extract device ID from configuration.

        Default implementation: tries common attribute names (identifier, id, device_id).
        Override this if your config uses a different attribute name.

        :param device_config: Device configuration
        :return: Device identifier
        :raises AttributeError: If no valid ID attribute is found
        """
        for attr in ("identifier", "id", "device_id"):
            if hasattr(device_config, attr):
                value = getattr(device_config, attr)
                if value:
                    return str(value)

        raise AttributeError(
            f"Device config {type(device_config).__name__} has no 'identifier', 'id', or 'device_id' attribute. "
            f"Override get_device_id() to specify which attribute to use."
        )

    def get_device_name(self, device_config: ConfigT) -> str:
        """
        Extract device name from configuration.

        Default implementation: tries common attribute names (name, friendly_name, device_name).
        Override this if your config uses a different attribute name.

        :param device_config: Device configuration
        :return: Device name
        :raises AttributeError: If no valid name attribute is found
        """
        for attr in ("name", "friendly_name", "device_name"):
            if hasattr(device_config, attr):
                value = getattr(device_config, attr)
                if value:
                    return str(value)

        raise AttributeError(
            f"Device config {type(device_config).__name__} has no 'name', 'friendly_name', or 'device_name' attribute. "
            f"Override get_device_name() to specify which attribute to use."
        )

    def format_discovered_device_label(self, device: DiscoveredDevice) -> str:
        """
        Format how a discovered device appears in the dropdown list.

        Override this method to customize how devices are displayed to users
        during discovery. The default format shows the device name and address.

        :param device: The discovered device to format
        :return: Formatted label string

        Example - Include model information:
            def format_discovered_device_label(self, device):
                model = device.extra_data.get("model", "Unknown")
                return f"{device.name} - {model} ({device.address})"

        Example - Show additional details:
            def format_discovered_device_label(self, device):
                version = device.extra_data.get("version", "")
                return f"{device.name} [{version}] at {device.address}"
        """
        return f"{device.name} ({device.address})"

    async def get_discovered_devices_screen(
        self, devices: list[DiscoveredDevice]
    ) -> RequestUserInput:
        """
        Build the discovered devices selection screen.

        Override this method to completely customize the discovery screen layout,
        such as adding additional fields, changing the title, or using a different
        input type.

        The default implementation creates a dropdown with all discovered devices
        (using format_discovered_device_label for labels), plus a "Setup Manually"
        option, and includes any additional fields from get_additional_discovery_fields().

        The selected device's identifier will be passed to create_device_from_discovery().

        :param devices: List of discovered devices
        :return: RequestUserInput screen to show to the user

        Example - Custom screen with additional fields:
            async def get_discovered_devices_screen(self, devices):
                dropdown_items = [
                    {
                        "id": d.identifier,
                        "label": {"en": self.format_discovered_device_label(d)}
                    }
                    for d in devices
                ]
                dropdown_items.append({"id": "manual", "label": {"en": "Manual Setup"}})

                return RequestUserInput(
                    {"en": "Select Your Device"},
                    [
                        {
                            "id": "choice",
                            "label": {"en": "Available Devices"},
                            "field": {"dropdown": {"value": dropdown_items[0]["id"], "items": dropdown_items}}
                        },
                        {
                            "id": "zone",
                            "label": {"en": "Default Zone"},
                            "field": {"number": {"value": 1, "min": 1, "max": 10}}
                        }
                    ]
                )
        """
        dropdown_devices = []
        for device in devices:
            dropdown_devices.append(
                {
                    "id": device.identifier,
                    "label": {"en": self.format_discovered_device_label(device)},
                }
            )

        # Add manual entry option
        dropdown_devices.append({"id": "manual", "label": {"en": "Setup Manually"}})

        fields = [
            {
                "field": {
                    "dropdown": {
                        "value": dropdown_devices[0]["id"],
                        "items": dropdown_devices,
                    }
                },
                "id": "choice",
                "label": {"en": "Discovered Devices"},
            }
        ]

        # Add any additional discovery fields
        fields.extend(self.get_additional_discovery_fields())

        return RequestUserInput({"en": "Discovered Devices"}, fields)

    def get_additional_discovery_fields(self) -> list[dict]:
        """
        Get additional fields to show during discovery.

        Override to add custom fields (e.g., volume step, zone selection).

        :return: List of field definitions
        """
        return []

    def extract_additional_setup_data(
        self, input_values: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Extract additional setup data from input values.

        Override to extract additional custom fields.

        :param input_values: User input values
        :return: Dictionary of additional data
        """
        _ = input_values  # Mark as intentionally unused
        return {}

    async def get_pre_discovery_screen(self) -> RequestUserInput | None:
        """
        Request pre-discovery configuration screen(s).

        Override this method to show configuration screens BEFORE device discovery.
        This is useful for collecting credentials, API keys, server addresses, or
        other information needed to perform discovery.

        The collected data is stored in self._pre_discovery_data and can be accessed
        during discovery (in discover_devices()) or device creation.

        To show a pre-discovery screen:
        1. Return a RequestUserInput with the fields you need
        2. Handle the response in handle_pre_discovery_response()
        3. Return another RequestUserInput to show more screens, or None to proceed

        :return: RequestUserInput to show a screen, or None to skip pre-discovery
        """
        return None

    async def handle_pre_discovery_response(self, msg: UserDataResponse) -> SetupAction:
        """
        Handle response from pre-discovery screens.

        Override this method to process responses from screens created by
        get_pre_discovery_screen(). The input values are automatically stored
        in self._pre_discovery_data before this method is called.

        You should:
        1. Validate the input (optionally)
        2. Either:
           - Return another RequestUserInput for more pre-discovery screens, or
           - Return None to proceed to device discovery

        If you return None, the base class will call discover_devices() where
        you can access self._pre_discovery_data to use the collected information.

        :param msg: User data response from pre-discovery screen
        :return: RequestUserInput for another screen, or None to proceed to discovery
        """
        _ = msg  # Mark as intentionally unused
        # Default: No additional handling, proceed to discovery
        return None

    async def get_additional_configuration_screen(
        self, device_config: ConfigT, previous_input: dict[str, Any]
    ) -> RequestUserInput | None:
        """
        Request additional configuration screens after device creation.

        Override this method to show additional setup screens that collect more
        information about the device. This is called after query_device
        (for both manual entry and discovery paths) but BEFORE the device is saved.

        **AUTO-POPULATION:** Any fields returned by this screen will automatically
        populate matching attributes on self._pending_device_config. You typically
        don't need to manually handle the response!

        Example - Simple additional screen:
            async def get_additional_configuration_screen(self, device_config, previous_input):
                return RequestUserInput(
                    {"en": "Additional Settings"},
                    [
                        {"id": "token", "label": {"en": "API Token"},
                         "field": {"text": {"value": ""}}},
                        {"id": "zone", "label": {"en": "Zone"},
                         "field": {"number": {"value": 1}}}
                    ]
                )
                # token and zone will auto-populate if device_config has those attributes!

        Example - Conditional screen:
            async def get_additional_configuration_screen(self, device_config, previous_input):
                if device_config.requires_auth:
                    return RequestUserInput(
                        {"en": "Authentication"},
                        [{"id": "password", "label": {"en": "Password"},
                          "field": {"text": {"value": ""}}}]
                    )
                return None  # No additional screen needed

        :param device_config: The device configuration (also in self._pending_device_config)
        :param previous_input: Input values from the previous screen
        :return: RequestUserInput to show another screen, or None to complete setup
        """
        _ = device_config  # Mark as intentionally unused
        _ = previous_input
        return None

    async def handle_additional_configuration_response(
        self, msg: UserDataResponse
    ) -> ConfigT | SetupAction | None:
        """
        Handle response from additional configuration screens.

        Override this method to process responses from custom setup screens
        created by get_additional_configuration_screen().

        **AUTO-POPULATION:** The framework automatically populates self._pending_device_config
        from msg.input_values where field names match config attributes. In most cases,
        you don't need to override this method at all!

        Return one of:
        - **None** (recommended): Auto-populated fields are saved automatically
        - **ConfigT** (device config): Replace pending config and save this one
        - **RequestUserInput**: Show another configuration screen
        - **SetupError**: Abort setup with an error

        Example - No override needed (auto-population):
            # If your screen has fields like "token" and "zone" that match
            # attributes on your device config, they're automatically set!
            # No need to override handle_additional_configuration_response at all.

        Example - With validation:
            async def handle_additional_configuration_response(self, msg):
                # Fields already auto-populated, just validate
                if not self._pending_device_config.token:
                    return SetupError(error_type=IntegrationSetupError.AUTHORIZATION_ERROR)

                # Or add computed fields
                self._pending_device_config.full_url = (
                    f"https://{self._pending_device_config.address}:8080"
                )
                return None  # Save and complete

        Example - Show another screen:
            async def handle_additional_configuration_response(self, msg):
                # Check if we need authentication
                if self._pending_device_config.requires_auth:
                    return RequestUserInput(
                        {"en": "Enter Password"},
                        [{"id": "password", "label": {"en": "Password"},
                          "field": {"text": {"value": ""}}}]
                    )
                return None

        Example - Replace entire config (advanced):
            async def handle_additional_configuration_response(self, msg):
                # Create completely new config (rarely needed)
                return MyDeviceConfig(
                    identifier=self._pending_device_config.identifier,
                    name=self._pending_device_config.name,
                    address=self._pending_device_config.address,
                    token=msg.input_values["token"],  # Manual access if needed
                )

        :param msg: User data response from additional screen
        :return: Device config to save, SetupAction, or None to complete
        """
        _ = msg  # Mark as intentionally unused
        # Default: No additional handling, auto-populated fields are saved
        return None

    async def get_restore_prompt_text(self) -> str:
        """
        Get the text to display on the restore prompt screen.

        Override this method to customize the message shown to users when they
        first start setup. This screen appears before any device configuration
        and offers them the option to restore from a backup.

        The default message explains that the user can restore from a backup
        if they're upgrading from a previous version.

        :return: Text to display in the restore prompt screen

        Example - Custom message:
            async def get_restore_prompt_text(self):
                return (
                    "Welcome to MyDevice Integration v2.0! "
                    "If you're upgrading from v1.x, you can restore your "
                    "previous configuration using a backup. Otherwise, "
                    "continue with the setup process."
                )

        Example - Integration-specific instructions:
            async def get_restore_prompt_text(self):
                return (
                    "Are you upgrading this integration? "
                    "If you have a configuration backup from a previous version, "
                    "enable the option below to restore it. This will import "
                    "all your device settings and preferences."
                )
        """
        return (
            "Are you upgrading this integration? "
            "If you have a configuration backup, you can restore it now. "
            "Otherwise, continue with the setup process to add a new device. "
            "Once configured, you can create a backup from the integration settings screen by running the Setup again."
        )

"""
Base setup flow for Unfolded Circle Remote integrations.

Provides reusable setup flow logic for device configuration.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Generic, TypeVar, cast

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
from .migration import MigrationData, migrate_entities_on_remote, get_driver_version

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
    MIGRATION_CHECK = 9
    MIGRATION = 10


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
        driver: BaseIntegrationDriver,
        device_class: type | None = None,
        discovery: BaseDiscovery | None = None,
        show_migration_in_ui: bool | None = None,
    ):
        """
        Initialize the setup flow.

        Child classes typically don't need to override __init__ - the driver,
        device_class, and discovery are set automatically by create_handler().

        :param config_manager: Device configuration manager instance
        :param driver: Reference to the driver instance (provides access to driver state)
        :param device_class: The device class (enables calling class methods for validation)
        :param discovery: Discovery instance for auto-discovery.
                         Pass None if the device does not support discovery.
                         This is typically instantiated in your driver's main() and
                         passed via create_handler().
        :param show_migration_in_ui: Whether to show migration option in configuration mode.
                                    Default is None (auto-detect based on get_migration_data override).
                                    Set to True/False to explicitly override auto-detection.
        """
        self.config = config_manager
        self.driver = driver
        self.device_class = device_class
        self.discovery = discovery

        # Auto-detect migration support if not explicitly set
        if show_migration_in_ui is None:
            # Check if get_migration_data is overridden in child class
            show_migration_in_ui = (
                type(self).get_migration_data != BaseSetupFlow.get_migration_data
            )

        self.show_migration_in_ui = show_migration_in_ui
        self._setup_step = SetupSteps.INIT
        self._add_mode = False
        self._pending_device_config: ConfigT | None = None  # For multi-screen flows
        self._pre_discovery_data: dict[
            str, Any
        ] = {}  # Store data from pre-discovery screens
        self._migration_required: bool | None = (
            None  # Cached migration requirement status
        )
        self._previous_version: str | None = (
            None  # Previous version for migration check
        )

    @classmethod
    def create_handler(
        cls,
        driver: BaseIntegrationDriver,
        discovery: BaseDiscovery | None = None,
    ):
        """
        Create a setup handler function with the given configuration.

        This is a convenience factory method that creates a closure containing
        the setup flow instance, suitable for passing to IntegrationAPI.init().

        The driver_id is automatically extracted from the driver instance. If the driver
        has a driver_id set, it will be used to automatically fetch the current version
        from the Remote during migration.

        Example usage in driver's main():
            discovery = MyDiscovery(api_key="...", timeout=30)
            setup_handler = MySetupFlow.create_handler(driver, discovery=discovery)
            api.init("driver-name", setup_handler=setup_handler)

        :param driver: The driver instance. The config_manager and driver_id will be
                      retrieved from the driver.
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
                setup_flow = cls(
                    driver.config_manager,
                    driver=driver,
                    device_class=driver._device_class,
                    discovery=discovery,
                )

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
        elif isinstance(msg, UserDataResponse):
            _LOG.debug("User data response: %s", msg)
            return await self._handle_user_data_response(msg)
        elif isinstance(msg, AbortDriverSetup):
            _LOG.info("Setup was aborted with code: %s", msg.error)
            self._setup_step = SetupSteps.INIT
            return SetupError()
        else:
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
        _LOG.debug("setup_data: %s", msg.setup_data)

        # Check for migration requirement if previous_version is provided in setup_data
        # This allows programmatic detection (e.g., by manager) without requiring reconfigure mode
        if msg.setup_data and "previous_version" in msg.setup_data:
            self._previous_version = msg.setup_data["previous_version"]
            _LOG.info(
                "Checking migration requirement for upgrade from version %s",
                self._previous_version,
            )
            self._migration_required = await self.is_migration_required(
                self._previous_version
            )
            _LOG.info(
                "Migration required: %s (previous: %s)",
                self._migration_required,
                self._previous_version,
            )

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

        if self._setup_step == SetupSteps.MIGRATION_CHECK:
            return await self._handle_migration_check_response(msg)

        if self._setup_step == SetupSteps.MIGRATION:
            return await self._handle_migration_response(msg)

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
            # Add migration option if explicitly enabled
            if self.show_migration_in_ui:
                dropdown_actions.append(
                    {
                        "id": "migrate",
                        "label": {"en": "Migrate Entities"},
                    }
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

            case "migrate":
                return await self._handle_migration(msg)

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

        # Type assertion: when identifier is provided, get_discovered_devices returns a single device
        assert isinstance(discovered, DiscoveredDevice)

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

                # Validate that result is not a SetupAction (should be ConfigT at this point)
                if isinstance(result, (RequestUserInput, SetupError, SetupComplete)):
                    _LOG.error(
                        "Unexpected SetupAction type after filtering: %s",
                        type(result).__name__,
                    )
                    self._pending_device_config = None
                    return SetupError(error_type=IntegrationSetupError.OTHER)

                # User returned a device config instance - use it as the final config
                # Cast is safe here because we've eliminated all SetupAction types above
                self._pending_device_config = cast(ConfigT, result)

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

        If migration is required (based on previous_version), adds a visible
        notification field that both informs the user and provides metadata
        for the integration manager.
        """
        prompt_text = await self.get_restore_prompt_text()

        settings = [
            {
                "id": "info",
                "label": {"en": "Integration Upgrade"},
                "field": {"label": {"value": {"en": prompt_text}}},
            },
        ]

        # Add migration data field if migration is required (for manager consumption)
        # Normal users won't see this since they don't provide previous_version
        if self._migration_required is True:
            settings.append(
                {
                    "id": "migration_required",
                    "label": {"en": ""},
                    "field": {"label": {"value": self._previous_version or ""}},
                }
            )

        settings.append(
            {
                "id": "restore_from_backup",
                "label": {"en": "Restore from backup"},
                "field": {"checkbox": {"value": False}},
            }
        )

        return RequestUserInput(
            {"en": "Restore Configuration?"},
            settings,
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

    async def _handle_backup(self) -> RequestUserInput | SetupError:
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

        return await self._build_restore_screen_with_error(None, "")

    async def _build_restore_screen_with_error(
        self, error_message: str | None, restore_data: str
    ) -> RequestUserInput:
        """
        Build the restore configuration screen, optionally with an error message.

        :param error_message: Optional error message to display, or None for no error
        :param restore_data: Previous restore data to pre-fill (for retry)
        :return: RequestUserInput for restore screen
        """
        fields = []

        # Add error message if provided
        if error_message:
            fields.append(
                {
                    "id": "error",
                    "label": {"en": "Error"},
                    "field": {"label": {"value": {"en": f"⚠️ {error_message}"}}},
                }
            )

        # Add instructions
        fields.append(
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
            }
        )

        # Add textarea for backup data
        fields.append(
            {
                "id": "restore_data",
                "label": {"en": "Configuration Backup Data"},
                "field": {"textarea": {"value": restore_data}},
            }
        )

        return RequestUserInput({"en": "Restore Configuration"}, fields)

    async def _handle_restore_response(
        self, msg: UserDataResponse
    ) -> SetupComplete | SetupError | RequestUserInput:
        """
        Handle restore configuration form submission.

        :param msg: User data response containing backup JSON
        :return: Setup action
        """
        restore_data = msg.input_values.get("restore_data", "").strip()

        # Validate that data was provided
        if not restore_data:
            _LOG.warning("No restore data provided, showing restore screen again")
            return await self._build_restore_screen_with_error(
                "Please paste the configuration backup data.", restore_data
            )

        # Validate that it's valid JSON
        try:
            json.loads(restore_data)
        except json.JSONDecodeError as err:
            _LOG.warning("Invalid JSON provided: %s", err)
            return await self._build_restore_screen_with_error(
                f"Invalid JSON format: {err.msg} at line {err.lineno}, column {err.colno}",
                restore_data,
            )

        # Attempt to restore the configuration
        try:
            success = self.config.restore_from_backup_json(restore_data)

            if not success:
                _LOG.warning("Failed to restore configuration from backup")
                return await self._build_restore_screen_with_error(
                    "Invalid configuration format. Please ensure you're pasting the complete backup data.",
                    restore_data,
                )

            await asyncio.sleep(1)
            _LOG.info("Configuration restored successfully")
            return SetupComplete()

        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("Restore error: %s", err)
            return await self._build_restore_screen_with_error(
                f"Failed to restore configuration: {str(err)}", restore_data
            )

    async def _handle_migration(
        self, msg: UserDataResponse | None = None
    ) -> RequestUserInput | SetupComplete | SetupError:
        """
        Handle migration request.

        Supports two flows:
        1. Direct check (manager provides previous_version in initial call)
        2. UI flow (shows form to collect version, for testing/debugging)

        :param msg: Optional UserDataResponse with previous_version for direct check
        :return: Setup action
        """
        # Check if this is a migration execution request (has both versions) - check this FIRST
        if (
            msg
            and "current_version" in msg.input_values
            and "previous_version" in msg.input_values
        ):
            # Direct flow: perform migration immediately
            _LOG.info("Starting migration execution (direct)")
            self._setup_step = SetupSteps.MIGRATION
            return await self._handle_migration_response(msg)

        # Check if manager provided just previous_version (migration check only)
        if msg and "previous_version" in msg.input_values:
            # Direct flow: perform check immediately
            _LOG.info("Starting migration check (direct)")
            self._setup_step = SetupSteps.MIGRATION_CHECK
            return await self._handle_migration_check_response(msg)

        # UI flow: show form to collect version
        _LOG.info("Starting migration check (UI flow)")
        self._setup_step = SetupSteps.MIGRATION_CHECK

        return RequestUserInput(
            {"en": "Check Migration Requirement"},
            [
                {
                    "id": "info",
                    "label": {"en": "Migration Check"},
                    "field": {
                        "label": {
                            "value": {
                                "en": "Provide the previous integration version to check if migration is required."
                            }
                        }
                    },
                },
                {
                    "id": "previous_version",
                    "label": {"en": "Previous Version"},
                    "field": {"text": {"value": ""}},
                },
            ],
        )

    async def _handle_migration_check_response(
        self, msg: UserDataResponse
    ) -> RequestUserInput | SetupComplete:
        """
        Handle migration check response.

        Calls is_migration_required() and returns a screen with the result
        that the manager can read via GET request.

        For UI flow: if migration is needed, prompts for current_version to proceed.
        For manager flow: returns result immediately.

        :param msg: User data response containing previous_version
        :return: RequestUserInput with migration_required field or next step
        """
        previous_version = msg.input_values.get("previous_version", "").strip()

        if not previous_version:
            _LOG.warning("No previous version provided")
            migration_required = False
        else:
            # Call the overridable method
            migration_required = await self.is_migration_required(previous_version)

        _LOG.info(
            "Migration check: previous_version=%s, required=%s",
            previous_version,
            migration_required,
        )

        # If this is a UI flow (user clicked through) and migration is required,
        # show the migration execution form
        if migration_required and self.show_migration_in_ui:
            _LOG.info("Migration required, showing execution form")
            self._setup_step = SetupSteps.MIGRATION

            # Build form fields
            fields = [
                {
                    "id": "info",
                    "label": {"en": "Migration Required"},
                    "field": {
                        "label": {
                            "value": {
                                "en": f"Migration is required from version {previous_version}. "
                                f"Provide the migration details to update entity references on the Remote."
                            }
                        }
                    },
                },
                {
                    "id": "previous_version",
                    "label": {"en": "Previous Version"},
                    "field": {"text": {"value": previous_version}},
                },
            ]

            # Only show current_version input if driver doesn't have driver_id
            # Otherwise, it will be fetched automatically
            driver_id = self.driver.driver_id if self.driver else None
            if not driver_id:
                fields.append(
                    {
                        "id": "current_version",
                        "label": {"en": "Current Version"},
                        "field": {"text": {"value": ""}},
                    }
                )

            fields.extend(
                [
                    {
                        "id": "remote_url",
                        "label": {"en": "Remote URL"},
                        "field": {"text": {"value": "http://localhost"}},
                    },
                    {
                        "id": "remote_url_note",
                        "label": {"en": "Note"},
                        "field": {
                            "label": {
                                "value": {
                                    "en": "Use 'http://localhost' if this integration runs on the Remote. "
                                    "Otherwise, provide the Remote's IP address (e.g., 'http://192.168.1.100')."
                                }
                            }
                        },
                    },
                    {
                        "id": "pin",
                        "label": {"en": "Remote PIN"},
                        "field": {"text": {"value": ""}},
                    },
                ]
            )

            return RequestUserInput({"en": "Perform Migration"}, fields)

        # Return a screen with the result that manager can read
        # The manager will look for the migration_required field value
        return RequestUserInput(
            {"en": "Migration Check Result"},
            [
                {
                    "id": "migration_required",
                    "label": {"en": "Migration Required"},
                    "field": {"checkbox": {"value": migration_required}},
                },
                {
                    "id": "info",
                    "label": {"en": "Result"},
                    "field": {
                        "label": {
                            "value": {
                                "en": f"Migration {'is' if migration_required else 'is not'} required for upgrade from {previous_version}"
                            }
                        }
                    },
                },
            ],
        )

    async def _handle_migration_response(
        self, msg: UserDataResponse
    ) -> RequestUserInput | SetupComplete | SetupError:
        """
        Handle migration execution request.

        Expects previous_version, remote_url, and pin. If driver_id is configured,
        current_version will be automatically fetched from the Remote.
        Calls get_migration_data() to get entity mappings, then calls
        migrate_entities_on_remote() to perform the migration on the Remote.

        :param msg: User data response containing version info and Remote credentials
        :return: RequestUserInput with migration results or SetupComplete
        """
        previous_version = msg.input_values.get("previous_version", "").strip()
        current_version = msg.input_values.get("current_version", "").strip()
        remote_url = msg.input_values.get("remote_url", "http://localhost").strip()
        pin = msg.input_values.get("pin", "").strip()

        # Ensure remote_url has protocol prefix
        if remote_url and not remote_url.startswith(("http://", "https://")):
            remote_url = f"http://{remote_url}"
            _LOG.debug("Added http:// prefix to remote_url: %s", remote_url)

        # If driver has driver_id set and current_version is not provided, fetch it from Remote
        driver_id = self.driver.driver_id if self.driver else None
        if driver_id and not current_version and remote_url and pin:
            _LOG.info("Fetching current version from Remote for driver %s", driver_id)

            fetched_version = await get_driver_version(
                remote_url=remote_url, driver_id=driver_id, pin=pin
            )

            if fetched_version:
                current_version = fetched_version
                _LOG.info("Retrieved current version from Remote: %s", current_version)
            else:
                _LOG.warning("Failed to fetch current version from Remote")

        # Validate required fields - if missing, re-show the form with current values
        missing_fields = []
        if not current_version:
            missing_fields.append("Current Version")
        if not remote_url:
            missing_fields.append("Remote URL")
        if not pin:
            missing_fields.append("Remote PIN")

        if missing_fields:
            _LOG.warning(
                "Missing required fields for migration: %s", ", ".join(missing_fields)
            )
            return RequestUserInput(
                {"en": "Perform Migration"},
                [
                    {
                        "id": "error",
                        "label": {"en": "Missing Information"},
                        "field": {
                            "label": {
                                "value": {
                                    "en": f"Please provide the following required fields: {', '.join(missing_fields)}"
                                }
                            }
                        },
                    },
                    {
                        "id": "previous_version",
                        "label": {"en": "Previous Version"},
                        "field": {"text": {"value": previous_version}},
                    },
                    {
                        "id": "current_version",
                        "label": {"en": "Current Version"},
                        "field": {"text": {"value": current_version}},
                    },
                    {
                        "id": "remote_url",
                        "label": {"en": "Remote URL"},
                        "field": {"text": {"value": remote_url or "http://localhost"}},
                    },
                    {
                        "id": "remote_url_note",
                        "label": {"en": "Note"},
                        "field": {
                            "label": {
                                "value": {
                                    "en": "Use 'http://localhost' if this integration runs on the Remote. "
                                    "Otherwise, provide the Remote's IP address (e.g., 'http://192.168.1.100')."
                                }
                            }
                        },
                    },
                    {
                        "id": "pin",
                        "label": {"en": "Remote PIN"},
                        "field": {"text": {"value": pin}},
                    },
                ],
            )

        # At this point, all required fields are present
        assert current_version is not None, "current_version should be validated above"

        _LOG.info("Performing migration: %s -> %s", previous_version, current_version)

        try:
            # Get the migration data from the developer's implementation
            migration_data = await self.get_migration_data(
                previous_version, current_version
            )

            entity_count = len(migration_data.get("entity_mappings", []))
            _LOG.info(
                "Generated migration data: %d entity mappings, driver %s -> %s",
                entity_count,
                migration_data.get("previous_driver_id"),
                migration_data.get("new_driver_id"),
            )

            # Perform the migration on the Remote
            _LOG.info("Executing migration on Remote at %s", remote_url)
            success = await migrate_entities_on_remote(
                remote_url=remote_url,
                migration_data=migration_data,
                pin=pin,
            )

            if not success:
                _LOG.error("Migration failed on Remote")
                return SetupError(error_type=IntegrationSetupError.OTHER)

            _LOG.info("Migration completed successfully on Remote")

            # Check if this is a manager/automated flow
            # Manager sets automated=true to get migration data response instead of SetupComplete
            is_automated = (
                str(msg.input_values.get("automated", False)).strip().lower() == "true"
            )

            if is_automated:
                # Manager flow: return migration data for the manager to process
                _LOG.debug(
                    "Migration complete (automated flow) - returning migration data"
                )
                migration_json = json.dumps(migration_data, indent=2)

                return RequestUserInput(
                    {"en": "Migration Complete"},
                    [
                        {
                            "id": "migration_success",
                            "label": {"en": "Migration Status"},
                            "field": {"checkbox": {"value": True}},
                        },
                        {
                            "id": "migration_data",
                            "label": {"en": "Migration Data (JSON)"},
                            "field": {"textarea": {"value": migration_json}},
                        },
                    ],
                )
            else:
                # User flow: just complete the setup
                _LOG.info("Migration complete (user flow) - setup complete")
                return SetupComplete()

        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("Migration error: %s", err)
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

        **Using Device Class for Validation:**

        The framework provides `self.device_class` which you can use to call class methods
        for validation. This keeps validation logic with your device class:

            class MyDevice(StatelessHTTPDevice):
                @classmethod
                async def validate_connection(cls, host: str, token: str) -> dict:
                    '''Validate credentials and return device info.'''
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"http://{host}/api/info",
                                               headers={"Token": token}) as resp:
                            if resp.status != 200:
                                raise ConnectionError("Invalid credentials")
                            return await resp.json()

            # In your setup flow:
            async def query_device(self, input_values):
                try:
                    info = await self.device_class.validate_connection(
                        host=input_values["host"],
                        token=input_values["token"]
                    )
                    return MyDeviceConfig(
                        identifier=info["device_id"],
                        name=info["name"],
                        host=input_values["host"],
                        token=input_values["token"]
                    )
                except ConnectionError:
                    return SetupError(error_type=IntegrationSetupError.CONNECTION_REFUSED)

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

    async def handle_pre_discovery_response(
        self, msg: UserDataResponse
    ) -> SetupAction | None:
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

    async def is_migration_required(self, previous_version: str) -> bool:
        """
        Check if migration is required when upgrading from a previous version.

        This method is called by the integration manager during the upgrade process
        to determine if entity migration is needed. The manager will:
        1. Call this method with the previous integration version
        2. Read the response to determine if migration is needed
        3. If True, trigger the migration flow after upgrade completes

        Override this method to implement version-specific migration detection.
        The default implementation always returns False (no migration needed).

        :param previous_version: The previous integration version (e.g., "1.2.3")
        :return: True if migration is required, False otherwise

        Example - Simple version check:
            async def is_migration_required(self, previous_version: str) -> bool:
                # Migration needed for upgrades from v1.x to v2.x
                return previous_version.startswith("1.")

        Example - Specific version ranges:
            async def is_migration_required(self, previous_version: str) -> bool:
                from packaging import version
                prev = version.parse(previous_version)
                # Migration needed for versions below 2.0.0
                return prev < version.parse("2.0.0")

        Example - Configuration-based check:
            async def is_migration_required(self, previous_version: str) -> bool:
                # Check if config manager indicates migration is needed
                return self.config.migration_required()
        """
        _ = previous_version  # Mark as intentionally unused
        return False

    async def get_migration_data(
        self, previous_version: str, current_version: str
    ) -> MigrationData:
        """
        Get migration data with entity name mappings.

        This method is called by the integration manager after an upgrade when
        is_migration_required() returned True. It should return a list of entity
        name mappings that the manager will use to update entity references.

        The manager will handle:
        - Updating entity IDs in the Remote's configuration
        - Updating button/page mappings
        - Preserving user customizations

        Return format:
        {
            "previous_driver_id": "mydriver_v1",
            "new_driver_id": "mydriver_v2",
            "entity_mappings": [
                {"previous_entity_id": "media_player.tv", "new_entity_id": "player.tv"},
                {"previous_entity_id": "light.bedroom", "new_entity_id": "light.bed"},
            ]
        }

        :param previous_version: The previous integration version
        :param current_version: The current integration version
        :return: MigrationData dictionary with driver IDs and entity mappings

        Example - Simple entity rename:
            async def get_migration_data(self, previous_version, current_version):
                from .migration import EntityMigrationMapping

                mappings: list[EntityMigrationMapping] = []

                # Load all device configs
                for device in self.config.all():
                    # Old naming: {device_id}_player
                    # New naming: {device_id}.player
                    mappings.append({
                        "previous_entity_id": f"{device.identifier}_player",
                        "new_entity_id": f"{device.identifier}.player"
                    })

                return {
                    "previous_driver_id": "mydriver_v1",
                    "new_driver_id": "mydriver_v2",
                    "entity_mappings": mappings
                }

        Example - Using device class methods:
            async def get_migration_data(self, previous_version, current_version):
                from .migration import EntityMigrationMapping

                mappings: list[EntityMigrationMapping] = []

                for device in self.config.all():
                    # Use class method to generate entity IDs
                    old_entities = self.device_class.get_v1_entity_ids(device)
                    new_entities = self.device_class.get_v2_entity_ids(device)

                    for old, new in zip(old_entities, new_entities):
                        if old != new:
                            mappings.append({
                                "previous_entity_id": old,
                                "new_entity_id": new
                            })

                return {
                    "previous_driver_id": self.get_driver_id(previous_version),
                    "new_driver_id": self.get_driver_id(current_version),
                    "entity_mappings": mappings
                }

        Example - With migration logging:
            async def get_migration_data(self, previous_version, current_version):
                from .migration import EntityMigrationMapping

                _LOG.info("Migrating from %s to %s", previous_version, current_version)
                mappings: list[EntityMigrationMapping] = []

                for device in self.config.all():
                    device_mappings = self._migrate_device_entities(device)
                    mappings.extend(device_mappings)
                    _LOG.debug("Migrated %d entities for %s",
                              len(device_mappings), device.name)

                return {
                    "previous_driver_id": "myintegration",
                    "new_driver_id": "myintegration",  # Driver ID unchanged
                    "entity_mappings": mappings
                }
        """
        _ = previous_version  # Mark as intentionally unused
        _ = current_version
        return {"previous_driver_id": "", "new_driver_id": "", "entity_mappings": []}

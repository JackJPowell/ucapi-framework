"""Tests for BaseSetupFlow."""
# pylint: disable=redefined-outer-name,protected-access

import json
from dataclasses import dataclass

import pytest
from ucapi import (
    AbortDriverSetup,
    DriverSetupRequest,
    IntegrationSetupError,
    RequestUserInput,
    SetupComplete,
    SetupError,
    UserDataResponse,
)

from ucapi_framework.config import BaseConfigManager
from ucapi_framework.discovery import BaseDiscovery, DiscoveredDevice
from ucapi_framework.setup import BaseSetupFlow, SetupSteps


@dataclass
class DeviceConfigForTests:
    """Test device configuration."""

    identifier: str
    name: str
    address: str
    port: int = 8080


class DeviceManagerForTests(BaseConfigManager[DeviceConfigForTests]):
    """Test device manager implementation."""

    def deserialize_device(self, data: dict) -> DeviceConfigForTests | None:
        try:
            return DeviceConfigForTests(
                identifier=data.get("identifier", ""),
                name=data.get("name", ""),
                address=data.get("address", ""),
                port=data.get("port", 8080),
            )
        except (KeyError, TypeError, ValueError):
            return None


class DiscoveryForTests(BaseDiscovery):
    """Test discovery implementation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mock_devices = [
            DiscoveredDevice("dev1", "Device 1", "192.168.1.1"),
            DiscoveredDevice("dev2", "Device 2", "192.168.1.2"),
        ]

    async def discover(self):
        return self.mock_devices


class ConcreteSetupFlow(BaseSetupFlow[DeviceConfigForTests]):
    """Concrete setup flow implementation for testing."""

    async def discover_devices(self):
        if self.discovery:
            devices = await self.discovery.discover()
            # Store devices for later lookup
            self.discovery._discovered_devices = devices
            return devices
        return []

    async def prepare_input_from_discovery(self, discovered, additional_input):
        """Convert discovered device to input_values format."""
        # Map discovered device to the format expected by query_device
        return {
            "identifier": discovered.identifier,
            "name": discovered.name,
            "address": discovered.address,
            "port": discovered.extra_data.get("port", 8080)
            if discovered.extra_data
            else 8080,
            **{k: v for k, v in additional_input.items() if k != "choice"},
        }

    async def query_device(self, input_values):
        """Create device from input values (works for both manual and discovery)."""
        # Validate required fields
        identifier = input_values.get("identifier")
        name = input_values.get("name")
        address = input_values.get("address")

        if not identifier or not name or not address:
            raise ValueError(
                "Missing required fields: identifier, name, and address are required"
            )

        return DeviceConfigForTests(
            identifier=identifier,
            name=name,
            address=address,
            port=int(input_values.get("port", 8080)),
        )

    def get_manual_entry_form(self):
        """Get manual entry form."""
        return RequestUserInput(
            {"en": "Manual Entry"},
            [
                {
                    "id": "identifier",
                    "label": {"en": "Device ID"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "name",
                    "label": {"en": "Device Name"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "address",
                    "label": {"en": "IP Address"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "port",
                    "label": {"en": "Port"},
                    "field": {"number": {"value": 8080, "min": 1, "max": 65535}},
                },
            ],
        )


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary configuration directory."""
    return str(tmp_path)


@pytest.fixture
def config_manager(temp_config_dir):
    """Create a test configuration manager."""
    return DeviceManagerForTests(temp_config_dir)


@pytest.fixture
def discovery():
    """Create a test discovery instance."""
    return DiscoveryForTests()


@pytest.fixture
def setup_flow(config_manager, discovery):
    """Create a test setup flow instance."""
    return ConcreteSetupFlow(config_manager, discovery=discovery)


class TestBaseSetupFlow:
    """Tests for BaseSetupFlow."""

    def test_init(self, config_manager):
        """Test setup flow initialization."""
        flow = ConcreteSetupFlow(config_manager)

        assert flow.config == config_manager
        assert flow.discovery is None
        assert flow._setup_step == SetupSteps.INIT

    def test_init_with_discovery(self, config_manager, discovery):
        """Test initialization with discovery."""
        flow = ConcreteSetupFlow(config_manager, discovery=discovery)

        assert flow.discovery == discovery

    def test_create_handler_factory(self, config_manager):
        """Test create_handler factory method."""
        # Create a mock driver with config_manager property
        from unittest.mock import MagicMock

        mock_driver = MagicMock()
        mock_driver.config_manager = config_manager

        handler = ConcreteSetupFlow.create_handler(mock_driver)

        assert callable(handler)

    @pytest.mark.asyncio
    async def test_handle_driver_setup_initial(self, setup_flow):
        """Test handling initial driver setup request."""
        request = DriverSetupRequest(reconfigure=False, setup_data={})

        result = await setup_flow.handle_driver_setup(request)

        # Should return discovery screen or manual entry
        assert isinstance(result, RequestUserInput)

    @pytest.mark.asyncio
    async def test_handle_driver_setup_reconfigure(self, setup_flow, config_manager):
        """Test handling reconfigure request."""
        # Add a device to config first
        device = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config_manager.add_or_update(device)

        request = DriverSetupRequest(reconfigure=True, setup_data={})

        result = await setup_flow.handle_driver_setup(request)

        # Should return configuration mode screen
        assert isinstance(result, RequestUserInput)
        assert setup_flow._setup_step == SetupSteps.CONFIGURATION_MODE

    @pytest.mark.asyncio
    async def test_handle_abort(self, setup_flow):
        """Test handling abort message."""
        abort = AbortDriverSetup(error=IntegrationSetupError.OTHER)

        result = await setup_flow.handle_driver_setup(abort)

        assert isinstance(result, SetupError)
        assert setup_flow._setup_step == SetupSteps.INIT

    @pytest.mark.asyncio
    async def test_discovery_flow(self, setup_flow):
        """Test complete discovery flow."""
        # Start setup
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await setup_flow.handle_driver_setup(request)

        # Should show restore prompt
        assert isinstance(result, RequestUserInput)
        assert setup_flow._setup_step == SetupSteps.RESTORE_PROMPT

        # Skip restore
        user_response = UserDataResponse(input_values={"restore_from_backup": False})
        result = await setup_flow.handle_driver_setup(user_response)

        # Should show discovered devices
        assert isinstance(result, RequestUserInput)
        assert setup_flow._setup_step == SetupSteps.DISCOVER

        # Select a device
        user_response = UserDataResponse(input_values={"choice": "dev1"})
        result = await setup_flow.handle_driver_setup(user_response)

        # Should complete
        assert isinstance(
            result, (SetupComplete, RequestUserInput)
        )  # May have additional screens

    @pytest.mark.asyncio
    async def test_manual_entry_flow(self, setup_flow):
        """Test manual entry flow."""
        # Start setup
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Skip restore
        user_response = UserDataResponse(input_values={"restore_from_backup": False})
        await setup_flow.handle_driver_setup(user_response)

        # Select manual entry
        user_response = UserDataResponse(input_values={"choice": "manual"})
        result = await setup_flow.handle_driver_setup(user_response)

        # Should show manual entry form
        assert isinstance(result, RequestUserInput)
        assert setup_flow._setup_step == SetupSteps.MANUAL_ENTRY

        # Submit manual entry
        manual_data = UserDataResponse(
            input_values={
                "identifier": "manual-dev",
                "name": "Manual Device",
                "address": "192.168.1.99",
                "port": "9090",
            }
        )
        result = await setup_flow.handle_driver_setup(manual_data)

        # Should complete or show additional config
        assert isinstance(result, (SetupComplete, RequestUserInput))

    @pytest.mark.asyncio
    async def test_configuration_mode_add(self, setup_flow, config_manager):
        """Test configuration mode - add device."""
        # Start reconfigure with existing device
        device = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config_manager.add_or_update(device)

        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select add action
        user_response = UserDataResponse(
            input_values={"choice": "dev1", "action": "add"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should go to discovery or show pre-discovery/restore screens
        assert isinstance(result, RequestUserInput)

    @pytest.mark.asyncio
    async def test_configuration_mode_remove(self, setup_flow, config_manager):
        """Test configuration mode - remove device."""
        # Add devices
        device1 = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config_manager.add_or_update(device1)

        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select remove action
        user_response = UserDataResponse(
            input_values={"choice": "dev1", "action": "remove"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should complete
        assert isinstance(result, SetupComplete)
        assert not config_manager.contains("dev1")

    @pytest.mark.asyncio
    async def test_configuration_mode_reset(self, setup_flow, config_manager):
        """Test configuration mode - reset."""
        # Add devices
        config_manager.add_or_update(
            DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        )
        config_manager.add_or_update(
            DeviceConfigForTests("dev2", "Device 2", "192.168.1.2")
        )

        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select reset action
        user_response = UserDataResponse(
            input_values={"choice": "dev1", "action": "reset"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should show restore prompt
        assert isinstance(result, RequestUserInput)
        assert setup_flow._setup_step == SetupSteps.RESTORE_PROMPT

        # All devices should be cleared
        assert len(list(config_manager.all())) == 0

    @pytest.mark.asyncio
    async def test_backup(self, setup_flow, config_manager):
        """Test backup functionality."""
        # Add devices
        config_manager.add_or_update(
            DeviceConfigForTests("dev1", "Device 1", "192.168.1.1", 8080)
        )

        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select backup action
        user_response = UserDataResponse(
            input_values={"choice": "dev1", "action": "backup"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should show backup screen
        assert isinstance(result, RequestUserInput)
        assert setup_flow._setup_step == SetupSteps.BACKUP

        # User acknowledges backup
        ack_response = UserDataResponse(input_values={})
        result = await setup_flow.handle_driver_setup(ack_response)

        assert isinstance(result, SetupComplete)

    @pytest.mark.asyncio
    async def test_restore(self, setup_flow, config_manager):
        """Test restore functionality."""
        # Create backup data
        backup_data = json.dumps(
            [
                {
                    "identifier": "dev1",
                    "name": "Device 1",
                    "address": "192.168.1.1",
                    "port": 8080,
                },
                {
                    "identifier": "dev2",
                    "name": "Device 2",
                    "address": "192.168.1.2",
                    "port": 9090,
                },
            ]
        )

        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select restore action
        user_response = UserDataResponse(
            input_values={"choice": "", "action": "restore"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should show restore screen
        assert isinstance(result, RequestUserInput)
        assert setup_flow._setup_step == SetupSteps.RESTORE

        # Submit restore data
        restore_response = UserDataResponse(input_values={"restore_data": backup_data})
        result = await setup_flow.handle_driver_setup(restore_response)

        assert isinstance(result, SetupComplete)

        # Devices should be restored
        assert config_manager.contains("dev1")
        assert config_manager.contains("dev2")

    @pytest.mark.asyncio
    async def test_restore_prompt_accept(self, config_manager):
        """Test restore prompt when user chooses to restore."""
        flow = ConcreteSetupFlow(config_manager)

        # Start initial setup
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await flow.handle_driver_setup(request)

        # Should show restore prompt
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.RESTORE_PROMPT
        assert result.title.get("en") == "Restore Configuration?"

        # User chooses to restore
        restore_prompt_response = UserDataResponse(
            input_values={"restore_from_backup": True}
        )
        result = await flow.handle_driver_setup(restore_prompt_response)

        # Should show restore screen
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.RESTORE

    @pytest.mark.asyncio
    async def test_restore_prompt_skip(self, config_manager):
        """Test restore prompt when user skips restore."""
        flow = ConcreteSetupFlow(config_manager)

        # Start initial setup
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await flow.handle_driver_setup(request)

        # Should show restore prompt
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.RESTORE_PROMPT

        # User skips restore
        restore_prompt_response = UserDataResponse(
            input_values={"restore_from_backup": False}
        )
        result = await flow.handle_driver_setup(restore_prompt_response)

        # Should proceed to manual entry (no discovery)
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.MANUAL_ENTRY

    @pytest.mark.asyncio
    async def test_restore_prompt_custom_text(self, config_manager):
        """Test custom restore prompt text."""

        class CustomRestorePromptFlow(ConcreteSetupFlow):
            async def get_restore_prompt_text(self):
                return "Custom restore message for testing"

        flow = CustomRestorePromptFlow(config_manager)

        # Start initial setup
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await flow.handle_driver_setup(request)

        # Check custom text is used
        assert isinstance(result, RequestUserInput)
        info_field = next(f for f in result.settings if f["id"] == "info")
        assert (
            info_field["field"]["label"]["value"]["en"]
            == "Custom restore message for testing"
        )

    @pytest.mark.asyncio
    async def test_duplicate_device_rejected(self, setup_flow, config_manager):
        """Test that duplicate devices are rejected in add mode."""
        # Add existing device
        device = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config_manager.add_or_update(device)

        # Enable add mode
        setup_flow._add_mode = True

        # Check if trying to finalize a duplicate device returns an error
        result = await setup_flow._finalize_device_setup(device, {})

        assert isinstance(result, SetupError)
        assert result.error_type == IntegrationSetupError.OTHER

    @pytest.mark.asyncio
    async def test_get_device_id(self, setup_flow):
        """Test get_device_id method."""
        device = DeviceConfigForTests("dev-123", "Test Device", "192.168.1.1")

        device_id = setup_flow.get_device_id(device)

        assert device_id == "dev-123"

    @pytest.mark.asyncio
    async def test_get_device_name(self, setup_flow):
        """Test get_device_name method."""
        device = DeviceConfigForTests("dev-123", "Test Device", "192.168.1.1")

        name = setup_flow.get_device_name(device)

        assert name == "Test Device"

    def test_get_additional_discovery_fields_default(self, setup_flow):
        """Test default get_additional_discovery_fields returns empty list."""
        fields = setup_flow.get_additional_discovery_fields()

        assert fields == []

    def test_extract_additional_setup_data_default(self, setup_flow):
        """Test default extract_additional_setup_data returns empty dict."""
        data = setup_flow.extract_additional_setup_data({"field1": "value1"})

        assert data == {}

    @pytest.mark.asyncio
    async def test_get_pre_discovery_screen_default(self, setup_flow):
        """Test default get_pre_discovery_screen returns None."""
        screen = await setup_flow.get_pre_discovery_screen()

        assert screen is None

    @pytest.mark.asyncio
    async def test_handle_pre_discovery_response_default(self, setup_flow):
        """Test default handle_pre_discovery_response returns None."""
        msg = UserDataResponse(input_values={"field": "value"})

        result = await setup_flow.handle_pre_discovery_response(msg)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_additional_configuration_screen_default(self, setup_flow):
        """Test default get_additional_configuration_screen returns None."""
        device = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        screen = await setup_flow.get_additional_configuration_screen(device, {})

        assert screen is None

    @pytest.mark.asyncio
    async def test_handle_additional_configuration_response_default(self, setup_flow):
        """Test default handle_additional_configuration_response returns None."""
        msg = UserDataResponse(input_values={"field": "value"})

        result = await setup_flow.handle_additional_configuration_response(msg)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_device_mode(self, setup_flow, config_manager):
        """Test update mode (remove then re-add)."""
        # Add device
        device = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config_manager.add_or_update(device)

        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select update action
        user_response = UserDataResponse(
            input_values={"choice": "dev1", "action": "update"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Device should be removed
        assert not config_manager.contains("dev1")

        # Should show restore prompt or discovery
        assert isinstance(result, RequestUserInput)

    @pytest.mark.asyncio
    async def test_no_discovery_goes_to_manual(self, config_manager):
        """Test that without discovery, setup goes to restore prompt then manual entry."""
        flow = ConcreteSetupFlow(config_manager)

        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await flow.handle_driver_setup(request)

        # Should show restore prompt first
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.RESTORE_PROMPT

        # Skip restore
        user_response = UserDataResponse(input_values={"restore_from_backup": False})
        result = await flow.handle_driver_setup(user_response)

        # Should go to manual entry
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.MANUAL_ENTRY


class TestSetupSteps:
    """Tests for SetupSteps enum."""

    def test_setup_steps_values(self):
        """Test SetupSteps enum values."""
        assert SetupSteps.INIT == 0
        assert SetupSteps.CONFIGURATION_MODE == 1
        assert SetupSteps.RESTORE_PROMPT == 2
        assert SetupSteps.PRE_DISCOVERY == 3
        assert SetupSteps.DISCOVER == 4
        assert SetupSteps.DEVICE_CHOICE == 5
        assert SetupSteps.MANUAL_ENTRY == 6
        assert SetupSteps.BACKUP == 7
        assert SetupSteps.RESTORE == 8


class TestSetupFlowAdvanced:
    """Advanced setup flow tests."""

    @pytest.mark.asyncio
    async def test_pre_discovery_flow(self, config_manager):
        """Test pre-discovery configuration flow."""

        class PreDiscoverySetupFlow(ConcreteSetupFlow):
            async def get_pre_discovery_screen(self):
                return RequestUserInput(
                    {"en": "Pre-Discovery Config"},
                    [
                        {
                            "id": "api_key",
                            "label": {"en": "API Key"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

            async def handle_pre_discovery_response(self, msg):
                # Store the API key
                self._pre_discovery_data["api_key"] = msg.input_values.get("api_key")
                return None  # Proceed to discovery

        flow = PreDiscoverySetupFlow(config_manager, discovery=DiscoveryForTests())

        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await flow.handle_driver_setup(request)

        # Should show restore prompt first
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.RESTORE_PROMPT

        # Skip restore
        restore_response = UserDataResponse(input_values={"restore_from_backup": False})
        result = await flow.handle_driver_setup(restore_response)

        # Should show pre-discovery screen
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.PRE_DISCOVERY

        # Submit pre-discovery data
        user_response = UserDataResponse(input_values={"api_key": "test-key-123"})
        result = await flow.handle_driver_setup(user_response)

        # Should proceed to discovery
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.DISCOVER
        assert flow._pre_discovery_data["api_key"] == "test-key-123"

    @pytest.mark.asyncio
    async def test_additional_configuration_flow(self, config_manager, discovery):
        """Test additional configuration screens after device creation."""

        class AdditionalConfigSetupFlow(ConcreteSetupFlow):
            async def get_additional_configuration_screen(
                self, device_config, previous_input
            ):
                return RequestUserInput(
                    {"en": "Additional Config"},
                    [
                        {
                            "id": "zone",
                            "label": {"en": "Zone"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

            async def handle_additional_configuration_response(self, msg):
                # Update pending device config
                _ = msg.input_values.get("zone")  # Would be used in real implementation
                # In real implementation, you'd add this to device config
                return None  # Complete setup

        flow = AdditionalConfigSetupFlow(config_manager, discovery=discovery)

        request = DriverSetupRequest(reconfigure=False, setup_data={})
        await flow.handle_driver_setup(request)

        # Skip restore
        restore_response = UserDataResponse(input_values={"restore_from_backup": False})
        await flow.handle_driver_setup(restore_response)

        # Select device
        user_response = UserDataResponse(input_values={"choice": "dev1"})
        result = await flow.handle_driver_setup(user_response)

        # Should show additional config screen
        assert isinstance(result, RequestUserInput)

        # Submit additional config
        additional_response = UserDataResponse(input_values={"zone": "Living Room"})
        result = await flow.handle_driver_setup(additional_response)

        # Should complete
        assert isinstance(result, SetupComplete)

    @pytest.mark.asyncio
    async def test_error_handling_invalid_json_restore(self, setup_flow):
        """Test error handling for invalid JSON during restore."""
        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select restore
        user_response = UserDataResponse(
            input_values={"choice": "", "action": "restore"}
        )
        await setup_flow.handle_driver_setup(user_response)

        # Submit invalid JSON
        restore_response = UserDataResponse(
            input_values={"restore_data": "invalid json {"}
        )
        result = await setup_flow.handle_driver_setup(restore_response)

        assert isinstance(result, SetupError)

    @pytest.mark.asyncio
    async def test_discovery_device_not_found_shows_manual_entry(self, setup_flow):
        """Test fallback to manual entry when discovered device not found."""
        # Simulate selecting a device that doesn't exist in discovery results
        msg = UserDataResponse(input_values={"choice": "nonexistent"})
        setup_flow._setup_step = SetupSteps.DISCOVER

        result = await setup_flow._handle_device_selection(msg)

        # Should fall back to manual entry form
        assert isinstance(result, RequestUserInput)
        assert setup_flow._setup_step == SetupSteps.MANUAL_ENTRY

    @pytest.mark.asyncio
    async def test_handler_factory_creates_instance_on_first_call(self, config_manager):
        """Test that create_handler factory creates instance lazily."""
        # Create a mock driver with config_manager property
        from unittest.mock import MagicMock

        mock_driver = MagicMock()
        mock_driver.config_manager = config_manager

        handler = ConcreteSetupFlow.create_handler(mock_driver)

        # First call should create the instance
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await handler(request)

        assert isinstance(result, RequestUserInput)

        # Second call should reuse the same instance
        result2 = await handler(request)
        assert isinstance(result2, RequestUserInput)

    @pytest.mark.asyncio
    async def test_discovery_with_no_discovery_class(self, config_manager):
        """Test setup flow when no discovery class is provided."""
        setup_flow = ConcreteSetupFlow(config_manager)

        # Start setup
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await setup_flow.handle_driver_setup(request)

        # Should skip discovery and go to manual entry
        assert isinstance(result, RequestUserInput)

    @pytest.mark.asyncio
    async def test_handle_discovered_device_selection_error(
        self, setup_flow, config_manager
    ):
        """Test handling invalid device selection from discovery."""
        # Add a discovered device
        device = DiscoveredDevice("dev1", "Device 1", "192.168.1.1")
        setup_flow.discovery._discovered_devices.append(device)

        setup_flow._setup_step = SetupSteps.DEVICE_CHOICE

        # Select invalid device
        user_response = UserDataResponse(input_values={"choice": "invalid_id"})
        result = await setup_flow.handle_driver_setup(user_response)

        # Should return error
        assert isinstance(result, SetupError)

    @pytest.mark.asyncio
    async def test_handle_manual_entry_with_validation_error(self, setup_flow):
        """Test manual entry with validation errors."""
        setup_flow._setup_step = SetupSteps.MANUAL_ENTRY

        # Provide invalid input that will trigger create_device_from_user_input error
        user_response = UserDataResponse(input_values={})
        result = await setup_flow.handle_driver_setup(user_response)

        assert isinstance(result, SetupError)

    @pytest.mark.asyncio
    async def test_backup_returns_screen(self, setup_flow, config_manager):
        """Test backup flow returns backup screen."""
        # Add devices
        device1 = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config_manager.add_or_update(device1)

        # Start reconfigure flow
        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select backup
        user_response = UserDataResponse(
            input_values={"choice": "", "action": "backup"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should return backup screen with data
        assert isinstance(result, RequestUserInput)
        assert result.title.get("en") == "Configuration Backup"

    @pytest.mark.asyncio
    async def test_pre_discovery_screen_flow(self, config_manager, discovery):
        """Test pre-discovery screen in full flow."""

        class PreDiscoverySetupFlow(ConcreteSetupFlow):
            async def get_pre_discovery_screen(self):
                return RequestUserInput(
                    title="Pre-Discovery",
                    settings=[
                        {
                            "id": "zone",
                            "label": {"en": "Zone"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

            async def handle_pre_discovery_response(self, user_input):
                self._pre_discovery_data = user_input
                return None  # Continue with discovery

        setup_flow = PreDiscoverySetupFlow(config_manager, discovery=discovery)

        # Start setup
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await setup_flow.handle_driver_setup(request)

        # Should show restore prompt first
        assert isinstance(result, RequestUserInput)
        assert result.title.get("en") == "Restore Configuration?"

        # Skip restore
        user_response = UserDataResponse(input_values={"restore_from_backup": False})
        result = await setup_flow.handle_driver_setup(user_response)

        # Should show pre-discovery screen
        assert isinstance(result, RequestUserInput)
        assert result.title == "Pre-Discovery"

        # Submit pre-discovery data
        user_response = UserDataResponse(input_values={"zone": "living_room"})
        result = await setup_flow.handle_driver_setup(user_response)

        # Should proceed to discovery or device choice
        assert isinstance(result, RequestUserInput)

    @pytest.mark.asyncio
    async def test_additional_configuration_screen_flow(
        self, config_manager, discovery
    ):
        """Test additional configuration screen after device selection."""

        class AdditionalConfigSetupFlow(ConcreteSetupFlow):
            async def get_additional_configuration_screen(
                self, device_config, previous_input
            ):
                return RequestUserInput(
                    title="Additional Config",
                    settings=[
                        {
                            "id": "option",
                            "label": {"en": "Option"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

            async def handle_additional_configuration_response(
                self, device_config, user_input
            ):
                # Modify config with additional data
                return device_config

        setup_flow = AdditionalConfigSetupFlow(config_manager, discovery=discovery)

        # Start setup and go through manual entry
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Assume we're at manual entry
        setup_flow._setup_step = SetupSteps.MANUAL_ENTRY

        # Submit device data
        user_response = UserDataResponse(
            input_values={
                "identifier": "dev1",
                "name": "Device 1",
                "address": "192.168.1.1",
            }
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should show additional configuration screen
        assert isinstance(result, RequestUserInput)
        assert result.title == "Additional Config"

    @pytest.mark.asyncio
    async def test_update_mode_removes_existing_device(
        self, setup_flow, config_manager
    ):
        """Test update mode removes existing device before re-adding."""
        # Add existing device
        device = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config_manager.add_or_update(device)

        # Start reconfigure
        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select update mode
        user_response = UserDataResponse(
            input_values={"choice": "dev1", "action": "update"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should proceed to discovery or manual entry
        assert isinstance(result, RequestUserInput)

    @pytest.mark.asyncio
    async def test_update_mode_with_invalid_device(self, setup_flow, config_manager):
        """Test update mode with device that doesn't exist."""
        # Start reconfigure
        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Try to update nonexistent device
        user_response = UserDataResponse(
            input_values={"choice": "invalid_device", "action": "update"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should return error
        assert isinstance(result, SetupError)

    @pytest.mark.asyncio
    async def test_remove_mode_with_invalid_device(self, setup_flow, config_manager):
        """Test remove mode with device that doesn't exist."""
        # Start reconfigure
        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Try to remove nonexistent device
        user_response = UserDataResponse(
            input_values={"choice": "invalid_device", "action": "remove"}
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should return error
        assert isinstance(result, SetupError)

    @pytest.mark.asyncio
    async def test_pre_discovery_response_error_handling(
        self, config_manager, discovery
    ):
        """Test error handling in pre-discovery response."""

        class ErrorPreDiscoveryFlow(ConcreteSetupFlow):
            async def get_pre_discovery_screen(self):
                return RequestUserInput(
                    title="Pre-Discovery",
                    settings=[
                        {
                            "id": "zone",
                            "label": {"en": "Zone"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

            async def handle_pre_discovery_response(self, user_input):
                raise RuntimeError("Pre-discovery error")

        setup_flow = ErrorPreDiscoveryFlow(config_manager, discovery=discovery)

        # Start setup
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Submit pre-discovery data that will cause error
        setup_flow._setup_step = SetupSteps.PRE_DISCOVERY
        user_response = UserDataResponse(input_values={"zone": "living_room"})
        result = await setup_flow.handle_driver_setup(user_response)

        # Should return error
        assert isinstance(result, SetupError)

    @pytest.mark.asyncio
    async def test_manual_entry_with_creation_error(self, setup_flow):
        """Test manual entry when device creation fails."""
        setup_flow._setup_step = SetupSteps.MANUAL_ENTRY

        # Provide incomplete input that will fail
        user_response = UserDataResponse(
            input_values={"identifier": "dev1"}  # Missing required fields
        )
        result = await setup_flow.handle_driver_setup(user_response)

        assert isinstance(result, SetupError)

    @pytest.mark.asyncio
    async def test_restore_with_empty_data(self, setup_flow):
        """Test restore with empty restore data."""
        # Start reconfigure
        request = DriverSetupRequest(reconfigure=True, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Select restore
        user_response = UserDataResponse(
            input_values={"choice": "", "action": "restore"}
        )
        await setup_flow.handle_driver_setup(user_response)

        # Submit empty restore data
        restore_response = UserDataResponse(input_values={"restore_data": ""})
        result = await setup_flow.handle_driver_setup(restore_response)

        assert isinstance(result, SetupError)

    @pytest.mark.asyncio
    async def test_additional_config_returns_screen(self, config_manager, discovery):
        """Test additional configuration that returns another screen."""

        class MultiScreenFlow(ConcreteSetupFlow):
            async def get_additional_configuration_screen(
                self, device_config, previous_input
            ):
                if "step2" not in previous_input:
                    return RequestUserInput(
                        title="Step 2",
                        settings=[
                            {
                                "id": "step2",
                                "label": {"en": "Step 2"},
                                "field": {"text": {"value": ""}},
                            }
                        ],
                    )
                return None

            async def handle_additional_configuration_response(
                self, device_config, user_input
            ):
                return device_config

        setup_flow = MultiScreenFlow(config_manager, discovery=discovery)

        # Go through manual entry
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        await setup_flow.handle_driver_setup(request)

        setup_flow._setup_step = SetupSteps.MANUAL_ENTRY
        user_response = UserDataResponse(
            input_values={
                "identifier": "dev1",
                "name": "Device 1",
                "address": "192.168.1.1",
            }
        )
        result = await setup_flow.handle_driver_setup(user_response)

        # Should show first additional config screen
        assert isinstance(result, RequestUserInput)
        assert result.title == "Step 2"

    @pytest.mark.asyncio
    async def test_pre_discovery_returns_screen(self, config_manager, discovery):
        """Test pre-discovery that returns a screen to interrupt flow."""

        class InterruptingPreDiscoveryFlow(ConcreteSetupFlow):
            async def get_pre_discovery_screen(self):
                return RequestUserInput(
                    title="Pre-Discovery",
                    settings=[
                        {
                            "id": "zone",
                            "label": {"en": "Zone"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

            async def handle_pre_discovery_response(self, user_input):
                # Return another screen to interrupt
                return RequestUserInput(
                    title="Interrupted",
                    settings=[
                        {
                            "id": "confirm",
                            "label": {"en": "Confirm"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

        setup_flow = InterruptingPreDiscoveryFlow(config_manager, discovery=discovery)

        # Start setup
        request = DriverSetupRequest(reconfigure=False, setup_data={})
        await setup_flow.handle_driver_setup(request)

        # Submit pre-discovery data
        setup_flow._setup_step = SetupSteps.PRE_DISCOVERY
        user_response = UserDataResponse(input_values={"zone": "living_room"})
        result = await setup_flow.handle_driver_setup(user_response)

        # Should show the interrupting screen
        assert isinstance(result, RequestUserInput)
        assert result.title == "Interrupted"


class TestSetupFlowDiscoveryErrorHandling:
    """Test discovery error handling paths."""

    @pytest.mark.asyncio
    async def test_discover_devices_with_exception(self, config_manager):
        """Test that discover_devices handles exceptions gracefully."""

        class FailingDiscovery:
            """Mock discovery that raises exception."""

            async def discover(self):
                raise RuntimeError("Discovery failed!")

        class TestSetupFlow(BaseSetupFlow):
            """Test flow with failing discovery."""

            async def prepare_input_from_discovery(self, discovered, additional_input):
                """Convert discovered device to input format."""
                return {
                    "identifier": discovered.identifier,
                    "name": discovered.name,
                    **additional_input,
                }

            async def get_pre_discovery_screen(self):
                return None

            async def get_additional_config_screen(
                self, device_id, additional_data=None
            ):
                return None

            async def query_device(self, input_values):
                """Required abstract method."""
                _ = input_values  # Unused in test
                return {"id": "manual"}

            def get_manual_entry_form(self):
                """Required abstract method."""
                return RequestUserInput(
                    {"en": "Manual Entry"},
                    [
                        {
                            "id": "id",
                            "label": {"en": "ID"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

        setup_flow = TestSetupFlow(config_manager, discovery=FailingDiscovery())

        # Call discover_devices directly - should return empty list
        devices = await setup_flow.discover_devices()
        assert devices == []

    @pytest.mark.asyncio
    async def test_discovery_uses_default_prepare_input(self, config_manager):
        """Test discovery uses default prepare_input_from_discovery implementation."""

        from ucapi_framework.discovery import DiscoveredDevice

        class DummyDiscovery:
            """Mock discovery."""

            def __init__(self):
                self.devices = [
                    DiscoveredDevice(
                        identifier="test_device",
                        name="Test Device",
                        address="192.168.1.100",
                    )
                ]

            async def discover(self):
                return self.devices

        class MinimalSetupFlow(BaseSetupFlow):
            """Setup flow that uses default prepare_input_from_discovery."""

            async def query_device(self, input_values):
                """Create device from input values."""
                return DeviceConfigForTests(
                    identifier=input_values["identifier"],
                    name=input_values["name"],
                    address=input_values["address"],
                )

            def get_manual_entry_form(self):
                """Required abstract method."""
                return RequestUserInput(
                    {"en": "Manual Entry"},
                    [
                        {
                            "id": "id",
                            "label": {"en": "ID"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

        # Use setup flow with default prepare_input_from_discovery
        discovery = DummyDiscovery()
        setup_flow = MinimalSetupFlow(config_manager, discovery=discovery)

        # Test the default prepare_input_from_discovery
        discovered = discovery.devices[0]
        input_values = await setup_flow.prepare_input_from_discovery(
            discovered, {"extra": "data"}
        )

        # Should map to default fields matching DiscoveredDevice attributes
        assert input_values["identifier"] == "test_device"
        assert input_values["address"] == "192.168.1.100"
        assert input_values["name"] == "Test Device"
        assert input_values["extra"] == "data"


class TestSetupFlowReturnTypes:
    """Test the new return type flexibility for device creation methods."""

    @pytest.mark.asyncio
    async def test_manual_entry_returns_setup_error(self, config_manager, discovery):
        """Test that manual entry can return SetupError directly."""

        class ErrorReturningSetupFlow(BaseSetupFlow[DeviceConfigForTests]):
            """Setup flow that returns errors from manual entry."""

            async def query_device(self, input_values):
                """Return error if validation fails."""
                host = input_values.get("host", "").strip()
                if not host:
                    return SetupError(
                        error_type=IntegrationSetupError.CONNECTION_REFUSED
                    )
                return DeviceConfigForTests(
                    identifier="test", name="Test", address=host
                )

            def get_manual_entry_form(self):
                """Required abstract method."""
                return RequestUserInput(
                    {"en": "Manual Entry"},
                    [
                        {
                            "id": "host",
                            "label": {"en": "Host"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

        setup_flow = ErrorReturningSetupFlow(config_manager, discovery=discovery)
        setup_flow._setup_step = SetupSteps.MANUAL_ENTRY

        # Test with missing host
        msg = UserDataResponse(input_values={"host": ""})
        result = await setup_flow._handle_manual_entry_response(msg)

        assert isinstance(result, SetupError)
        assert result.error_type == IntegrationSetupError.CONNECTION_REFUSED

    @pytest.mark.asyncio
    async def test_manual_entry_returns_request_user_input(
        self, config_manager, discovery
    ):
        """Test that manual entry can return RequestUserInput to re-show form."""

        class FormRedisplaySetupFlow(BaseSetupFlow[DeviceConfigForTests]):
            """Setup flow that re-displays form with validation errors."""

            async def query_device(self, input_values):
                """Re-display form if validation fails."""
                identifier = input_values.get("identifier", "").strip()
                if not identifier:
                    return RequestUserInput(
                        {"en": "Invalid Input"},
                        [
                            {
                                "id": "error",
                                "label": {"en": "Error"},
                                "field": {
                                    "label": {"value": {"en": "Identifier is required"}}
                                },
                            },
                            {
                                "id": "identifier",
                                "label": {"en": "Identifier"},
                                "field": {"text": {"value": ""}},
                            },
                        ],
                    )
                return DeviceConfigForTests(
                    identifier=identifier, name="Test", address="127.0.0.1"
                )

            def get_manual_entry_form(self):
                """Required abstract method."""
                return RequestUserInput(
                    {"en": "Manual Entry"},
                    [
                        {
                            "id": "identifier",
                            "label": {"en": "Identifier"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

        setup_flow = FormRedisplaySetupFlow(config_manager, discovery=discovery)
        setup_flow._setup_step = SetupSteps.MANUAL_ENTRY

        # Test with missing identifier
        msg = UserDataResponse(input_values={"identifier": ""})
        result = await setup_flow._handle_manual_entry_response(msg)

        assert isinstance(result, RequestUserInput)
        assert result.title == {"en": "Invalid Input"}
        assert len(result.settings) == 2
        assert result.settings[0]["id"] == "error"

    @pytest.mark.asyncio
    async def test_discovery_returns_setup_error(self, config_manager, discovery):
        """Test that discovery device creation can return SetupError directly."""

        class ErrorReturningDiscoveryFlow(BaseSetupFlow[DeviceConfigForTests]):
            """Setup flow that returns errors from discovery."""

            async def prepare_input_from_discovery(self, discovered, additional_input):
                """Convert discovered device to input format."""
                return {
                    "identifier": discovered.identifier,
                    "name": discovered.name,
                    "address": discovered.address,
                    **additional_input,
                }

            async def query_device(self, input_values):
                """Return error if device connection fails."""
                if input_values.get("identifier") == "unreachable":
                    return SetupError(
                        error_type=IntegrationSetupError.CONNECTION_REFUSED
                    )
                return DeviceConfigForTests(
                    identifier=input_values["identifier"],
                    name=input_values["name"],
                    address=input_values.get("address", "127.0.0.1"),
                )

            def get_manual_entry_form(self):
                """Required abstract method."""
                return RequestUserInput(
                    {"en": "Manual Entry"},
                    [{"id": "id", "field": {"text": {"value": ""}}}],
                )

        setup_flow = ErrorReturningDiscoveryFlow(config_manager, discovery=discovery)
        setup_flow._setup_step = SetupSteps.DISCOVER

        # Add the "unreachable" device to mock discovery
        from ucapi_framework.discovery import DiscoveredDevice

        unreachable_device = DiscoveredDevice(
            "unreachable", "Unreachable Device", "192.168.1.99"
        )
        discovery._discovered_devices.append(unreachable_device)

        # Test with unreachable device
        msg = UserDataResponse(input_values={"choice": "unreachable"})
        result = await setup_flow._handle_device_selection(msg)

        assert isinstance(result, SetupError)
        assert result.error_type == IntegrationSetupError.CONNECTION_REFUSED

    @pytest.mark.asyncio
    async def test_discovery_returns_request_user_input(
        self, config_manager, discovery
    ):
        """Test that discovery device creation can return RequestUserInput for auth."""

        class AuthRequestingDiscoveryFlow(BaseSetupFlow[DeviceConfigForTests]):
            """Setup flow that requests authentication during discovery."""

            async def prepare_input_from_discovery(self, discovered, additional_input):
                """Convert discovered device to input format."""
                return {
                    "identifier": discovered.identifier,
                    "name": discovered.name,
                    "address": discovered.address,
                    **additional_input,
                }

            async def query_device(self, input_values):
                """Request authentication if not provided."""
                password = input_values.get("password")
                if not password:
                    return RequestUserInput(
                        {"en": "Authentication Required"},
                        [
                            {
                                "id": "password",
                                "label": {"en": "Password"},
                                "field": {"text": {"value": ""}},
                            }
                        ],
                    )
                return DeviceConfigForTests(
                    identifier=input_values["identifier"],
                    name=input_values["name"],
                    address=input_values.get("address", "127.0.0.1"),
                )

            def get_manual_entry_form(self):
                """Required abstract method."""
                return RequestUserInput(
                    {"en": "Manual Entry"},
                    [{"id": "id", "field": {"text": {"value": ""}}}],
                )

        setup_flow = AuthRequestingDiscoveryFlow(config_manager, discovery=discovery)
        setup_flow._setup_step = SetupSteps.DISCOVER

        # Populate discovered devices (normally done by discover())
        discovery._discovered_devices = await discovery.discover()

        # Test with missing password
        msg = UserDataResponse(input_values={"choice": "dev1"})
        result = await setup_flow._handle_device_selection(msg)

        assert isinstance(result, RequestUserInput)
        assert result.title == {"en": "Authentication Required"}
        assert result.settings[0]["id"] == "password"

    @pytest.mark.asyncio
    async def test_manual_entry_returns_valid_config(self, config_manager, discovery):
        """Test that manual entry still works when returning valid config."""

        class StandardSetupFlow(BaseSetupFlow[DeviceConfigForTests]):
            """Standard setup flow that returns config."""

            async def query_device(self, input_values):
                """Return valid config."""
                return DeviceConfigForTests(
                    identifier="test",
                    name="Test Device",
                    address=input_values.get("address", "127.0.0.1"),
                )

            def get_manual_entry_form(self):
                """Required abstract method."""
                return RequestUserInput(
                    {"en": "Manual Entry"},
                    [
                        {
                            "id": "address",
                            "label": {"en": "Address"},
                            "field": {"text": {"value": ""}},
                        }
                    ],
                )

        setup_flow = StandardSetupFlow(config_manager, discovery=discovery)
        setup_flow._setup_step = SetupSteps.MANUAL_ENTRY

        # Test with valid input
        msg = UserDataResponse(input_values={"address": "192.168.1.100"})
        result = await setup_flow._handle_manual_entry_response(msg)

        assert isinstance(result, SetupComplete)
        assert config_manager.contains("test")

    @pytest.mark.asyncio
    async def test_discovery_returns_valid_config(self, config_manager, discovery):
        """Test that discovery still works when returning valid config."""

        class StandardDiscoveryFlow(BaseSetupFlow[DeviceConfigForTests]):
            """Standard setup flow that returns config from discovery."""

            async def prepare_input_from_discovery(self, discovered, additional_input):
                """Convert discovered device to input format."""
                return {
                    "identifier": discovered.identifier,
                    "name": discovered.name,
                    "address": discovered.address,
                    **additional_input,
                }

            async def query_device(self, input_values):
                """Return valid config for both discovery and manual."""
                return DeviceConfigForTests(
                    identifier=input_values.get("identifier", "manual"),
                    name=input_values.get("name", "Manual"),
                    address=input_values.get("address", "127.0.0.1"),
                )

            def get_manual_entry_form(self):
                """Required abstract method."""
                return RequestUserInput(
                    {"en": "Manual Entry"},
                    [{"id": "id", "field": {"text": {"value": ""}}}],
                )

        setup_flow = StandardDiscoveryFlow(config_manager, discovery=discovery)
        setup_flow._setup_step = SetupSteps.DISCOVER

        # Populate discovered devices (normally done by discover())
        discovery._discovered_devices = await discovery.discover()

        # Test with valid device
        msg = UserDataResponse(input_values={"choice": "dev1"})
        result = await setup_flow._handle_device_selection(msg)

        assert isinstance(result, SetupComplete)
        assert config_manager.contains("dev1")


class TestAdditionalConfigurationReturnTypes:
    """Test different return types from handle_additional_configuration_response."""

    @pytest.mark.asyncio
    async def test_additional_config_returns_device_config(self, config_manager):
        """Test returning a complete device config from additional configuration."""

        class FlowWithAdditionalConfigReturningDevice(BaseSetupFlow):
            """Flow that returns a device config from additional configuration."""

            def __init__(self, config, **kwargs):
                super().__init__(config, **kwargs)
                self.config_returned = False

            async def query_device(self, input_values):
                # Create initial partial device
                return DeviceConfigForTests(
                    identifier=input_values["id"],
                    name="Partial Device",
                    address="192.168.1.100",
                    port=8080,
                )

            async def get_additional_configuration_screen(
                self, device_config, previous_input
            ):
                # Show additional screen to collect more data
                return RequestUserInput(
                    {"en": "Additional Config"},
                    [
                        {"id": "token", "field": {"text": {"value": ""}}},
                        {"id": "zone", "field": {"number": {"value": 1}}},
                    ],
                )

            async def handle_additional_configuration_response(self, msg):
                # Return a complete device config (Pattern 2 from docstring)
                token = msg.input_values["token"]
                zone = msg.input_values["zone"]

                # Create and return complete device config
                self.config_returned = True
                return DeviceConfigForTests(
                    identifier=self._pending_device_config.identifier,
                    name=f"Device Zone {zone}",
                    address=self._pending_device_config.address,
                    port=int(token),  # Use token as port for testing
                )

            def get_manual_entry_form(self):
                return RequestUserInput(
                    {"en": "Manual"}, [{"id": "id", "field": {"text": {"value": ""}}}]
                )

        setup_flow = FlowWithAdditionalConfigReturningDevice(config_manager)
        setup_flow._setup_step = SetupSteps.MANUAL_ENTRY

        # Simulate manual entry
        msg1 = UserDataResponse(input_values={"id": "test-device"})
        result1 = await setup_flow._handle_manual_entry_response(msg1)

        # Should get additional config screen
        assert isinstance(result1, RequestUserInput)
        assert result1.title == {"en": "Additional Config"}

        # Simulate additional config response with device config return
        msg2 = UserDataResponse(input_values={"token": "9090", "zone": "3"})
        result2 = await setup_flow._handle_additional_configuration_response(msg2)

        # Should complete setup
        assert isinstance(result2, SetupComplete)
        assert setup_flow.config_returned is True

        # Verify device was saved with the returned config
        assert config_manager.contains("test-device")
        device = config_manager.get("test-device")
        assert device.name == "Device Zone 3"
        assert device.port == 9090  # Token used as port

    @pytest.mark.asyncio
    async def test_additional_config_modifies_pending_returns_none(
        self, config_manager
    ):
        """Test modifying pending config and returning None (Pattern 1)."""

        class FlowWithAdditionalConfigModifyingPending(BaseSetupFlow):
            """Flow that modifies pending config and returns None."""

            async def query_device(self, input_values):
                return DeviceConfigForTests(
                    identifier=input_values["id"],
                    name="Initial Name",
                    address="192.168.1.100",
                    port=8080,
                )

            async def get_additional_configuration_screen(
                self, device_config, previous_input
            ):
                return RequestUserInput(
                    {"en": "Additional Config"},
                    [{"id": "new_port", "field": {"number": {"value": 9000}}}],
                )

            async def handle_additional_configuration_response(self, msg):
                # Modify pending config and return None (Pattern 1 from docstring)
                self._pending_device_config.port = msg.input_values["new_port"]
                return None

            def get_manual_entry_form(self):
                return RequestUserInput(
                    {"en": "Manual"}, [{"id": "id", "field": {"text": {"value": ""}}}]
                )

        setup_flow = FlowWithAdditionalConfigModifyingPending(config_manager)
        setup_flow._setup_step = SetupSteps.MANUAL_ENTRY

        # Simulate manual entry
        msg1 = UserDataResponse(input_values={"id": "test-device-2"})
        result1 = await setup_flow._handle_manual_entry_response(msg1)

        # Should get additional config screen
        assert isinstance(result1, RequestUserInput)

        # Simulate additional config response with None return
        msg2 = UserDataResponse(input_values={"new_port": 7070})
        result2 = await setup_flow._handle_additional_configuration_response(msg2)

        # Should complete setup
        assert isinstance(result2, SetupComplete)

        # Verify device was saved with modified pending config
        assert config_manager.contains("test-device-2")
        device = config_manager.get("test-device-2")
        assert device.port == 7070

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

from ucapi_framework.config import BaseDeviceManager
from ucapi_framework.discovery import BaseDiscovery, DiscoveredDevice
from ucapi_framework.setup import BaseSetupFlow, SetupSteps


@dataclass
class DeviceConfigForTests:
    """Test device configuration."""

    identifier: str
    name: str
    address: str
    port: int = 8080


class DeviceManagerForTests(BaseDeviceManager[DeviceConfigForTests]):
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
            return await self.discovery.discover()
        return []

    async def create_device_from_discovery(self, device_id, additional_data=None):
        """Create device from discovered device."""
        # Validate that device exists in discovered devices
        if self.discovery:
            discovered = await self.discovery.discover()
            if not any(d.identifier == device_id for d in discovered):
                raise ValueError(f"Device {device_id} not found")

        return DeviceConfigForTests(
            identifier=device_id,
            name=f"Device {device_id}",
            address="192.168.1.100",
        )

    async def create_device_from_manual_entry(self, input_values):
        """Create device from manual entry."""
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
        handler = ConcreteSetupFlow.create_handler(config_manager)

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

        # Should go to discovery
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

        # Should go to discovery
        assert isinstance(result, RequestUserInput)

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

        # Should go to discovery
        assert isinstance(result, RequestUserInput)

    @pytest.mark.asyncio
    async def test_no_discovery_goes_to_manual(self, config_manager):
        """Test that without discovery, setup goes straight to manual entry."""
        flow = ConcreteSetupFlow(config_manager)

        request = DriverSetupRequest(reconfigure=False, setup_data={})
        result = await flow.handle_driver_setup(request)

        # Should go to manual entry
        assert isinstance(result, RequestUserInput)
        assert flow._setup_step == SetupSteps.MANUAL_ENTRY


class TestSetupSteps:
    """Tests for SetupSteps enum."""

    def test_setup_steps_values(self):
        """Test SetupSteps enum values."""
        assert SetupSteps.INIT == 0
        assert SetupSteps.CONFIGURATION_MODE == 1
        assert SetupSteps.PRE_DISCOVERY == 2
        assert SetupSteps.DISCOVER == 3
        assert SetupSteps.DEVICE_CHOICE == 4
        assert SetupSteps.MANUAL_ENTRY == 5
        assert SetupSteps.BACKUP == 6
        assert SetupSteps.RESTORE == 7


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
    async def test_create_device_from_discovery_not_found(self, setup_flow):
        """Test error when device not found during creation from discovery."""
        with pytest.raises(ValueError, match="Device nonexistent not found"):
            await setup_flow.create_device_from_discovery("nonexistent", {})

    @pytest.mark.asyncio
    async def test_handler_factory_creates_instance_on_first_call(self, config_manager):
        """Test that create_handler factory creates instance lazily."""
        handler = ConcreteSetupFlow.create_handler(config_manager, None)

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

            def serialize_device(self, device):
                return {"id": device.id}

            def deserialize_device(self, device_data):
                return device_data

            async def create_device_from_discovery(
                self, device_id, additional_data=None
            ):
                return {"id": device_id}

            async def get_pre_discovery_screen(self):
                return None

            async def get_additional_config_screen(
                self, device_id, additional_data=None
            ):
                return None

            async def create_device_from_manual_entry(self, input_values):
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
    async def test_create_device_not_implemented_with_discovery(self, config_manager):
        """Test create_device_from_discovery raises error when not overridden."""

        class DummyDiscovery:
            """Mock discovery."""

            async def discover(self):
                return [{"id": "test"}]

        class MinimalSetupFlow(BaseSetupFlow):
            """Setup flow that doesn't override create_device_from_discovery."""

            def serialize_device(self, device):
                return device

            def deserialize_device(self, device_data):
                return device_data

            async def create_device_from_manual_entry(self, input_values):
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

        # Use setup flow that doesn't override create_device_from_discovery
        setup_flow = MinimalSetupFlow(config_manager, discovery=DummyDiscovery())

        # Should raise NotImplementedError
        with pytest.raises(NotImplementedError, match="must be overridden"):
            await setup_flow.create_device_from_discovery("test", {})

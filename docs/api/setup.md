# Setup Flow API Reference

The setup flow handles user interaction for device configuration and discovery.

## BaseSetupFlow

::: ucapi_framework.setup.BaseSetupFlow
    options:
      show_root_heading: true
      show_source: false
      members:
        - __init__
        - create_handler
        - handle_driver_setup
        - query_device
        - get_manual_entry_form
        - discover_devices
        - prepare_input_from_discovery
        - get_discovered_devices
        - get_device_id
        - get_device_name
        - format_discovered_device_label
        - get_discovered_devices_screen
        - get_additional_discovery_fields
        - extract_additional_setup_data
        - get_pre_discovery_screen
        - handle_pre_discovery_response
        - get_additional_configuration_screen
        - handle_additional_configuration_response

## SetupSteps

::: ucapi_framework.setup.SetupSteps
    options:
      show_root_heading: true
      show_source: false

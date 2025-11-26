# Driver API Reference

The driver is the central coordinator for your integration, managing device lifecycle, entity registration, and Remote events.

## BaseIntegrationDriver

::: ucapi_framework.driver.BaseIntegrationDriver
    options:
      show_root_heading: true
      show_source: false
      members:
        - __init__
        - on_r2_connect_cmd
        - on_r2_disconnect_cmd
        - on_r2_enter_standby
        - on_r2_exit_standby
        - on_subscribe_entities
        - on_unsubscribe_entities
        - add_configured_device
        - setup_device_event_handlers
        - register_available_entities
        - on_device_connected
        - on_device_disconnected
        - on_device_connection_error
        - on_device_update
        - get_device_config
        - get_device_id
        - get_device_name
        - get_device_address
        - create_entities
        - map_device_state
        - device_from_entity_id
        - get_entity_ids_for_device
        - remove_device
        - clear_devices
        - on_device_added
        - on_device_removed

## Helper Functions

::: ucapi_framework.driver.create_entity_id
    options:
      show_root_heading: true
      show_source: false

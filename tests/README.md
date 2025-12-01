# Comprehensive pytest tests for the ucapi-framework

This directory contains comprehensive test coverage for the ucapi-framework package.

## Structure

- `conftest.py` - Shared fixtures and pytest configuration
- `test_config.py` - Tests for `BaseConfigManager` configuration management
- `test_device.py` - Tests for device interface classes (StatelessHTTPDevice, PollingDevice, WebSocketDevice, PersistentConnectionDevice)
- `test_discovery.py` - Tests for discovery classes (SSDP, mDNS, Network Scan)
- `test_driver.py` - Tests for `BaseIntegrationDriver`
- `test_setup.py` - Tests for `BaseSetupFlow`

## Running Tests

### Run all tests
```bash
pytest
```

### Run with coverage report
```bash
pytest --cov=ucapi_framework --cov-report=html
```

### Run specific test file
```bash
pytest tests/test_config.py
```

### Run specific test
```bash
pytest tests/test_config.py::TestBaseConfigManager::test_add_device
```

### Run with verbose output
```bash
pytest -v
```

### Run and show print statements
```bash
pytest -s
```

## Test Coverage

The test suite aims for comprehensive coverage of:

- **Configuration Management** (`BaseConfigManager`)
  - CRUD operations
  - JSON serialization/deserialization
  - Backup and restore functionality
  - Configuration file handling
  - Error handling

- **Device Interfaces** (`BaseDeviceInterface` and subclasses)
  - Connection lifecycle
  - Event emission
  - Polling mechanisms
  - WebSocket handling
  - Persistent connections with reconnection logic
  - Error handling and recovery

- **Integration Driver** (`BaseIntegrationDriver`)
  - Remote Two event handling
  - Device lifecycle management
  - Entity subscription/unsubscription
  - State synchronization
  - Event propagation

- **Setup Flow** (`BaseSetupFlow`)
  - Configuration mode
  - Device discovery
  - Manual entry
  - Backup and restore
  - Multi-step setup flows
  - Error handling

- **Discovery** (`BaseDiscovery` and implementations)
  - SSDP discovery
  - mDNS/Bonjour discovery
  - Device filtering
  - Error handling

## Writing New Tests

When adding new tests:

1. Follow the existing naming conventions (`test_*`)
2. Use descriptive test names that explain what is being tested
3. Use appropriate fixtures from `conftest.py`
4. Mock external dependencies
5. Test both success and failure paths
6. Test edge cases and boundary conditions
7. Use `@pytest.mark.asyncio` for async tests

### Example Test

```python
@pytest.mark.asyncio
async def test_device_connects_successfully(self, mock_device_config, event_loop):
    """Test that device connects successfully."""
    device = ConcreteDevice(mock_device_config, loop=event_loop)
    
    await device.connect()
    
    assert device.connected is True
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines. The test suite should:

- Complete in a reasonable time
- Have minimal external dependencies
- Use mocking for external services
- Be deterministic (no flaky tests)
- Provide clear failure messages

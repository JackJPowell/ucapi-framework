# Contributing Tests to ucapi-framework

## Quick Guide to Adding New Tests

### 1. Choose the Right Test File

- **config.py** changes → `tests/test_config.py`
- **device.py** changes → `tests/test_device.py`
- **driver.py** changes → `tests/test_driver.py`
- **setup.py** changes → `tests/test_setup.py`
- **discovery.py** changes → `tests/test_discovery.py`

### 2. Follow the Test Naming Convention

```python
def test_<what_is_being_tested>_<expected_behavior>(self, fixtures):
    """Test that <describe the test in plain English>."""
    # Arrange
    # Act
    # Assert
```

Examples:
- `test_device_connects_successfully`
- `test_config_manager_handles_invalid_json`
- `test_driver_updates_entity_state_on_device_event`

### 3. Use Existing Fixtures

Available fixtures in `conftest.py`:
- `temp_config_dir` - Temporary directory for config files
- `event_loop` - Async event loop
- `sample_device` - Sample device configuration
- `sample_devices` - List of device configurations
- `mock_api` - Mock IntegrationAPI
- `mock_device_config` - Mock device configuration

### 4. Test Structure Template

```python
class TestNewFeature:
    """Tests for new feature."""
    
    def test_basic_functionality(self, fixture):
        """Test the basic case works."""
        # Arrange
        obj = SomeClass(fixture)
        
        # Act
        result = obj.do_something()
        
        # Assert
        assert result == expected_value
    
    def test_error_handling(self, fixture):
        """Test that errors are handled gracefully."""
        obj = SomeClass(fixture)
        
        with pytest.raises(ValueError, match="expected error"):
            obj.do_something_invalid()
    
    @pytest.mark.asyncio
    async def test_async_operation(self, fixture):
        """Test async functionality."""
        obj = SomeClass(fixture)
        
        result = await obj.async_method()
        
        assert result is not None
```

### 5. Testing Async Code

Always use `@pytest.mark.asyncio` decorator:

```python
@pytest.mark.asyncio
async def test_device_connects(self, mock_device_config, event_loop):
    """Test device connection."""
    device = MyDevice(mock_device_config, loop=event_loop)
    
    await device.connect()
    
    assert device.connected is True
```

### 6. Mocking External Dependencies

Use `unittest.mock` for mocking:

```python
from unittest.mock import AsyncMock, MagicMock, Mock, patch

@pytest.mark.asyncio
async def test_http_request(self):
    """Test HTTP request with mocked aiohttp."""
    with patch("aiohttp.ClientSession") as mock_session:
        mock_session.return_value.__aenter__.return_value = AsyncMock()
        
        # Your test code here
```

### 7. Testing File Operations

Use `temp_config_dir` fixture:

```python
def test_config_persistence(self, temp_config_dir):
    """Test configuration is saved to file."""
    manager = MyManager(temp_config_dir)
    manager.save_config({"key": "value"})
    
    # Verify file exists
    config_file = os.path.join(temp_config_dir, "config.json")
    assert os.path.exists(config_file)
```

### 8. Testing Event Emission

```python
def test_event_emitted(self, device):
    """Test that event is emitted on state change."""
    events_received = []
    device.events.on(DeviceEvents.UPDATE, lambda *args: events_received.append(args))
    
    device.update_state("new_state")
    
    assert len(events_received) == 1
    assert events_received[0][0] == device.identifier
```

### 9. Testing Abstract Base Classes

Create concrete implementations for testing:

```python
class ConcreteTestClass(AbstractBaseClass):
    """Concrete implementation for testing."""
    
    def required_method(self):
        return "test_implementation"

def test_abstract_class_functionality():
    """Test abstract class through concrete implementation."""
    obj = ConcreteTestClass()
    assert obj.required_method() == "test_implementation"
```

### 10. Testing Error Conditions

```python
def test_handles_missing_file(self, temp_config_dir):
    """Test graceful handling of missing config file."""
    manager = ConfigManager(temp_config_dir)
    
    # Should not raise, should return empty/default
    result = manager.load()
    
    assert result == []

def test_raises_on_invalid_input(self):
    """Test that invalid input raises appropriate error."""
    obj = MyClass()
    
    with pytest.raises(ValueError, match="Invalid input"):
        obj.process(None)
```

## Running Your New Tests

### Run just your new test
```bash
pytest tests/test_config.py::TestNewFeature::test_basic_functionality -v
```

### Run the whole test class
```bash
pytest tests/test_config.py::TestNewFeature -v
```

### Run with coverage to see what you're covering
```bash
pytest tests/test_config.py --cov=ucapi_framework.config --cov-report=term-missing -v
```

## Checklist Before Committing

- [ ] Test name clearly describes what is being tested
- [ ] Test has a docstring explaining the test
- [ ] Test follows Arrange-Act-Assert pattern
- [ ] Test is independent (doesn't depend on other tests)
- [ ] Async tests use `@pytest.mark.asyncio`
- [ ] External dependencies are mocked
- [ ] Both success and failure cases are tested
- [ ] Test runs successfully in isolation
- [ ] Test runs successfully with full test suite
- [ ] Code coverage is maintained or improved

## Common Patterns

### Testing Configuration CRUD

```python
def test_add_and_retrieve_device(self, config_manager):
    """Test adding and retrieving a device."""
    device = TestDevice("id1", "Device 1", "192.168.1.1")
    
    config_manager.add_or_update(device)
    retrieved = config_manager.get("id1")
    
    assert retrieved is not None
    assert retrieved.name == "Device 1"
```

### Testing Device Lifecycle

```python
@pytest.mark.asyncio
async def test_device_lifecycle(self, device):
    """Test complete device lifecycle."""
    assert device.connected is False
    
    await device.connect()
    assert device.connected is True
    
    await device.disconnect()
    assert device.connected is False
```

### Testing Event Propagation

```python
@pytest.mark.asyncio
async def test_device_event_propagates_to_entity(self, driver):
    """Test device events update entity state."""
    config = TestDeviceConfig("dev1", "Device 1", "192.168.1.1")
    driver.add_configured_device(config)
    
    device = driver._configured_devices["dev1"]
    device._state = "playing"
    
    await driver.on_device_connected("dev1")
    
    # Verify entity state was updated
    driver.api.configured_entities.update_attributes.assert_called()
```

## Questions?

- Check existing tests for similar patterns
- Review `tests/README.md` for more details
- Look at the test files for examples

## Code Coverage Goals

- Aim for >=90% line coverage
- Focus on testing public APIs
- Don't test trivial getters/setters
- Do test error handling and edge cases

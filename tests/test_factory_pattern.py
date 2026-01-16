"""Tests for factory pattern in create_entities."""

import asyncio
from dataclasses import dataclass

from ucapi import media_player, remote, sensor

from ucapi_framework.device import BaseDeviceInterface, DeviceEvents
from ucapi_framework.driver import BaseIntegrationDriver


@dataclass
class DeviceConfig:
    """Test device configuration."""

    identifier: str
    name: str
    address: str


@dataclass
class SensorConfig:
    """Configuration for a sensor."""

    sensor_id: str
    name: str
    unit: str


# Static sensor types list (Lyngdorf pattern)
SENSOR_TYPES = [
    SensorConfig("power", "Power Consumption", "W"),
    SensorConfig("volume", "Volume Level", "dB"),
    SensorConfig("temperature", "Temperature", "°C"),
]


class TestDevice(BaseDeviceInterface):
    """Test device with hub capabilities."""

    def __init__(self, device_config, loop=None, config_manager=None):
        super().__init__(device_config, loop, config_manager)
        self._connected = False
        # Simulated hub-discovered entities
        self.lights = [
            {"device_id": "light1", "name": "Living Room"},
            {"device_id": "light2", "name": "Bedroom"},
        ]
        self.scenes = [
            {"scene_id": "scene1", "name": "Movie Time"},
            {"scene_id": "scene2", "name": "Good Night"},
        ]

    @property
    def identifier(self) -> str:
        return self.device_config.identifier

    @property
    def name(self) -> str:
        return self.device_config.name

    @property
    def address(self) -> str:
        return self.device_config.address

    @property
    def log_id(self) -> str:
        return f"{self.name}[{self.identifier}]"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def state(self):
        return None

    async def connect(self) -> bool:
        self._connected = True
        self.events.emit(DeviceEvents.CONNECTED, self.identifier)
        return True

    async def disconnect(self) -> None:
        self._connected = False
        self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)


class TestSensor(sensor.Sensor):
    """Test sensor entity."""

    def __init__(self, device_config, sensor_config):
        super().__init__(
            f"sensor.{device_config.identifier}_{sensor_config.sensor_id}",
            sensor_config.name,
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.UNKNOWN,
                sensor.Attributes.VALUE: 0,
                sensor.Attributes.UNIT: sensor_config.unit,
            },
        )


class TestFactoryPattern:
    """Test factory pattern functionality in create_entities."""

    def test_factory_function_returning_single_entity(self):
        """Test factory function that returns a single entity."""

        def create_media_player(cfg, dev):  # noqa: ARG001
            return media_player.MediaPlayer(
                f"media_player.{cfg.identifier}",
                cfg.name,
                features=[media_player.Features.ON_OFF],
                attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN},
            )

        class FactorySingleDriver(BaseIntegrationDriver):
            pass

        loop = asyncio.new_event_loop()
        driver = FactorySingleDriver(
            device_class=TestDevice,
            entity_classes=[create_media_player],
            loop=loop,
        )

        config = DeviceConfig("test1", "Test Device", "192.168.1.1")
        device = TestDevice(config, loop=loop)

        entities = driver.create_entities(config, device)

        assert len(entities) == 1
        assert entities[0].id == "media_player.test1"
        assert entities[0].name["en"] == "Test Device"

        loop.close()

    def test_factory_function_returning_list(self):
        """Test factory function that returns a list of entities (Lyngdorf pattern)."""

        def create_sensors(cfg, dev):  # noqa: ARG001
            return [TestSensor(cfg, sensor_config) for sensor_config in SENSOR_TYPES]

        class FactoryListDriver(BaseIntegrationDriver):
            pass

        loop = asyncio.new_event_loop()
        driver = FactoryListDriver(
            device_class=TestDevice,
            entity_classes=[create_sensors],
            loop=loop,
        )

        config = DeviceConfig("test1", "Test Device", "192.168.1.1")
        device = TestDevice(config, loop=loop)

        entities = driver.create_entities(config, device)

        assert len(entities) == 3
        assert entities[0].id == "sensor.test1_power"
        assert entities[1].id == "sensor.test1_volume"
        assert entities[2].id == "sensor.test1_temperature"

        loop.close()

    def test_lambda_factory_returning_list(self):
        """Test lambda factory that returns a list (inline pattern)."""

        class LambdaDriver(BaseIntegrationDriver):
            pass

        loop = asyncio.new_event_loop()
        driver = LambdaDriver(
            device_class=TestDevice,
            entity_classes=[
                lambda cfg, dev: [  # noqa: ARG005
                    TestSensor(cfg, sensor_config) for sensor_config in SENSOR_TYPES
                ]
            ],
            loop=loop,
        )

        config = DeviceConfig("test1", "Test Device", "192.168.1.1")
        device = TestDevice(config, loop=loop)

        entities = driver.create_entities(config, device)

        assert len(entities) == 3
        assert all(entity.id.startswith("sensor.test1_") for entity in entities)

        loop.close()

    def test_hub_based_discovery_pattern(self):
        """Test hub-based discovery with factories (Lutron pattern)."""

        def create_lights(cfg, dev):  # noqa: ARG001
            return [
                media_player.MediaPlayer(
                    f"light.{cfg.identifier}_{light['device_id']}",
                    light["name"],
                    features=[],
                    attributes={
                        media_player.Attributes.STATE: media_player.States.UNKNOWN
                    },
                )
                for light in dev.lights
            ]

        def create_scenes(cfg, dev):  # noqa: ARG001
            return [
                remote.Remote(
                    f"button.{cfg.identifier}_{scene['scene_id']}",
                    scene["name"],
                    features=[],
                    attributes={remote.Attributes.STATE: remote.States.UNKNOWN},
                )
                for scene in dev.scenes
            ]

        class HubDriver(BaseIntegrationDriver):
            pass

        loop = asyncio.new_event_loop()
        driver = HubDriver(
            device_class=TestDevice,
            entity_classes=[create_lights, create_scenes],
            loop=loop,
        )

        config = DeviceConfig("hub1", "Test Hub", "192.168.1.1")
        device = TestDevice(config, loop=loop)

        entities = driver.create_entities(config, device)

        # Should have 2 lights + 2 scenes = 4 entities
        assert len(entities) == 4

        # Check lights
        light_entities = [e for e in entities if e.id.startswith("light.")]
        assert len(light_entities) == 2
        assert light_entities[0].id == "light.hub1_light1"
        assert light_entities[1].id == "light.hub1_light2"

        # Check scenes
        scene_entities = [e for e in entities if e.id.startswith("button.")]
        assert len(scene_entities) == 2
        assert scene_entities[0].id == "button.hub1_scene1"
        assert scene_entities[1].id == "button.hub1_scene2"

        loop.close()

    def test_mixed_classes_and_factories(self):
        """Test mixing entity classes and factory functions."""

        def create_sensors(cfg, dev):  # noqa: ARG001
            return [TestSensor(cfg, sensor_config) for sensor_config in SENSOR_TYPES]

        class MixedDriver(BaseIntegrationDriver):
            pass

        loop = asyncio.new_event_loop()
        driver = MixedDriver(
            device_class=TestDevice,
            entity_classes=[
                media_player.MediaPlayer,  # Class
                create_sensors,  # Named factory
                lambda cfg, dev: remote.Remote(  # Lambda factory returning single
                    f"remote.{cfg.identifier}",
                    f"{cfg.name} Remote",
                    features=[],
                    attributes={remote.Attributes.STATE: remote.States.UNKNOWN},
                ),
            ],
            loop=loop,
        )

        config = DeviceConfig("test1", "Test Device", "192.168.1.1")
        device = TestDevice(config, loop=loop)

        # Need to mock create_entities since MediaPlayer class needs specific params
        # Instead, let's create a proper test
        class MediaPlayerEntity(media_player.MediaPlayer):
            def __init__(self, cfg, dev):  # noqa: ARG002
                super().__init__(
                    f"media_player.{cfg.identifier}",
                    cfg.name,
                    features=[media_player.Features.ON_OFF],
                    attributes={
                        media_player.Attributes.STATE: media_player.States.UNKNOWN
                    },
                )

        driver = MixedDriver(
            device_class=TestDevice,
            entity_classes=[
                MediaPlayerEntity,  # Class
                create_sensors,  # Named factory
                lambda cfg, dev: remote.Remote(  # noqa: ARG005
                    f"remote.{cfg.identifier}",
                    f"{cfg.name} Remote",
                    features=[],
                    attributes={remote.Attributes.STATE: remote.States.UNKNOWN},
                ),
            ],
            loop=loop,
        )

        entities = driver.create_entities(config, device)

        # Should have 1 media_player + 3 sensors + 1 remote = 5 entities
        assert len(entities) == 5

        # Verify entity types
        mp_entities = [e for e in entities if e.id.startswith("media_player.")]
        sensor_entities = [e for e in entities if e.id.startswith("sensor.")]
        remote_entities = [e for e in entities if e.id.startswith("remote.")]

        assert len(mp_entities) == 1
        assert len(sensor_entities) == 3
        assert len(remote_entities) == 1

        loop.close()

    def test_empty_factory_list(self):
        """Test factory that returns empty list."""

        def create_nothing(cfg, dev):  # noqa: ARG001
            return []

        class EmptyDriver(BaseIntegrationDriver):
            pass

        loop = asyncio.new_event_loop()
        driver = EmptyDriver(
            device_class=TestDevice,
            entity_classes=[create_nothing],
            loop=loop,
        )

        config = DeviceConfig("test1", "Test Device", "192.168.1.1")
        device = TestDevice(config, loop=loop)

        entities = driver.create_entities(config, device)

        assert len(entities) == 0

        loop.close()

    def test_callable_vs_type_detection(self):
        """Test that classes are correctly distinguished from factory functions."""

        class EntityClass(media_player.MediaPlayer):
            def __init__(self, cfg, dev):  # noqa: ARG002
                super().__init__(
                    f"media_player.{cfg.identifier}_class",
                    f"{cfg.name} Class",
                    features=[],
                    attributes={
                        media_player.Attributes.STATE: media_player.States.UNKNOWN
                    },
                )

        def entity_factory(cfg, dev):  # noqa: ARG001
            return media_player.MediaPlayer(
                f"media_player.{cfg.identifier}_factory",
                f"{cfg.name} Factory",
                features=[],
                attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN},
            )

        class DetectionDriver(BaseIntegrationDriver):
            pass

        loop = asyncio.new_event_loop()
        driver = DetectionDriver(
            device_class=TestDevice,
            entity_classes=[
                EntityClass,  # Should be detected as class
                entity_factory,  # Should be detected as factory
            ],
            loop=loop,
        )

        config = DeviceConfig("test1", "Test Device", "192.168.1.1")
        device = TestDevice(config, loop=loop)

        entities = driver.create_entities(config, device)

        assert len(entities) == 2
        assert entities[0].id == "media_player.test1_class"
        assert entities[1].id == "media_player.test1_factory"

        loop.close()

    def test_factory_with_conditional_logic(self):
        """Test factory with conditional entity creation."""

        @dataclass
        class ConditionalDeviceConfig(DeviceConfig):
            has_sensors: bool = True
            sensor_count: int = 2

        def create_conditional_sensors(cfg, dev):  # noqa: ARG001
            if not cfg.has_sensors:
                return []
            return [
                TestSensor(cfg, SENSOR_TYPES[i])
                for i in range(min(cfg.sensor_count, len(SENSOR_TYPES)))
            ]

        class ConditionalDriver(BaseIntegrationDriver):
            pass

        loop = asyncio.new_event_loop()
        driver = ConditionalDriver(
            device_class=TestDevice,
            entity_classes=[create_conditional_sensors],
            loop=loop,
        )

        # Test with sensors enabled, count=2
        config1 = ConditionalDeviceConfig("test1", "Device 1", "192.168.1.1", True, 2)
        device1 = TestDevice(config1, loop=loop)
        entities1 = driver.create_entities(config1, device1)
        assert len(entities1) == 2

        # Test with sensors disabled
        config2 = ConditionalDeviceConfig("test2", "Device 2", "192.168.1.2", False, 0)
        device2 = TestDevice(config2, loop=loop)
        entities2 = driver.create_entities(config2, device2)
        assert len(entities2) == 0

        # Test with all sensors
        config3 = ConditionalDeviceConfig("test3", "Device 3", "192.168.1.3", True, 99)
        device3 = TestDevice(config3, loop=loop)
        entities3 = driver.create_entities(config3, device3)
        assert len(entities3) == 3  # All SENSOR_TYPES

        loop.close()

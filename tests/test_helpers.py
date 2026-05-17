"""Tests for helper utilities."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from ucapi_framework.helpers import (
    find_orphaned_entities,
    find_unused_activity_entities,
    _extract_used_entity_ids,
    EntityAttributes,
    ButtonAttributes,
    ClimateAttributes,
    CoverAttributes,
    IREmitterAttributes,
    LightAttributes,
    MediaPlayerAttributes,
    RemoteAttributes,
    SelectAttributes,
    SensorAttributes,
    SwitchAttributes,
    VoiceAssistantAttributes,
)
from ucapi import (
    button,
    climate,
    cover,
    ir_emitter,
    light,
    media_player,
    remote,
    select,
    sensor,
    switch,
    voice_assistant,
)


@pytest.fixture
def mock_activities_list():
    """Mock activities list response."""
    return [
        {"entity_id": "activity.tv"},
        {"entity_id": "activity.music"},
        {"entity_id": "activity.gaming"},
    ]


@pytest.fixture
def mock_activity_with_orphaned():
    """Mock activity with orphaned entities."""
    return {
        "entity_id": "activity.tv",
        "name": {"en": "Watch TV"},
        "options": {
            "included_entities": [
                {
                    "entity_id": "integration.main.media_player.tv",
                    "available": True,  # This one is fine
                    "entity_commands": ["cmd1", "cmd2"],
                    "simple_commands": ["play", "pause"],
                },
                {
                    "entity_id": "integration.main.media_player.soundbar",
                    "available": False,  # This one is orphaned
                    "entity_commands": ["cmd3", "cmd4"],
                    "simple_commands": ["volume_up", "volume_down"],
                    "name": {"en": "Soundbar"},
                },
                {
                    "entity_id": "integration.main.light.ambient",
                    # No 'available' property means it's fine
                    "entity_commands": ["on", "off"],
                    "simple_commands": ["toggle"],
                },
            ]
        },
    }


@pytest.fixture
def mock_activity_clean():
    """Mock activity with no orphaned entities."""
    return {
        "entity_id": "activity.music",
        "name": {"en": "Listen to Music"},
        "options": {
            "included_entities": [
                {
                    "entity_id": "integration.main.media_player.speaker",
                    "entity_commands": ["play", "pause"],
                    "simple_commands": ["next", "prev"],
                },
            ]
        },
    }


@pytest.fixture
def mock_activity_all_orphaned():
    """Mock activity where all entities are orphaned."""
    return {
        "entity_id": "activity.gaming",
        "name": {"en": "Gaming"},
        "options": {
            "included_entities": [
                {
                    "entity_id": "integration.main.media_player.console",
                    "available": False,
                    "entity_commands": ["power"],
                    "simple_commands": ["select"],
                },
                {
                    "entity_id": "integration.main.light.rgb",
                    "available": False,
                    "entity_commands": ["on", "off"],
                    "simple_commands": ["color"],
                },
            ]
        },
    }


@pytest.mark.asyncio
async def test_find_orphaned_entities_with_pin(
    mock_activities_list,
    mock_activity_with_orphaned,
    mock_activity_clean,
    mock_activity_all_orphaned,
):
    """Test finding orphaned entities using PIN authentication."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        # Setup mock responses
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        # Mock GET /api/activities/{id} calls
        activity_responses = {
            "activity.tv": mock_activity_with_orphaned,
            "activity.music": mock_activity_clean,
            "activity.gaming": mock_activity_all_orphaned,
        }

        def create_response(data, status=200):
            response = AsyncMock()
            response.status = status
            response.json = AsyncMock(return_value=data)
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock(return_value=None)
            return response

        def mock_get(url, **_kwargs):
            if "/api/activities" in url and url.split("?")[0].endswith(
                "/api/activities"
            ):
                return create_response(mock_activities_list)
            else:
                # Extract activity ID from URL
                activity_id = url.split("/")[-1]
                if activity_id in activity_responses:
                    return create_response(activity_responses[activity_id])
                else:
                    return create_response({}, 404)

        mock_ctx.get = mock_get

        # Call the function
        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            pin="1234",
        )

        # Verify results
        assert len(result) == 3  # 1 from activity.tv + 2 from activity.gaming

        # Check first orphaned entity
        assert result[0]["entity_id"] == "integration.main.media_player.soundbar"
        assert result[0]["available"] is False
        assert result[0]["activity_id"] == "activity.tv"
        assert result[0]["activity_name"] == {"en": "Watch TV"}
        assert "entity_commands" not in result[0]
        assert "simple_commands" not in result[0]
        assert result[0]["name"] == {"en": "Soundbar"}

        # Check gaming activity orphans
        gaming_orphans = [r for r in result if r["activity_id"] == "activity.gaming"]
        assert len(gaming_orphans) == 2


@pytest.mark.asyncio
async def test_find_orphaned_entities_with_api_key():
    """Test finding orphaned entities using API key authentication."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def create_response(data, status=200):
            response = AsyncMock()
            response.status = status
            response.json = AsyncMock(return_value=data)
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock(return_value=None)
            return response

        def mock_get(url, **kwargs):
            # Verify API key is in headers
            assert "Authorization" in kwargs.get("headers", {})
            assert kwargs["headers"]["Authorization"] == "Bearer test-api-key"
            return create_response([])

        mock_ctx.get = mock_get

        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            api_key="test-api-key",
        )

        assert result == []


@pytest.mark.asyncio
async def test_find_orphaned_entities_prefers_api_key_over_pin():
    """Test that API key is preferred over PIN when both are provided."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def create_response(data, status=200):
            response = AsyncMock()
            response.status = status
            response.json = AsyncMock(return_value=data)
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock(return_value=None)
            return response

        def mock_get(_url, **kwargs):
            # Verify API key is used, not BasicAuth
            assert "Authorization" in kwargs.get("headers", {})
            assert kwargs["headers"]["Authorization"] == "Bearer test-api-key"
            assert kwargs.get("auth") is None  # No BasicAuth when api_key present
            return create_response([])

        mock_ctx.get = mock_get

        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            pin="1234",
            api_key="test-api-key",
        )

        assert result == []


@pytest.mark.asyncio
async def test_find_orphaned_entities_no_auth_raises_error():
    """Test that missing authentication raises ValueError."""
    with pytest.raises(ValueError, match="Either pin or api_key must be provided"):
        await find_orphaned_entities(remote_url="http://192.168.1.100")


@pytest.mark.asyncio
async def test_find_orphaned_entities_api_error():
    """Test handling of API errors."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def create_response(data, status=200):
            response = AsyncMock()
            response.status = status
            response.json = AsyncMock(return_value=data)
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock(return_value=None)
            return response

        def mock_get(_url, **_kwargs):
            return create_response({}, 500)

        mock_ctx.get = mock_get

        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            pin="1234",
        )

        # Should return empty list on error
        assert result == []


@pytest.mark.asyncio
async def test_find_orphaned_entities_network_error():
    """Test handling of network errors."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(_url, **_kwargs):
            raise ConnectionError("Network error")

        mock_ctx.get = mock_get

        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            pin="1234",
        )

        # Should return empty list on error
        assert result == []


@pytest.mark.asyncio
async def test_find_orphaned_entities_aiohttp_client_error():
    """Test handling of aiohttp.ClientError (covers the specific ClientError branch)."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(_url, **_kwargs):
            raise aiohttp.ClientError("connection refused")

        mock_ctx.get = mock_get

        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            pin="1234",
        )

        assert result == []


@pytest.mark.asyncio
async def test_find_orphaned_entities_activity_fetch_failure():
    """Test handling when individual activity fetch fails."""
    activities = [{"entity_id": "activity.tv"}, {"entity_id": "activity.music"}]

    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def create_response(data, status=200):
            response = AsyncMock()
            response.status = status
            response.json = AsyncMock(return_value=data)
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock(return_value=None)
            return response

        def mock_get(url, **_kwargs):
            if "/api/activities" in url and url.split("?")[0].endswith(
                "/api/activities"
            ):
                return create_response(activities)
            else:
                # Fail on individual activity fetch
                return create_response({}, 404)

        mock_ctx.get = mock_get

        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            pin="1234",
        )

        # Should continue and return empty list since no activities loaded successfully
        assert result == []


@pytest.mark.asyncio
async def test_find_orphaned_entities_no_included_entities():
    """Test activity with no included_entities."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        activity_no_entities = {
            "entity_id": "activity.empty",
            "name": {"en": "Empty Activity"},
            "options": {},  # No included_entities
        }

        def create_response(data, status=200):
            response = AsyncMock()
            response.status = status
            response.json = AsyncMock(return_value=data)
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock(return_value=None)
            return response

        def mock_get(url, **_kwargs):
            if "/api/activities" in url and url.split("?")[0].endswith(
                "/api/activities"
            ):
                return create_response([{"entity_id": "activity.empty"}])
            else:
                return create_response(activity_no_entities)

        mock_ctx.get = mock_get

        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            pin="1234",
        )

        assert result == []


@pytest.mark.asyncio
async def test_find_orphaned_entities_preserves_entity_data():
    """Test that all entity data except commands is preserved."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        activity = {
            "entity_id": "activity.test",
            "name": {"en": "Test"},
            "options": {
                "included_entities": [
                    {
                        "entity_id": "test.entity",
                        "available": False,
                        "entity_commands": ["cmd1"],
                        "simple_commands": ["cmd2"],
                        "name": {"en": "Test Entity"},
                        "icon": "uc:test",
                        "custom_field": "custom_value",
                    }
                ]
            },
        }

        def create_response(data, status=200):
            response = AsyncMock()
            response.status = status
            response.json = AsyncMock(return_value=data)
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock(return_value=None)
            return response

        def mock_get(url, **_kwargs):
            if "/api/activities" in url and url.split("?")[0].endswith(
                "/api/activities"
            ):
                return create_response([{"entity_id": "activity.test"}])
            else:
                return create_response(activity)

        mock_ctx.get = mock_get

        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            pin="1234",
        )

        assert len(result) == 1
        orphan = result[0]

        # Check removed fields
        assert "entity_commands" not in orphan
        assert "simple_commands" not in orphan

        # Check preserved fields
        assert orphan["entity_id"] == "test.entity"
        assert orphan["available"] is False
        assert orphan["name"] == {"en": "Test Entity"}
        assert orphan["icon"] == "uc:test"
        assert orphan["custom_field"] == "custom_value"

        # Check added context fields
        assert orphan["activity_id"] == "activity.test"
        assert orphan["activity_name"] == {"en": "Test"}


@pytest.mark.asyncio
async def test_find_orphaned_entities_skips_activity_without_entity_id():
    """Test that activity summaries without entity_id are skipped."""
    activities = [
        {},  # No entity_id — should be skipped
        {"entity_id": "activity.valid"},
    ]
    valid_activity = {
        "entity_id": "activity.valid",
        "name": {"en": "Valid"},
        "options": {"included_entities": []},
    }

    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def create_response(data, status=200):
            response = AsyncMock()
            response.status = status
            response.json = AsyncMock(return_value=data)
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock(return_value=None)
            return response

        def mock_get(url, **_kwargs):
            if url.endswith("/api/activities?limit=100"):
                return create_response(activities)
            return create_response(valid_activity)

        mock_ctx.get = mock_get

        result = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            pin="1234",
        )

        assert result == []


# ---------------------------------------------------------------------------
# Entity attribute dataclass tests
# ---------------------------------------------------------------------------


def test_entity_attributes_defaults():
    """EntityAttributes defaults STATE to None."""
    attrs = EntityAttributes()
    assert attrs.STATE is None


def test_entity_attributes_with_value():
    """EntityAttributes accepts an arbitrary STATE value."""
    attrs = EntityAttributes(STATE="active")
    assert attrs.STATE == "active"


def test_button_attributes_defaults():
    attrs = ButtonAttributes()
    assert attrs.STATE is None


def test_button_attributes_with_state():
    attrs = ButtonAttributes(STATE=button.States.AVAILABLE)
    assert attrs.STATE == button.States.AVAILABLE


def test_climate_attributes_defaults():
    attrs = ClimateAttributes()
    assert attrs.STATE is None
    assert attrs.CURRENT_TEMPERATURE is None
    assert attrs.TARGET_TEMPERATURE is None
    assert attrs.TARGET_TEMPERATURE_HIGH is None
    assert attrs.TARGET_TEMPERATURE_LOW is None
    assert attrs.FAN_MODE is None


def test_climate_attributes_with_values():
    attrs = ClimateAttributes(
        STATE=climate.States.HEAT,
        CURRENT_TEMPERATURE=20.5,
        TARGET_TEMPERATURE=22.0,
        FAN_MODE="auto",
    )
    assert attrs.STATE == climate.States.HEAT
    assert attrs.CURRENT_TEMPERATURE == 20.5
    assert attrs.TARGET_TEMPERATURE == 22.0
    assert attrs.FAN_MODE == "auto"


def test_cover_attributes_defaults():
    attrs = CoverAttributes()
    assert attrs.STATE is None
    assert attrs.POSITION is None
    assert attrs.TILT_POSITION is None


def test_cover_attributes_with_values():
    attrs = CoverAttributes(STATE=cover.States.OPEN, POSITION=75, TILT_POSITION=30)
    assert attrs.STATE == cover.States.OPEN
    assert attrs.POSITION == 75
    assert attrs.TILT_POSITION == 30


def test_ir_emitter_attributes_defaults():
    attrs = IREmitterAttributes()
    assert attrs.STATE is None


def test_ir_emitter_attributes_with_state():
    attrs = IREmitterAttributes(STATE=ir_emitter.States.ON)
    assert attrs.STATE == ir_emitter.States.ON


def test_light_attributes_defaults():
    attrs = LightAttributes()
    assert attrs.STATE is None
    assert attrs.HUE is None
    assert attrs.SATURATION is None
    assert attrs.BRIGHTNESS is None
    assert attrs.COLOR_TEMPERATURE is None


def test_light_attributes_with_values():
    attrs = LightAttributes(
        STATE=light.States.ON,
        HUE=120,
        SATURATION=80,
        BRIGHTNESS=200,
        COLOR_TEMPERATURE=4000,
    )
    assert attrs.STATE == light.States.ON
    assert attrs.HUE == 120
    assert attrs.SATURATION == 80
    assert attrs.BRIGHTNESS == 200
    assert attrs.COLOR_TEMPERATURE == 4000


def test_media_player_attributes_defaults():
    attrs = MediaPlayerAttributes()
    assert attrs.STATE is None
    assert attrs.VOLUME is None
    assert attrs.MUTED is None
    assert attrs.SHUFFLE is None
    assert attrs.SOURCE_LIST is None
    assert attrs.SOUND_MODE_LIST is None


def test_media_player_attributes_with_values():
    attrs = MediaPlayerAttributes(
        STATE=media_player.States.PLAYING,
        VOLUME=50,
        MUTED=False,
        MEDIA_TITLE="Song",
        SHUFFLE=True,
        SOURCE="Spotify",
    )
    assert attrs.STATE == media_player.States.PLAYING
    assert attrs.VOLUME == 50
    assert attrs.MUTED is False
    assert attrs.MEDIA_TITLE == "Song"
    assert attrs.SHUFFLE is True
    assert attrs.SOURCE == "Spotify"


def test_remote_attributes_defaults():
    attrs = RemoteAttributes()
    assert attrs.STATE is None


def test_remote_attributes_with_state():
    attrs = RemoteAttributes(STATE=remote.States.ON)
    assert attrs.STATE == remote.States.ON


def test_select_attributes_defaults():
    attrs = SelectAttributes()
    assert attrs.STATE is None
    assert attrs.CURRENT_OPTION is None
    assert attrs.OPTIONS is None


def test_select_attributes_with_values():
    attrs = SelectAttributes(
        STATE=select.States.ON,
        CURRENT_OPTION="option_a",
        OPTIONS=["option_a", "option_b"],
    )
    assert attrs.CURRENT_OPTION == "option_a"
    assert attrs.OPTIONS == ["option_a", "option_b"]


def test_sensor_attributes_defaults():
    attrs = SensorAttributes()
    assert attrs.STATE is None
    assert attrs.VALUE is None
    assert attrs.UNIT is None


def test_sensor_attributes_with_values():
    attrs = SensorAttributes(STATE=sensor.States.ON, VALUE=23.4, UNIT="°C")
    assert attrs.VALUE == 23.4
    assert attrs.UNIT == "°C"


def test_switch_attributes_defaults():
    attrs = SwitchAttributes()
    assert attrs.STATE is None


def test_switch_attributes_with_state():
    attrs = SwitchAttributes(STATE=switch.States.ON)
    assert attrs.STATE == switch.States.ON


def test_voice_assistant_attributes_defaults():
    attrs = VoiceAssistantAttributes()
    assert attrs.STATE is None


def test_voice_assistant_attributes_with_state():
    attrs = VoiceAssistantAttributes(STATE=voice_assistant.States.ON)
    assert attrs.STATE == voice_assistant.States.ON


# ---------------------------------------------------------------------------
# _extract_used_entity_ids tests
# ---------------------------------------------------------------------------


def test_extract_used_entity_ids_empty_activity():
    """Empty activity returns an empty set."""
    result = _extract_used_entity_ids({})
    assert result == set()


def test_extract_used_entity_ids_sequences():
    """Entity IDs in sequences are extracted."""
    activity = {
        "options": {
            "sequences": {
                "on": [
                    {"command": {"entity_id": "integration.main.media_player.tv"}},
                    {"command": {"entity_id": "integration.main.light.ambient"}},
                ],
                "off": [
                    {"command": {"entity_id": "integration.main.media_player.tv"}},
                ],
            }
        }
    }
    result = _extract_used_entity_ids(activity)
    assert "integration.main.media_player.tv" in result
    assert "integration.main.light.ambient" in result
    assert len(result) == 2


def test_extract_used_entity_ids_sequences_non_list_skipped():
    """Non-list sequence values are skipped without error."""
    activity = {
        "options": {
            "sequences": {
                "on": "not-a-list",
                "off": [{"command": {"entity_id": "integration.main.switch.power"}}],
            }
        }
    }
    result = _extract_used_entity_ids(activity)
    assert result == {"integration.main.switch.power"}


def test_extract_used_entity_ids_sequences_step_without_entity_id():
    """Steps without entity_id in their command are skipped."""
    activity = {
        "options": {
            "sequences": {
                "on": [
                    {"command": {}},
                    {"command": {"entity_id": "integration.main.light.rgb"}},
                ]
            }
        }
    }
    result = _extract_used_entity_ids(activity)
    assert result == {"integration.main.light.rgb"}


def test_extract_used_entity_ids_button_mapping():
    """Entity IDs in short_press and long_press button mappings are extracted."""
    activity = {
        "options": {
            "button_mapping": [
                {
                    "short_press": {"entity_id": "integration.main.light.ceiling"},
                    "long_press": {"entity_id": "integration.main.switch.fan"},
                },
                {
                    "short_press": {},  # No entity_id
                },
            ]
        }
    }
    result = _extract_used_entity_ids(activity)
    assert "integration.main.light.ceiling" in result
    assert "integration.main.switch.fan" in result
    assert len(result) == 2


def test_extract_used_entity_ids_user_interface_command():
    """Entity IDs in UI page item commands are extracted."""
    activity = {
        "options": {
            "user_interface": {
                "pages": [
                    {
                        "items": [
                            {"command": {"entity_id": "integration.main.remote.av"}},
                        ]
                    }
                ]
            }
        }
    }
    result = _extract_used_entity_ids(activity)
    assert result == {"integration.main.remote.av"}


def test_extract_used_entity_ids_user_interface_media_player():
    """media_player_id in UI items is extracted."""
    activity = {
        "options": {
            "user_interface": {
                "pages": [
                    {
                        "items": [
                            {"media_player_id": "integration.main.media_player.tv"},
                        ]
                    }
                ]
            }
        }
    }
    result = _extract_used_entity_ids(activity)
    assert result == {"integration.main.media_player.tv"}


def test_extract_used_entity_ids_user_interface_sensor():
    """sensor_id in UI items is extracted."""
    activity = {
        "options": {
            "user_interface": {
                "pages": [
                    {
                        "items": [
                            {"sensor": {"sensor_id": "integration.main.sensor.temp"}},
                        ]
                    }
                ]
            }
        }
    }
    result = _extract_used_entity_ids(activity)
    assert result == {"integration.main.sensor.temp"}


def test_extract_used_entity_ids_user_interface_select():
    """select_id in UI items is extracted."""
    activity = {
        "options": {
            "user_interface": {
                "pages": [
                    {
                        "items": [
                            {"select": {"select_id": "integration.main.select.mode"}},
                        ]
                    }
                ]
            }
        }
    }
    result = _extract_used_entity_ids(activity)
    assert result == {"integration.main.select.mode"}


def test_extract_used_entity_ids_combined():
    """All sources are combined into a single set (deduplication)."""
    activity = {
        "options": {
            "sequences": {
                "on": [{"command": {"entity_id": "integration.main.light.a"}}]
            },
            "button_mapping": [
                {"short_press": {"entity_id": "integration.main.light.a"}},  # duplicate
                {"long_press": {"entity_id": "integration.main.switch.b"}},
            ],
            "user_interface": {
                "pages": [
                    {"items": [{"media_player_id": "integration.main.media_player.c"}]}
                ]
            },
        }
    }
    result = _extract_used_entity_ids(activity)
    assert result == {
        "integration.main.light.a",
        "integration.main.switch.b",
        "integration.main.media_player.c",
    }


# ---------------------------------------------------------------------------
# find_unused_activity_entities tests
# ---------------------------------------------------------------------------


def _make_response(data, status=200):
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=data)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


@pytest.mark.asyncio
async def test_find_unused_activity_entities_no_auth_raises():
    with pytest.raises(ValueError, match="Either pin or api_key must be provided"):
        await find_unused_activity_entities(remote_url="http://192.168.1.100")


@pytest.mark.asyncio
async def test_find_unused_activity_entities_empty_list():
    """Returns empty list when no activities exist."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx
        mock_ctx.get = lambda url, **_: _make_response([])

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", api_key="key"
        )
        assert result == []


@pytest.mark.asyncio
async def test_find_unused_activity_entities_all_used():
    """No unused entities when all included entities appear in sequences."""
    activities = [{"entity_id": "activity.home"}]
    full_activity = {
        "entity_id": "activity.home",
        "name": {"en": "Home"},
        "options": {
            "included_entities": [
                {
                    "entity_id": "integration.main.light.ceiling",
                    "entity_commands": [],
                    "simple_commands": [],
                },
            ],
            "sequences": {
                "on": [{"command": {"entity_id": "integration.main.light.ceiling"}}]
            },
        },
    }

    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(url, **_):
            if url.endswith("/api/activities?limit=100"):
                return _make_response(activities)
            return _make_response(full_activity)

        mock_ctx.get = mock_get

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", pin="1234"
        )
        assert result == []


@pytest.mark.asyncio
async def test_find_unused_activity_entities_detects_unused():
    """Entities in included_entities but absent from sequences are flagged."""
    activities = [{"entity_id": "activity.tv"}]
    full_activity = {
        "entity_id": "activity.tv",
        "name": {"en": "TV"},
        "options": {
            "included_entities": [
                {
                    "entity_id": "integration.main.media_player.tv",
                    "entity_commands": ["cmd"],
                    "simple_commands": [],
                },
                {
                    "entity_id": "integration.main.light.bias",
                    "entity_commands": [],
                    "simple_commands": [],
                },
            ],
            "sequences": {
                "on": [{"command": {"entity_id": "integration.main.media_player.tv"}}]
            },
        },
    }

    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(url, **_):
            if url.endswith("/api/activities?limit=100"):
                return _make_response(activities)
            return _make_response(full_activity)

        mock_ctx.get = mock_get

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", api_key="key"
        )

        assert len(result) == 1
        assert result[0]["entity_id"] == "integration.main.light.bias"
        assert result[0]["activity_id"] == "activity.tv"
        assert result[0]["activity_name"] == {"en": "TV"}
        assert "entity_commands" not in result[0]
        assert "simple_commands" not in result[0]


@pytest.mark.asyncio
async def test_find_unused_activity_entities_no_included_entities():
    """Activities with no included_entities are skipped."""
    activities = [{"entity_id": "activity.empty"}]
    full_activity = {
        "entity_id": "activity.empty",
        "name": {"en": "Empty"},
        "options": {},
    }

    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(url, **_):
            if url.endswith("/api/activities?limit=100"):
                return _make_response(activities)
            return _make_response(full_activity)

        mock_ctx.get = mock_get

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", pin="1234"
        )
        assert result == []


@pytest.mark.asyncio
async def test_find_unused_activity_entities_api_error():
    """Returns empty list when initial activities fetch fails."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx
        mock_ctx.get = lambda url, **_: _make_response({}, 500)

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", pin="1234"
        )
        assert result == []


@pytest.mark.asyncio
async def test_find_unused_activity_entities_individual_activity_fetch_failure():
    """Continues gracefully when a single activity fetch returns non-200."""
    activities = [{"entity_id": "activity.broken"}, {"entity_id": "activity.ok"}]
    ok_activity = {
        "entity_id": "activity.ok",
        "name": {"en": "OK"},
        "options": {
            "included_entities": [
                {
                    "entity_id": "integration.main.switch.plug",
                    "entity_commands": [],
                    "simple_commands": [],
                },
            ],
            "sequences": {},
        },
    }

    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(url, **_):
            if url.endswith("/api/activities?limit=100"):
                return _make_response(activities)
            if "activity.broken" in url:
                return _make_response({}, 404)
            return _make_response(ok_activity)

        mock_ctx.get = mock_get

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", pin="1234"
        )

        # activity.ok's entity is unused (no sequences reference it)
        assert len(result) == 1
        assert result[0]["entity_id"] == "integration.main.switch.plug"


@pytest.mark.asyncio
async def test_find_unused_activity_entities_network_error():
    """Returns empty list on network/aiohttp error."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(_url, **_kwargs):
            raise aiohttp.ClientError("connection refused")

        mock_ctx.get = mock_get

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", api_key="key"
        )
        assert result == []


@pytest.mark.asyncio
async def test_find_unused_activity_entities_unexpected_error():
    """Returns empty list on unexpected generic exception."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(_url, **_kwargs):
            raise RuntimeError("unexpected failure")

        mock_ctx.get = mock_get

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", api_key="key"
        )
        assert result == []


@pytest.mark.asyncio
async def test_find_unused_activity_entities_skips_no_entity_id():
    """Activity summaries without entity_id are skipped."""
    activities = [{}, {"entity_id": "activity.real"}]
    full_activity = {
        "entity_id": "activity.real",
        "name": {"en": "Real"},
        "options": {"included_entities": []},
    }

    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(url, **_):
            if url.endswith("/api/activities?limit=100"):
                return _make_response(activities)
            return _make_response(full_activity)

        mock_ctx.get = mock_get

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", api_key="key"
        )
        assert result == []


@pytest.mark.asyncio
async def test_find_unused_activity_entities_uses_api_key_auth():
    """Verifies Bearer token is sent when api_key is supplied."""
    with patch("ucapi_framework.helpers.aiohttp.ClientSession") as mock_session:
        mock_ctx = MagicMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        def mock_get(url, **kwargs):
            assert kwargs.get("headers", {}).get("Authorization") == "Bearer secret"
            return _make_response([])

        mock_ctx.get = mock_get

        result = await find_unused_activity_entities(
            remote_url="http://192.168.1.100", api_key="secret"
        )
        assert result == []

"""Tests for helper utilities."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ucapi_framework.helpers import find_orphaned_entities


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

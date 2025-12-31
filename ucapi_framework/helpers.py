"""
Helper utilities for Unfolded Circle Remote integrations.

Provides diagnostic and maintenance helper methods for Remote operations.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from typing import Any
import aiohttp

_LOG = logging.getLogger(__name__)


async def find_orphaned_entities(
    remote_url: str,
    pin: str | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    Find orphaned entities in activities on the Remote.

    Scans all activities and identifies entities that are marked as unavailable
    (available=false). These are typically entities that were deleted or renamed
    but still referenced in activity configurations.

    Authentication can be done via PIN (Basic Auth) or API key (Bearer token).
    One of `pin` or `api_key` must be provided. API key is preferred over PIN.

    :param remote_url: The Remote's base URL (e.g., "http://192.168.1.100")
    :param pin: Remote's web-configurator PIN for Basic Auth (username: "web-configurator")
    :param api_key: Remote's API key for Bearer token authentication
    :return: List of orphaned entity dictionaries (with entity_commands and simple_commands removed)
    :raises ValueError: If neither pin nor api_key is provided

    Example:
        orphaned = await find_orphaned_entities(
            remote_url="http://192.168.1.100",
            api_key="your-api-key-here"
        )

        for entity in orphaned:
            print(f"Orphaned entity: {entity['entity_id']} in activity {entity['activity_id']}")
    """
    if not pin and not api_key:
        raise ValueError("Either pin or api_key must be provided for authentication")

    _LOG.info("Scanning for orphaned entities on Remote at %s", remote_url)

    # Build authentication - prefer api_key over pin
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    auth = None
    if pin and not api_key:
        auth = aiohttp.BasicAuth(login="web-configurator", password=pin)

    orphaned_entities: list[dict[str, Any]] = []

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Get all activities
            activities_url = f"{remote_url}/api/activities"
            async with session.get(
                activities_url,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    _LOG.error("Failed to fetch activities: HTTP %d", response.status)
                    return orphaned_entities

                activities_list = await response.json()
                _LOG.info("Found %d activities to scan", len(activities_list))

            # Step 2: Fetch full activity details and check for orphaned entities
            for activity_summary in activities_list:
                activity_id = activity_summary.get("entity_id")
                if not activity_id:
                    continue

                # Get full activity details
                activity_url = f"{remote_url}/api/activities/{activity_id}"
                async with session.get(
                    activity_url,
                    headers=headers,
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        _LOG.warning(
                            "Failed to fetch activity %s: HTTP %d",
                            activity_id,
                            response.status,
                        )
                        continue

                    activity = await response.json()

                    # Get activity name - try summary first, then full activity
                    activity_name = activity_summary.get("name") or activity.get(
                        "name", {}
                    )

                    _LOG.debug(
                        "Processing activity %s, name: %s",
                        activity_id,
                        activity_name.get("en", "no name")
                        if isinstance(activity_name, dict)
                        else activity_name,
                    )

                    # Check included_entities for orphaned entities
                    options = activity.get("options", {})
                    included_entities = options.get("included_entities", [])

                    for entity in included_entities:
                        # Check if entity is marked as unavailable
                        # Note: 'available' property only exists when it's False
                        if "available" in entity and entity["available"] is False:
                            # Create a copy of the entity dict without entity_commands and simple_commands
                            orphaned_entity = {
                                k: v
                                for k, v in entity.items()
                                if k not in ("entity_commands", "simple_commands")
                            }
                            # Add activity context for reference
                            orphaned_entity["activity_id"] = activity_id
                            orphaned_entity["activity_name"] = activity_name

                            orphaned_entities.append(orphaned_entity)
                            _LOG.debug(
                                "Found orphaned entity: %s in activity %s (%s)",
                                entity.get("entity_id"),
                                activity_name.get("en", activity_id)
                                if isinstance(activity_name, dict)
                                else activity_id,
                                activity_id,
                            )

            _LOG.info("Found %d orphaned entities", len(orphaned_entities))
            return orphaned_entities

    except aiohttp.ClientError as err:
        _LOG.error("Network error while scanning for orphaned entities: %s", err)
        return orphaned_entities
    except Exception as err:  # pylint: disable=broad-except
        _LOG.error("Unexpected error while scanning for orphaned entities: %s", err)
        return orphaned_entities

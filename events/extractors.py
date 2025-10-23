"""
Event data extractors for the events app.

This module provides functions to determine sourcetypes and extract structured data
from event raw data, such as JSON parsing.
"""

import json
import logging

logger = logging.getLogger(__name__)


def is_json_sourcetype(event):
    """
    Check if the event sourcetype is JSON.

    Args:
        event: The event object to check.

    Returns:
        bool: True if sourcetype is 'json', False otherwise.
    """
    result = event.sourcetype.lower() == "json"
    logger.debug(f"Event sourcetype '{event.sourcetype}' is JSON: {result}")
    return result


def extract_json(event):
    """
    Extract JSON data from the event.

    Parses the event's raw data as JSON.

    Args:
        event: The event object containing JSON data.

    Returns:
        dict: Parsed JSON data.

    Raises:
        json.JSONDecodeError: If the data is not valid JSON.
    """
    try:
        data = json.loads(event.data)
        logger.debug("Successfully extracted JSON from event data")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from event data: {e}")
        raise
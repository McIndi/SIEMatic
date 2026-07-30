"""
Event data extractors for the events app.

This module provides functions to determine sourcetypes and extract structured data
from event raw data, such as JSON parsing.
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def apply_extractions(event):
    """
    Apply configured field extractions to an event without saving it.

    The caller remains responsible for persisting the mutated event. Keeping
    extraction separate from persistence lets both normal saves and
    ``bulk_create`` perform exactly one database write.
    """
    results = {}
    extractions = getattr(settings, 'FIELD_EXTRACTIONS', {})
    logger.debug(
        "Running field extractions for event %s, %d extractors configured",
        event.id,
        len(extractions),
    )
    for predicate, extraction in extractions.items():
        if predicate(event):
            try:
                extracted = extraction(event)
                results.update(extracted)
                logger.debug(
                    "Applied extractor %s to event %s",
                    extraction.__name__,
                    event.id,
                )
            except Exception as exc:
                logger.error(
                    "Error in extractor %s for event %s: %s",
                    extraction.__name__,
                    event.id,
                    exc,
                )

    if results:
        event.extracted_fields = event.extracted_fields or {}
        event.extracted_fields.update(results)
        logger.debug(
            "Extracted %d fields for event %s", len(results), event.id
        )
    return event


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

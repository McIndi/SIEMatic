"""
Signals for the events app.

This module handles post-save signals for Event models to perform
automatic field extractions based on configured extractors.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Event

logger = logging.getLogger(__name__)


def run_field_extractions(event):
    """
    Run field extractions on an event based on configured extractors.

    Iterates through FIELD_EXTRACTIONS settings and applies matching extractors.

    Args:
        event: The Event instance to process.
    """
    results = {}
    extractions = getattr(settings, 'FIELD_EXTRACTIONS', {})
    logger.debug(f"Running field extractions for event {event.id}, {len(extractions)} extractors configured")
    for predicate, extraction in extractions.items():
        if predicate(event):
            try:
                extracted = extraction(event)
                results.update(extracted)
                logger.debug(f"Applied extractor {extraction.__name__} to event {event.id}")
            except Exception as e:
                logger.error(f"Error in extractor {extraction.__name__} for event {event.id}: {e}")
    if results:
        # Prevent recursion by setting a flag
        if not getattr(event, '_extraction_done', False):
            event.extracted_fields.update(results)
            event._extraction_done = True
            event.save()
            logger.info(f"Updated extracted_fields for event {event.id} with {len(results)} fields")


@receiver(post_save, sender=Event)
def event_field_extraction_signal(sender, instance, created, **kwargs):
    """
    Signal receiver for post-save on Event model.

    Triggers field extraction for new or updated events.

    Args:
        sender: The model class (Event).
        instance: The Event instance.
        created: Whether the instance was created.
        **kwargs: Additional signal arguments.
    """
    logger.debug(f"Received post_save signal for event {instance.id}, created={created}")
    run_field_extractions(instance)

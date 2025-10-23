"""
WebSocket routing for the indexer app.

This module defines URL patterns for WebSocket connections handled by consumers.
"""
from django.urls import re_path
from .consumers import EventConsumer

websocket_urlpatterns = [
    re_path(r'indexer/$', EventConsumer.as_asgi()),
]

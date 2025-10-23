"""
ASGI config for SIEMatic project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

# Set default settings module if not already set
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SIEMatic.settings.dev')


from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

import indexer.routing

application = ProtocolTypeRouter({
	"http": get_asgi_application(),
	"websocket": AuthMiddlewareStack(
		URLRouter(
			indexer.routing.websocket_urlpatterns
		),
	),
})

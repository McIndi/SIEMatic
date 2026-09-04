import os

from django.conf import settings

def indexer_mode(request):
    """
    Context processor to add indexer mode flag to all templates.
    """
    return {
        'is_indexer_mode': os.getenv('INDEXER_MODE') == '1',
    }

def oidc(request):
    """
    Context processor exposing whether an identity provider is configured.

    The login page needs this to decide whether to offer the provider button,
    and the name to put on it.
    """
    return {
        'oidc_enabled': settings.OIDC_ENABLED,
        'oidc_provider_name': settings.OIDC_PROVIDER_NAME,
    }

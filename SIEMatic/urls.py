"""
URL configuration for SIEMatic project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from rest_framework import routers
from rest_framework.authtoken import views as drf_auth_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from search2.api import SavedSearchViewSet

# Check if we're running in indexer mode (minimal URLs only)
is_indexer = os.getenv("INDEXER_MODE") == "1"

if is_indexer:
    # Indexer mode: only serve authentication and API token URLs
    urlpatterns = [
        path('', include('project.urls')),
        path('api-token-auth/', drf_auth_views.obtain_auth_token, name='api_token_auth'),
        path('accounts/', include('django.contrib.auth.urls')),
    ]
else:
    # Normal mode: serve full application
    router = routers.DefaultRouter()
    if 'events' in settings.INSTALLED_APPS:
        from events.views import EventViewSet
        router.register(r'events', EventViewSet)
    router.register(r'savedsearches', SavedSearchViewSet, basename='savedsearch')
    urlpatterns = [
        path('', include('project.urls')),
        path('admin/', admin.site.urls),
        path('api/', include(router.urls)),
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api-token-auth/', drf_auth_views.obtain_auth_token, name='api_token_auth'),
        path('accounts/', include('django.contrib.auth.urls')),
        path('search2/', include('search2.urls')),
        path('dashboarding/', include('dashboarding.urls')),
    ]
    if settings.DEBUG:
        import debug_toolbar
        urlpatterns += [
            path('__debug__/', include('debug_toolbar.urls')),
        ]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

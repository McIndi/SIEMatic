from django.urls import path

from . import views

from .api import Search2RunView

urlpatterns = [
    path('', views.dashboard, name='search2_dashboard'),
    path('api/run/', Search2RunView.as_view(), name='search2_run_api'),

    path('savedsearches/', views.savedsearch_list, name='savedsearch_list'),
    path('savedsearches/create/', views.savedsearch_create, name='savedsearch_create'),
    path('savedsearches/<int:pk>/edit/', views.savedsearch_update, name='savedsearch_update'),
    path('savedsearches/<int:pk>/delete/', views.savedsearch_delete, name='savedsearch_delete'),
]


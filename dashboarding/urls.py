from django.urls import path
from . import views

app_name = 'dashboarding'

urlpatterns = [
    path('', views.dashboard_list, name='dashboard_list'),
    path('create/', views.dashboard_create, name='dashboard_create'),
    path('<int:pk>/edit/', views.dashboard_edit, name='dashboard_edit'),
    path('<int:pk>/delete/', views.dashboard_delete, name='dashboard_delete'),
    path('<int:pk>/', views.dashboard_detail, name='dashboard_detail'),
    path('panel/preview/', views.panel_preview, name='panel_preview'),
]
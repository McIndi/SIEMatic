from django.urls import path

from . import views

app_name = 'crawlers'

urlpatterns = [
    path('', views.finding_list, name='finding_list'),
    path('bulk-status/', views.finding_bulk_update, name='finding_bulk_update'),
    path('<int:pk>/', views.finding_detail, name='finding_detail'),
    path('<int:pk>/update/', views.finding_update, name='finding_update'),
    path('<int:pk>/delete/', views.finding_delete, name='finding_delete'),
]

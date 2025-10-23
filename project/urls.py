"""
URL configuration for the project app.

This module defines URL patterns for authentication, user profiles, and landing pages.
"""
from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import PasswordResetView, LogoutView
from .views import landing_page, profile_view, register
from django.urls import include
from django.contrib.auth.decorators import login_required

urlpatterns = [
    path('', landing_page, name='landing_page'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', login_required(LogoutView.as_view(next_page='login')), name='logout'),
    path('password_reset/', PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path('password_change/', auth_views.PasswordChangeView.as_view(), name='password_change'),
    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(), name='password_change_done'),
    path('profile/', profile_view, name='profile'),
    path('register/', register, name='register'),
]
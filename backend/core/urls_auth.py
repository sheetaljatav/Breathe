from django.urls import path

from . import auth_views

urlpatterns = [
    path("login", auth_views.LoginView.as_view(), name="auth-login"),
    path("logout", auth_views.LogoutView.as_view(), name="auth-logout"),
    path("me", auth_views.MeView.as_view(), name="auth-me"),
    path("csrf", auth_views.CsrfView.as_view(), name="auth-csrf"),
]

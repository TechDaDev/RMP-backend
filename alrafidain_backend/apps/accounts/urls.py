from django.urls import path

from .views import (
    ActivateAccountView,
    ConfirmPasswordResetView,
    LoginView,
    MeView,
    RegisterView,
    RequestPasswordResetView,
    ResendActivationOTPView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="accounts-register"),
    path("login/", LoginView.as_view(), name="accounts-login"),
    path("me/", MeView.as_view(), name="accounts-me"),
    path("activate/", ActivateAccountView.as_view(), name="accounts-activate"),
    path("resend-activation-otp/", ResendActivationOTPView.as_view(), name="accounts-resend-otp"),
    path(
        "password-reset/request/",
        RequestPasswordResetView.as_view(),
        name="accounts-password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        ConfirmPasswordResetView.as_view(),
        name="accounts-password-reset-confirm",
    ),
]

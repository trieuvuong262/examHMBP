from django.urls import path

from zalo.views_password_reset import (
    ForgotPasswordNewView,
    ForgotPasswordOtpView,
    ForgotPasswordRequestView,
)

urlpatterns = [
    path(
        'forgot-password/',
        ForgotPasswordRequestView.as_view(),
        name='password_reset_request',
    ),
    path(
        'forgot-password/otp/',
        ForgotPasswordOtpView.as_view(),
        name='password_reset_otp',
    ),
    path(
        'forgot-password/new/',
        ForgotPasswordNewView.as_view(),
        name='password_reset_new',
    ),
]

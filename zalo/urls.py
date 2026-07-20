from django.urls import path

from zalo.views_password_reset import (
    ForgotPasswordCollectEmailView,
    ForgotPasswordConfirmView,
    ForgotPasswordEmailSentView,
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
        'forgot-password/email/',
        ForgotPasswordCollectEmailView.as_view(),
        name='password_reset_collect_email',
    ),
    path(
        'forgot-password/email-sent/',
        ForgotPasswordEmailSentView.as_view(),
        name='password_reset_email_sent',
    ),
    path(
        'forgot-password/confirm/<uidb64>/<token>/',
        ForgotPasswordConfirmView.as_view(),
        name='jp_password_reset_confirm',
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

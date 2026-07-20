"""Views quên mật khẩu qua OTP Zalo."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters

from audit.utils import get_client_ip
from zalo.password_reset import (
    SESSION_KEY,
    PasswordResetError,
    complete_password_reset,
    get_reset_record,
    phone_display_for_record,
    request_password_reset_otp,
    verify_password_reset_otp,
)


def _guest_only(request):
    if request.user.is_authenticated:
        return redirect('home_portal')
    return None


@method_decorator(never_cache, name='dispatch')
@method_decorator(csrf_protect, name='dispatch')
class ForgotPasswordRequestView(View):
    template_name = 'registration/password_reset_request.html'

    def get(self, request):
        denied = _guest_only(request)
        if denied:
            return denied
        return render(request, self.template_name, {'identifier': ''})

    def post(self, request):
        denied = _guest_only(request)
        if denied:
            return denied
        identifier = (request.POST.get('identifier') or '').strip()
        if not identifier:
            messages.error(request, 'Vui lòng nhập tên đăng nhập hoặc mã nhân sự.')
            return render(request, self.template_name, {'identifier': identifier}, status=400)

        result = request_password_reset_otp(identifier, ip=get_client_ip(request))
        if not result.ok:
            messages.error(request, result.message)
            return render(request, self.template_name, {'identifier': identifier}, status=400)

        messages.success(request, result.message)
        if result.session_token:
            request.session[SESSION_KEY] = result.session_token
            return redirect('password_reset_otp')
        return render(request, self.template_name, {'identifier': identifier})


@method_decorator(never_cache, name='dispatch')
@method_decorator(csrf_protect, name='dispatch')
class ForgotPasswordOtpView(View):
    template_name = 'registration/password_reset_otp.html'

    def get(self, request):
        denied = _guest_only(request)
        if denied:
            return denied
        record = get_reset_record(request.session.get(SESSION_KEY))
        if not record or record.status not in ('pending', 'verified'):
            messages.warning(request, 'Vui lòng nhập tài khoản để nhận OTP.')
            return redirect('password_reset_request')
        if record.is_expired() and record.status == 'pending':
            messages.error(request, 'Mã OTP đã hết hạn. Vui lòng yêu cầu mã mới.')
            request.session.pop(SESSION_KEY, None)
            return redirect('password_reset_request')
        if record.status == 'verified':
            return redirect('password_reset_new')
        return render(request, self.template_name, {
            'phone_masked': phone_display_for_record(record),
            'attempts_left': record.attempts_left(),
        })

    def post(self, request):
        denied = _guest_only(request)
        if denied:
            return denied
        try:
            verify_password_reset_otp(
                request.session.get(SESSION_KEY),
                request.POST.get('otp') or '',
            )
        except PasswordResetError as exc:
            messages.error(request, str(exc))
            record = get_reset_record(request.session.get(SESSION_KEY))
            if not record or record.is_expired() or record.attempts_left() <= 0:
                request.session.pop(SESSION_KEY, None)
                return redirect('password_reset_request')
            return render(request, self.template_name, {
                'phone_masked': phone_display_for_record(record),
                'attempts_left': record.attempts_left(),
            }, status=400)
        return redirect('password_reset_new')


@method_decorator(sensitive_post_parameters('password1', 'password2'), name='dispatch')
@method_decorator(never_cache, name='dispatch')
@method_decorator(csrf_protect, name='dispatch')
class ForgotPasswordNewView(View):
    template_name = 'registration/password_reset_new.html'

    def get(self, request):
        denied = _guest_only(request)
        if denied:
            return denied
        record = get_reset_record(request.session.get(SESSION_KEY))
        if not record or record.status != 'verified':
            messages.warning(request, 'Vui lòng xác thực OTP trước.')
            return redirect('password_reset_request')
        if record.is_expired():
            messages.error(request, 'Phiên đã hết hạn. Vui lòng bắt đầu lại.')
            request.session.pop(SESSION_KEY, None)
            return redirect('password_reset_request')
        return render(request, self.template_name)

    def post(self, request):
        denied = _guest_only(request)
        if denied:
            return denied
        try:
            complete_password_reset(
                request.session.get(SESSION_KEY),
                request.POST.get('password1') or '',
                request.POST.get('password2') or '',
            )
        except PasswordResetError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, status=400)

        request.session.pop(SESSION_KEY, None)
        messages.success(request, 'Đặt mật khẩu mới thành công. Vui lòng đăng nhập.')
        return redirect('login')

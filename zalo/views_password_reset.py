"""Views quên mật khẩu — chọn Zalo (bảo trì) hoặc Email."""

from __future__ import annotations

from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters

from zalo.email_password_reset import (
    SESSION_EMAIL_USER_ID,
    get_user_from_uidb64,
    save_user_email_and_send_reset,
    set_password_from_email_token,
    start_email_password_reset,
)
from zalo.password_reset import (
    SESSION_KEY,
    PasswordResetError,
    complete_password_reset,
    get_reset_record,
    phone_display_for_record,
    resolve_user_for_password_reset,
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
        request.session.pop(SESSION_EMAIL_USER_ID, None)
        return render(request, self.template_name, {
            'identifier': '',
            'channel': 'email',
        })

    def post(self, request):
        denied = _guest_only(request)
        if denied:
            return denied

        identifier = (request.POST.get('identifier') or '').strip()
        channel = (request.POST.get('channel') or '').strip().lower()
        ctx = {'identifier': identifier, 'channel': channel or 'email'}

        if not identifier:
            messages.error(request, 'Vui lòng nhập tên đăng nhập hoặc mã nhân sự.')
            return render(request, self.template_name, ctx, status=400)

        if channel == 'zalo':
            messages.warning(
                request,
                'Kênh Zalo đang bảo trì. Vui lòng chọn Email để đặt lại mật khẩu.',
            )
            ctx['channel'] = 'email'
            return render(request, self.template_name, ctx)

        if channel != 'email':
            messages.error(request, 'Vui lòng chọn cách nhận hướng dẫn: Zalo hoặc Email.')
            return render(request, self.template_name, ctx, status=400)

        result = start_email_password_reset(identifier, request)
        if not result.ok:
            messages.error(request, result.message)
            return render(request, self.template_name, ctx, status=400)

        if result.needs_email:
            user = resolve_user_for_password_reset(identifier)
            if not user:
                messages.error(request, result.message)
                return render(request, self.template_name, ctx, status=400)
            request.session[SESSION_EMAIL_USER_ID] = user.pk
            messages.info(request, result.message)
            return redirect('password_reset_collect_email')

        messages.success(request, result.message)
        return redirect('password_reset_email_sent')


@method_decorator(never_cache, name='dispatch')
@method_decorator(csrf_protect, name='dispatch')
class ForgotPasswordCollectEmailView(View):
    template_name = 'registration/password_reset_collect_email.html'

    def get(self, request):
        denied = _guest_only(request)
        if denied:
            return denied
        user_id = request.session.get(SESSION_EMAIL_USER_ID)
        if not user_id:
            messages.warning(request, 'Vui lòng nhập tài khoản trước.')
            return redirect('password_reset_request')
        return render(request, self.template_name, {'email': ''})

    def post(self, request):
        denied = _guest_only(request)
        if denied:
            return denied
        user_id = request.session.get(SESSION_EMAIL_USER_ID)
        if not user_id:
            messages.warning(request, 'Vui lòng nhập tài khoản trước.')
            return redirect('password_reset_request')

        email = (request.POST.get('email') or '').strip()
        try:
            result = save_user_email_and_send_reset(request, int(user_id), email)
        except PasswordResetError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, {'email': email}, status=400)

        request.session.pop(SESSION_EMAIL_USER_ID, None)
        messages.success(request, result.message)
        return redirect('password_reset_email_sent')


@method_decorator(never_cache, name='dispatch')
class ForgotPasswordEmailSentView(View):
    template_name = 'registration/password_reset_email_sent.html'

    def get(self, request):
        denied = _guest_only(request)
        if denied:
            return denied
        return render(request, self.template_name)


@method_decorator(sensitive_post_parameters('password1', 'password2'), name='dispatch')
@method_decorator(never_cache, name='dispatch')
@method_decorator(csrf_protect, name='dispatch')
class ForgotPasswordConfirmView(View):
    """Đặt MK mới từ link email (uidb64 + token)."""

    template_name = 'registration/password_reset_new.html'

    def _user_ok(self, uidb64, token):
        user = get_user_from_uidb64(uidb64)
        if not user or not default_token_generator.check_token(user, token):
            return None
        return user

    def get(self, request, uidb64, token):
        denied = _guest_only(request)
        if denied:
            return denied
        if not self._user_ok(uidb64, token):
            messages.error(request, 'Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.')
            return redirect('password_reset_request')
        return render(request, self.template_name, {
            'via_email_link': True,
            'uidb64': uidb64,
            'token': token,
        })

    def post(self, request, uidb64, token):
        denied = _guest_only(request)
        if denied:
            return denied
        try:
            set_password_from_email_token(
                uidb64,
                token,
                request.POST.get('password1') or '',
                request.POST.get('password2') or '',
            )
        except PasswordResetError as exc:
            messages.error(request, str(exc))
            if not self._user_ok(uidb64, token):
                return redirect('password_reset_request')
            return render(request, self.template_name, {
                'via_email_link': True,
                'uidb64': uidb64,
                'token': token,
            }, status=400)

        messages.success(request, 'Đặt mật khẩu mới thành công. Vui lòng đăng nhập.')
        return redirect('login')


# --- Zalo OTP (giữ cho khi hết bảo trì; hiện UI chính không dẫn vào) ---

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
            messages.warning(request, 'Kênh Zalo đang bảo trì. Vui lòng dùng Email.')
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
    """Đặt MK sau OTP Zalo (session)."""

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

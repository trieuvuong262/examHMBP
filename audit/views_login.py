from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters

from audit.login_security import (
    is_ip_blocked,
    is_user_locked,
    it_contact_display,
    max_user_attempts,
    record_successful_login,
    remaining_user_attempts,
    resolve_user_by_login_identifier,
)
from audit.utils import get_client_ip


@method_decorator(sensitive_post_parameters('password'), name='dispatch')
@method_decorator(csrf_protect, name='dispatch')
@method_decorator(never_cache, name='dispatch')
class PortalLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        ip = get_client_ip(request)
        if is_ip_blocked(ip):
            return self._lockout_response(request, kind='ip')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        username = (request.POST.get('username') or '').strip()
        user = resolve_user_by_login_identifier(username)
        if user and is_user_locked(user):
            return self._lockout_response(request, kind='user', user=user)
        response = super().post(request, *args, **kwargs)
        if user and is_user_locked(user):
            return self._lockout_response(request, kind='user', user=user)
        return response

    def form_valid(self, form):
        record_successful_login(form.get_user())
        return super().form_valid(form)

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy('login_redirect')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        username = (self.request.POST.get('username') or '').strip()
        user = resolve_user_by_login_identifier(username)
        remaining = remaining_user_attempts(user) if user else max_user_attempts()
        context['login_max_attempts'] = max_user_attempts()
        context['login_remaining_attempts'] = remaining
        context['login_show_warning'] = bool(
            user and remaining and remaining <= 3 and not is_user_locked(user),
        )
        context['login_user_locked'] = bool(user and is_user_locked(user))
        context['login_ip_blocked'] = is_ip_blocked(get_client_ip(self.request))
        return context

    def _lockout_response(self, request, *, kind: str, user=None):
        return render(
            request,
            'registration/login_lockout.html',
            {
                'lockout_kind': kind,
                'locked_user': user,
                'it_contact': it_contact_display(),
                'max_attempts': max_user_attempts(),
            },
            status=403,
        )

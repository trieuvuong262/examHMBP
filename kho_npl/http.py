"""reverse/redirect kho_npl theo namespace hiện tại (kho_npl | kho_vat_tu)."""

from django.shortcuts import redirect as django_redirect
from django.urls import reverse as django_reverse

from kho_npl.stock_domain import namespace_from_current_request


def reverse(viewname, *args, **kwargs):
    if (
        kwargs.get('current_app') is None
        and isinstance(viewname, str)
        and viewname.startswith('kho_npl:')
    ):
        kwargs['current_app'] = namespace_from_current_request()
    return django_reverse(viewname, *args, **kwargs)


def redirect(to, *args, permanent=False, preserve_request=False, **kwargs):
    if isinstance(to, str) and to.startswith('kho_npl:'):
        to = reverse(to, args=args if args else None, kwargs=kwargs or None)
        return django_redirect(to, permanent=permanent, preserve_request=preserve_request)
    return django_redirect(
        to, *args, permanent=permanent, preserve_request=preserve_request, **kwargs
    )

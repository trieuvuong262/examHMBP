from django import template
from django.urls import reverse

from assessment.certificates import layout_for_certificate

register = template.Library()


@register.simple_tag
def certificate_program(cert):
    return layout_for_certificate(cert)


@register.simple_tag(takes_context=True)
def certificate_verify_url(context, cert):
    code = cert.get('code') if isinstance(cert, dict) else getattr(cert, 'code', '')
    if not code:
        return ''
    path = reverse('certificate_verify', args=[code])
    request = context.get('request')
    if request:
        return request.build_absolute_uri(path)
    return path

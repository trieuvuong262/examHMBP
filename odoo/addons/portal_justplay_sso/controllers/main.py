"""SSO từ Portal JustPlay — xác thực token HMAC và tạo session Odoo."""

import base64
import hashlib
import hmac
import json
import logging
import time

import werkzeug

from odoo import http
from odoo.http import request
from odoo.tools import config

_logger = logging.getLogger(__name__)


def _sso_secret() -> str:
    return (config.get('portal_sso_secret') or '').strip()


def _verify_token(token: str, secret: str) -> tuple[str, int]:
    if not token or '.' not in token:
        raise ValueError('invalid token')
    payload_b64, sig_b64 = token.split('.', 1)
    expected = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    sig_pad = '=' * (-len(sig_b64) % 4)
    if not hmac.compare_digest(expected, base64.urlsafe_b64decode(sig_b64 + sig_pad)):
        raise ValueError('bad signature')
    payload_pad = '=' * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + payload_pad).decode())
    login = (payload.get('login') or '').strip()
    exp = int(payload.get('exp') or 0)
    if not login:
        raise ValueError('missing login')
    return login, exp


class PortalJustPlaySSOController(http.Controller):

    @http.route('/portal/sso', type='http', auth='none', csrf=False, sitemap=False)
    def portal_sso(self, token=None, **kwargs):
        secret = _sso_secret()
        if not secret or not token:
            return werkzeug.utils.redirect('/web/login')

        try:
            login, exp = _verify_token(token, secret)
        except Exception:
            _logger.warning('Portal SSO token invalid')
            return werkzeug.utils.redirect('/web/login?error=sso_invalid')

        if time.time() > exp:
            return werkzeug.utils.redirect('/web/login?error=sso_expired')

        user = request.env['res.users'].sudo().search([
            ('login', '=ilike', login),
            ('active', '=', True),
        ], limit=1)
        if not user:
            _logger.warning('Portal SSO user not found: %s', login)
            return werkzeug.utils.redirect('/web/login?error=sso_user')

        request.session.uid = user.id
        request.session.login = user.login
        request.session.session_token = user._compute_session_token(request.session.sid)
        request.session.rotate = True

        redirect_to = (kwargs.get('redirect') or '/web').strip()
        if not redirect_to.startswith('/'):
            redirect_to = '/web'
        return werkzeug.utils.redirect(redirect_to)

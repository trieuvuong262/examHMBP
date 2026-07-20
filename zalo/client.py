"""Client Zalo OA OAuth v4 + ZBS Template Message (OTP qua SĐT)."""

from __future__ import annotations

import logging
import secrets
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class ZaloAPIError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        status_code: int | None = None,
        payload: Any = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.payload = payload


def zalo_is_configured() -> bool:
    if not getattr(settings, 'ZALO_ENABLED', False):
        return False
    return bool(
        (getattr(settings, 'ZALO_APP_ID', '') or '').strip()
        and (getattr(settings, 'ZALO_APP_SECRET', '') or '').strip()
        and (getattr(settings, 'ZALO_OTP_TEMPLATE_ID', '') or '').strip()
    )


def zalo_has_refresh_token() -> bool:
    from zalo.models import ZaloOAuthToken

    env_rt = (getattr(settings, 'ZALO_REFRESH_TOKEN', '') or '').strip()
    if env_rt:
        return True
    try:
        return bool(ZaloOAuthToken.get_solo().refresh_token)
    except Exception:
        return False


def zalo_is_ready() -> bool:
    """Đủ cấu hình + có refresh/access token để gửi OTP."""
    return zalo_is_configured() and zalo_has_refresh_token()


class ZaloClient:
    def __init__(self) -> None:
        self.app_id = (getattr(settings, 'ZALO_APP_ID', '') or '').strip()
        self.app_secret = (getattr(settings, 'ZALO_APP_SECRET', '') or '').strip()
        self.token_url = (
            getattr(settings, 'ZALO_TOKEN_URL', '')
            or 'https://oauth.zaloapp.com/v4/oa/access_token'
        ).strip()
        self.message_url = (
            getattr(settings, 'ZALO_MESSAGE_URL', '')
            or 'https://business.openapi.zalo.me/message/template'
        ).strip()
        self.template_id = (getattr(settings, 'ZALO_OTP_TEMPLATE_ID', '') or '').strip()
        self.otp_param = (getattr(settings, 'ZALO_OTP_TEMPLATE_PARAM', '') or 'otp').strip() or 'otp'
        self.timeout = max(10, int(getattr(settings, 'ZALO_API_TIMEOUT', 30) or 30))
        self.development_mode = bool(getattr(settings, 'ZALO_DEVELOPMENT_MODE', True))

    def get_access_token(self) -> str:
        from zalo.models import ZaloOAuthToken

        state = ZaloOAuthToken.get_solo()
        if state.access_token_valid():
            return state.access_token

        refresh = (state.refresh_token or '').strip() or (
            getattr(settings, 'ZALO_REFRESH_TOKEN', '') or ''
        ).strip()
        if not refresh:
            raise ZaloAPIError(
                'Chưa có refresh_token Zalo. Chạy: python manage.py zalo_oauth_exchange --code …'
            )

        return self._refresh_access_token(refresh)

    def exchange_authorization_code(self, code: str, *, code_verifier: str = '') -> dict:
        """Đổi authorization code → access_token + refresh_token (lần đầu)."""
        code = (code or '').strip()
        if not code:
            raise ZaloAPIError('Thiếu authorization code.')
        data = {
            'app_id': self.app_id,
            'grant_type': 'authorization_code',
            'code': code,
        }
        verifier = (code_verifier or '').strip() or (
            getattr(settings, 'ZALO_CODE_VERIFIER', '') or ''
        ).strip()
        if verifier:
            data['code_verifier'] = verifier
        return self._request_token(data)

    def _refresh_access_token(self, refresh_token: str) -> str:
        data = {
            'app_id': self.app_id,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }
        payload = self._request_token(data)
        return payload['access_token']

    def _request_token(self, form_data: dict) -> dict:
        from zalo.models import ZaloOAuthToken

        try:
            response = requests.post(
                self.token_url,
                data=form_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'secret_key': self.app_secret,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ZaloAPIError(f'Không kết nối được OAuth Zalo: {exc}') from exc

        payload = _safe_json(response)
        if response.status_code >= 400 or _zalo_error_code(payload) not in (None, 0):
            raise ZaloAPIError(
                _zalo_error_message(payload) or 'Lấy access token Zalo thất bại.',
                error_code=_zalo_error_code(payload),
                status_code=response.status_code,
                payload=payload,
            )

        access = (payload.get('access_token') or '').strip()
        refresh = (payload.get('refresh_token') or '').strip()
        if not access:
            raise ZaloAPIError('Phản hồi token Zalo không có access_token.', payload=payload)

        expires_in = int(payload.get('expires_in') or 90000)
        expires_at = timezone.now() + timezone.timedelta(seconds=max(60, expires_in - 60))

        with transaction.atomic():
            state = ZaloOAuthToken.get_solo()
            state.access_token = access
            if refresh:
                state.refresh_token = refresh
            state.expires_at = expires_at
            state.save(update_fields=['access_token', 'refresh_token', 'expires_at', 'updated_at'])

        logger.info('Zalo OA token đã làm mới (expires_at=%s)', expires_at.isoformat())
        return {
            'access_token': access,
            'refresh_token': refresh or state.refresh_token,
            'expires_in': expires_in,
            'expires_at': expires_at,
        }

    def send_template_message(
        self,
        *,
        phone: str,
        template_data: dict,
        template_id: str | None = None,
        tracking_id: str | None = None,
        development: bool | None = None,
    ) -> dict:
        """
        Gửi ZBS Template qua SĐT.
        ``phone`` phải dạng ``84xxxxxxxxx`` (xem ``hrm.phone.normalize_phone``).
        """
        phone = (phone or '').strip()
        if not phone:
            raise ZaloAPIError('Thiếu số điện thoại nhận OTP.')

        tid = (template_id or self.template_id or '').strip()
        if not tid:
            raise ZaloAPIError('Chưa cấu hình ZALO_OTP_TEMPLATE_ID.')

        body: dict[str, Any] = {
            'phone': phone,
            'template_id': tid,
            'template_data': template_data or {},
            'tracking_id': (tracking_id or '').strip() or f'jp-{secrets.token_hex(8)}',
        }
        use_dev = self.development_mode if development is None else bool(development)
        if use_dev:
            body['mode'] = 'development'

        token = self.get_access_token()
        try:
            response = requests.post(
                self.message_url,
                json=body,
                headers={
                    'Content-Type': 'application/json',
                    'access_token': token,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ZaloAPIError(f'Không kết nối được ZBS API: {exc}') from exc

        payload = _safe_json(response)
        err = _zalo_error_code(payload)
        if response.status_code >= 400 or (err is not None and err != 0):
            raise ZaloAPIError(
                _zalo_error_message(payload) or 'Gửi ZBS template thất bại.',
                error_code=err,
                status_code=response.status_code,
                payload=payload,
            )
        return payload if isinstance(payload, dict) else {'raw': payload}

    def send_otp(
        self,
        *,
        phone: str,
        otp: str,
        tracking_id: str | None = None,
        development: bool | None = None,
        extra_template_data: dict | None = None,
    ) -> dict:
        otp = (otp or '').strip()
        if not otp:
            raise ZaloAPIError('Thiếu mã OTP.')
        data = {self.otp_param: otp}
        if extra_template_data:
            data.update(extra_template_data)
        return self.send_template_message(
            phone=phone,
            template_data=data,
            tracking_id=tracking_id,
            development=development,
        )


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {'text': (response.text or '')[:500]}


def _zalo_error_code(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ('error', 'error_code', 'errorCode'):
        if key in payload and payload[key] is not None and payload[key] != '':
            try:
                return int(payload[key])
            except (TypeError, ValueError):
                return None
    return None


def _zalo_error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ''
    for key in ('message', 'error_message', 'errorMessage', 'error_description'):
        msg = payload.get(key)
        if msg:
            return str(msg)
    return ''

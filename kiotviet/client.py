"""Client gọi KiotViet Public API (OAuth2 + REST)."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_token_cache: str | None = None
_token_expires_at: float = 0.0


class KiotVietAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class KiotVietClient:
    def __init__(self) -> None:
        self.retailer = (getattr(settings, 'KIOTVIET_RETAILER', '') or '').strip()
        self.client_id = (getattr(settings, 'KIOTVIET_CLIENT_ID', '') or '').strip()
        self.client_secret = (getattr(settings, 'KIOTVIET_CLIENT_SECRET', '') or '').strip()
        self.token_url = (
            getattr(settings, 'KIOTVIET_TOKEN_URL', '') or 'https://id.kiotviet.vn/connect/token'
        ).strip()
        self.api_base = (
            getattr(settings, 'KIOTVIET_API_BASE_URL', '') or 'https://public.kiotapi.com'
        ).rstrip('/')

    @staticmethod
    def is_configured() -> bool:
        if not getattr(settings, 'KIOTVIET_ENABLED', False):
            return False
        return bool(
            (getattr(settings, 'KIOTVIET_RETAILER', '') or '').strip()
            and (getattr(settings, 'KIOTVIET_CLIENT_ID', '') or '').strip()
            and (getattr(settings, 'KIOTVIET_CLIENT_SECRET', '') or '').strip()
        )

    def get_access_token(self) -> str:
        global _token_cache, _token_expires_at
        now = time.time()
        if _token_cache and now < _token_expires_at - 60:
            return _token_cache

        try:
            response = requests.post(
                self.token_url,
                data={
                    'scope': 'PublicApi.Access',
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise KiotVietAPIError(f'Không kết nối được máy chủ OAuth KiotViet: {exc}') from exc

        if response.status_code >= 400:
            raise KiotVietAPIError(
                'Lấy access token thất bại.',
                status_code=response.status_code,
                payload=_safe_json(response),
            )

        data = response.json()
        token = data.get('access_token')
        if not token:
            raise KiotVietAPIError('Phản hồi token không hợp lệ.', payload=data)

        expires_in = int(data.get('expires_in') or 86400)
        _token_cache = token
        _token_expires_at = now + expires_in
        return token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
    ) -> Any:
        url = f'{self.api_base}/{path.lstrip("/")}'
        headers = {
            'Retailer': self.retailer,
            'Authorization': f'Bearer {self.get_access_token()}',
        }
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise KiotVietAPIError(f'Lỗi kết nối API KiotViet: {exc}') from exc

        if response.status_code >= 400:
            raise KiotVietAPIError(
                _api_error_message(response),
                status_code=response.status_code,
                payload=_safe_json(response),
            )

        if not response.content:
            return {}
        return response.json()

    def list_customers(self, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', 'customers', params=clean)

    def get_customer(self, customer_id: int | str) -> dict:
        return self._request('GET', f'customers/{customer_id}')

    def get_customer_by_code(self, code: str) -> dict:
        return self._request('GET', f'customers/code/{code}')

    def list_orders(self, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', 'orders', params=clean)

    def get_order(self, order_id: int | str) -> dict:
        return self._request('GET', f'orders/{order_id}')

    def get_order_by_code(self, code: str) -> dict:
        return self._request('GET', f'orders/code/{code}')

    def list_invoices(self, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', 'invoices', params=clean)

    def get_invoice(self, invoice_id: int | str) -> dict:
        return self._request('GET', f'invoices/{invoice_id}')

    def get_invoice_by_code(self, code: str) -> dict:
        return self._request('GET', f'invoices/code/{code}')

    def list_branches(self, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', 'branches', params=clean)

    def list_categories(self, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', 'categories', params=clean)

    def list_products(self, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', 'products', params=clean)

    def get_product(self, product_id: int | str, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', f'products/{product_id}', params=clean)

    def get_product_by_code(self, code: str, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', f'products/code/{code}', params=clean)

    def list_product_on_hand(self, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', 'productOnHands', params=clean)

    def list_purchase_orders(self, **params: Any) -> dict:
        clean = {k: v for k, v in params.items() if v not in (None, '')}
        return self._request('GET', 'purchaseorders', params=clean)

    def get_purchase_order(self, purchase_order_id: int | str) -> dict:
        return self._request('GET', f'purchaseorders/{purchase_order_id}')


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:500] if response.text else None


def _api_error_message(response: requests.Response) -> str:
    data = _safe_json(response)
    if isinstance(data, dict):
        for key in ('message', 'error', 'error_description', 'responseStatus', 'status'):
            val = data.get(key)
            if val:
                return str(val)
    return f'API KiotViet trả lỗi (HTTP {response.status_code}).'

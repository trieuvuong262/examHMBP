"""SMTP backend Portal — hỗ trợ tắt xác minh chứng chỉ (mail nội bộ)."""

from __future__ import annotations

import ssl

from django.core.mail.backends.smtp import EmailBackend


class PortalSMTPBackend(EmailBackend):
    def __init__(self, *args, ssl_verify: bool = True, **kwargs):
        self.ssl_verify = bool(ssl_verify)
        super().__init__(*args, **kwargs)

    @property
    def ssl_context(self):
        if not self.ssl_verify:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return super().ssl_context

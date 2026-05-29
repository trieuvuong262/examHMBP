"""Đọc cấu hình Gemini — ưu tiên DB, fallback .env."""

from django.conf import settings


def get_gemini_credentials() -> tuple[str, str]:
    from .models import LibraryQAConfig

    cfg = LibraryQAConfig.load()
    api_key = (cfg.gemini_api_key or '').strip()
    model = (cfg.gemini_model or '').strip()

    if not api_key:
        api_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    if not model:
        model = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-pro') or 'gemini-1.5-pro'

    return api_key, model


def is_qa_enabled() -> bool:
    return bool(get_gemini_credentials()[0])


def qa_config_source() -> str:
    """Trả về nguồn key đang dùng: db | env | none."""
    from .models import LibraryQAConfig

    cfg = LibraryQAConfig.load()
    if (cfg.gemini_api_key or '').strip():
        return 'db'
    if (getattr(settings, 'GEMINI_API_KEY', '') or '').strip():
        return 'env'
    return 'none'

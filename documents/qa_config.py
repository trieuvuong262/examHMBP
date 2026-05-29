"""Đọc cấu hình trợ lý AI — ưu tiên DB, fallback .env."""

from django.conf import settings

DEFAULT_MODEL = 'gemini-2.5-flash'

# Model cũ không còn trên API mới — map sang model thay thế
MODEL_ALIASES = {
    'gemini-1.5-pro': 'gemini-2.5-flash',
    'gemini-1.5-flash': 'gemini-2.5-flash',
    'gemini-2.0-flash': 'gemini-2.5-flash',
}

FALLBACK_MODELS = (
    'gemini-2.5-flash',
    'gemini-flash-latest',
    'gemini-2.0-flash-lite',
    'gemini-2.5-pro',
)


def resolve_model(name: str) -> str:
    model = (name or '').strip() or DEFAULT_MODEL
    return MODEL_ALIASES.get(model, model)


def get_gemini_credentials() -> tuple[str, str]:
    from .models import LibraryQAConfig

    cfg = LibraryQAConfig.load()
    api_key = (cfg.gemini_api_key or '').strip()
    model = resolve_model((cfg.gemini_model or '').strip())

    if not api_key:
        api_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    if not model:
        model = resolve_model(getattr(settings, 'GEMINI_MODEL', DEFAULT_MODEL))

    return api_key, model


def models_to_try(primary: str) -> list[str]:
    ordered = [resolve_model(primary), *FALLBACK_MODELS]
    seen = set()
    out = []
    for name in ordered:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


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

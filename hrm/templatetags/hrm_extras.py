from django import template

register = template.Library()


def _is_mostly_uppercase(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    upper_count = sum(1 for c in letters if c.isupper())
    return upper_count / len(letters) >= 0.75


@register.filter
def display_title(value):
    """Chuyển chuỗi IN HOA sang viết hoa chữ cái đầu mỗi từ; giữ nguyên nếu đã đúng kiểu."""
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return text
    if not _is_mostly_uppercase(text):
        return text
    return text.title()

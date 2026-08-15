"""Đọc ảnh phiếu báo cáo SX viết tay bằng Gemini Vision."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from documents.qa_config import get_gemini_credentials, models_to_try


class ProductionReportImageAIError(RuntimeError):
    """Lỗi an toàn để hiển thị khi AI không thể đọc phiếu."""


EXTRACTION_PROMPT = """Bạn đọc ảnh phiếu báo cáo sản xuất viết tay của Just Play.
Trích xuất chính xác những gì nhìn thấy; KHÔNG suy đoán hoặc tự sửa mã hàng/chữ viết.

Chỉ trả về JSON hợp lệ, không markdown, theo schema:
{
  "employee_code": "mã NV hoặc chuỗi rỗng",
  "employee_name": "tên trên phiếu hoặc chuỗi rỗng",
  "declared_work_hours": số hoặc null,
  "sessions": [
    {
      "code": "mã hàng hoặc chuỗi rỗng",
      "process": "nguyên văn cột Công đoạn - Size hoặc chuỗi rỗng",
      "start_time": "HH:MM hoặc chuỗi rỗng",
      "end_time": "HH:MM hoặc chuỗi rỗng",
      "total": số hoặc 0,
      "damaged": số hoặc 0,
      "norm": số hoặc null,
      "note": "ghi chú hoặc chuỗi rỗng"
    }
  ],
  "warnings": ["các ô chữ viết không rõ / dữ liệu thiếu"]
}

Quy ước:
- Chỉ thêm sessions có ít nhất mã hàng, công đoạn, giờ hoặc số lượng.
- Chuẩn hóa giờ thành HH:MM nếu đọc được.
- "Thời gian thực tế" và "Hiệu suất" là kết quả tính; không dùng để thay thế giờ bắt đầu/kết thúc.
- Nếu một giá trị không đọc được, dùng chuỗi rỗng/null và ghi cảnh báo.
"""


def _parse_response_json(text: str) -> dict:
    raw = (text or '').strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s*```$', '', raw)
    start = raw.find('{')
    end = raw.rfind('}')
    if start < 0 or end < start:
        raise ProductionReportImageAIError('AI không trả về dữ liệu phiếu hợp lệ. Hãy thử ảnh rõ hơn.')
    try:
        value = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ProductionReportImageAIError('AI trả về dữ liệu chưa đọc được. Hãy thử lại ảnh rõ hơn.') from exc
    if not isinstance(value, dict):
        raise ProductionReportImageAIError('AI không trả về đúng cấu trúc dữ liệu phiếu.')
    return value


def _decimal_or_blank(value):
    if value is None or isinstance(value, bool):
        return ''
    text = str(value).strip().replace(',', '.')
    if not text:
        return ''
    try:
        normalized = Decimal(text).quantize(Decimal('0.01'))
        return format(normalized, 'f').rstrip('0').rstrip('.') or '0'
    except (InvalidOperation, ValueError):
        return ''


def _integer_or_zero(value):
    if value is None or isinstance(value, bool):
        return '0'
    text = str(value).strip().replace(',', '.')
    try:
        return str(max(0, int(Decimal(text))))
    except (InvalidOperation, ValueError):
        return '0'


def _normalize_time(value):
    text = str(value or '').strip()
    if not text:
        return ''
    match = re.search(r'(\d{1,2})\s*[:h.]\s*(\d{1,2})', text, flags=re.IGNORECASE)
    if not match:
        return ''
    hour, minute = int(match.group(1)), int(match.group(2))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return ''
    return f'{hour:02d}:{minute:02d}'


def _normalize_extracted_data(value: dict) -> dict:
    sessions = []
    warnings = [
        str(item).strip()[:300]
        for item in (value.get('warnings') or [])
        if str(item).strip()
    ]
    for row in value.get('sessions') or []:
        if not isinstance(row, dict):
            continue
        item = {
            'code': str(row.get('code') or '').strip()[:100],
            'process': str(row.get('process') or '').strip()[:255],
            'start_time': _normalize_time(row.get('start_time')),
            'end_time': _normalize_time(row.get('end_time')),
            'total': _integer_or_zero(row.get('total')),
            'damaged': _integer_or_zero(row.get('damaged')),
            'norm': _decimal_or_blank(row.get('norm')),
            'note': str(row.get('note') or '').strip()[:500],
        }
        if any((
            item['code'], item['process'], item['start_time'],
            item['end_time'], item['total'] != '0',
        )):
            sessions.append(item)
    if not sessions:
        warnings.append('Không tìm thấy công đoạn hợp lệ. Hãy kiểm tra ảnh hoặc nhập thủ công.')

    declared_work_hours = _decimal_or_blank(value.get('declared_work_hours'))
    return {
        'employee_code': str(value.get('employee_code') or '').strip()[:80],
        'employee_name': str(value.get('employee_name') or '').strip()[:255],
        'declared_work_hours': declared_work_hours,
        'sessions': sessions,
        'warnings': warnings,
    }


def _friendly_error(exc: Exception) -> ProductionReportImageAIError:
    if isinstance(exc, genai_errors.ClientError):
        if exc.code in (401, 403) or exc.status in {'UNAUTHENTICATED', 'PERMISSION_DENIED'}:
            return ProductionReportImageAIError('AI chưa được cấp quyền đọc ảnh. Nhờ IT kiểm tra cấu hình AI.')
        if exc.code == 429 or exc.status == 'RESOURCE_EXHAUSTED':
            return ProductionReportImageAIError('AI đang bận. Hãy thử lại sau vài phút.')
        if exc.code == 400 or exc.status == 'INVALID_ARGUMENT':
            return ProductionReportImageAIError('Ảnh hoặc cấu hình AI không hợp lệ. Hãy thử ảnh JPG/PNG rõ hơn.')
    return ProductionReportImageAIError('Không thể phân tích ảnh lúc này. Hãy thử lại hoặc nhập thủ công.')


def extract_production_report_image(image_file) -> dict:
    """Gửi ảnh, trả dữ liệu đã chuẩn hóa để đổ vào form Nhập hộ."""
    if not image_file:
        raise ProductionReportImageAIError('Chưa có ảnh phiếu báo cáo.')
    image_file.open('rb')
    try:
        image_bytes = image_file.read()
    finally:
        image_file.close()
    if not image_bytes:
        raise ProductionReportImageAIError('Ảnh phiếu báo cáo đang trống.')

    content_type = (getattr(image_file, 'content_type', '') or '').lower()
    if not content_type.startswith('image/'):
        content_type = 'image/jpeg'

    api_key, primary_model = get_gemini_credentials()
    if not api_key:
        raise ProductionReportImageAIError('AI chưa được cấu hình. Nhờ IT bật Trợ lý AI trước khi import ảnh.')

    last_exc = None
    for model_name in models_to_try(primary_model):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=content_type),
                    EXTRACTION_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    temperature=0,
                ),
            )
            return _normalize_extracted_data(_parse_response_json(response.text))
        except genai_errors.ClientError as exc:
            last_exc = exc
            if exc.code == 404 or exc.status == 'NOT_FOUND':
                continue
            raise _friendly_error(exc) from exc
        except ProductionReportImageAIError:
            raise
        except Exception as exc:
            last_exc = exc
            break
    raise _friendly_error(last_exc or RuntimeError('Không có model AI khả dụng.'))

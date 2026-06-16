"""
Chuẩn hoá Danh sách Thiết Bị.xlsx theo portal + mã phương án B.
Phân tích ảnh Google Drive (cache local) bằng Gemini Vision.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / '.env')

SOURCE = Path(r'c:\Users\Vuong-IT\Desktop\Danh sách Thiết Bị.xlsx')
OUT_PATH = Path(r'c:\Users\Vuong-IT\Desktop\Danh sách Thiết Bị - Portal chuẩn.xlsx')
CACHE_DIR = Path(__file__).parent / 'equipment_import_cache'
ANALYSIS_CACHE = Path(__file__).parent / 'equipment_image_analysis.json'
LINKS_JSON = Path(__file__).parent / '_excel_links.json'

TODAY = '2026-05-28 08:00'

# Phương án B — tiền tố theo mã loại portal
PREFIX_BY_CATEGORY = {
    'SEW_LOCKSTITCH': 'MAY',
    'SEW_DOUBLE': 'MAY2',
    'SEW_OVERLOCK': 'OVL',
    'SEW_INTERLOCK': 'ITL',
    'SEW_SPECIAL': 'MAYS',
    'SEW_AUTO': 'MAYA',
    'SEW_AUX': 'MAYX',
    'CUT_MACHINE': 'CAT',
    'CUT_SPREAD': 'TRV',
    'CUT_TABLE': 'BCT',
    'CUT_AUX': 'CATA',
    'CUT_MEASURE': 'CAN',
    'CUT_CAD': 'CAD',
    'PRINT_MACHINE': 'IN',
    'LABEL_PRESS': 'EP',
    'BARCODE_PRINT': 'TEM',
    'EMB_MACHINE': 'TH',
    'FINISH_IRON': 'UI',
    'FINISH_PRESS': 'EPH',
    'FINISH_TUNNEL': 'TNL',
    'FINISH_TRIM': 'XC',
    'WASH_MACHINE': 'GIAT',
    'DRY_MACHINE': 'SAY',
    'QC_DETECT': 'KIM',
    'QC_CAMERA': 'CAM',
    'QC_LAB': 'LAB',
    'PACK_MACHINE': 'DG',
    'PACK_SCALE': 'CAN',
    'WARE_SCANNER': 'SCAN',
    'PC': 'PC',
    'Laptop': 'LT',
    'Printer': 'PR',
    'DISPLAY': 'MN',
    'CCTV': 'CCTV',
    'Network': 'NW',
    'PHONE': 'DT',
    'ATTENDANCE': 'CC',
    'Tool': 'DC',
    'PROD_OTHER': 'MX',
    'SAMPLE_SEW': 'MAYM',
}

CATEGORY_LABELS = {
    'SEW_LOCKSTITCH': 'Máy may 1 kim (lockstitch)',
    'SEW_DOUBLE': 'Máy may 2 kim',
    'SEW_OVERLOCK': 'Máy may overlock',
    'SEW_INTERLOCK': 'Máy may interlock / flatlock',
    'SEW_SPECIAL': 'Máy may chuyên dụng',
    'SEW_AUTO': 'Máy may tự động / CNC',
    'SEW_AUX': 'Phụ trợ may',
    'CUT_MACHINE': 'Máy cắt (dao rung, đĩa, laser…)',
    'CUT_SPREAD': 'Máy trải vải',
    'CUT_TABLE': 'Bàn cắt / spreading table',
    'CUT_AUX': 'Máy cắt phụ',
    'CUT_MEASURE': 'Cân / đo vải',
    'CUT_CAD': 'Plotter / CAD cắt',
    'PRINT_MACHINE': 'Máy in (screen, DTG, sublimation…)',
    'LABEL_PRESS': 'Máy ép nhãn / logo',
    'BARCODE_PRINT': 'Máy in tem / mã vạch',
    'EMB_MACHINE': 'Máy thêu',
    'FINISH_IRON': 'Bàn ủi / máy ủi hơi',
    'FINISH_PRESS': 'Máy ép / heat press',
    'FINISH_TUNNEL': 'Tunnel / form finisher',
    'FINISH_TRIM': 'Cắt chỉ / xử lý lông',
    'PC': 'Máy tính bàn (PC)',
    'Laptop': 'Laptop',
    'Printer': 'Máy in',
    'DISPLAY': 'Màn hình / TV / Andon',
    'CCTV': 'Camera an ninh (CCTV)',
    'Network': 'Server / Thiết bị mạng',
    'Tool': 'Dụng cụ / bàn ghế xưởng',
    'PROD_OTHER': 'Máy sản xuất khác',
}

STATUS_MAP = {
    'đang hoạt động': 'active',
    'hoạt động': 'active',
    'active': 'active',
    'mới lắp': 'new',
    'new': 'new',
    'đang hỏng': 'broken',
    'hỏng': 'broken',
    'broken': 'broken',
    'bảo trì': 'maintenance',
    'maintenance': 'maintenance',
    'thanh lý': 'scrapped',
    'scrapped': 'scrapped',
}

STATUS_LABEL = {
    'active': 'Đang hoạt động',
    'new': 'Mới lắp',
    'broken': 'Đang hỏng',
    'maintenance': 'Đang bảo trì',
    'scrapped': 'Đã hủy / Thanh lý',
}

EXPORT_COLS_PROD = [
    ('device_code', 'Mã thiết bị'),
    ('name', 'Tên thiết bị'),
    ('category', 'Loại (mã)'),
    ('category_label', 'Loại thiết bị'),
    ('managed_department', 'Bộ phận quản lý (tên phòng ban)'),
    ('status', 'Trạng thái (new / active / broken / maintenance / scrapped)'),
    ('status_label', 'Trạng thái (hiển thị)'),
    ('usage_department_text', 'Phòng ban sử dụng'),
    ('usage_room', 'Phòng / vị trí (Line, khu vực…)'),
    ('assigned_user_text', 'Người dùng / người phụ trách'),
    ('contact_email', 'Email liên hệ'),
    ('handover_date', 'Ngày bàn giao (YYYY-MM-DD)'),
    ('model_number', 'Model / hãng'),
    ('serial_number', 'Serial Number'),
    ('description', 'Mô tả'),
    ('configuration', 'Thông số kỹ thuật'),
    ('quantity', 'Số lượng'),
    ('unit_price', 'Đơn giá (VNĐ)'),
    ('total_price', 'Thành tiền (VNĐ)'),
    ('created_at', 'Ngày tạo'),
    ('updated_at', 'Cập nhật lần cuối'),
]

EXPORT_COLS_IT = [
    ('device_code', 'Mã thiết bị'),
    ('name', 'Tên thiết bị'),
    ('category', 'Loại (mã)'),
    ('category_label', 'Loại thiết bị'),
    ('managed_department', 'Bộ phận quản lý (tên phòng ban)'),
    ('status', 'Trạng thái (new / active / broken / maintenance / scrapped)'),
    ('status_label', 'Trạng thái (hiển thị)'),
    ('usage_department_text', 'Phòng ban sử dụng'),
    ('usage_room', 'Phòng / vị trí (Line, khu vực…)'),
    ('assigned_user_text', 'Người dùng / người phụ trách'),
    ('contact_email', 'Email liên hệ'),
    ('handover_date', 'Ngày bàn giao (YYYY-MM-DD)'),
    ('model_number', 'Model / hãng'),
    ('serial_number', 'Serial Number'),
    ('description', 'Mô tả'),
    ('configuration', 'Cấu hình (RAM, CPU…)'),
    ('hostname', 'Hostname'),
    ('ip_address', 'Địa chỉ IP'),
    ('quantity', 'Số lượng'),
    ('unit_price', 'Đơn giá (VNĐ)'),
    ('created_at', 'Ngày tạo'),
    ('updated_at', 'Cập nhật lần cuối'),
]


def _is_url(text: str) -> bool:
    return bool(text and re.search(r'https?://', text))


def _extract_drive_id(url: str) -> str | None:
    m = re.search(r'/d/([^/]+)', url or '')
    return m.group(1) if m else None


MANUAL_OVERRIDES: dict[str, dict] = {
    '1mAtPu8IZaQHcLY_OYsgA3MzR5wgxznUR': {
        'mo_ta': 'Máy may công nghiệp JUKI DDL-7000A, motor liền trục, bảng điều khiển kỹ thuật số, cắt chỉ tự động.',
        'thong_so': 'Hãng: JUKI\nModel: DDL-7000A-S7NBK\nLoại: Máy may 1 kim điện tử\nMotor: Direct-drive\nXuất xứ: Việt Nam\nSerial (ảnh): 4E6S801244',
    },
    '19nYNX8KI45NkxrF-IOlkHqsNhDeUwz0X': {
        'mo_ta': 'Máy vắt sổ công nghiệp SIRUBA, 4 chỉ, có bảng điều khiển kỹ thuật số và đèn LED.',
        'thong_so': 'Hãng: SIRUBA\nModel: 747KQT-514M-3-24/DK/LU/H\nLoại: Máy overlock 4 chỉ\nXuất xứ: China\nCE',
    },
    '1laY37IKyazqdZgs9c_-MJXD_EPKlutwl': {
        'mo_ta': 'Máy ép nhiệt khí nén 2 mâm GaoShang, dùng ép nhãn/logo lên vải.',
        'thong_so': 'Hãng: GaoShang\nModel: GS-4060\nLoại: Pneumatic dual-station heat press\nĐiều khiển: Màn hình cảm ứng\nHệ thống: Khí nén',
    },
    '1tyTtQgS0tqdHpjxIOTwfVBpv-9wprqJn': {
        'mo_ta': 'Máy may interlock/kansai SIRUBA C007KP, đầu nhỏ (cylinder-bed).',
        'thong_so': 'Hãng: SIRUBA\nModel: C007KP\nLoại: Máy interlock đầu nhỏ\n4 tension dial',
    },
    '1ElY_6PPuqxUQpN0HVxp-wsAQ6BqOqR2r': {
        'mo_ta': 'Máy cắt tự động bullmer model E80.',
        'thong_so': 'Hãng: bullmer\nModel: E80\nĐiện áp: AC400V 50Hz 3P/N/PE\nCông suất: 22KW\nDòng đầy tải: 58A\nĐiện áp điều khiển: DC24V\nNăm SX: 2022',
    },
    '1tlt8ho7YizM6kUBuEVVMvxexeHu8WFW6': {
        'mo_ta': 'Máy in/ép chuyển nhiệt cuộn khổ lớn tại xưởng Just Play, có hệ thống hút khói.',
        'thong_so': 'Loại: Máy ép nhiệt cuộn / in chuyển nhiệt\nTính năng: Rulo liên tục, hút khói\nỨng dụng: In áo thể thao',
    },
    '1lmMFMUxV2KvluNmGryJ7UKxzjsa-EDO0': {
        'mo_ta': 'Máy ép nhiệt DENG DA (Pengda) PD-1700D-600.',
        'thong_so': 'Hãng: DENG DA / Pengda\nModel: PD-1700D-600\nSerial: 2203VN0034D140\nĐiện áp: 380V 3 pha\nCông suất: 42KW\nTrọng lượng: 2000KG\nNSX: 03/2022',
    },
    '1QXp-T5XZ5nkICpJy97XFfnAl9RNFGXPq': {
        'mo_ta': 'Máy ép nhãn GaoShang GS-TB2.',
        'thong_so': 'Hãng: Dongguan Gaoshang\nModel: GS-TB2\nSerial: GS260424B552\nĐiện áp: 220V\nCông suất: 1KW\nDòng định mức: 4.5A\nKích thước: 20x30cm\nTrọng lượng: 60KG',
    },
}


def _safe_quantity(value) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 1
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return 1


def _clean_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ''
    text = str(value).strip()
    if not text or text.lower() in {
        'nan', 'none', 'nếu có', 'không cần', 'cũ', 'cu', 'cũ ',
        'cũ thì không cần/ mới thì bắt buộc',
    }:
        return ''
    if _is_url(text):
        return ''
    return re.sub(r'\s+', ' ', text)


def _normalize_status(raw) -> tuple[str, str]:
    text = _clean_text(raw).lower()
    if not text:
        return 'active', STATUS_LABEL['active']
    for key, code in STATUS_MAP.items():
        if key in text:
            return code, STATUS_LABEL.get(code, raw)
    if text in STATUS_LABEL:
        return text, STATUS_LABEL[text]
    return 'active', STATUS_LABEL['active']


def infer_category(name: str, sheet: str, loai_text: str = '') -> str:
    blob = f'{name} {loai_text} {sheet}'.lower()
    rules = [
        (r'bullmer|máy cắt|may cat|dao rung|laser cắt|cutting machine', 'CUT_MACHINE'),
        (r'trải vải|spreading|trai vai', 'CUT_SPREAD'),
        (r'plotter|cad cắt|in sơ đồ', 'CUT_CAD'),
        (r'chuyển nhiệt|in nhiệt|sublimation|dtg', 'PRINT_MACHINE'),
        (r'ép nhãn|ép logo|heat press|máy ép|烫画', 'LABEL_PRESS'),
        (r'máy thêu|thêu', 'EMB_MACHINE'),
        (r'bàn ủi|máy ủi|ủi hơi|lò hơi|steam', 'FINISH_IRON'),
        (r'máy tính bàn|máy tính|desktop|\bpc\b', 'PC'),
        (r'laptop|notebook', 'Laptop'),
        (r'máy in(?!\s*chuyển)|printer', 'Printer'),
        (r'màn hình|monitor|tv', 'DISPLAY'),
        (r'camera|cctv', 'CCTV'),
        (r'overlock|vắt sổ|vatsổ|vắt cổ|over lock|747kqt', 'SEW_OVERLOCK'),
        (r'2 kim|hai kim|double', 'SEW_DOUBLE'),
        (r'interlock|flatlock|vắt thùa|c007kp', 'SEW_INTERLOCK'),
        (r'bartack|nút|đính nút|kansai|chuyên dụng', 'SEW_SPECIAL'),
        (r'máy may tự động|auto sew|cnc', 'SEW_AUTO'),
        (r'1 kim|một kim|lockstitch|juki ddl|ddl-|ddk-|luồng thẳng', 'SEW_LOCKSTITCH'),
        (r'máy may|may juki|may ', 'SEW_LOCKSTITCH'),
        (r'cân|đo vải', 'CUT_MEASURE'),
        (r'kim detector|phát hiện kim', 'QC_DETECT'),
    ]
    for pattern, code in rules:
        if re.search(pattern, blob):
            return code
    sheet_map = {
        'MAY': 'SEW_LOCKSTITCH',
        'ÉP LOGO': 'LABEL_PRESS',
        'ỦI': 'FINISH_IRON',
        'IN NHIỆT': 'PRINT_MACHINE',
        'CẮT, TRẢI VẢI': 'CUT_MACHINE',
        'HÀNH CHÍNH NHÂN SỰ': 'PC',
        'GẤP XẾP': 'PC',
        'ĐIỀU PHỐI': 'PC',
        'Kho Nguyên phụ liệu': 'WARE_SCANNER',
    }
    return sheet_map.get(sheet, 'PROD_OTHER')


def is_it_category(code: str) -> bool:
    return code in {'PC', 'Laptop', 'Printer', 'Network', 'Internet', 'CCTV', 'PHONE', 'ATTENDANCE', 'DISPLAY'}


def allocate_code(prefix: str, counters: dict[str, int]) -> str:
    counters[prefix] = counters.get(prefix, 0) + 1
    return f'{prefix}-{counters[prefix]:06d}'


def download_drive_images(file_ids: list[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for fid in file_ids:
        out = CACHE_DIR / f'{fid}.jpg'
        if out.exists() and out.stat().st_size > 1000:
            continue
        url = f'https://drive.google.com/uc?export=download&id={fid}'
        try:
            r = requests.get(url, timeout=60, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 1000:
                out.write_bytes(r.content)
        except Exception:
            pass


def analyze_images_with_gemini(file_ids: list[str], *, use_gemini: bool = True) -> dict[str, dict]:
    cached = dict(MANUAL_OVERRIDES)
    if ANALYSIS_CACHE.exists():
        cached.update(json.loads(ANALYSIS_CACHE.read_text(encoding='utf-8')))

    # Manual overrides win over failed API entries
    for fid, data in MANUAL_OVERRIDES.items():
        cached[fid] = data

    if not use_gemini:
        return cached

    pending = [fid for fid in file_ids if fid not in cached or not (cached[fid].get('mo_ta') or cached[fid].get('thong_so'))]
    if not pending:
        return cached

    api_key = (os.getenv('GEMINI_API_KEY') or '').strip()
    if not api_key:
        print('WARN: GEMINI_API_KEY missing — skip vision analysis')
        return cached

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')

    prompt = (
        'Bạn là chuyên gia thiết bị may công nghiệp và IT. Phân tích ảnh thiết bị này rất kỹ.\n'
        'Trả về ĐÚNG JSON (không markdown), hai khóa:\n'
        '{"mo_ta":"...","thong_so":"..."}\n'
        '- mo_ta: 1-3 câu mô tả thiết bị (hãng, model, chức năng, tình trạng nhìn thấy)\n'
        '- thong_so: bullet text các thông số đọc được trên tem/nhãn/invoice: '
        'model, serial, điện áp, công suất, tốc độ, RPM, trọng lượng, kích thước, năm SX…\n'
        'Nếu là ảnh PC: ghi CPU, RAM, SSD, mainboard. Nếu máy may: ghi tốc độ mũi kim, loại mũi, motor…\n'
        'Không bịa — chỉ ghi những gì nhìn/đọc được. Tiếng Việt.'
    )

    for i, fid in enumerate(pending, 1):
        img_path = CACHE_DIR / f'{fid}.jpg'
        if not img_path.exists():
            cached[fid] = {'mo_ta': '', 'thong_so': '', 'error': 'no_image'}
            continue
        try:
            image_bytes = img_path.read_bytes()
            resp = client.models.generate_content(
                model=model,
                contents=[
                    types.Content(
                        role='user',
                        parts=[
                            types.Part(text=prompt),
                            types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=1200),
            )
            text = (resp.text or '').strip()
            text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.I)
            data = json.loads(text)
            cached[fid] = {
                'mo_ta': str(data.get('mo_ta', '')).strip(),
                'thong_so': str(data.get('thong_so', '')).strip(),
            }
            print(f'  analyzed {i}/{len(pending)} {fid[:12]}…')
        except Exception as exc:
            cached[fid] = {'mo_ta': '', 'thong_so': '', 'error': str(exc)[:200]}
            print(f'  FAIL {fid[:12]}: {exc}')
        if i % 5 == 0:
            ANALYSIS_CACHE.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding='utf-8')
            time.sleep(1.5)
        else:
            time.sleep(0.4)

    ANALYSIS_CACHE.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding='utf-8')
    return cached


def _fallback_from_row(name: str, model: str, serial: str, cat: str) -> tuple[str, str]:
    label = CATEGORY_LABELS.get(cat, cat)
    desc_bits = [name]
    if label and label not in name:
        desc_bits.append(f'Loại: {label}')
    if model:
        desc_bits.append(f'Model {model}')
    cfg_bits = []
    if model:
        cfg_bits.append(f'Model: {model}')
    if serial:
        cfg_bits.append(f'Serial: {serial}')
    return '. '.join(desc_bits), '\n'.join(cfg_bits)


def _merge_specs(model: str, analysis: dict, existing_desc: str, existing_cfg: str, name: str, cat: str = '') -> tuple[str, str]:
    mo_ta = analysis.get('mo_ta', '').strip()
    thong_so = analysis.get('thong_so', '').strip()
    desc_parts = [p for p in [existing_desc, mo_ta, f'Hãng/model: {model}' if model else ''] if p]
    desc = '. '.join(dict.fromkeys(desc_parts))
    cfg_parts = []
    if thong_so:
        cfg_parts.append(thong_so)
    if existing_cfg and not _is_url(existing_cfg):
        cfg_parts.append(existing_cfg)
    if model and model not in desc:
        cfg_parts.insert(0, f'Model: {model}')
    cfg = '\n'.join(dict.fromkeys(cfg_parts))
    if not desc:
        desc = name
    if not cfg and not mo_ta and not thong_so:
        return _fallback_from_row(name, model, '', cat)
    return desc[:2000], cfg[:4000]


def transform_workbook(*, use_gemini: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    dfs = pd.read_excel(SOURCE, sheet_name=None)
    counters: dict[str, int] = defaultdict(int)
    prod_rows: list[dict] = []
    it_rows: list[dict] = []

    all_ids: list[str] = []
    for df in dfs.values():
        for col in ('Mô tả', 'Thông số kỹ thuật', 'Cấu hình (RAM, CPU…)'):
            if col in df.columns:
                for v in df[col].dropna():
                    fid = _extract_drive_id(str(v))
                    if fid:
                        all_ids.append(fid)

    unique_ids = sorted(set(all_ids))
    print(f'Unique Drive images: {len(unique_ids)}')
    download_drive_images(unique_ids)
    analysis = analyze_images_with_gemini(unique_ids, use_gemini=use_gemini)

    for sheet_name, df in dfs.items():
        df = df.copy()
        for _, row in df.iterrows():
            name = _clean_text(row.get('Tên thiết bị'))
            if not name:
                continue

            loai_code_raw = _clean_text(row.get('Loại (mã)'))
            loai_label_raw = _clean_text(row.get('Loại thiết bị'))
            cat = loai_code_raw if loai_code_raw else infer_category(name, sheet_name, loai_label_raw)
            if cat not in CATEGORY_LABELS:
                cat = infer_category(name, sheet_name, loai_label_raw)

            prefix = PREFIX_BY_CATEGORY.get(cat, 'MX')
            device_code = allocate_code(prefix, counters)

            status_raw = row.get('Trạng thái (new / active / broken / maintenance / scrapped)') or row.get('Trạng thái mã')
            status, status_label = _normalize_status(status_raw)
            if not status_label:
                status_label = _clean_text(row.get('Trạng thái (hiển thị)')) or STATUS_LABEL[status]

            model = _clean_text(row.get('Model / hãng') or row.get('Model'))
            serial = _clean_text(row.get('Serial Number') or row.get('Serial'))
            usage_room = _clean_text(row.get('Phòng / vị trí (Line, khu vực…)') or row.get('Vị trí'))
            if not usage_room:
                usage_room = _clean_text(row.get('Phòng ban sử dụng')) or sheet_name

            desc_raw = _clean_text(row.get('Mô tả'))
            cfg_raw = _clean_text(row.get('Thông số kỹ thuật') or row.get('Cấu hình'))

            desc_fid = _extract_drive_id(str(row.get('Mô tả', '')))
            cfg_fid = _extract_drive_id(str(row.get('Thông số kỹ thuật', '')))
            img_analysis = {}
            if desc_fid and desc_fid in analysis:
                img_analysis = analysis[desc_fid]
            elif cfg_fid and cfg_fid in analysis:
                img_analysis = analysis[cfg_fid]

            description, configuration = _merge_specs(model, img_analysis, desc_raw, cfg_raw, name, cat)

            # Bổ sung serial vào thông số nếu chưa có
            if serial and serial not in configuration:
                configuration = f'Serial: {serial}\n{configuration}'.strip()

            handover = _clean_text(row.get('Ngày bàn giao (YYYY-MM-DD)'))
            if handover and re.match(r'^\d{4}-\d{2}-\d{2}', handover):
                handover_val = handover[:10]
            else:
                handover_val = ''

            base = {
                'device_code': device_code,
                'name': name,
                'category': cat,
                'category_label': CATEGORY_LABELS.get(cat, loai_label_raw or cat),
                'managed_department': _clean_text(row.get('Bộ phận quản lý (tên phòng ban)')) or sheet_name,
                'status': status,
                'status_label': status_label,
                'usage_department_text': _clean_text(row.get('Phòng ban sử dụng')) or sheet_name,
                'usage_room': usage_room,
                'assigned_user_text': _clean_text(row.get('Người dùng / người phụ trách')),
                'contact_email': _clean_text(row.get('Email liên hệ')),
                'handover_date': handover_val,
                'model_number': model,
                'serial_number': serial,
                'description': description,
                'configuration': configuration,
                'quantity': _safe_quantity(row.get('Số lượng')),
                'unit_price': '',
                'total_price': '',
                'created_at': TODAY,
                'updated_at': TODAY,
            }

            if is_it_category(cat):
                it_row = dict(base)
                it_row['hostname'] = ''
                it_row['ip_address'] = ''
                it_rows.append(it_row)
            else:
                prod_rows.append(base)

    prod_df = pd.DataFrame(prod_rows)
    it_df = pd.DataFrame(it_rows)
    return prod_df, it_df


def _format_df(df: pd.DataFrame, cols_spec: list) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[label for _k, label in cols_spec])
    ordered = [k for k, _l in cols_spec if k in df.columns]
    rename = {k: l for k, l in cols_spec}
    return df[ordered].rename(columns=rename)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--use-gemini', action='store_true', help='Gọi Gemini Vision (tốn quota)')
    args = parser.parse_args()

    print('Source:', SOURCE)
    prod_df, it_df = transform_workbook(use_gemini=args.use_gemini)
    print(f'Production rows: {len(prod_df)}, IT rows: {len(it_df)}')

    with pd.ExcelWriter(OUT_PATH, engine='openpyxl') as writer:
        _format_df(prod_df, EXPORT_COLS_PROD).to_excel(writer, sheet_name='Thiết bị sản xuất', index=False)
        if not it_df.empty:
            _format_df(it_df, EXPORT_COLS_IT).to_excel(writer, sheet_name='Thiết bị IT', index=False)
        all_df = pd.concat([prod_df, it_df], ignore_index=True)
        _format_df(all_df, EXPORT_COLS_PROD).to_excel(writer, sheet_name='Tổng hợp', index=False)

    print('Written:', OUT_PATH)
    print('Analysis cache:', ANALYSIS_CACHE)


if __name__ == '__main__':
    main()

"""Gợi ý câu hỏi thông minh — rule-based + AI, tránh lặp lịch sử."""

from __future__ import annotations

import json
import logging
import re
import unicodedata

from .knowledge_base import build_documents_index, build_user_context

logger = logging.getLogger(__name__)

SUGGESTION_INSTRUCTION = """Bạn gợi ý câu hỏi tiếp theo cho nhân viên JustPlay tra cứu trên portal nội bộ.

NHIỆM VỤ: Sinh đúng 3 câu hỏi follow-up THÔNG MINH — mỗi câu một hướng KHÁC NHAU:
1) ĐÀO SÂU: chi tiết, bước cụ thể, điều kiện, ai phê duyệt, thời hạn… từ câu trả lời vừa rồi
2) LIÊN QUAN: tài liệu/chủ đề khác trong portal (nêu đúng tên tài liệu nếu có trong ngữ cảnh)
3) HÀNH ĐỘNG: yêu cầu link, tóm tắt ngắn, so sánh, hoặc bước tiếp theo user nên làm

QUY TẮC:
- Tiếng Việt tự nhiên, ngắn (≤ 90 ký tự), kết thúc bằng ?
- KHÔNG lặp câu đã hỏi trong lịch sử hội thoại
- Bám sát câu hỏi + câu trả lời mới nhất; nếu trả lời nhắc tài liệu → gợi ý "Gửi link …" hoặc "Tóm tắt …"
- Chỉ gợi ý trong phạm vi portal; không hỏi lan man

Trả về JSON duy nhất: {"suggestions": ["câu 1", "câu 2", "câu 3"]}
Không markdown, không giải thích."""


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize('NFD', text or '')
    return ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')


def _normalize_q(text: str) -> set[str]:
    text = _strip_accents((text or '').lower())
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = {t for t in text.split() if len(t) > 1}
    stop = {
        'toi', 'ban', 'la', 'gi', 'co', 'khong', 'duoc', 'nhu', 'the', 'nao', 'va', 'cua',
        'trong', 'tren', 'portal', 'justplay', 'xin', 'cho', 'hay', 've', 'mot', 'cac',
    }
    return tokens - stop


def _is_duplicate(candidate: str, existing: list[str], threshold: float = 0.55) -> bool:
    c_tokens = _normalize_q(candidate)
    if not c_tokens:
        return True
    for item in existing:
        e_tokens = _normalize_q(item)
        if not e_tokens:
            continue
        overlap = len(c_tokens & e_tokens) / min(len(c_tokens), len(e_tokens))
        if overlap >= threshold:
            return True
    return False


def _is_repeat_of_asked(candidate: str, asked: list[str]) -> bool:
    """Chỉ bỏ qua khi gần như hỏi lại y nguyên — vẫn cho phép 'Gửi link …', 'Tóm tắt …'."""
    action_prefixes = ('gui link', 'tom tat', 'diem chinh', 'cac buoc', 'ai la', 'con tai')
    cand_norm = _strip_accents(candidate.lower())
    if any(cand_norm.startswith(p) for p in action_prefixes):
        return False
    return _is_duplicate(candidate, asked, threshold=0.82)


def _filter_unique(suggestions: list[str], history: list | None = None, limit: int = 3) -> list[str]:
    asked = [
        (turn.get('text') or '').strip()
        for turn in (history or [])
        if turn.get('role') == 'user'
    ]
    seen: list[str] = []
    out: list[str] = []
    for item in suggestions:
        q = ' '.join((item or '').split())
        if not q:
            continue
        if not q.endswith('?'):
            q = q.rstrip('.!') + '?'
        q = q[:90]
        if _is_repeat_of_asked(q, asked):
            continue
        if _is_duplicate(q, seen, threshold=0.55):
            continue
        out.append(q)
        seen.append(q)
        if len(out) >= limit:
            break
    return out


def _parse_suggestions(raw: str) -> list[str]:
    text = (raw or '').strip()
    if not text:
        return []

    fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fence:
        text = fence.group(1).strip()

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            items = payload.get('suggestions') or payload.get('questions') or []
            if isinstance(items, list):
                return [' '.join(str(x).split()) for x in items if str(x).strip()]
    except json.JSONDecodeError:
        pass

    lines = []
    for line in text.splitlines():
        line = re.sub(r'^[\s\d\.\-\*•]+', '', line).strip().strip('"\'')
        if line and not line.startswith('{') and not line.startswith('['):
            lines.append(line)
    return lines


def _mentioned_documents(answer: str, index: list[dict]) -> list[dict]:
    answer_lower = _strip_accents(answer.lower())
    hits = []
    for doc in index:
        title_key = _strip_accents(doc['title'].lower())
        if title_key and title_key in answer_lower:
            hits.append(doc)
    return hits


def _related_documents(question: str, answer: str, index: list[dict], mentioned: list[dict]) -> list[dict]:
    mentioned_ids = {d['id'] for d in mentioned}
    q_tokens = _normalize_q(question + ' ' + answer)
    scored = []
    for doc in index:
        if doc['id'] in mentioned_ids:
            continue
        doc_tokens = _normalize_q(
            f"{doc['title']} {doc.get('category', '')} {doc.get('summary', '')}"
        )
        if not doc_tokens:
            continue
        score = len(q_tokens & doc_tokens)
        if doc['category'] and _strip_accents(doc['category'].lower()) in _strip_accents(answer.lower()):
            score += 2
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: (-x[0], x[1]['title']))
    return [doc for _, doc in scored[:3]]


def _rule_based_suggestions(
    user,
    question: str,
    answer: str,
    history: list | None,
    request=None,
) -> list[str]:
    index = build_documents_index(request)
    suggestions: list[str] = []
    mentioned = _mentioned_documents(answer, index)
    related = _related_documents(question, answer, index, mentioned)

    for doc in mentioned[:1]:
        suggestions.append(f'Gửi link {doc["title"]}?')
        if doc.get('summary'):
            suggestions.append(f'Điểm chính trong {doc["title"]} là gì?')
        else:
            suggestions.append(f'Tóm tắt ngắn {doc["title"]}?')

    answer_l = answer.lower()
    if any(k in answer_l for k in ('quy trình', 'bước', 'thực hiện', 'cách')):
        suggestions.append('Các bước cụ thể tôi cần làm tiếp theo?')
    if any(k in answer_l for k in ('liên hệ', 'hr', 'it', 'quản lý', 'phê duyệt')):
        suggestions.append('Ai là người phê duyệt hoặc liên hệ trong trường hợp này?')
    if 'http' in answer_l or 'link' in answer_l:
        suggestions.append('Còn tài liệu liên quan nào khác không?')

    for doc in related[:2]:
        suggestions.append(f'{doc["title"]} liên quan thế nào?')

    if 'module' in _strip_accents(question.lower()) or 'quyền' in question.lower():
        suggestions.append('Module nào trên portal tôi được phép dùng?')

    if not suggestions and index:
        starter = index[0]
        suggestions.append(f'Tóm tắt {starter["title"]}?')
        if len(index) > 1:
            suggestions.append(f'Gửi link {index[1]["title"]}?')

    if not history:
        profile_ctx = build_user_context(user)
        if 'Nhân viên' in profile_ctx:
            suggestions.append('Tôi nên bắt đầu tra cứu từ tài liệu nào?')

    return _filter_unique(suggestions, history, limit=5)


def build_suggestion_prompt(
    user,
    question: str,
    answer: str,
    history: list | None,
    request=None,
) -> str:
    index = build_documents_index(request)
    doc_lines = [
        f"- {d['title']} ({d['category']})" + (f": {d['summary'][:80]}" if d.get('summary') else '')
        for d in index[:25]
    ]
    history_lines = []
    for turn in (history or [])[-6:]:
        role = turn.get('role')
        text = (turn.get('text') or '').strip()
        if role == 'user' and text:
            history_lines.append(f'[ĐÃ HỎI — không lặp] {text[:220]}')
        elif role == 'model' and text:
            history_lines.append(f'[Trợ lý] {text[:280]}')

    return '\n'.join([
        build_user_context(user),
        '',
        '=== CHỈ MỤC TÀI LIỆU (để gợi ý liên quan) ===',
        *(doc_lines or ['(chưa có tài liệu)']),
        '',
        '=== LỊCH SỬ HỘI THOẠI ===',
        *(history_lines or ['(chưa có)']),
        '',
        f'=== LƯỢT VỪA RỒI ===',
        f'Câu hỏi: {question[:500]}',
        f'Câu trả lời: {answer[:1400]}',
        '',
        'Sinh 3 câu hỏi follow-up (JSON).',
    ])


def merge_suggestions(
    ai_items: list[str],
    rule_items: list[str],
    history: list | None,
    limit: int = 3,
) -> list[str]:
    """Ưu tiên AI, bổ sung rule-based nếu thiếu hoặc trùng."""
    combined = list(ai_items) + list(rule_items)
    return _filter_unique(combined, history, limit=limit)


def generate_initial_suggestions(user, request=None) -> list[str]:
    """Gợi ý thông minh trước câu hỏi đầu tiên — theo vai trò & tài liệu."""
    index = build_documents_index(request)
    profile = build_user_context(user)
    suggestions: list[str] = []

    if index:
        top = index[0]
        suggestions.append(f'Gửi link {top["title"]}?')
        if len(index) > 1:
            suggestions.append(f'{index[1]["title"]} nói về nội dung gì?')
        if top.get('category'):
            suggestions.append(f'Có tài liệu nào khác trong nhóm {top["category"]}?')

    if 'Nhân viên' in profile or 'Trưởng nhóm' in profile:
        suggestions.append('Tôi được dùng những module nào trên portal?')
    else:
        suggestions.append('Hướng dẫn sử dụng portal ở đâu?')

    return _filter_unique(suggestions, history=None, limit=3)

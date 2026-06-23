"""Tách và chuẩn hoá URL trong ô Link báo cáo."""

from __future__ import annotations

import re

_URL_IN_TEXT_RE = re.compile(r'https?://[^\s<>"\')\]\},]+', re.I)
_TRAILING_PUNCT = '.,;:!?)]}\'"'


def _strip_url_punctuation(url: str) -> str:
    return (url or '').rstrip(_TRAILING_PUNCT)


def extract_urls_from_text(text: str) -> list[str]:
    """Lấy mọi URL http(s) trong một dòng text tự do."""
    urls: list[str] = []
    for match in _URL_IN_TEXT_RE.finditer(text or ''):
        url = _strip_url_punctuation(match.group(0))
        if url and url not in urls:
            urls.append(url)
    return urls


def parse_link_lines(links_text: str) -> list[str]:
    """Danh sách URL từ nội dung ô Link — mỗi dòng có thể kèm câu chữ."""
    urls: list[str] = []
    for line in (links_text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        found = extract_urls_from_text(line)
        if found:
            for url in found:
                if url not in urls:
                    urls.append(url)
            continue
        if re.match(r'^www\.', line, re.I):
            url = 'https://' + _strip_url_punctuation(line.split()[0])
            if url not in urls:
                urls.append(url)
            continue
        if re.match(r'^https?://', line, re.I):
            url = _strip_url_punctuation(line.split()[0])
            if url not in urls:
                urls.append(url)
    return urls


def normalize_links_text(links_text: str) -> str:
    """Khi lưu form — chỉ giữ URL, mỗi dòng một link."""
    return '\n'.join(parse_link_lines(links_text))


def link_line_note(line: str, url: str) -> str:
    """Phần chữ thừa trên dòng (hiển thị ghi chú ngắn)."""
    note = (line or '').replace(url, '', 1).strip(' \t:–-—|')
    return note

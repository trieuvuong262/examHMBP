"""
Remove Bootstrap Icons — chỉ icon trang trí (không nằm trong nút / link btn).

Giữ icon trong: button, a.btn, dropdown-toggle.
Giữ nguyên: portal_sidebar.html, hamburger mobile (base.html).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    return subprocess.call([sys.executable, str(ROOT / 'scripts' / 'strip_decorative_icons.py')], cwd=ROOT)


if __name__ == '__main__':
    sys.exit(main())

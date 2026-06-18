"""Khôi phục HTML trước khi gỡ icon, rồi chỉ gỡ icon trang trí + vỏ icon rỗng."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = 'bf93380~1'
FILE_LIST = ROOT / 'scripts' / '_icon_strip_files.txt'


def git_checkout_files() -> None:
    paths = [
        line.strip()
        for line in FILE_LIST.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    if not paths:
        raise SystemExit('No files in _icon_strip_files.txt')
    batch = 40
    for i in range(0, len(paths), batch):
        chunk = paths[i:i + batch]
        subprocess.run(
            ['git', 'checkout', SOURCE_COMMIT, '--', *chunk],
            cwd=ROOT,
            check=True,
        )
    print(f'Restored {len(paths)} HTML files from {SOURCE_COMMIT}')


def run_script(name: str) -> None:
    subprocess.run([sys.executable, str(ROOT / 'scripts' / name)], cwd=ROOT, check=True)


def main() -> int:
    git_checkout_files()
    run_script('strip_decorative_icons.py')
    run_script('strip_icon_shells.py')
    print('\nRollback complete: interactive button icons kept, decorative icons removed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

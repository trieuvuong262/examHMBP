#!/usr/bin/env python3
"""Deploy guide TOC reorganization to VPS via scp + docker cp."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "root@103.90.224.203"
REMOTE = "/opt/portaljustplay"
CONTAINER = "portaljustplay-web-1"

INNER_DIR = ROOT / "templates" / "guide" / "inner"

FILES = [
    "templates/guide/_section_panel.html",
    "templates/guide/_default_body.html",
    "static/css/justplay-theme.css",
] + [
    f"templates/guide/inner/{p.name}" for p in sorted(INNER_DIR.glob("*.html"))
]


def run(cmd, check=True):
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def main():
    for rel in FILES:
        src = ROOT / rel
        if not src.exists():
            print(f"MISSING {src}", file=sys.stderr)
            sys.exit(1)
        remote_path = f"{REMOTE}/{rel.replace(chr(92), '/')}"
        run(["scp", "-o", "StrictHostKeyChecking=no", str(src), f"{HOST}:{remote_path}"])

    remote_cmds = """
set -e
cd {REMOTE}
for f in {files}; do
  docker cp "$f" {CONTAINER}:/app/$f
done
docker compose exec -T web python manage.py collectstatic --noinput
docker compose restart web
docker compose exec -T web python manage.py shell -c 'from hrm.models import UserGuide; g=UserGuide.load(); print("overrides", list((g.section_overrides or {{}}).keys()))'
""".format(REMOTE=REMOTE, CONTAINER=CONTAINER, files=" ".join(FILES))
    run(["ssh", "-o", "StrictHostKeyChecking=no", HOST, remote_cmds])
    print("Deploy done.")


if __name__ == "__main__":
    main()

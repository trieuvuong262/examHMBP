#!/usr/bin/env python
"""Export JustPlay-NAS-Config.local.json from Portal DB for local PS1 testing."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from documents.views_nas_download import nas_download_config, nas_user_bundle_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Portal username (e.g. huuchung)")
    parser.add_argument(
        "-o",
        "--output",
        default=str(ROOT / "scripts" / "JustPlay-NAS-Config.local.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    User = get_user_model()
    try:
        user = User.objects.get(username=args.username)
    except User.DoesNotExist:
        print(f"User not found: {args.username}", file=sys.stderr)
        return 1

    class _Req:
        def build_absolute_uri(self, path: str) -> str:
            base = os.getenv("PORTAL_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
            if path == "/":
                return f"{base}/"
            return f"{base}{path}"

    cfg = nas_download_config()
    bundle = nas_user_bundle_config(_Req(), user, cfg)
    out = Path(args.output)
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shares = bundle.get("shares") or []
    print(f"Wrote {out} ({len(shares)} shares for {args.username})")
    if shares:
        print("  " + ", ".join(shares))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

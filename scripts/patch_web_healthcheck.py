#!/usr/bin/env python3
"""Patch web service healthcheck in docker-compose.yml (slim image has no wget)."""
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"

OLD = """    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://127.0.0.1:8000/ || exit 1"]
      interval: 20s
      timeout: 5s
      retries: 5"""

NEW = """    healthcheck:
      test:
        [
          "CMD-SHELL",
          "python -c \\"import http.client; c=http.client.HTTPConnection('127.0.0.1',8000,timeout=5); c.request('GET','/accounts/login/'); r=c.getresponse(); exit(0 if r.status in (200,301,302) else 1)\\"",
        ]
      interval: 20s
      timeout: 10s
      retries: 5
      start_period: 30s"""

# Also patch urllib-based healthcheck from an earlier hotfix.
OLD_URLLIB = """    healthcheck:
      test:
        [
          "CMD-SHELL",
          "python -c \\"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/accounts/login/', timeout=5)\\"",
        ]
      interval: 20s
      timeout: 10s
      retries: 5
      start_period: 30s"""


def main():
    text = COMPOSE.read_text(encoding="utf-8")
    if OLD in text:
        COMPOSE.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    elif OLD_URLLIB in text:
        COMPOSE.write_text(text.replace(OLD_URLLIB, NEW, 1), encoding="utf-8")
    elif "http.client.HTTPConnection('127.0.0.1',8000" in text:
        print("already patched")
        return
    else:
        raise SystemExit(f"healthcheck block not found in {COMPOSE}")
    print(f"patched {COMPOSE}")


if __name__ == "__main__":
    main()

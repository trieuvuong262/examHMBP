"""So sánh số bảng giữa hrms_db (local dev) và portaljustplay_db."""
from pathlib import Path

import psycopg2

LOCAL = {
    "host": "127.0.0.1",
    "user": "postgres",
    "password": "123123",
    "dbname": "hrms_db",
}

VPS_LIST = Path(__file__).with_name("_vps_tables.txt")


def table_names(cfg):
    conn = psycopg2.connect(**cfg)
    cur = conn.cursor()
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
    )
    names = {row[0] for row in cur.fetchall()}
    conn.close()
    return names


def load_vps_names():
    if not VPS_LIST.exists():
        return None
    names = set()
    for line in VPS_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("(") or "rows)" in line:
            continue
        parts = line.split("|")
        if parts:
            names.add(parts[0].strip())
    return names or None


def main():
    local = table_names(LOCAL)
    print(f"hrms_db (local dev): {len(local)} bang")

    vps = load_vps_names()
    if vps:
        print(f"portaljustplay_db (VPS): {len(vps)} bang")
        only_local = sorted(local - vps)
        only_vps = sorted(vps - local)
        if only_local:
            print(f"Chi co tren local hrms_db ({len(only_local)}):")
            for t in only_local[:20]:
                print(f"  - {t}")
        if only_vps:
            print(f"Chi co tren VPS ({len(only_vps)}):")
            for t in only_vps[:20]:
                print(f"  - {t}")
        if not only_local and not only_vps:
            print("Hai DB co CUNG danh sach bang (public).")
    else:
        print("Chua co _vps_tables.txt — export tu VPS de so sanh.")

    try:
        old = table_names({**LOCAL, "dbname": "portaljustplay_db"})
        print(f"\nportaljustplay_db (tren may local, neu co): {len(old)} bang")
        if len(old) < len(local):
            print("=> DB portaljustplay_db LOCAL la ban cu/thieu — KHONG phai VPS.")
    except Exception as exc:
        print("portaljustplay_db local:", exc)


if __name__ == "__main__":
    main()

import psycopg2

for dbname in ("hrms_db", "hrm_db", "portaljustplay_db"):
    try:
        conn = psycopg2.connect(
            host="127.0.0.1",
            user="postgres",
            password="123123",
            dbname=dbname,
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE tablename LIKE 'announcements%'"
        )
        tables = cur.fetchall()
        cur.execute(
            "SELECT app, name FROM django_migrations WHERE app='announcements'"
        )
        migrations = cur.fetchall()
        print(dbname, "tables=", tables, "migrations=", migrations)
        conn.close()
    except Exception as exc:
        print(dbname, "ERROR", exc)

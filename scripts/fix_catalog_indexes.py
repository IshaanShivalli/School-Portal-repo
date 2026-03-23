import os
import psycopg2


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is required")
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DROP INDEX IF EXISTS idx_catalog_schools_lookup")
                cur.execute("DROP INDEX IF EXISTS uniq_catalog_schools_lookup")
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_catalog_schools_lookup "
                    "ON catalog_schools (country, state, district, school_type)"
                )
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uniq_catalog_schools_lookup "
                    "ON catalog_schools (country, state, district, school_type, name)"
                )
        print("OK")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

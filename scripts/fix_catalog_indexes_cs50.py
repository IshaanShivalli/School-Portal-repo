import os
from cs50 import SQL


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is required")
    db = SQL(db_url)
    db.execute("DROP INDEX IF EXISTS idx_catalog_schools_lookup")
    db.execute("DROP INDEX IF EXISTS uniq_catalog_schools_lookup")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_schools_lookup "
        "ON catalog_schools (country, state, district, school_type)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uniq_catalog_schools_lookup "
        "ON catalog_schools (country, state, district, school_type, name)"
    )
    print("OK")


if __name__ == "__main__":
    main()

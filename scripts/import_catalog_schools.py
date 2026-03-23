import argparse
import csv
import os
import sys
import tempfile
from typing import List, Tuple

import psycopg2

GOV_KEYWORDS = (
    "government",
    "department",
    "local body",
    "kendriya",
    "navodaya",
    "kvs",
    "jawa",
    "tribal",
    "social welfare",
    "railway",
    "defence",
    "municipal",
    "zila",
    "govt",
)

OTHER_KEYWORDS = (
    "unrecognized",
    "madarsa",
    "other",
    "private unaided (unrecognized)",
)


def normalize_school_type(management: str) -> str:
    m = (management or "").strip().lower()
    if not m:
        return "other"
    if "private" in m:
        return "private"
    if any(k in m for k in OTHER_KEYWORDS):
        return "other"
    if any(k in m for k in GOV_KEYWORDS):
        return "government"
    return "other"


def ensure_tables(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_schools (
            id SERIAL PRIMARY KEY,
            country TEXT,
            school_type TEXT NOT NULL,
            state TEXT NOT NULL,
            district TEXT,
            name TEXT NOT NULL
        )
        """
    )
    cur.execute("ALTER TABLE catalog_schools ADD COLUMN IF NOT EXISTS country TEXT")
    cur.execute("ALTER TABLE catalog_schools ADD COLUMN IF NOT EXISTS district TEXT")
    cur.execute("UPDATE catalog_schools SET country = 'India' WHERE country IS NULL")
    cur.execute("UPDATE catalog_schools SET district = 'Unknown District' WHERE district IS NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_catalog_schools_lookup ON catalog_schools (country, state, district, school_type)")


def main():
    parser = argparse.ArgumentParser(description="Import schools into catalog_schools.")
    parser.add_argument("--db", dest="db_url", default=os.environ.get("DATABASE_URL"), help="PostgreSQL URL")
    parser.add_argument("--csv", dest="csv_path", required=True, help="Path to udise_schools.csv")
    parser.add_argument("--reset", action="store_true", help="Clear catalog_schools before insert")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit for testing")
    args = parser.parse_args()

    if not args.db_url:
        print("DATABASE_URL is required", file=sys.stderr)
        sys.exit(2)

    csv_path = args.csv_path
    if not os.path.exists(csv_path):
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(2)

    conn = psycopg2.connect(args.db_url)
    inserted = 0
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_tables(cur)
                if args.reset:
                    cur.execute("TRUNCATE catalog_schools")

                cur.execute("CREATE TEMP TABLE temp_catalog_schools (country TEXT, school_type TEXT, state TEXT, district TEXT, name TEXT)")

                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False) as tmp:
                        temp_path = tmp.name
                        writer = csv.writer(tmp)
                        with open(csv_path, newline="", encoding="utf-8") as fh:
                            reader = csv.DictReader(fh)
                            if "schname" not in reader.fieldnames or "stname" not in reader.fieldnames or "dtname" not in reader.fieldnames:
                                raise ValueError("CSV missing required columns: schname, stname, dtname")
                            for idx, row in enumerate(reader, start=1):
                                name = (row.get("schname") or "").strip()
                                state = (row.get("stname") or "").strip()
                                district = (row.get("dtname") or "").strip()
                                management = (row.get("management") or "").strip()
                                if not name or not state:
                                    continue
                                school_type = normalize_school_type(management)
                                writer.writerow(["India", school_type, state, district or "Unknown District", name])
                                inserted += 1
                                if args.limit and idx >= args.limit:
                                    break

                    with open(temp_path, "r", encoding="utf-8") as tmp_in:
                        cur.copy_expert(
                            "COPY temp_catalog_schools (country, school_type, state, district, name) FROM STDIN WITH (FORMAT CSV)",
                            tmp_in,
                        )
                finally:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)

                cur.execute(
                    "INSERT INTO catalog_schools (country, school_type, state, district, name) "
                    "SELECT DISTINCT t.country, t.school_type, t.state, t.district, t.name "
                    "FROM temp_catalog_schools t "
                    "WHERE NOT EXISTS ("
                    "  SELECT 1 FROM catalog_schools c "
                    "  WHERE c.country = t.country AND c.state = t.state AND c.district = t.district "
                    "    AND c.school_type = t.school_type AND c.name = t.name"
                    ")"
                )

        print(f"Imported ~{inserted} rows into catalog_schools")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

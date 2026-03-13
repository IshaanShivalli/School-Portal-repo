import argparse
import csv
import os
import sys
from typing import List

import psycopg2
from psycopg2.extras import execute_values


def load_states(csv_path: str) -> List[str]:
    states = set()
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if "state" not in reader.fieldnames:
            raise ValueError("CSV missing 'state' column")
        for row in reader:
            state = (row.get("state") or "").strip()
            if state:
                states.add(state)
    return sorted(states)


def ensure_tables(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_states (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
        """
    )


def upsert_states(cur, states: List[str]):
    rows = [(s,) for s in states]
    execute_values(
        cur,
        "INSERT INTO catalog_states (name) VALUES %s ON CONFLICT (name) DO NOTHING",
        rows,
        page_size=500,
    )


def main():
    parser = argparse.ArgumentParser(description="Import unique states into catalog_states.")
    parser.add_argument("--db", dest="db_url", default=os.environ.get("DATABASE_URL"), help="PostgreSQL URL")
    parser.add_argument("--csv", dest="csv_path", required=True, help="Path to 100_prof1.csv")
    parser.add_argument("--reset", action="store_true", help="Clear catalog_states before insert")
    args = parser.parse_args()

    if not args.db_url:
        print("DATABASE_URL is required", file=sys.stderr)
        sys.exit(2)

    states = load_states(args.csv_path)
    if not states:
        print("No states found", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(args.db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_tables(cur)
                if args.reset:
                    cur.execute("TRUNCATE catalog_states")
                upsert_states(cur, states)
        print(f"Inserted {len(states)} states into catalog_states")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

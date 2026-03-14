import csv
import os

INPUT_CSV = "udise_schools.csv"
CHUNK_SIZE = 50000 
OUTPUT_DIR = "chunks"

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(INPUT_CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    chunk_num = 0
    rows = []

    for row in reader:
        rows.append(row)
        if len(rows) >= CHUNK_SIZE:
            out_path = f"{OUTPUT_DIR}/chunk_{chunk_num}.csv"
            with open(out_path, "w", newline="", encoding="utf-8") as out:
                writer = csv.DictWriter(out, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
            print(f"Written {out_path} ({len(rows)} rows)")
            rows = []
            chunk_num += 1

    # Write remaining rows
    if rows:
        out_path = f"{OUTPUT_DIR}/chunk_{chunk_num}.csv"
        with open(out_path, "w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Written {out_path} ({len(rows)} rows)")

print("Done!")
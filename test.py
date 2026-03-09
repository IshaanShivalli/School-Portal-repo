from cs50 import SQL

db = SQL("sqlite:///db.sqlite3")

try:
       db.execute("ALTER TABLE feedback ADD COLUMN rating INTEGER NOT NULL DEFAULT 5")
except:
       pass
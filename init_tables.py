import sqlite3
from datetime import datetime

conn = sqlite3.connect("database.db")
c = conn.cursor()

# Skapa pending_cities om den inte finns
c.execute('''
CREATE TABLE IF NOT EXISTS pending_cities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    submitted_by TEXT,
    timestamp TEXT
)
''')

# (Valfritt) approved_cities också
c.execute('''
CREATE TABLE IF NOT EXISTS approved_cities (
    name TEXT PRIMARY KEY
)
''')

conn.commit()
conn.close()
print("✅ Tables created")

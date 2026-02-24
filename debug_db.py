import sqlite3
import os

db_path = "people_counter.db"
if not os.path.exists(db_path):
    print(f"Database {db_path} not found")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- Tables ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print(cursor.fetchall())
    
    print("\n--- Tripwires ---")
    try:
        cursor.execute("SELECT * FROM tripwires;")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error reading tripwires: {e}")
        
    print("\n--- Video Sources ---")
    try:
        cursor.execute("SELECT id, name, type FROM video_sources;")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error reading video_sources: {e}")
        
    conn.close()

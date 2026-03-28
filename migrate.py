import sqlite3
import os

db_path = "database.db"

def migrate():
    if not os.path.exists(db_path):
        print("Database does not exist yet. Skip migration.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get current columns
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Current columns in 'users': {columns}")

    needed_columns = [
        ("token_mos", "TEXT"),
        ("token_mo", "TEXT"),
        ("student_id", "TEXT"),
        ("tests_solved", "INTEGER DEFAULT 0"),
        ("avg_score", "REAL DEFAULT 0"),
        ("speed", "TEXT DEFAULT 'normal'"),
        ("ai_enabled", "INTEGER DEFAULT 1")
    ]

    for col_name, col_type in needed_columns:
        if col_name not in columns:
            print(f"Adding column '{col_name}'...")
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                print(f"Column '{col_name}' added successfully.")
            except Exception as e:
                print(f"Error adding '{col_name}': {e}")
    
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()

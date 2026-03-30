import sqlite3
import os
from config import DB_NAME

def migrate_user_groups():
    print(f"Migrating database: {DB_NAME}")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    try:
        # 1. Create a new table with the updated CHECK constraint
        print("Creating temporary table...")
        cur.execute('''
        CREATE TABLE IF NOT EXISTS user_groups_new (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            telegram_username TEXT,
            group_name TEXT NOT NULL CHECK(group_name IN ('INFRA', 'CE', 'APPS', 'MONITORING'))
        )''')
        
        # 2. Copy data from the old table to the new one
        print("Copying data...")
        cur.execute("INSERT INTO user_groups_new (user_id, username, telegram_username, group_name) SELECT user_id, username, telegram_username, group_name FROM user_groups")
        
        # 3. Drop the old table
        print("Dropping old table...")
        cur.execute("DROP TABLE user_groups")
        
        # 4. Rename the new table to the old one's name
        print("Renaming new table...")
        cur.execute("ALTER TABLE user_groups_new RENAME TO user_groups")
        
        # 5. Initialize the new settings (kuota_monitoring, max_hari_monitoring) 
        # This will be handled by init_default_settings() in core/database.py when the app runs, 
        # but let's do it here too just to be sure.
        print("Initializing new settings...")
        defaults = [
            ('kuota_monitoring', '1', 'Jumlah orang Monitoring per hari'),
            ('max_hari_monitoring', '31', 'Maksimal hari standby per bulan untuk Monitoring'),
        ]
        for key, value, desc in defaults:
            cur.execute("SELECT 1 FROM settings WHERE key = ?", (key,))
            if not cur.fetchone():
                cur.execute("INSERT INTO settings (key, value, description) VALUES (?, ?, ?)", (key, value, desc))
        
        conn.commit()
        print("✅ Migration successful!")
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_user_groups()

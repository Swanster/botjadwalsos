# fix_jadwal_usernames.py
# Script untuk memperbaiki data username di tabel jadwal
# yang kosong atau tidak sesuai dengan user_groups

import sqlite3
import os

DB_NAME = os.path.join('data', 'jadwal_pro.db')

def fix_jadwal_usernames():
    """Update semua jadwal records dengan username yang benar dari user_groups."""
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Ambil semua user dari user_groups
    cur.execute("SELECT user_id, username, telegram_username FROM user_groups")
    user_groups = {row['user_id']: dict(row) for row in cur.fetchall()}
    
    # Ambil semua jadwal yang perlu diperbaiki
    cur.execute("""
        SELECT j.id, j.user_id, j.username, j.telegram_username, j.tanggal
        FROM jadwal j
    """)
    jadwal_list = cur.fetchall()
    
    print(f"📊 Total jadwal records: {len(jadwal_list)}")
    print(f"👥 Total registered users: {len(user_groups)}")
    print("-" * 50)
    
    updated_count = 0
    
    for j in jadwal_list:
        user_id = j['user_id']
        current_username = j['username'] or ''
        current_tg_username = j['telegram_username'] or ''
        
        if user_id in user_groups:
            ug = user_groups[user_id]
            correct_username = ug['username'] or ''
            correct_tg_username = ug['telegram_username'] or ''
            
            # Check if update needed
            needs_update = (
                current_username != correct_username or 
                current_tg_username != correct_tg_username
            )
            
            if needs_update:
                print(f"📝 Updating jadwal ID {j['id']} (tanggal: {j['tanggal']}):")
                print(f"   User ID: {user_id}")
                print(f"   Username: '{current_username}' → '{correct_username}'")
                print(f"   TG Username: '{current_tg_username}' → '{correct_tg_username}'")
                
                cur.execute("""
                    UPDATE jadwal 
                    SET username = ?, telegram_username = ?
                    WHERE id = ?
                """, (correct_username, correct_tg_username, j['id']))
                
                updated_count += 1
    
    conn.commit()
    conn.close()
    
    print("-" * 50)
    print(f"✅ Selesai! {updated_count} records berhasil diperbarui.")
    
    return updated_count

if __name__ == "__main__":
    print("=" * 50)
    print("🔧 Fix Jadwal Usernames Script")
    print("=" * 50)
    fix_jadwal_usernames()

#!/usr/bin/env python3
"""
Script untuk update data jadwal lama dengan nama lengkap dari user_groups.
Menampilkan Nama Lengkap di Google Sheets, bukan username Telegram.

Jalankan: python update_jadwal_usernames.py
"""

import sqlite3
import os
from config import DB_NAME

def update_jadwal_usernames():
    """Update semua data di tabel jadwal dengan username dari user_groups."""
    
    if not os.path.exists(DB_NAME):
        print(f"❌ Database tidak ditemukan: {DB_NAME}")
        return
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    print("=" * 60)
    print("🔄 Update Data Jadwal dengan Nama Lengkap")
    print("=" * 60)
    
    # 1. Cek berapa banyak data di user_groups
    cur.execute("SELECT COUNT(*) as total FROM user_groups")
    total_users = cur.fetchone()['total']
    print(f"\n📊 Total user di user_groups: {total_users}")
    
    # 2. Cek berapa banyak data di jadwal
    cur.execute("SELECT COUNT(*) as total FROM jadwal")
    total_jadwal = cur.fetchone()['total']
    print(f"📊 Total data jadwal: {total_jadwal}")
    
    # 3. Ambil semua user dari user_groups
    cur.execute("""
        SELECT user_id, username, telegram_username 
        FROM user_groups 
        WHERE username IS NOT NULL
    """)
    users = cur.fetchall()
    
    print(f"\n🔄 Memulai update {len(users)} user...")
    
    # 4. Update data jadwal untuk setiap user
    updated_count = 0
    for user in users:
        user_id = user['user_id']
        nama_lengkap = user['username']
        telegram_username = user['telegram_username']
        
        # Update jadwal untuk user ini
        cur.execute("""
            UPDATE jadwal 
            SET username = ?, 
                telegram_username = ?
            WHERE user_id = ?
        """, (nama_lengkap, telegram_username, user_id))
        
        rows_updated = cur.rowcount
        if rows_updated > 0:
            updated_count += rows_updated
            print(f"  ✓ {nama_lengkap} (@{telegram_username}): {rows_updated} jadwal diupdate")
    
    # 5. Commit perubahan
    conn.commit()
    
    print("\n" + "=" * 60)
    print(f"✅ Selesai! {updated_count} data jadwal diupdate.")
    print("=" * 60)
    
    # 6. Tampilkan ringkasan
    print("\n📋 Ringkasan:")
    print(f"  • Data jadwal sebelum: {total_jadwal}")
    print(f"  • Data yang diupdate: {updated_count}")
    print(f"  • Data yang tidak berubah: {total_jadwal - updated_count}")
    
    # 7. Tampilkan preview data setelah update
    print("\n📋 Preview 5 data pertama:")
    cur.execute("""
        SELECT j.tanggal, j.username, j.telegram_username, ug.group_name
        FROM jadwal j
        LEFT JOIN user_groups ug ON j.user_id = ug.user_id
        ORDER BY j.tanggal ASC, j.username ASC
        LIMIT 5
    """)
    
    preview = cur.fetchall()
    if preview:
        print(f"  {'Tanggal':<12} | {'Nama Lengkap':<25} | {'Telegram':<20} | {'Group'}")
        print(f"  {'-'*12} | {'-'*25} | {'-'*20} | {'-'*10}")
        for row in preview:
            telegram = f"@{row['telegram_username']}" if row['telegram_username'] else "-"
            group = row['group_name'] if row['group_name'] else "-"
            print(f"  {row['tanggal']:<12} | {row['username']:<25} | {telegram:<20} | {group}")
    
    conn.close()
    
    print("\n✅ Script selesai. Sekarang sync ulang ke Google Sheets!")
    print("   Buka web dashboard → Google Sheets → Sync Semua Data")

if __name__ == "__main__":
    update_jadwal_usernames()

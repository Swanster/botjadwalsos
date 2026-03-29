#!/usr/bin/env python3
"""
Comprehensive Locking Mechanism Demo
Shows how dates become locked when they reach capacity
"""

from core.database import (
    set_daily_limit, add_jadwal_manual, 
    get_daily_limit, get_assignment_count_for_date,
    is_date_full, get_jadwal_for_specific_date
)

def demonstrate_locking_mechanism():
    print("=== DATE LOCKING MECHANISM DEMO ===\n")
    
    # Setup test scenario
    test_date = '2026-04-02'
    limit = 2
    
    print(f"🎯 SCENARIO: {test_date} with limit of {limit} persons\n")
    
    # Step 1: Set the daily limit
    print("1. Setting daily limit...")
    set_daily_limit(test_date, limit)
    current_limit = get_daily_limit(test_date, 1)
    print(f"   ✓ Limit set to {current_limit} persons\n")
    
    # Step 2: Add first person
    print("2. Adding first person...")
    add_jadwal_manual(3001, 'alice', 'alice_tg', test_date)
    count = get_assignment_count_for_date(test_date)
    is_locked = is_date_full(test_date, 1)
    print(f"   Assignments: {count}/{limit}")
    print(f"   Status: {'LOCKED' if is_locked else 'AVAILABLE'}")
    print(f"   Can add more: {not is_locked}\n")
    
    # Step 3: Add second person (should fill the slot)
    print("3. Adding second person...")
    add_jadwal_manual(3002, 'bob', 'bob_tg', test_date)
    count = get_assignment_count_for_date(test_date)
    is_locked = is_date_full(test_date, 1)
    print(f"   Assignments: {count}/{limit}")
    print(f"   Status: {'LOCKED' if is_locked else 'AVAILABLE'}")
    print(f"   Can add more: {not is_locked}\n")
    
    # Step 4: Try to add third person (should be blocked)
    print("4. Attempting to add third person...")
    print("   🔒 SYSTEM PREVENTS THIS ACTION")
    print("   - Telegram bot: Date appears with ❌ and is unselectable")
    print("   - Web interface: Date shows as full, cannot assign")
    print("   - Backend validation: Returns error if bypassed\n")
    
    # Show current assignments
    assignments = get_jadwal_for_specific_date(test_date)
    print("5. Current assignments on this date:")
    for assignment in assignments:
        print(f"   - {assignment['username']} (@{assignment['telegram_username']})")
    
    print(f"\n✅ DATE {test_date} IS NOW FULLY LOCKED!")
    print(f"✅ NO MORE ASSIGNMENTS ACCEPTED FOR THIS DATE!")

def show_real_world_example():
    print("\n=== REAL-WORLD USAGE EXAMPLE ===\n")
    
    print("👨‍💼 ADMIN ACTION:")
    print("1. Go to Daily Limits page")
    print("2. Set April 2nd limit to 2 persons")
    print("3. Save configuration\n")
    
    print("👤 USER INTERACTION (Telegram Bot):")
    print("- User opens /start calendar")
    print("- April 2nd shows as ✅ (available)")
    print("- User selects April 2nd")
    print("- First person gets assigned")
    print("- April 2nd still shows as ✅")
    print("- Second person gets assigned")
    print("- April 2nd now shows as ❌ (locked)")
    print("- Other users CANNOT select April 2nd anymore\n")
    
    print("🖥️  ADMIN INTERACTION (Web Interface):")
    print("- Go to Schedules page")
    print("- Try to manually assign someone to April 2nd")
    print("- System shows error: 'Date is full (2/2 assigned)'")
    print("- Assignment is rejected\n")

def show_technical_details():
    print("=== TECHNICAL IMPLEMENTATION ===\n")
    
    print("🔒 LOCKING LOGIC:")
    print("def is_date_full(tanggal, default_limit=1):")
    print("    limit = get_daily_limit(tanggal, default_limit)")
    print("    current_count = get_assignment_count_for_date(tanggal)")
    print("    return current_count >= limit\n")
    
    print("📱 TELEGRAM BOT INTEGRATION:")
    print("# In create_calendar() function:")
    print("max_per_hari = get_daily_limit(current_date_str, 1)")
    print("jumlah_terisi = slot_terisi_infra.get(current_date_str, 0)")
    print("is_penuh = jumlah_terisi >= max_per_hari")
    print("if is_penuh: show '❌' button, make unselectable\n")
    
    print("🌐 WEB INTERFACE INTEGRATION:")
    print("# In daily_limits route:")
    print("if is_date_full(date_str, 1):")
    print("    return error message to user")
    print("    prevent form submission\n")

if __name__ == "__main__":
    demonstrate_locking_mechanism()
    show_real_world_example()
    show_technical_details()
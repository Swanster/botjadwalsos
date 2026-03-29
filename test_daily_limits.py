#!/usr/bin/env python3
"""
Test script for daily assignment limits functionality
"""

from core.database import (
    set_daily_limit, get_daily_limit, get_all_daily_limits, delete_daily_limit,
    add_jadwal_manual, get_jadwal_for_specific_date, is_date_full
)

def test_daily_limits():
    print("=== Testing Daily Assignment Limits ===\n")
    
    # Test 1: Set daily limits
    print("1. Setting daily limits...")
    set_daily_limit('2026-04-01', 1)  # Only 1 person allowed
    set_daily_limit('2026-04-02', 2)  # 2 people allowed
    set_daily_limit('2026-04-03', 3)  # 3 people allowed
    print("✓ Daily limits set successfully\n")
    
    # Test 2: Get daily limits
    print("2. Retrieving daily limits...")
    limits = get_all_daily_limits()
    for limit in limits:
        print(f"   {limit['tanggal']}: {limit['max_assignments']} persons")
    print()
    
    # Test 3: Test default limit
    print("3. Testing default limit...")
    default_limit = get_daily_limit('2026-04-10', 1)  # Date without specific limit
    print(f"   Default limit for 2026-04-10: {default_limit} persons\n")
    
    # Test 4: Test assignment counting
    print("4. Testing assignment counting...")
    
    # Add some test assignments
    add_jadwal_manual(1001, 'user1', 'user1_tg', '2026-04-01')
    add_jadwal_manual(1002, 'user2', 'user2_tg', '2026-04-01')  # This should exceed limit
    
    assignments = get_jadwal_for_specific_date('2026-04-01')
    print(f"   Assignments on 2026-04-01: {len(assignments)} persons")
    for assignment in assignments:
        print(f"     - {assignment['username']}")
    
    # Check if date is full
    is_full = is_date_full('2026-04-01', 1)
    print(f"   Is 2026-04-01 full? {is_full}")
    print()
    
    # Test 5: Test another date
    print("5. Testing date with higher limit...")
    add_jadwal_manual(1003, 'user3', 'user3_tg', '2026-04-02')
    add_jadwal_manual(1004, 'user4', 'user4_tg', '2026-04-02')
    
    assignments_day2 = get_jadwal_for_specific_date('2026-04-02')
    print(f"   Assignments on 2026-04-02: {len(assignments_day2)} persons")
    is_full_day2 = is_date_full('2026-04-02', 1)
    print(f"   Is 2026-04-02 full? {is_full_day2}")
    print()
    
    # Test 6: Clean up
    print("6. Cleaning up test data...")
    delete_daily_limit('2026-04-01')
    delete_daily_limit('2026-04-02')
    delete_daily_limit('2026-04-03')
    print("✓ Test completed successfully!")

if __name__ == "__main__":
    test_daily_limits()
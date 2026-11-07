#!/usr/bin/env python3
"""
Demo script showing the new bulk monthly limits feature
"""

from core.database import (
    set_daily_limit, get_daily_limit, get_all_daily_limits, 
    delete_daily_limit
)
import calendar
from datetime import datetime

def demo_bulk_monthly_limits():
    print("=== Demo: Bulk Monthly Limits Feature ===\n")
    
    # Clear any existing April 2026 limits for clean demo
    print("1. Cleaning existing April 2026 limits...")
    for day in range(1, 31):
        tanggal = f"2026-04-{day:02d}"
        delete_daily_limit(tanggal)
    print("✓ Cleaned existing limits\n")
    
    # Show current state
    print("2. Current state (should be empty for April 2026):")
    limits = get_all_daily_limits()
    april_limits = [l for l in limits if l['tanggal'].startswith('2026-04')]
    print(f"   April 2026 limits: {len(april_limits)} dates\n")
    
    # Demonstrate bulk setting
    print("3. Setting bulk limit of 2 persons/day for April 2026...")
    tahun, bulan = 2026, 4
    days_in_month = calendar.monthrange(tahun, bulan)[1]
    target_limit = 2
    
    success_count = 0
    for day in range(1, days_in_month + 1):
        tanggal = f"{tahun}-{bulan:02d}-{day:02d}"
        if set_daily_limit(tanggal, target_limit):
            success_count += 1
    
    print(f"✓ Successfully set limit {target_limit} for {success_count}/{days_in_month} days\n")
    
    # Verify results
    print("4. Verification:")
    limits_after = get_all_daily_limits()
    april_limits_after = [l for l in limits_after if l['tanggal'].startswith('2026-04')]
    
    print(f"   Total April limits now: {len(april_limits_after)}")
    
    # Sample verification
    sample_dates = ['2026-04-01', '2026-04-15', '2026-04-30']
    for date in sample_dates:
        limit = get_daily_limit(date, 1)  # Default 1
        print(f"   {date}: {limit} persons")
    
    # Show different months still use default
    print(f"\n5. Other months still use default:")
    may_limit = get_daily_limit('2026-05-01', 1)
    jun_limit = get_daily_limit('2026-06-01', 1)
    print(f"   May 2026-05-01: {may_limit} persons (default)")
    print(f"   June 2026-06-01: {jun_limit} persons (default)")
    
    print("\n=== Bulk feature working perfectly! ===")

def show_usage_examples():
    print("\n=== Usage Examples ===")
    print("\n📊 WEB INTERFACE (Easiest):")
    print("1. Go to Daily Limits page")
    print("2. Select 'Untuk Seluruh Bulan' section") 
    print("3. Choose Month: April, Year: 2026")
    print("4. Set Max Orang/Hari: 2")
    print("5. Click 'Atur untuk Seluruh Bulan'")
    print("   → Result: All 30 days in April 2026 set to 2 persons limit")
    
    print("\n📝 MIXED CONFIGURATION:")
    print("# Set April 2026 to 2 persons for all days")
    print("# But override specific dates if needed")
    print("set_daily_limit('2026-04-01', 1)  # Override: April 1st = 1 person only")
    print("set_daily_limit('2026-04-15', 3)  # Override: April 15th = 3 persons")
    print("# Rest of April stays at 2 persons")

if __name__ == "__main__":
    demo_bulk_monthly_limits()
    show_usage_examples()
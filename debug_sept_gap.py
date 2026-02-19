#!/usr/bin/env python3
"""
Debug the 2024_sep_w3 gap by testing different date ranges
"""

from datetime import date, timedelta
from collectors.clinicaltrials.clinicaltrials_fetch import fetch_studies_raw

# The original week that returned 0 trials
week_start = date(2024, 9, 9)
week_end = date(2024, 9, 15)

print("Testing different date ranges to find where the data is...\n")

# Test 1: The exact week that failed
print(f"Test 1: Original week ({week_start} → {week_end})")
raw = fetch_studies_raw(
    updated_from=week_start,
    updated_to=week_end,
    page_size=1000,
    max_studies=100,
)
print(f"  Result: {len(raw)} trials\n")

# Test 2: Previous week (should have data)
prev_start = date(2024, 9, 2)
prev_end = date(2024, 9, 8)
print(f"Test 2: Previous week ({prev_start} → {prev_end})")
raw = fetch_studies_raw(
    updated_from=prev_start,
    updated_to=prev_end,
    page_size=1000,
    max_studies=100,
)
print(f"  Result: {len(raw)} trials\n")

# Test 3: Next week (should have data)
next_start = date(2024, 9, 16)
next_end = date(2024, 9, 22)
print(f"Test 3: Next week ({next_start} → {next_end})")
raw = fetch_studies_raw(
    updated_from=next_start,
    updated_to=next_end,
    page_size=1000,
    max_studies=100,
)
print(f"  Result: {len(raw)} trials\n")

# Test 4: First half of the problem week
mid = date(2024, 9, 12)
print(f"Test 4: First half ({week_start} → {mid})")
raw = fetch_studies_raw(
    updated_from=week_start,
    updated_to=mid,
    page_size=1000,
    max_studies=100,
)
print(f"  Result: {len(raw)} trials\n")

# Test 5: Second half of the problem week
print(f"Test 5: Second half ({mid + timedelta(days=1)} → {week_end})")
raw = fetch_studies_raw(
    updated_from=mid + timedelta(days=1),
    updated_to=week_end,
    page_size=1000,
    max_studies=100,
)
print(f"  Result: {len(raw)} trials\n")

# Test 6: Overlap with previous week
overlap_start = date(2024, 9, 8)
print(f"Test 6: Overlap prev week ({overlap_start} → {mid})")
raw = fetch_studies_raw(
    updated_from=overlap_start,
    updated_to=mid,
    page_size=1000,
    max_studies=100,
)
print(f"  Result: {len(raw)} trials\n")

# Test 7: Overlap with next week
overlap_end = date(2024, 9, 16)
print(f"Test 7: Overlap next week ({mid} → {overlap_end})")
raw = fetch_studies_raw(
    updated_from=mid,
    updated_to=overlap_end,
    page_size=1000,
    max_studies=100,
)
print(f"  Result: {len(raw)} trials\n")

# Test 8: Two-week span including the problem week
print(f"Test 8: Two-week span ({prev_start} → {week_end})")
raw = fetch_studies_raw(
    updated_from=prev_start,
    updated_to=week_end,
    page_size=1000,
    max_studies=100,
)
print(f"  Result: {len(raw)} trials\n")

print("=" * 60)
print("CONCLUSION:")
print("If Tests 2 & 3 have data but Test 1 doesn't, the API has a gap for that week.")
print("If Tests 4-7 show data, we can identify which specific days have issues.")
print("If Test 8 has more trials than Test 2 alone, we know data exists somewhere.")

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parse_rates import parse_lines

SAMPLE = """2025 TOTAL PROPERTY TAX RATES IN MICHIGAN
Total Millage for Principal Residence School District or Ag Exemption
Total Millage NonHomestead
COUNTY: Alcona
Alcona Twp 011010
ALCONA COMMUNITY SCH 20.2097 38.2097 14.2097 26.2097 20.2097 38.2097
VILLAGE OF LINCOLN ALCONA COMMUNITY SCH 27.8951 45.8951 21.8951 33.8951 27.8951 45.8951
*See the disclaimers at the end of this report. Page 1 of 176
COUNTY: Livingston
Genoa Twp 471050
BRIGHTON AREA SCHOOL 19.7707 37.7707 13.7707 25.7707 19.7707 37.7707
TR-HO/BR TR 96 16.8507 16.8507 10.8507 16.8507 16.8507 16.8507
TR-HO/ BR TR 13 18.3807 36.3807 12.3807 24.3807 18.3807 36.3807
HOWELL PUBLIC SCHOOL 23.0582 41.0582 17.0582 29.0582 23.0582 41.0582
HOWELL PUBLIC SCHOOL 23.5582 41.5582 17.0582 29.0582 23.0582 41.0582
Brighton City 472010
BRIGHTON AREA SCHOOL 36.6593 54.6593 30.6593 42.6593 36.6593 54.6593
AlgerCOUNTY:
Au Train Twp 021010
AUTRAIN-ONOTA PUBLIC 24.5800 42.5800 24.5800 42.5800 30.580018.5800
"""
rows = parse_lines(SAMPLE.splitlines())
for r in rows: print(r["county_name"], r["unit_code"], r["unit_name"], r["unit_type"], r["is_village"], r["label"], r["pre"], r["nh"], r["dup"])
assert len(rows) == 7, len(rows)
assert rows[1]["is_village"] == 1 and rows[1]["pre"] == "27.8951"
assert rows[4]["dup"] == 1
assert rows[5]["unit_type"] == "C" and rows[5]["nh"] == "54.6593"
assert rows[6]["county_name"] == "Alger" and rows[6]["c6"] == "18.5800"
print("ok")

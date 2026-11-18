import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parse_rates import parse_lines

# Shape of `pdftotext -layout` output from the 2025 report.
SAMPLE = """2025 TOTAL PROPERTY TAX RATES IN MICHIGAN
                                           School District         or Ag Exemption      NonHomestead     Personal (IPP)   Personal (CPP)      or Ag Exemption     NonHomestead
COUNTY: Alcona
 Gustin Twp                                  011050

                                           ALCONA COMMUNITY SCH        20.4251             38.4251           14.4251          26.4251              20.4251            38.4251
  VILLAGE OF LINCOLN                       ALCONA COMMUNITY SCH        27.8951             45.8951           21.8951          33.8951              27.8951            45.8951
                                           OSCODA AREA SCHOOLS         21.6125             39.6125           15.6125          27.6125              21.6125            39.6125
COUNTY: Livingston
 Genoa Twp                                   471050
                                           BRIGHTON AREA SCHOOL        19.7707             37.7707           13.7707          25.7707              19.7707            37.7707
                                           TR-HO/BR TR 96              16.8507             16.8507           10.8507          16.8507              16.8507            16.8507
                                           HOWELL PUBLIC SCHOOL        23.0582             41.0582           17.0582          29.0582              23.0582            41.0582
                                           HOWELL PUBLIC SCHOOL        23.5582             41.5582           17.0582          29.0582              23.0582            41.0582
 Brighton City                               472010
                                           BRIGHTON AREA SCHOOL        36.6593             54.6593           30.6593          42.6593              36.6593            54.6593
COUNTY: Wayne
 Grosse Pointe Shores Village Cit            822150
                                           GROSSE POINTE PUBLIC        40.1000             58.1000           34.1000          46.1000              40.1000            58.1000
"""
rows = parse_lines(SAMPLE.splitlines())
for r in rows:
    print(r["county_name"], r["unit_code"], r["unit_name"], r["unit_type"], r["village"] or "-", r["school"], r["pre"], r["nh"], r["dup"])
assert len(rows) == 8, len(rows)
assert rows[1]["village"] == "LINCOLN" and rows[1]["school"] == "ALCONA COMMUNITY SCH" and rows[1]["pre"] == "27.8951"
assert rows[5]["dup"] == 1
assert rows[6]["unit_type"] == "C" and rows[6]["nh"] == "54.6593"
assert rows[7]["unit_type"] == "C"
print("ok")

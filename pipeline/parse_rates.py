"""Parse Treasury's "Total Property Tax Rates in Michigan" PDF into a CSV.

The report lists, for every city and township, one row per school district
(and per village + school district) with six millage columns. The first two
are the totals for a principal residence (homestead) and for non-homestead
property, without special assessments. Those are the two this site uses.

Line shapes handled (seen in the 2019-2025 reports):
    COUNTY: Livingston            (or "LivingstonCOUNTY:" in older years)
    Brighton Twp 471010           unit header: name, type, 6-digit code
    BRIGHTON AREA SCHOOL 19.8570 37.8570 13.8570 25.8570 19.8570 37.8570
    VILLAGE OF FOWLERVILLE FOWLERVILLE COMMU 30.1 ...   (village row)
    TR-HO/BR TR 96 16.8507 ...    (transfer district: skipped)

Usage: python pipeline/parse_rates.py rates.pdf out.csv
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

NUM = re.compile(r"\d+\.\d{4}")
TAIL = re.compile(r"((?:\d+\.\d{4}\s*){6})\s*$")
UNIT = re.compile(r"^(?P<name>.+?)\s+(?P<code>\d{6})\s*$")
COUNTY_A = re.compile(r"^COUNTY:\s*(?P<name>.+?)\s*$", re.I)
COUNTY_B = re.compile(r"^(?P<name>.+?)\s*COUNTY:\s*$", re.I)
SKIP = ("See the disclaimers", "TOTAL PROPERTY TAX RATES", "Total Millage", "Principal Residence",
        "Principle Residence", "NonHomestead", "or Ag Exemption", "Personal (", "AdValorem",
        "School District", "Commercial", "Industrial")

FIELDS = ["county_code", "county_name", "unit_code", "unit_name", "unit_type", "is_village",
          "village", "school", "label", "pre", "nh", "c3", "c4", "c5", "c6", "dup"]


def pdf_lines(path):
    """Text lines from the PDF. Uses pdftotext in layout mode, which keeps each row on one line
    with wide gaps between columns; falls back to pdfplumber."""
    try:
        txt = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True,
                             capture_output=True, text=True).stdout
        return txt.splitlines()
    except (FileNotFoundError, subprocess.CalledProcessError):
        import pdfplumber
        lines = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                lines.extend((page.extract_text() or "").splitlines())
        return lines


def unit_type(name):
    n = name.strip().lower()
    # Long names are cut off in the report, e.g. "Grosse Pointe Shores Village Cit".
    if re.search(r"\scit(y)?$", n) or n.startswith("city of "):
        return "C"
    if n.endswith(" twp") or n.endswith(" township") or "charter" in n:
        return "T"
    return "?"


def parse_lines(lines):
    rows, county, unit = [], None, None
    seen = set()
    for raw in lines:
        raw = raw.replace("\u00a0", " ").rstrip()
        line = " ".join(raw.split())
        if not line:
            continue
        t = TAIL.search(line)
        if not t and any(s.lower() in line.lower() for s in SKIP):
            continue
        m = None if t else (COUNTY_A.match(line) or COUNTY_B.match(line))
        if m:
            county = m.group("name").strip()
            continue
        if t:
            if unit is None:
                continue
            label = line[:t.start()].strip()
            nums = NUM.findall(t.group(1))
            if not label or len(nums) != 6:
                continue
            if label.upper().startswith("TR-") or label.upper().startswith("TR "):
                continue
            is_vil = label.upper().startswith("VILLAGE OF ")
            # In layout text the village name and the school name are separated by a wide gap.
            rt = TAIL.search(raw)
            parts = re.split(r"\s{2,}", raw[:rt.start()].strip()) if rt else [label]
            village, school = "", label
            if is_vil:
                if len(parts) >= 2:
                    village, school = parts[0][len("VILLAGE OF "):].strip(), " ".join(parts[1:]).strip()
                else:
                    village, school = label[len("VILLAGE OF "):].strip(), ""
            key = (unit["code"], label.upper())
            dup = key in seen
            seen.add(key)
            rows.append({
                "county_code": unit["code"][:2], "county_name": county or "",
                "unit_code": unit["code"], "unit_name": unit["name"], "unit_type": unit["type"],
                "is_village": int(is_vil), "village": village, "school": school, "label": label,
                "pre": nums[0], "nh": nums[1], "c3": nums[2], "c4": nums[3], "c5": nums[4], "c6": nums[5],
                "dup": int(dup),
            })
            continue
        u = UNIT.match(line)
        if u:
            name = u.group("name").strip()
            unit = {"name": name, "code": u.group("code"), "type": unit_type(name)}
    return rows


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    rows = parse_lines(pdf_lines(src))
    if len(rows) < 1000:
        sys.exit(f"Only {len(rows)} rate rows parsed from {src}: the report format may have changed.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    units = {r["unit_code"] for r in rows}
    print(f"Parsed {len(rows)} rate rows in {len(units)} cities and townships "
          f"({sum(r['is_village'] for r in rows)} village rows, {sum(r['dup'] for r in rows)} repeated rows).")


if __name__ == "__main__":
    main()

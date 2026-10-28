"""Synthetic GST Data Generator for Books Purchase Register and GSTR-2B Returns.

Generates realistic paired datasets for FY 2023-24 covering:
- Exact Matches (full ITC eligible under Section 16(2)(aa))
- Invoice Number Formatting / Typo variations (fuzzy match)
- Value & Tax Rate Mismatches (differential claim)
- Missing in 2B / Books Only (vendor non-filing audit risk)
- Missing in Books / Portal Only (unrecorded purchase/liability)
- Section 17(5) Blocked Credits (motor vehicles, catering, club memberships)
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple
import openpyxl


VENDORS = [
    ("Tata Steel Limited", "20AAACT2727Q1ZW", "20-Jharkhand", 18),
    ("Infosys BPM Limited", "29AAACI4798H1ZN", "29-Karnataka", 18),
    ("Blue Dart Express Ltd", "27AAACB0446N1ZT", "27-Maharashtra", 18),
    ("Dell International Services", "29AAACD3059M1ZQ", "29-Karnataka", 18),
    ("Larsen & Toubro Limited", "27AAACL0149P1ZY", "27-Maharashtra", 18),
    ("Reliance Retail Limited", "27AABCR1518J1ZS", "27-Maharashtra", 12),
    ("Asian Paints Limited", "27AAACA0823H1ZW", "27-Maharashtra", 18),
    ("Godrej & Boyce Mfg Co", "27AAACG0580D1ZX", "27-Maharashtra", 18),
    ("Wipro Enterprises Ltd", "29AAACW0389C1ZE", "29-Karnataka", 18),
    ("Bharat Petroleum Corp", "27AAACB0080L1ZS", "27-Maharashtra", 18),
    ("Adani Enterprises Ltd", "24AAACA2804L1ZZ", "24-Gujarat", 18),
    ("Siemens Healthcare Pvt", "27AAACS1342B1Z6", "27-Maharashtra", 12),
    ("ITC Limited - Packaging", "19AAACI0503D1Z9", "19-West Bengal", 12),
    ("Taj Gateway Hotel & Catering", "27AAACT0045P1Z8", "27-Maharashtra", 5),
    ("HDFC ERGO General Insurance", "27AAACH2702H1Z1", "27-Maharashtra", 18),
]


def generate_gst_dataset(
    output_dir: Path,
    num_invoices: int = 80,
    seed: int = 42,
) -> Tuple[Path, Path]:
    """Generate paired Books Purchase Register and GSTR-2B Portal datasets."""
    random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    books_rows: List[Dict] = []
    portal_rows: List[Dict] = []

    start_date = date(2023, 4, 1)
    client_state = "27"  # Maharashtra

    inv_seq = 1001

    for i in range(num_invoices):
        vendor_name, gstin, pos, rate = random.choice(VENDORS)
        inv_no_raw = f"INV/{inv_seq}"
        days_offset = random.randint(0, 360)
        inv_date = start_date + timedelta(days=days_offset)
        taxable = Decimal(str(random.randint(10, 500) * 1000))  # 10k to 500k
        tax_rate = Decimal(str(rate))
        total_tax = (taxable * tax_rate) / Decimal("100")

        # Split into IGST vs CGST/SGST based on POS
        is_inter_state = not pos.startswith(client_state)
        if is_inter_state:
            igst = total_tax
            cgst = Decimal("0.0")
            sgst = Decimal("0.0")
        else:
            igst = Decimal("0.0")
            cgst = total_tax / Decimal("2")
            sgst = total_tax / Decimal("2")

        inv_value = taxable + total_tax
        inv_seq += 1

        # Scenario distribution
        r = random.random()

        if r < 0.65:
            # 1. Exact Match
            books_rows.append({
                "date": inv_date.strftime("%d-%b-%Y"),
                "party": vendor_name,
                "gstin": gstin,
                "inv_no": inv_no_raw,
                "taxable": taxable,
                "rate": tax_rate,
                "igst": igst,
                "cgst": cgst,
                "sgst": sgst,
                "cess": Decimal("0.0"),
                "total": inv_value,
                "notes": "Raw material purchase / IT services",
            })
            portal_rows.append({
                "gstin": gstin,
                "inv_no": inv_no_raw,
                "date": inv_date.strftime("%d-%b-%Y"),
                "total": inv_value,
                "pos": pos,
                "rchrg": "N",
                "type": "Regular",
                "rate": tax_rate,
                "taxable": taxable,
                "igst": igst,
                "cgst": cgst,
                "sgst": sgst,
                "cess": Decimal("0.0"),
                "eligibility": "Inputs",
            })

        elif r < 0.77:
            # 2. Fuzzy Match (Invoice number format variation)
            # e.g., Books has '1045', Portal has 'INV/1045' or vice-versa
            books_inv = f"{inv_seq - 1}"  # stripped number in books
            portal_inv = inv_no_raw

            books_rows.append({
                "date": inv_date.strftime("%d-%b-%Y"),
                "party": vendor_name,
                "gstin": gstin,
                "inv_no": books_inv,
                "taxable": taxable,
                "rate": tax_rate,
                "igst": igst,
                "cgst": cgst,
                "sgst": sgst,
                "cess": Decimal("0.0"),
                "total": inv_value,
                "notes": "Vendor bill entry",
            })
            portal_rows.append({
                "gstin": gstin,
                "inv_no": portal_inv,
                "date": (inv_date + timedelta(days=random.randint(-5, 5))).strftime("%d-%b-%Y"),
                "total": inv_value,
                "pos": pos,
                "rchrg": "N",
                "type": "Regular",
                "rate": tax_rate,
                "taxable": taxable,
                "igst": igst,
                "cgst": cgst,
                "sgst": sgst,
                "cess": Decimal("0.0"),
                "eligibility": "Inputs",
            })

        elif r < 0.85:
            # 3. Value Mismatch (e.g. Books entered higher/lower taxable or tax)
            var_taxable = taxable + Decimal(str(random.choice([-5000, 5000, 10000])))
            var_tax = (var_taxable * tax_rate) / Decimal("100")
            var_igst = var_tax if is_inter_state else Decimal("0.0")
            var_cgst = Decimal("0.0") if is_inter_state else (var_tax / Decimal("2"))
            var_sgst = Decimal("0.0") if is_inter_state else (var_tax / Decimal("2"))

            books_rows.append({
                "date": inv_date.strftime("%d-%b-%Y"),
                "party": vendor_name,
                "gstin": gstin,
                "inv_no": inv_no_raw,
                "taxable": var_taxable,
                "rate": tax_rate,
                "igst": var_igst,
                "cgst": var_cgst,
                "sgst": var_sgst,
                "cess": Decimal("0.0"),
                "total": var_taxable + var_tax,
                "notes": "Price amendment variance",
            })
            portal_rows.append({
                "gstin": gstin,
                "inv_no": inv_no_raw,
                "date": inv_date.strftime("%d-%b-%Y"),
                "total": inv_value,
                "pos": pos,
                "rchrg": "N",
                "type": "Regular",
                "rate": tax_rate,
                "taxable": taxable,
                "igst": igst,
                "cgst": cgst,
                "sgst": sgst,
                "cess": Decimal("0.0"),
                "eligibility": "Inputs",
            })

        elif r < 0.90:
            # 4. Books Only (Missing in 2B - Vendor GSTR-1 non-filing / Section 16(2)(aa) risk)
            books_rows.append({
                "date": inv_date.strftime("%d-%b-%Y"),
                "party": vendor_name,
                "gstin": gstin,
                "inv_no": inv_no_raw,
                "taxable": taxable,
                "rate": tax_rate,
                "igst": igst,
                "cgst": cgst,
                "sgst": sgst,
                "cess": Decimal("0.0"),
                "total": inv_value,
                "notes": "Vendor pending GSTR-1 filing",
            })

        elif r < 0.95:
            # 5. Section 17(5) Blocked Credit
            blocked_desc = random.choice([
                ("Corporate executive car insurance premium", "27AAACH2702H1Z1", "HDFC ERGO General Insurance"),
                ("Annual corporate party dinner catering", "27AAACT0045P1Z8", "Taj Gateway Hotel & Catering"),
                ("Director premium gym & fitness club membership", "27AAACG0580D1ZX", "Godrej Fitness & Wellness"),
            ])
            desc, b_gstin, b_party = blocked_desc
            books_rows.append({
                "date": inv_date.strftime("%d-%b-%Y"),
                "party": b_party,
                "gstin": b_gstin,
                "inv_no": f"BLK/{inv_seq}",
                "taxable": taxable,
                "rate": tax_rate,
                "igst": igst,
                "cgst": cgst,
                "sgst": sgst,
                "cess": Decimal("0.0"),
                "total": inv_value,
                "notes": desc,
            })

        else:
            # 6. Portal Only (Missing in Books - Unrecorded purchase / vendor error)
            portal_rows.append({
                "gstin": gstin,
                "inv_no": inv_no_raw,
                "date": inv_date.strftime("%d-%b-%Y"),
                "total": inv_value,
                "pos": pos,
                "rchrg": "N",
                "type": "Regular",
                "rate": tax_rate,
                "taxable": taxable,
                "igst": igst,
                "cgst": cgst,
                "sgst": sgst,
                "cess": Decimal("0.0"),
                "eligibility": "Inputs",
            })

    # Write Books Purchase Register Excel & CSV
    books_xlsx = output_dir / "Tally_Purchase_Register_FY2023_24.xlsx"
    books_csv = output_dir / "Tally_Purchase_Register_FY2023_24.csv"

    wb_books = openpyxl.Workbook()
    ws_books = wb_books.active
    ws_books.title = "Purchase_Register"
    b_headers = [
        "Voucher Date", "Supplier Name", "Supplier GSTIN", "Invoice Number",
        "Taxable Value", "GST Rate %", "IGST Amount", "CGST Amount",
        "SGST Amount", "Cess Amount", "Total Invoice Value", "Item Narration"
    ]
    ws_books.append(b_headers)
    for r in books_rows:
        ws_books.append([
            r["date"], r["party"], r["gstin"], r["inv_no"],
            float(r["taxable"]), float(r["rate"]), float(r["igst"]),
            float(r["cgst"]), float(r["sgst"]), float(r["cess"]),
            float(r["total"]), r["notes"]
        ])
    wb_books.save(books_xlsx)

    with open(books_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(b_headers)
        for r in books_rows:
            writer.writerow([
                r["date"], r["party"], r["gstin"], r["inv_no"],
                r["taxable"], r["rate"], r["igst"], r["cgst"],
                r["sgst"], r["cess"], r["total"], r["notes"]
            ])

    # Write Portal GSTR-2B Excel & CSV (conforming exactly to official GSTN GSTR2 template)
    portal_xlsx = output_dir / "GSTR2B_Portal_FY2023_24.xlsx"
    portal_csv = output_dir / "GSTR2B_Portal_FY2023_24.csv"

    wb_portal = openpyxl.Workbook()
    ws_portal = wb_portal.active
    ws_portal.title = "b2b"
    p_headers = [
        "GSTIN of Supplier", "Invoice Number", "Invoice date", "Invoice Value",
        "Place Of Supply", "Reverse Charge", "Invoice Type", "Rate",
        "Taxable Value", "Integrated Tax Paid", "Central Tax Paid",
        "State/UT Tax Paid", "Cess Paid", "Eligibility For ITC"
    ]
    # Add title banner just like official GSTN template
    ws_portal.append(["Summary Of Supplies From Registered Suppliers B2B(3)"])
    ws_portal.append(["No. of Suppliers", "No. of Invoices", "Total Invoice Value"])
    ws_portal.append([len(set(r["gstin"] for r in portal_rows)), len(portal_rows), float(sum(r["total"] for r in portal_rows))])
    ws_portal.append(p_headers)

    for r in portal_rows:
        ws_portal.append([
            r["gstin"], r["inv_no"], r["date"], float(r["total"]),
            r["pos"], r["rchrg"], r["type"], float(r["rate"]),
            float(r["taxable"]), float(r["igst"]), float(r["cgst"]),
            float(r["sgst"]), float(r["cess"]), r["eligibility"]
        ])
    wb_portal.save(portal_xlsx)

    with open(portal_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(p_headers)
        for r in portal_rows:
            writer.writerow([
                r["gstin"], r["inv_no"], r["date"], r["total"],
                r["pos"], r["rchrg"], r["type"], r["rate"],
                r["taxable"], r["igst"], r["cgst"], r["sgst"],
                r["cess"], r["eligibility"]
            ])

    return books_xlsx, portal_xlsx

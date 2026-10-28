"""Ingestion engine for GST Returns (GSTR-2B, GSTR-1, GSTR-2) and Books Purchase/Sales Registers.

Supports:
- Official GSTN Excel templates (GSTR2_Excel_Workbook_Template, GSTR1_Excel_Workbook_Template)
- Official GSTN Section-wise CSV files (b2b.csv, b2b,sez,de.csv)
- Standard GST portal JSON downloads (GSTR-2B / GSTR-1 JSON schema)
- Tally Prime & ERP Purchase Registers (.xlsx, .csv) with synonym auto-detection
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import openpyxl

from auditiq.gst.models import GstInvoice
from auditiq.gst.normalize import (
    detect_blocked_credit_17_5,
    normalize_gstin,
    normalize_invoice_number,
    parse_date_safe,
    parse_decimal_safe,
)


# Column synonyms for Books Purchase Registers
BOOKS_SYNONYMS = {
    "gstin": ["gstin", "party gstin", "supplier gstin", "vendor gstin", "gstin/uin", "party's gstin"],
    "party_name": ["party name", "supplier name", "vendor name", "particulars", "ledger name", "party"],
    "invoice_number": ["invoice number", "invoice no", "inv no", "bill no", "voucher no", "ref no", "supplier inv no", "inv #"],
    "invoice_date": ["invoice date", "date", "inv date", "bill date", "voucher date"],
    "taxable_value": ["taxable value", "taxable amount", "assessable value", "taxable amt", "base amount", "net amount"],
    "rate": ["rate", "tax rate", "gst rate", "rate %", "gst %"],
    "igst": ["integrated tax", "igst", "igst amount", "integrated tax paid", "igst amt"],
    "cgst": ["central tax", "cgst", "cgst amount", "central tax paid", "cgst amt"],
    "sgst": ["state/ut tax", "state tax", "sgst", "sgst amount", "state/ut tax paid", "sgst amt", "utgst"],
    "cess": ["cess", "cess amount", "cess paid", "compensation cess"],
    "total_value": ["total value", "invoice value", "gross total", "total amount", "bill amount", "total"],
    "notes": ["narration", "remarks", "item description", "description", "nature of purchase", "expense type"],
}


def _match_header_synonyms(headers: List[str], synonym_map: Dict[str, List[str]]) -> Dict[str, int]:
    """Map normalized standard keys to column indexes based on synonym matching."""
    mapping: Dict[str, int] = {}
    normalized_headers = [str(h).strip().lower() if h is not None else "" for h in headers]

    for key, synonyms in synonym_map.items():
        for syn in synonyms:
            # Exact match first
            found = False
            for idx, h in enumerate(normalized_headers):
                if h == syn:
                    mapping[key] = idx
                    found = True
                    break
            if found:
                break
            # Substring match if exact match not found
            for idx, h in enumerate(normalized_headers):
                if syn in h and key not in mapping:
                    mapping[key] = idx
                    found = True
                    break
            if found:
                break
    return mapping


def load_portal_gstr2b_csv(file_path: Union[str, Path]) -> List[GstInvoice]:
    """Parse official GSTN GSTR-2B / GSTR-2 inward B2B supplies CSV (e.g. b2b.csv)."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"GST CSV file not found: {path}")

    invoices: List[GstInvoice] = []
    with open(path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        header_row: Optional[List[str]] = None
        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue
            # Look for header line containing GSTIN
            row_str = " ".join(c.lower() for c in row)
            if "gstin" in row_str and ("supplier" in row_str or "recipient" in row_str or "uin" in row_str):
                header_row = [c.strip() for c in row]
                break

        if not header_row:
            return invoices

        col_map = _match_header_synonyms(header_row, {
            "gstin": ["gstin of supplier", "gstin/uin of supplier", "gstin"],
            "invoice_number": ["invoice number", "inv no", "invoice no"],
            "invoice_date": ["invoice date"],
            "invoice_value": ["invoice value", "total value"],
            "place_of_supply": ["place of supply", "pos"],
            "reverse_charge": ["reverse charge"],
            "invoice_type": ["invoice type"],
            "rate": ["rate"],
            "taxable_value": ["taxable value"],
            "igst": ["integrated tax paid", "integrated tax", "igst"],
            "cgst": ["central tax paid", "central tax", "cgst"],
            "sgst": ["state/ut tax paid", "state/ut tax", "state tax", "sgst"],
            "cess": ["cess paid", "cess"],
            "itc_eligibility": ["eligibility for itc", "itc eligibility"],
        })

        for row in reader:
            if not row or len(row) <= max(col_map.values(), default=0):
                continue

            raw_gstin = row[col_map["gstin"]].strip() if "gstin" in col_map else ""
            if not raw_gstin or raw_gstin.lower().startswith("total"):
                continue

            gstin = normalize_gstin(raw_gstin)
            inv_no = str(row[col_map["invoice_number"]]).strip() if "invoice_number" in col_map else ""
            if not inv_no:
                continue

            inv_norm = normalize_invoice_number(inv_no)
            inv_date = parse_date_safe(row[col_map["invoice_date"]]) if "invoice_date" in col_map else None
            pos = row[col_map["place_of_supply"]].strip() if "place_of_supply" in col_map else ""
            rchrg = (str(row[col_map["reverse_charge"]]).strip().upper() == "Y") if "reverse_charge" in col_map else False
            inv_type = row[col_map["invoice_type"]].strip() if "invoice_type" in col_map else "Regular"
            rate = parse_decimal_safe(row[col_map["rate"]]) if "rate" in col_map else Decimal("0.0")
            taxable = parse_decimal_safe(row[col_map["taxable_value"]]) if "taxable_value" in col_map else Decimal("0.0")
            igst = parse_decimal_safe(row[col_map["igst"]]) if "igst" in col_map else Decimal("0.0")
            cgst = parse_decimal_safe(row[col_map["cgst"]]) if "cgst" in col_map else Decimal("0.0")
            sgst = parse_decimal_safe(row[col_map["sgst"]]) if "sgst" in col_map else Decimal("0.0")
            cess = parse_decimal_safe(row[col_map["cess"]]) if "cess" in col_map else Decimal("0.0")
            inv_val = parse_decimal_safe(row[col_map["invoice_value"]]) if "invoice_value" in col_map else (taxable + igst + cgst + sgst + cess)
            eligibility = row[col_map["itc_eligibility"]].strip() if "itc_eligibility" in col_map else "Eligible"

            blocked_reason = detect_blocked_credit_17_5(eligibility=eligibility)

            invoices.append(GstInvoice(
                source="portal",
                gstin=gstin,
                party_name="",
                invoice_number=inv_no,
                invoice_number_norm=inv_norm,
                invoice_date=inv_date,
                invoice_type=inv_type,
                place_of_supply=pos,
                reverse_charge=rchrg,
                rate=rate,
                taxable_value=taxable,
                igst=igst,
                cgst=cgst,
                sgst=sgst,
                cess=cess,
                total_tax=(igst + cgst + sgst + cess),
                invoice_value=inv_val,
                itc_eligibility=eligibility,
                blocked_reason=blocked_reason,
            ))

    return invoices


def load_portal_gstr2b_excel(file_path: Union[str, Path], sheet_name: Optional[str] = None) -> List[GstInvoice]:
    """Parse official GSTN GSTR-2B / GSTR-2 Excel workbook (e.g. GSTR2_Excel_Workbook_TemplateNew_V1.1.xlsx)."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"GST Excel file not found: {path}")

    # Use read_only=True and data_only=True for speed and memory efficiency
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    target_sheet = sheet_name
    if not target_sheet:
        for name in wb.sheetnames:
            if name.lower() in ("b2b", "gstr2b_b2b", "inward_b2b", "b2b,sez,de"):
                target_sheet = name
                break
        if not target_sheet:
            target_sheet = wb.sheetnames[0]

    ws = wb[target_sheet]
    rows = ws.iter_rows(values_only=True)

    header_row: Optional[List[str]] = None
    invoices: List[GstInvoice] = []

    for row in rows:
        if not row or not any(row):
            continue
        row_strs = [str(c).strip().lower() if c is not None else "" for c in row]
        joined = " ".join(row_strs)
        if "gstin" in joined and ("supplier" in joined or "recipient" in joined or "uin" in joined):
            header_row = [str(c).strip() if c is not None else "" for c in row]
            break

    if not header_row:
        wb.close()
        return invoices

    col_map = _match_header_synonyms(header_row, {
        "gstin": ["gstin of supplier", "gstin/uin of supplier", "gstin"],
        "invoice_number": ["invoice number", "inv no", "invoice no"],
        "invoice_date": ["invoice date"],
        "invoice_value": ["invoice value", "total value"],
        "place_of_supply": ["place of supply", "pos"],
        "reverse_charge": ["reverse charge"],
        "invoice_type": ["invoice type"],
        "rate": ["rate"],
        "taxable_value": ["taxable value"],
        "igst": ["integrated tax paid", "integrated tax", "igst"],
        "cgst": ["central tax paid", "central tax", "cgst"],
        "sgst": ["state/ut tax paid", "state/ut tax", "state tax", "sgst"],
        "cess": ["cess paid", "cess"],
        "itc_eligibility": ["eligibility for itc", "itc eligibility"],
    })

    for row in rows:
        if not row or not any(row):
            continue
        raw_gstin = str(row[col_map["gstin"]]).strip() if "gstin" in col_map and row[col_map["gstin"]] is not None else ""
        if not raw_gstin or raw_gstin.lower().startswith("total"):
            continue

        gstin = normalize_gstin(raw_gstin)
        inv_no = str(row[col_map["invoice_number"]]).strip() if "invoice_number" in col_map and row[col_map["invoice_number"]] is not None else ""
        if not inv_no:
            continue

        inv_norm = normalize_invoice_number(inv_no)
        inv_date = parse_date_safe(row[col_map["invoice_date"]]) if "invoice_date" in col_map else None
        pos = str(row[col_map["place_of_supply"]]).strip() if "place_of_supply" in col_map and row[col_map["place_of_supply"]] is not None else ""
        rchrg = (str(row[col_map["reverse_charge"]]).strip().upper() == "Y") if "reverse_charge" in col_map and row[col_map["reverse_charge"]] is not None else False
        inv_type = str(row[col_map["invoice_type"]]).strip() if "invoice_type" in col_map and row[col_map["invoice_type"]] is not None else "Regular"
        rate = parse_decimal_safe(row[col_map["rate"]]) if "rate" in col_map else Decimal("0.0")
        taxable = parse_decimal_safe(row[col_map["taxable_value"]]) if "taxable_value" in col_map else Decimal("0.0")
        igst = parse_decimal_safe(row[col_map["igst"]]) if "igst" in col_map else Decimal("0.0")
        cgst = parse_decimal_safe(row[col_map["cgst"]]) if "cgst" in col_map else Decimal("0.0")
        sgst = parse_decimal_safe(row[col_map["sgst"]]) if "sgst" in col_map else Decimal("0.0")
        cess = parse_decimal_safe(row[col_map["cess"]]) if "cess" in col_map else Decimal("0.0")
        inv_val = parse_decimal_safe(row[col_map["invoice_value"]]) if "invoice_value" in col_map else (taxable + igst + cgst + sgst + cess)
        eligibility = str(row[col_map["itc_eligibility"]]).strip() if "itc_eligibility" in col_map and row[col_map["itc_eligibility"]] is not None else "Eligible"

        blocked_reason = detect_blocked_credit_17_5(eligibility=eligibility)

        invoices.append(GstInvoice(
            source="portal",
            gstin=gstin,
            party_name="",
            invoice_number=inv_no,
            invoice_number_norm=inv_norm,
            invoice_date=inv_date,
            invoice_type=inv_type,
            place_of_supply=pos,
            reverse_charge=rchrg,
            rate=rate,
            taxable_value=taxable,
            igst=igst,
            cgst=cgst,
            sgst=sgst,
            cess=cess,
            total_tax=(igst + cgst + sgst + cess),
            invoice_value=inv_val,
            itc_eligibility=eligibility,
            blocked_reason=blocked_reason,
        ))

    wb.close()
    return invoices


def load_portal_json(file_path: Union[str, Path]) -> List[GstInvoice]:
    """Parse official GST portal JSON return file (e.g. GSTR-2B or GSTR-1 JSON)."""
    path = Path(file_path)
    with open(path, mode="r", encoding="utf-8") as f:
        data = json.load(f)

    invoices: List[GstInvoice] = []
    b2b_list = data.get("b2b", [])
    for party in b2b_list:
        gstin = normalize_gstin(party.get("ctin", ""))
        for inv in party.get("inv", []):
            inv_no = str(inv.get("inum", "")).strip()
            inv_norm = normalize_invoice_number(inv_no)
            inv_date = parse_date_safe(inv.get("idt"))
            inv_val = parse_decimal_safe(inv.get("val"))
            pos = str(inv.get("pos", ""))
            rchrg = (str(inv.get("rchrg", "")).upper() == "Y")
            inv_type = str(inv.get("inv_typ", "Regular"))

            # Sum item lines
            itms = inv.get("itms", [])
            taxable = Decimal("0.0")
            igst = Decimal("0.0")
            cgst = Decimal("0.0")
            sgst = Decimal("0.0")
            cess = Decimal("0.0")
            rate = Decimal("0.0")
            eligibility = "Eligible"

            for itm in itms:
                det = itm.get("itm_det", itm)
                rate = parse_decimal_safe(det.get("rt", 0))
                taxable += parse_decimal_safe(det.get("txval", 0))
                igst += parse_decimal_safe(det.get("iamt", 0))
                cgst += parse_decimal_safe(det.get("camt", 0))
                sgst += parse_decimal_safe(det.get("samt", 0))
                cess += parse_decimal_safe(det.get("csamt", 0))
                if "elg" in itm:
                    eligibility = str(itm.get("elg"))

            blocked_reason = detect_blocked_credit_17_5(eligibility=eligibility)

            invoices.append(GstInvoice(
                source="portal",
                gstin=gstin,
                party_name="",
                invoice_number=inv_no,
                invoice_number_norm=inv_norm,
                invoice_date=inv_date,
                invoice_type=inv_type,
                place_of_supply=pos,
                reverse_charge=rchrg,
                rate=rate,
                taxable_value=taxable,
                igst=igst,
                cgst=cgst,
                sgst=sgst,
                cess=cess,
                total_tax=(igst + cgst + sgst + cess),
                invoice_value=inv_val if inv_val > Decimal("0.0") else (taxable + igst + cgst + sgst + cess),
                itc_eligibility=eligibility,
                blocked_reason=blocked_reason,
            ))

    return invoices


def load_books_purchase_register_csv(file_path: Union[str, Path]) -> List[GstInvoice]:
    """Parse Books Purchase Register CSV export from Tally or ERP."""
    path = Path(file_path)
    invoices: List[GstInvoice] = []

    with open(path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        header_row: Optional[List[str]] = None
        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue
            row_str = " ".join(c.lower() for c in row)
            if ("gstin" in row_str or "party" in row_str or "supplier" in row_str) and ("invoice" in row_str or "voucher" in row_str or "bill" in row_str):
                header_row = [c.strip() for c in row]
                break

        if not header_row:
            return invoices

        col_map = _match_header_synonyms(header_row, BOOKS_SYNONYMS)

        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue

            raw_gstin = row[col_map["gstin"]].strip() if "gstin" in col_map and col_map["gstin"] < len(row) else ""
            party_name = row[col_map["party_name"]].strip() if "party_name" in col_map and col_map["party_name"] < len(row) else ""
            inv_no = row[col_map["invoice_number"]].strip() if "invoice_number" in col_map and col_map["invoice_number"] < len(row) else ""

            if not inv_no and not raw_gstin:
                continue
            if party_name.lower().startswith("total"):
                continue

            gstin = normalize_gstin(raw_gstin)
            inv_norm = normalize_invoice_number(inv_no)
            inv_date = parse_date_safe(row[col_map["invoice_date"]]) if "invoice_date" in col_map and col_map["invoice_date"] < len(row) else None
            rate = parse_decimal_safe(row[col_map["rate"]]) if "rate" in col_map and col_map["rate"] < len(row) else Decimal("0.0")
            taxable = parse_decimal_safe(row[col_map["taxable_value"]]) if "taxable_value" in col_map and col_map["taxable_value"] < len(row) else Decimal("0.0")
            igst = parse_decimal_safe(row[col_map["igst"]]) if "igst" in col_map and col_map["igst"] < len(row) else Decimal("0.0")
            cgst = parse_decimal_safe(row[col_map["cgst"]]) if "cgst" in col_map and col_map["cgst"] < len(row) else Decimal("0.0")
            sgst = parse_decimal_safe(row[col_map["sgst"]]) if "sgst" in col_map and col_map["sgst"] < len(row) else Decimal("0.0")
            cess = parse_decimal_safe(row[col_map["cess"]]) if "cess" in col_map and col_map["cess"] < len(row) else Decimal("0.0")
            notes = row[col_map["notes"]].strip() if "notes" in col_map and col_map["notes"] < len(row) else None

            tot_tax = igst + cgst + sgst + cess
            inv_val = parse_decimal_safe(row[col_map["total_value"]]) if "total_value" in col_map and col_map["total_value"] < len(row) else (taxable + tot_tax)

            blocked_reason = detect_blocked_credit_17_5(text=f"{party_name} {notes or ''}")

            invoices.append(GstInvoice(
                source="books",
                gstin=gstin,
                party_name=party_name,
                invoice_number=inv_no,
                invoice_number_norm=inv_norm,
                invoice_date=inv_date,
                invoice_type="Regular",
                place_of_supply="",
                reverse_charge=False,
                rate=rate,
                taxable_value=taxable,
                igst=igst,
                cgst=cgst,
                sgst=sgst,
                cess=cess,
                total_tax=tot_tax,
                invoice_value=inv_val,
                itc_eligibility="Ineligible" if blocked_reason else "Eligible",
                blocked_reason=blocked_reason,
                notes=notes,
            ))

    return invoices


def load_books_purchase_register_excel(file_path: Union[str, Path], sheet_name: Optional[str] = None) -> List[GstInvoice]:
    """Parse Books Purchase Register Excel workbook (.xlsx)."""
    path = Path(file_path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    target_sheet = sheet_name or wb.sheetnames[0]
    ws = wb[target_sheet]
    rows = ws.iter_rows(values_only=True)

    header_row: Optional[List[str]] = None
    invoices: List[GstInvoice] = []

    for row in rows:
        if not row or not any(row):
            continue
        row_strs = [str(c).strip().lower() if c is not None else "" for c in row]
        joined = " ".join(row_strs)
        if ("gstin" in joined or "party" in joined or "supplier" in joined) and ("invoice" in joined or "voucher" in joined or "bill" in joined):
            header_row = [str(c).strip() if c is not None else "" for c in row]
            break

    if not header_row:
        wb.close()
        return invoices

    col_map = _match_header_synonyms(header_row, BOOKS_SYNONYMS)

    for row in rows:
        if not row or not any(row):
            continue
        raw_gstin = str(row[col_map["gstin"]]).strip() if "gstin" in col_map and row[col_map["gstin"]] is not None else ""
        party_name = str(row[col_map["party_name"]]).strip() if "party_name" in col_map and row[col_map["party_name"]] is not None else ""
        inv_no = str(row[col_map["invoice_number"]]).strip() if "invoice_number" in col_map and row[col_map["invoice_number"]] is not None else ""

        if not inv_no and not raw_gstin:
            continue
        if party_name.lower().startswith("total"):
            continue

        gstin = normalize_gstin(raw_gstin)
        inv_norm = normalize_invoice_number(inv_no)
        inv_date = parse_date_safe(row[col_map["invoice_date"]]) if "invoice_date" in col_map else None
        rate = parse_decimal_safe(row[col_map["rate"]]) if "rate" in col_map else Decimal("0.0")
        taxable = parse_decimal_safe(row[col_map["taxable_value"]]) if "taxable_value" in col_map else Decimal("0.0")
        igst = parse_decimal_safe(row[col_map["igst"]]) if "igst" in col_map else Decimal("0.0")
        cgst = parse_decimal_safe(row[col_map["cgst"]]) if "cgst" in col_map else Decimal("0.0")
        sgst = parse_decimal_safe(row[col_map["sgst"]]) if "sgst" in col_map else Decimal("0.0")
        cess = parse_decimal_safe(row[col_map["cess"]]) if "cess" in col_map else Decimal("0.0")
        notes = str(row[col_map["notes"]]).strip() if "notes" in col_map and row[col_map["notes"]] is not None else None

        tot_tax = igst + cgst + sgst + cess
        inv_val = parse_decimal_safe(row[col_map["total_value"]]) if "total_value" in col_map else (taxable + tot_tax)

        blocked_reason = detect_blocked_credit_17_5(text=f"{party_name} {notes or ''}")

        invoices.append(GstInvoice(
            source="books",
            gstin=gstin,
            party_name=party_name,
            invoice_number=inv_no,
            invoice_number_norm=inv_norm,
            invoice_date=inv_date,
            invoice_type="Regular",
            place_of_supply="",
            reverse_charge=False,
            rate=rate,
            taxable_value=taxable,
            igst=igst,
            cgst=cgst,
            sgst=sgst,
            cess=cess,
            total_tax=tot_tax,
            invoice_value=inv_val,
            itc_eligibility="Ineligible" if blocked_reason else "Eligible",
            blocked_reason=blocked_reason,
            notes=notes,
        ))

    wb.close()
    return invoices


def auto_load_portal_file(file_path: Union[str, Path]) -> List[GstInvoice]:
    """Auto-detect format and load GST Portal data (Excel, CSV, or JSON)."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")

    ext = p.suffix.lower()
    if ext in (".xlsx", ".xls"):
        return load_portal_gstr2b_excel(p)
    elif ext == ".csv":
        return load_portal_gstr2b_csv(p)
    elif ext == ".json":
        return load_portal_json(p)
    else:
        raise ValueError(f"Unsupported portal file format '{ext}'. Expected .xlsx, .csv, or .json")


def auto_load_books_file(file_path: Union[str, Path]) -> List[GstInvoice]:
    """Auto-detect format and load Books Purchase Register data (Excel or CSV)."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")

    ext = p.suffix.lower()
    if ext in (".xlsx", ".xls"):
        return load_books_purchase_register_excel(p)
    elif ext == ".csv":
        return load_books_purchase_register_csv(p)
    else:
        raise ValueError(f"Unsupported books file format '{ext}'. Expected .xlsx or .csv")

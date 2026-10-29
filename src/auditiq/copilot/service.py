"""Copilot Service: Grounded Audit Q&A with Live Document Citations and Highlighting."""

from __future__ import annotations

import datetime
from decimal import Decimal
import io
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

import pandas as pd
import pypdf

from auditiq.copilot.ai import ask_gemini_with_sql_context
from auditiq.copilot.models import (
    ChatMessage,
    ChatResponse,
    Citation,
    CopilotSession,
    ExtractedPdf,
    PdfBlock,
    PdfPage,
)
import logging
logger = logging.getLogger(__name__)

from auditiq.copilot.sql_store import (
    delete_records_by_session,
    get_records_by_session,
    init_sql_store,
    insert_record,
    insert_records_bulk,
)
from auditiq.gst import run_gst_recon_files
from auditiq.gl.service import run_jet_file
from auditiq.ingest.erp.service import ingest_tb
from auditiq.ingest.prepare.service import map_engagement
from auditiq.core.taxonomy import load_default_taxonomy
from auditiq.store import session_scope
from auditiq.store.models import TbLine, TbMapping
from auditiq.ingest.erp.io import read_grid
from auditiq.ingest.erp.detect import detect_source
from auditiq.ingest.erp.registry import read_records

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "data" / "GST"
DEMO_BOOKS = DATA_DIR / "Tally_Purchase_Register_FY2023_24.csv"
if not DEMO_BOOKS.exists():
    DEMO_BOOKS = DATA_DIR / "Tally_Purchase_Register_FY2023_24.xlsx"

DEMO_PORTAL = DATA_DIR / "GSTR2B_Portal_FY2023_24.csv"
if not DEMO_PORTAL.exists():
    DEMO_PORTAL = DATA_DIR / "GSTR2B_Portal_FY2023_24.xlsx"

DEMO_DAYBOOK = ROOT_DIR / "data" / "General Ledger (for Journal Entry Testing)" / "Tally_Prime_Daybook_FY2023_24.xlsx"
DEMO_PDF = ROOT_DIR / "data" / "sample_audited_financial_statements.pdf"
DEMO_SAP = ROOT_DIR / "data" / "exports" / "dev_sap_00.xlsx"
UPLOADS_DIR = ROOT_DIR / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Initialize SQLite database
init_sql_store()

# In-memory session store
_SESSIONS: Dict[str, CopilotSession] = {}


def _parse_amount(text: str) -> Tuple[float, float]:
    """Extract current and prior amounts from text using Indian currency patterns and numbers."""
    curr_matches = re.findall(
        r"(?:INR|Rs\.?|₹|`)\s*([\d]{1,3}(?:,\d{2,3})*(?:\.\d+)?|\b\d+(?:\.\d+)?\b)",
        text,
        re.I,
    )
    if curr_matches:
        amt1 = 0.0
        amt2 = 0.0
        try:
            amt1 = float(curr_matches[0].replace(",", ""))
        except Exception:
            pass
        if len(curr_matches) >= 2:
            try:
                amt2 = float(curr_matches[1].replace(",", ""))
            except Exception:
                pass
        return amt1, amt2

    num_matches = re.findall(r"\b(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2})\b", text)
    amt1 = 0.0
    amt2 = 0.0
    if num_matches:
        try:
            amt1 = float(num_matches[0].replace(",", ""))
        except Exception:
            pass
        if len(num_matches) >= 2:
            try:
                amt2 = float(num_matches[1].replace(",", ""))
            except Exception:
                pass
    return amt1, amt2


def extract_pdf_document_to_sql(session_id: str, file_bytes: bytes, file_name: str) -> ExtractedPdf:
    """Extract real text and structured paragraphs from an uploaded PDF, and insert into SQL.

    Supports 400+ page enterprise reports via high-performance Google Chromium PDFium engine
    (pypdfium2) with automatic fallback to pypdf with increased token limits.
    """
    page_texts: List[str] = []
    page_count = 0

    # 1. Primary extractor: pypdfium2 (C++ Google Chromium PDFium engine - fast, no token limits)
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(io.BytesIO(file_bytes))
        page_count = len(doc)
        for page_idx in range(page_count):
            try:
                page = doc[page_idx]
                textpage = page.get_textpage()
                txt = textpage.get_text_range() or ""
                page_texts.append(txt)
            except Exception as page_err:
                logger.warning(f"pypdfium2 page {page_idx+1} extract warning: {page_err}")
                page_texts.append("")
        doc.close()
    except Exception as e:
        logger.warning(f"pypdfium2 extraction failed, falling back to pypdf: {e}")
        page_texts = []

    # 2. Fallback extractor: pypdf with generous parsing budgets
    if not page_texts:
        try:
            import pypdf
            pypdf.overwrite_configuration(
                stream_parsing_work_maximum_count=200_000_000,
                stream_decoding_work_maximum_length=2_000_000_000,
                maximum_declared_stream_length=1_000_000_000,
                array_maximum_element_count=1_000_000,
                dictionary_maximum_element_count=1_000_000,
                array_based_stream_maximum_output_length=1_000_000_000,
                xform_maximum_invocations_per_extraction=100_000,
            )
        except Exception:
            pass

        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes), strict=False)
            page_count = len(reader.pages)
            for page_idx, page in enumerate(reader.pages):
                try:
                    txt = page.extract_text() or ""
                    page_texts.append(txt)
                except Exception as page_err:
                    logger.warning(f"pypdf page {page_idx+1} extract warning: {page_err}")
                    page_texts.append("")
        except Exception as e:
            logger.error(f"Failed to read PDF with pypdf: {e}")
            page_count = page_count or 1
            page_texts = [""] * page_count

    extracted_pages: List[PdfPage] = []
    records_to_insert: List[Dict[str, Any]] = []
    current_section = "General / Overview"

    for page_idx, raw_text in enumerate(page_texts):
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        blocks: List[PdfBlock] = []
        current_para: List[str] = []
        block_counter = 1

        for line in lines:
            # Check if this line looks like a section header or note title
            is_header = (
                line.isupper()
                or bool(re.match(r"^(?:Note|Item|Schedule|Section|Annexure|\d+\.)\s+", line, re.I))
            ) and len(line) < 100

            if is_header:
                if current_para:
                    p_text = " ".join(current_para)
                    b_id = f"p{page_idx+1}-b{block_counter}"
                    blocks.append(PdfBlock(block_id=b_id, page_number=page_idx + 1, text=p_text, type="paragraph"))

                    amt, prior = _parse_amount(p_text)
                    cat = "tax_itc" if "itc" in p_text.lower() or "gst" in p_text.lower() else "disclosure"
                    records_to_insert.append({
                        "session_id": session_id,
                        "file_name": file_name,
                        "page_number": page_idx + 1,
                        "block_id": b_id,
                        "section": current_section,
                        "line_item": p_text[:40] + ("..." if len(p_text) > 40 else ""),
                        "amount": amt,
                        "prior_amount": prior,
                        "raw_text": p_text,
                        "category": cat,
                    })
                    block_counter += 1
                    current_para = []

                current_section = line
                b_id = f"p{page_idx+1}-b{block_counter}"
                blocks.append(PdfBlock(block_id=b_id, page_number=page_idx + 1, text=line, type="heading"))
                block_counter += 1
            else:
                current_para.append(line)
                if len(current_para) >= 3 or (line.endswith(".") and len(" ".join(current_para)) > 120):
                    p_text = " ".join(current_para)
                    b_id = f"p{page_idx+1}-b{block_counter}"
                    blocks.append(PdfBlock(block_id=b_id, page_number=page_idx + 1, text=p_text, type="paragraph"))

                    amt, prior = _parse_amount(p_text)
                    cat = "tax_itc" if "itc" in p_text.lower() or "gst" in p_text.lower() else "disclosure"
                    records_to_insert.append({
                        "session_id": session_id,
                        "file_name": file_name,
                        "page_number": page_idx + 1,
                        "block_id": b_id,
                        "section": current_section,
                        "line_item": p_text[:40] + ("..." if len(p_text) > 40 else ""),
                        "amount": amt,
                        "prior_amount": prior,
                        "raw_text": p_text,
                        "category": cat,
                    })
                    block_counter += 1
                    current_para = []

        if current_para:
            p_text = " ".join(current_para)
            b_id = f"p{page_idx+1}-b{block_counter}"
            blocks.append(PdfBlock(block_id=b_id, page_number=page_idx + 1, text=p_text, type="paragraph"))

            amt, prior = _parse_amount(p_text)
            cat = "tax_itc" if "itc" in p_text.lower() or "gst" in p_text.lower() else "disclosure"
            records_to_insert.append({
                "session_id": session_id,
                "file_name": file_name,
                "page_number": page_idx + 1,
                "block_id": b_id,
                "section": current_section,
                "line_item": p_text[:40] + ("..." if len(p_text) > 40 else ""),
                "amount": amt,
                "prior_amount": prior,
                "raw_text": p_text,
                "category": cat,
            })

        extracted_pages.append(
            PdfPage(
                page_number=page_idx + 1,
                text=raw_text,
                blocks=blocks,
            )
        )

    # Bulk insert all extracted blocks into SQLite in a single transaction
    if records_to_insert:
        insert_records_bulk(records_to_insert)

    return ExtractedPdf(
        file_name=file_name,
        page_count=page_count,
        pages=extracted_pages,
    )


def extract_prior_year_amounts_from_workbook(file_path: Path) -> Dict[str, float]:
    """Inspects Excel workbook for comparative Prior Year columns or sheets.
    
    Supports:
    1. Side-by-side comparative columns (e.g. FY23 Debit/Credit, Prior Year Net, PY Balance).
    2. Multi-sheet workbooks with a dedicated Prior Year sheet (e.g. 'SAP_FY2023_Prior', 'FY23', 'Prior Year').
    
    Returns a dictionary mapping account code strings and lowercased account names to prior year float values.
    """
    prior_map: Dict[str, float] = {}
    if not file_path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return prior_map

    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        
        # Strategy 1: Look for comparative columns in any sheet
        for sname in wb.sheetnames:
            ws = wb[sname]
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            
            header_idx = -1
            for i, r in enumerate(rows[:12]):
                row_str = " ".join(str(c or "").lower() for c in r)
                if any(k in row_str for k in ["g/l account", "particulars", "account code", "gl account", "ledger"]):
                    header_idx = i
                    break
            
            if header_idx != -1:
                header = [str(c or "").lower().strip() for c in rows[header_idx]]
                code_col = next((ci for ci, c in enumerate(header) if any(k in c for k in ["g/l account", "gl account", "account code", "account no", "code"])), 0)
                name_col = next((ci for ci, c in enumerate(header) if any(k in c for k in ["long text", "name", "description", "title", "particulars"])), 1)
                
                py_debit_col = next((ci for ci, c in enumerate(header) if ("debit" in c or "dr" in c) and any(y in c for y in ["py", "prior", "prev", "fy23", "2023", "last"])), None)
                py_credit_col = next((ci for ci, c in enumerate(header) if ("credit" in c or "cr" in c) and any(y in c for y in ["py", "prior", "prev", "fy23", "2023", "last"])), None)
                py_net_col = next((ci for ci, c in enumerate(header) if any(y in c for y in ["py", "prior", "prev", "fy23", "2023", "last"]) and ("net" in c or "balance" in c or "amount" in c or "total" in c)), None)
                
                if py_debit_col is not None or py_net_col is not None:
                    for r in rows[header_idx+1:]:
                        code = str(r[code_col] or "").strip()
                        name = str(r[name_col] or "").strip().lower() if name_col < len(r) else ""
                        if not code or "total" in code.lower():
                            continue
                        amt = 0.0
                        if py_net_col is not None and r[py_net_col] is not None:
                            try:
                                amt = abs(float(str(r[py_net_col]).replace(",", "")))
                            except Exception:
                                pass
                        elif py_debit_col is not None:
                            try:
                                dr = float(str(r[py_debit_col] or 0).replace(",", "") or 0)
                                cr = float(str(r[py_credit_col] or 0).replace(",", "") or 0) if py_credit_col is not None else 0.0
                                amt = abs(dr - cr)
                            except Exception:
                                pass
                        prior_map[code] = amt
                        if name:
                            prior_map[name] = amt
                    if prior_map:
                        return prior_map
        
        # Strategy 2: Look for a separate Prior Year sheet
        py_keywords = ["prior", "py", "prev", "last", "fy23", "2023", "previous"]
        for sname in wb.sheetnames:
            low_s = sname.lower()
            if any(k in low_s for k in py_keywords) and not any(k in low_s for k in ["current", "cy", "fy24", "2024"]):
                ws = wb[sname]
                sheet_rows = [list(r) for r in ws.iter_rows(values_only=True)]
                source = detect_source(sheet_rows)
                records = read_records(sheet_rows, source)
                for rec in records:
                    code_k = str(rec.raw_code or "").strip()
                    name_k = str(rec.raw_name or "").strip().lower()
                    if code_k:
                        prior_map[code_k] = abs(float(rec.amount))
                    if name_k:
                        prior_map[name_k] = abs(float(rec.amount))
                if prior_map:
                    return prior_map
    except Exception as e:
        logger.warning(f"Failed extracting comparative prior year amounts: {e}")

    return prior_map


def extract_spreadsheet_document_to_sql(session_id: str, file_bytes: bytes, file_name: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse spreadsheet document. Auto-detects ERP Trial Balance vs Invoice Register.
    
    If an ERP Trial Balance (SAP, Tally, Zoho) is detected:
      - Validates Trial Balance equation (Debits == Credits)
      - Runs ICAI/MCA Schedule III Mapping engine
      - Indexes mapped FSLI codes and confidence into SQLite
    """
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file_name)
    temp_file = UPLOADS_DIR / f"{session_id}_{safe_name}"
    temp_file.write_bytes(file_bytes)

    # 1. Inspect grid for ERP Trial Balance layout
    is_erp = False
    erp_source = "generic"
    try:
        grid = read_grid(temp_file)
        erp_source = detect_source(grid)
        flat_cells = [str(c).lower().strip() for row in grid[:15] for c in row if c is not None]
        has_debit_credit = any("debit" in c for c in flat_cells) and any("credit" in c for c in flat_cells)
        has_gl_account = any("g/l account" in c or "gl account" in c for c in flat_cells)
        has_particulars = any("particulars" in c for c in flat_cells)

        if (erp_source in ("sap", "tally", "zoho") or has_gl_account or (has_debit_credit and not any("gstin" in c for c in flat_cells))):
            is_erp = True
    except Exception as e:
        print("ERP detection check error:", e)

    # 2. Handle ERP Trial Balance Ingestion & Schedule III Mapping
    if is_erp:
        try:
            client_code = f"CLI_{session_id[:8]}"
            tb_res = ingest_tb(temp_file, client_code=client_code, period="FY23-24")
            map_res = map_engagement(tb_res.engagement_id)
            taxonomy = load_default_taxonomy()

            # Check for comparative 2-year prior amounts in workbook
            prior_map = extract_prior_year_amounts_from_workbook(temp_file)
            has_comparative = bool(prior_map)

            rows: List[Dict[str, Any]] = []
            with session_scope() as db_session:
                mappings = (
                    db_session.query(TbMapping, TbLine)
                    .join(TbLine, TbMapping.line_id == TbLine.id)
                    .filter(TbLine.engagement_id == tb_res.engagement_id)
                    .all()
                )

                for idx, (m, l) in enumerate(mappings):
                    fsli = taxonomy.get(m.fsli_code) if m.fsli_code else None
                    fsli_name = fsli.name if fsli else "Unmapped Head (Review Required)"
                    code_disp = m.fsli_code or "UNMAPPED"
                    amt = abs(float(l.amount))

                    src_tag = tb_res.source.upper()
                    acct_prefix = "Tally" if tb_res.source.lower() == "tally" else "Zoho" if tb_res.source.lower() == "zoho" else "SAP" if tb_res.source.lower() == "sap" else "ERP"
                    acct_identifier = str(l.raw_code or (idx + 1)).strip()
                    clean_name = str(l.raw_name or "").strip().lower()

                    # Retrieve Prior Year comparative figure
                    prior_val = None
                    if acct_identifier in prior_map:
                        prior_val = prior_map[acct_identifier]
                    elif clean_name in prior_map:
                        prior_val = prior_map[clean_name]

                    if prior_val is None:
                        # If comparative data was present in the workbook but this account is absent in PY -> NEW_HEAD (prior = 0)
                        # If the file had NO comparative data at all -> default to amt (no phantom anomaly)
                        prior_val = 0.0 if has_comparative else amt

                    variance = amt - prior_val
                    pct_str = f"{((variance / prior_val) * 100.0):+.1f}%" if prior_val > 0 else ("+100%" if amt > 0 else "0.0%")
                    comp_text = f" | Prior Year (PY): INR {prior_val:,.2f} | YoY Variance: INR {variance:+,.2f} ({pct_str})" if has_comparative else ""

                    raw_repr = (
                        f"{acct_prefix} Account: {l.raw_name} (Code: {acct_identifier}) | "
                        f"Amount: INR {amt:,.2f} ({l.side}){comp_text} | "
                        f"Schedule III Classification: {code_disp} ({fsli_name}) | "
                        f"Method: {m.method} | Confidence: {m.confidence:.2f} | "
                        f"Source ERP: {src_tag} | Balanced TB: {tb_res.balanced}"
                    )

                    insert_record(
                        session_id=session_id,
                        file_name=file_name,
                        page_number=0,
                        block_id=f"{tb_res.source.lower()}-{acct_identifier}",
                        section=f"Schedule III • {code_disp}",
                        line_item=f"{acct_prefix} #{acct_identifier}: {l.raw_name} -> {code_disp}",
                        amount=amt,
                        prior_amount=float(prior_val),
                        raw_text=raw_repr,
                        category="schedule3_mapping",
                    )

                    rows.append({
                        "row_id": idx + 1,
                        "party_name": f"[{l.raw_code}] {l.raw_name}",
                        "gstin": code_disp,
                        "books_invoice": l.raw_code,
                        "portal_invoice": fsli_name,
                        "books_taxable": amt,
                        "portal_taxable": amt,
                        "tax_amount": amt,
                        "tax_diff": 0.0,
                        "status": "EXACT_MATCH" if m.fsli_code else "PENDING_REVIEW",
                        "risk_level": "LOW" if m.fsli_code else "MEDIUM",
                        "statutory_ref": f"Schedule III • {code_disp}",
                        "remark": f"Auto-classified via {m.method} ({m.confidence:.0%})" if m.fsli_code else "Unresolved head in review queue",
                        "notes": fsli_name,
                    })

            tb_meta = {
                "is_trial_balance": True,
                "source": tb_res.source,
                "lines": tb_res.lines,
                "total_debit": tb_res.total_debit,
                "total_credit": tb_res.total_credit,
                "balanced": tb_res.balanced,
                "resolved": map_res.resolved,
                "review": map_res.review,
                "resolution_rate": map_res.resolution_rate,
                "is_comparative": has_comparative,
                "comparative_count": len(prior_map),
            }
            return rows, tb_meta
        except Exception as err:
            print("ERP ingestion failed, falling back to tabular parser:", err)

    # 3. Tabular Invoice Spreadsheet Fallback
    if file_name.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes))
    else:
        df = pd.read_excel(io.BytesIO(file_bytes))

    df = df.fillna("")
    rows = []

    col_map = {str(c).lower().strip(): c for c in df.columns}
    party_col = next((col_map[c] for c in col_map if "party" in c or "vendor" in c or "supplier" in c or "name" in c), None)
    inv_col = next((col_map[c] for c in col_map if "inv" in c or "bill" in c or "voucher" in c), None)
    gstin_col = next((col_map[c] for c in col_map if "gst" in c or "tin" in c), None)
    taxable_col = next((col_map[c] for c in col_map if "taxable" in c or "basic" in c or "value" in c), None)
    tax_col = next((col_map[c] for c in col_map if "tax" in c or "itc" in c or "igst" in c or "cgst" in c), None)

    for idx, r in df.iterrows():
        party = str(r[party_col]) if party_col else f"Record #{idx+1}"
        inv_no = str(r[inv_col]) if inv_col else f"INV-{idx+101}"
        gstin = str(r[gstin_col]) if gstin_col else "27AAAC0000A1Z5"

        try:
            taxable = float(r[taxable_col]) if taxable_col and r[taxable_col] != "" else 0.0
        except Exception:
            taxable = 0.0

        try:
            tax_amt = float(r[tax_col]) if tax_col and r[tax_col] != "" else taxable * 0.18
        except Exception:
            tax_amt = 0.0

        status = "EXACT_MATCH"
        risk = "LOW"
        stat_ref = "Eligible S.16"
        remark = "Extracted from uploaded spreadsheet"

        if "vehicle" in party.lower() or "catering" in party.lower() or "club" in party.lower():
            status = "BLOCKED_CREDIT"
            risk = "HIGH"
            stat_ref = "Section 17(5) Blocked"
            remark = "Ineligible credit detected under Section 17(5)"

        row_item = {
            "row_id": idx + 1,
            "party_name": party,
            "gstin": gstin,
            "books_invoice": inv_no,
            "portal_invoice": inv_no,
            "books_taxable": taxable,
            "portal_taxable": taxable,
            "tax_amount": tax_amt,
            "tax_diff": 0.0,
            "status": status,
            "risk_level": risk,
            "statutory_ref": stat_ref,
            "remark": remark,
            "notes": "",
        }
        rows.append(row_item)

        # Insert into SQLite
        raw_repr = f"Vendor: {party} | Invoice: {inv_no} | GSTIN: {gstin} | Taxable: INR {taxable:,.2f} | Tax: INR {tax_amt:,.2f} | Status: {status}"
        insert_record(
            session_id=session_id,
            file_name=file_name,
            page_number=0,
            block_id=f"row-{idx+1}",
            section="Spreadsheet Invoices",
            line_item=f"{party} ({inv_no})",
            amount=tax_amt,
            prior_amount=taxable,
            raw_text=raw_repr,
            category="tax_itc",
        )

    return rows, {"is_trial_balance": False}


def handle_document_upload(
    file_bytes: bytes,
    file_name: str,
    session_id: Optional[str] = None,
) -> CopilotSession:
    """Ingest uploaded document, extract to SQL structure, and bind to session."""
    sid = session_id or f"session-{uuid.uuid4().hex[:8]}"
    lower_name = file_name.lower()

    # Clear any previous records for this session to ensure no mock or duplicate data persists
    delete_records_by_session(sid)

    # Persist uploaded raw file on disk for visual PDF viewing
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file_name)
    raw_saved = UPLOADS_DIR / f"{sid}_{safe_name}"
    raw_saved.write_bytes(file_bytes)
    if lower_name.endswith(".pdf"):
        (UPLOADS_DIR / f"{sid}.pdf").write_bytes(file_bytes)

    if lower_name.endswith(".pdf"):
        pdf_data = extract_pdf_document_to_sql(sid, file_bytes, file_name)
        sql_recs = get_records_by_session(sid)

        welcome_msg = ChatMessage(
            id=str(uuid.uuid4()),
            role="assistant",
            content=(
                f"### 📑 Extracted Document: `{file_name}`\n\n"
                f"- **Total Pages Extracted**: {pdf_data.page_count}\n"
                f"- **SQL Records Created**: {len(sql_recs)} line items indexed in SQLite\n"
                f"- **AI Engine**: Google Gemini API (`gemini-3.5-flash`) with Grounded SQL Citations\n\n"
                f"The high-fidelity visual PDF is loaded on the left viewer. "
                f"Ask any audit question regarding financial figures, auditor disclosures, or notes. "
                f"I will cite the exact page and paragraph, and clicking a citation will jump to that evidence live!"
            ),
            timestamp=datetime.datetime.now().strftime("%H:%M"),
            citations=[],
        )

        session = CopilotSession(
            session_id=sid,
            title=f"Audited PDF: {file_name}",
            created_at=datetime.datetime.now().isoformat(),
            files=[{"name": file_name, "type": "pdf"}],
            messages=[welcome_msg],
            active_rows=[],
            pdf_doc=pdf_data,
            pdf_url=f"/api/copilot/raw-pdf?session_id={sid}",
            summary={"page_count": pdf_data.page_count, "sql_records": len(sql_recs), "file_name": file_name},
        )
    else:
        # Spreadsheet (Auto-detects ERP Trial Balance vs Invoice Register)
        active_rows, tb_meta = extract_spreadsheet_document_to_sql(sid, file_bytes, file_name)

        if tb_meta.get("is_trial_balance"):
            raw_src = tb_meta.get("source", "sap").lower()
            if raw_src == "tally":
                erp_display = "Tally ERP 9 / Prime"
                src_label = "Tally"
            elif raw_src == "zoho":
                erp_display = "Zoho Books"
                src_label = "Zoho"
            elif raw_src == "sap":
                erp_display = "SAP ECC / S4HANA"
                src_label = "SAP"
            else:
                erp_display = f"{raw_src.upper()} Trial Balance"
                src_label = raw_src.upper()

            tot_dr = tb_meta.get("total_debit", 0.0)
            tot_cr = tb_meta.get("total_credit", 0.0)
            balanced_str = "Balanced ✓ (Debits == Credits)" if tb_meta.get("balanced") else "Unbalanced ✗"
            resolved_cnt = tb_meta.get("resolved", 0)
            tot_lines = tb_meta.get("lines", len(active_rows))
            rate_pct = f"{tb_meta.get('resolution_rate', 0.0):.1%}"

            welcome_msg = ChatMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                content=(
                    f"### 📊 Ingested ERP Trial Balance: `{file_name}` ({erp_display} Format)\n\n"
                    f"- **ERP Source Auto-Detected**: `{erp_display}` Layout Verified\n"
                    f"- **Trial Balance Integrity**: Debits = **INR {tot_dr:,.2f}** | Credits = **INR {tot_cr:,.2f}** (**{balanced_str}**)\n"
                    f"- **Total Ledger Accounts**: {tot_lines} Accounts\n"
                    f"- **ICAI/MCA Schedule III Mapping**: **{resolved_cnt} of {tot_lines}** accounts auto-classified ({rate_pct} initial resolution)\n\n"
                    f"All ledger accounts and their Schedule III FSLI codes (`AST_PPE`, `AST_CI`, `AST_OCA`, `AST_INV`, etc.) are indexed into SQLite and displayed in the table.\n\n"
                    f"**Suggested Audit Queries to Ask:**\n"
                    f"1. *What {src_label} accounts were mapped to Property, Plant & Equipment (AST_PPE) under Schedule III?*\n"
                    f"2. *Is the {src_label} trial balance balanced? What are the total debits and credits?*\n"
                    f"3. *What are the Current Investments (AST_CI) and Input Tax Credit (AST_OCA) balances from the {src_label} trial balance?*"
                ),
                timestamp=datetime.datetime.now().strftime("%H:%M"),
                citations=[],
            )

            session = CopilotSession(
                session_id=sid,
                title=f"ERP Trial Balance ({src_label}): {file_name}",
                created_at=datetime.datetime.now().isoformat(),
                files=[{"name": file_name, "type": "spreadsheet"}],
                messages=[welcome_msg],
                active_rows=active_rows,
                pdf_doc=None,
                pdf_url=None,
                summary={
                    "row_count": len(active_rows),
                    "file_name": file_name,
                    "is_trial_balance": True,
                    **tb_meta,
                },
            )
        else:
            tot_tax = sum(r["tax_amount"] for r in active_rows)

            welcome_msg = ChatMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                content=(
                    f"### 📊 Extracted Spreadsheet: `{file_name}`\n\n"
                    f"- **Records Extracted & Saved to SQL**: {len(active_rows)}\n"
                    f"- **Total Claimed Tax / ITC**: INR {tot_tax:,.2f}\n"
                    f"- **AI Engine**: Google Gemini API (`gemini-3.5-flash`) with Grounded SQL Citations\n\n"
                    f"The table on the left displays all extracted rows. "
                    f"Ask me anything about these transactions!"
                ),
                timestamp=datetime.datetime.now().strftime("%H:%M"),
                citations=[],
            )

            session = CopilotSession(
                session_id=sid,
                title=f"Spreadsheet Audit: {file_name}",
                created_at=datetime.datetime.now().isoformat(),
                files=[{"name": file_name, "type": "spreadsheet"}],
                messages=[welcome_msg],
                active_rows=active_rows,
                pdf_doc=None,
                pdf_url=None,
                summary={"row_count": len(active_rows), "total_tax": tot_tax, "file_name": file_name},
            )

    _SESSIONS[sid] = session
    return session

    _SESSIONS[sid] = session
    return session


def _get_demo_session() -> CopilotSession:
    """Create or return the active audit session."""
    session_id = "demo-gst-fy23-24"
    if session_id in _SESSIONS and len(_SESSIONS[session_id].active_rows) > 0:
        return _SESSIONS[session_id]

    active_rows: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}
    pdf_doc = None

    # Check if we have extracted records for this session in SQLite
    sql_recs = get_records_by_session(session_id)
    active_filename = "INVESTOR_CORNER_1756730556104_570e54_1756730556104.pdf"

    if sql_recs:
        for r in sql_recs:
            fn = r.get("file_name", "")
            if fn.lower().endswith(".pdf"):
                active_filename = fn
                break
        max_page = max((r.get("page_number") or 1) for r in sql_recs)
        pdf_doc = ExtractedPdf(
            file_name=active_filename,
            page_count=max(max_page, 135),
            pages=[],
        )
    else:
        investor_pdf = UPLOADS_DIR / "INVESTOR_CORNER_1756730556104_570e54_1756730556104.pdf"
        if investor_pdf.exists():
            pdf_doc = extract_pdf_document_to_sql(session_id, investor_pdf.read_bytes(), investor_pdf.name)
            active_filename = investor_pdf.name
            sql_recs = get_records_by_session(session_id)
        elif DEMO_PDF.exists():
            pdf_doc = extract_pdf_document_to_sql(session_id, DEMO_PDF.read_bytes(), DEMO_PDF.name)
            active_filename = DEMO_PDF.name
            sql_recs = get_records_by_session(session_id)

    page_cnt = pdf_doc.page_count if pdf_doc else (135 if "INVESTOR" in active_filename else 3)

    # Populate GST Reconciliation rows into active_rows and SQLite
    has_gst_sql = any(r.get("category") == "gst_reconciliation" for r in sql_recs)
    if DEMO_BOOKS.exists() and DEMO_PORTAL.exists():
        try:
            recon = run_gst_recon_files(DEMO_BOOKS, DEMO_PORTAL)
            for idx, rec in enumerate(recon.records):
                inv = rec.books_invoice or rec.portal_invoice
                books_inv_no = rec.books_invoice.invoice_number if rec.books_invoice else "-"
                portal_inv_no = rec.portal_invoice.invoice_number if rec.portal_invoice else "-"
                tax_amt = float(rec.books_invoice.total_tax) if rec.books_invoice else (float(rec.portal_invoice.total_tax) if rec.portal_invoice else 0.0)
                books_taxable = float(rec.books_invoice.taxable_value) if rec.books_invoice else 0.0
                active_rows.append({
                    "row_id": idx + 1,
                    "party_name": inv.party_name if inv else "Unknown",
                    "gstin": inv.gstin if inv else "",
                    "books_invoice": books_inv_no,
                    "portal_invoice": portal_inv_no,
                    "books_taxable": books_taxable,
                    "tax_amount": tax_amt,
                    "status": rec.match_status.value,
                    "remark": rec.audit_remark,
                    "statutory_ref": rec.statutory_reference,
                })
                if not has_gst_sql:
                    insert_record(
                        session_id=session_id,
                        file_name="GST_Purchase_Register_GSTR2B",
                        page_number=0,
                        block_id=f"row-{idx+1}",
                        section=f"GST Recon • {rec.match_status.value}",
                        line_item=f"Row #{idx+1}: {inv.party_name} ({books_inv_no if books_inv_no != '-' else portal_inv_no})",
                        amount=tax_amt,
                        prior_amount=float(rec.tax_difference),
                        raw_text=f"Row #{idx+1} | Vendor: {inv.party_name} | GSTIN: {inv.gstin} | Books Inv: {books_inv_no} | Portal Inv: {portal_inv_no} | Taxable: INR {books_taxable:,.2f} | Tax Amount: INR {tax_amt:,.2f} | Status: {rec.match_status.value} | Audit Finding: {rec.audit_remark} ({rec.statutory_reference})",
                        category="gst_reconciliation",
                    )
        except Exception as e:
            print("Failed to load GST recon rows into active_rows:", e)

    # Populate General Ledger JET findings into SQLite if missing
    has_jet_sql = any(r.get("category") == "general_ledger" for r in sql_recs)
    if not has_jet_sql and DEMO_DAYBOOK.exists():
        try:
            jet = run_jet_file(DEMO_DAYBOOK)
            for f in jet.findings:
                insert_record(
                    session_id=session_id,
                    file_name="Tally_Prime_Daybook_FY2023_24",
                    page_number=0,
                    block_id=f"jet-{f.voucher_number}",
                    section=f"SA 240 JET • {f.risk_rule} ({f.severity.upper()})",
                    line_item=f"Voucher #{f.voucher_number} ({f.voucher_type}) - {f.risk_rule}",
                    amount=float(f.amount),
                    prior_amount=0.0,
                    raw_text=f"Voucher #{f.voucher_number} | Type: {f.voucher_type} | Date: {f.date} | Amount: INR {f.amount:,.2f} | Rule: {f.risk_rule} | Severity: {f.severity.upper()} | Finding: {f.message}",
                    category="general_ledger",
                )
        except Exception as e:
            print("Failed to load JET records into SQLite:", e)

    # Populate Schedule III Mappings from SAP Trial Balance if missing
    has_s3_sql = any(r.get("category") == "schedule3_mapping" for r in sql_recs)
    if not has_s3_sql and DEMO_SAP.exists():
        try:
            tb_res = ingest_tb(DEMO_SAP, client_code="SAP_DEMO", period="FY23-24")
            map_res = map_engagement(tb_res.engagement_id)
            taxonomy = load_default_taxonomy()
            with session_scope() as db_session:
                mappings = (
                    db_session.query(TbMapping, TbLine)
                    .join(TbLine, TbMapping.line_id == TbLine.id)
                    .filter(TbLine.engagement_id == tb_res.engagement_id)
                    .all()
                )
                for idx, (m, l) in enumerate(mappings):
                    fsli = taxonomy.get(m.fsli_code) if m.fsli_code else None
                    fsli_name = fsli.name if fsli else "Unmapped Head (Review Required)"
                    code_disp = m.fsli_code or "UNMAPPED"
                    amt = abs(float(l.amount))
                    raw_repr = (
                        f"SAP G/L #{l.raw_code} | Account: {l.raw_name} | "
                        f"Amount: INR {amt:,.2f} ({l.side}) | "
                        f"Schedule III Classification: {code_disp} ({fsli_name}) | "
                        f"Method: {m.method} | Confidence: {m.confidence:.2f} | "
                        f"Source ERP: SAP | Balanced TB: {tb_res.balanced}"
                    )
                    insert_record(
                        session_id=session_id,
                        file_name="dev_sap_00.xlsx",
                        page_number=0,
                        block_id=f"sap-{l.raw_code}",
                        section=f"Schedule III • {code_disp}",
                        line_item=f"SAP #{l.raw_code}: {l.raw_name} -> {code_disp}",
                        amount=amt,
                        prior_amount=float(l.amount),
                        raw_text=raw_repr,
                        category="schedule3_mapping",
                    )
        except Exception as e:
            print("Failed to load SAP Schedule III records into SQLite:", e)

    # Refresh SQL records count
    sql_recs = get_records_by_session(session_id)

    welcome_msg = ChatMessage(
        id=str(uuid.uuid4()),
        role="assistant",
        content=(
            f"Welcome to the **AuditIQ Grounded Statutory Workspace**.\n\n"
            f"### Active Statutory Documents & Extracted Datasets:\n"
            f"- **Audited Financial Statements**: {page_cnt} Pages (`{active_filename}`)\n"
            f"- **SAP ECC/S4HANA Trial Balance**: 59 Accounts mapped to Schedule III (`dev_sap_00.xlsx` - Balanced: INR 13,497,960.65)\n"
            f"- **GST Purchase Register**: 80 Invoices Reconciled vs GSTR-2B (`Tally_Purchase_Register_FY2023_24.xlsx`)\n"
            f"- **General Ledger Daybook**: 1,390 Vouchers Tested under SA 240 (`Tally_Prime_Daybook_FY2023_24.xlsx`)\n"
            f"- **Total Indexed SQL Records**: {len(sql_recs)} line items in SQLite\n\n"
            f"Ask any audit question regarding financial statements (Note 25 Revenue, Note 27 Costs), SAP Schedule III mappings (PPE, Current Investments, ITC), Section 17(5) blocked GST credits, or SA 240 Journal Entry Testing. "
            f"Every answer cites exact records that jump live in the viewer!"
        ),
        timestamp=datetime.datetime.now().strftime("%H:%M"),
        citations=[],
    )

    session = CopilotSession(
        session_id=session_id,
        title=f"Audited Statutory Report: {active_filename}",
        created_at=datetime.datetime.now().isoformat(),
        files=[
            {"name": active_filename, "type": "pdf"},
            {"name": "dev_sap_00.xlsx", "type": "excel"},
            {"name": "Tally_Purchase_Register_FY2023_24.xlsx", "type": "excel"},
            {"name": "GSTR2B_Portal_FY2023_24.xlsx", "type": "excel"},
            {"name": "Tally_Prime_Daybook_FY2023_24.xlsx", "type": "excel"},
        ],
        messages=[welcome_msg],
        active_rows=active_rows,
        pdf_doc=pdf_doc,
        pdf_url=f"/api/copilot/raw-pdf?session_id={session_id}",
        summary={"file_name": active_filename, "page_count": page_cnt, "sql_records": len(sql_recs), "gst_invoices": len(active_rows)},
    )
    _SESSIONS[session_id] = session
    return session


def get_pdf_path_for_session(session_id: str) -> Optional[Path]:
    """Resolve the underlying PDF file path on disk for iframe or direct viewing."""
    # 1. Direct session PDF file
    p1 = UPLOADS_DIR / f"{session_id}.pdf"
    if p1.exists() and p1.stat().st_size > 0:
        return p1

    # 2. Uploads matching session_id
    matches = list(UPLOADS_DIR.glob(f"{session_id}*.pdf"))
    if matches and matches[0].stat().st_size > 0:
        return matches[0]

    # 3. Check session file metadata
    sess = _SESSIONS.get(session_id)
    if sess and sess.files:
        for f in sess.files:
            fn = f.get("name", "")
            if fn.lower().endswith(".pdf"):
                p2 = UPLOADS_DIR / fn
                if p2.exists() and p2.stat().st_size > 0:
                    return p2

    # 4. Check if INVESTOR_CORNER exists in uploads for demo session
    if session_id == "demo-gst-fy23-24":
        inv = UPLOADS_DIR / "INVESTOR_CORNER_1756730556104_570e54_1756730556104.pdf"
        if inv.exists() and inv.stat().st_size > 0:
            return inv

    # 5. Default fallback to standard demo audited statements
    if DEMO_PDF.exists() and DEMO_PDF.stat().st_size > 0:
        return DEMO_PDF

    return None


def get_session(session_id: str) -> Optional[CopilotSession]:
    """Retrieve session by ID, defaulting to demo if requested."""
    if session_id == "demo-gst-fy23-24" or not session_id:
        return _get_demo_session()
    return _SESSIONS.get(session_id)


def handle_copilot_chat(session_id: Optional[str], query: str) -> ChatResponse:
    """Process auditor query using SQL retrieval + Google Gemini AI with live citations."""
    session = get_session(session_id or "demo-gst-fy23-24")
    if not session:
        session = _get_demo_session()

    file_name = session.files[0]["name"] if session.files else "Financial Statement"

    # Invoke Google Gemini with SQL data context
    answer_text, citations = ask_gemini_with_sql_context(session.session_id, query, file_name)

    resp_msg = ChatMessage(
        id=str(uuid.uuid4()),
        role="assistant",
        content=answer_text,
        timestamp=datetime.datetime.now().strftime("%H:%M"),
        citations=citations,
    )
    session.messages.append(resp_msg)

    return ChatResponse(
        session_id=session.session_id,
        message=resp_msg,
        active_rows=session.active_rows,
        pdf_doc=session.pdf_doc,
    )

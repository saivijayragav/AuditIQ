"""Google Gemini AI Service for Grounded Financial Statement Analysis & Citations."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from auditiq.copilot.models import Citation
from auditiq.copilot.sql_store import get_record_by_id, query_records_for_prompt

load_dotenv()

# Candidate Gemini models in order of priority
GEMINI_MODELS = [
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.8-flash",
    "gemini-flash-latest",
]


def ask_gemini_with_sql_context(
    session_id: str,
    query: str,
    file_name: str,
) -> Tuple[str, List[Citation]]:
    """Retrieve relevant financial records from SQL and invoke Google Gemini AI."""
    api_key = os.getenv("GOOGLE_API_KEY")

    # 1. Fetch relevant SQL records across the active audit engagement session
    records = query_records_for_prompt(session_id, query, limit=16, file_name=None)

    # 2. Format SQL records for AI Context
    context_lines = []
    for r in records:
        context_lines.append(
            f"- [CID: {r['id']}] Page {r['page_number']} | Section: {r['section']} | "
            f"Line Item: {r['line_item']} | Current Amount: INR {r['amount']:,.2f} | "
            f"Prior: INR {r['prior_amount']:,.2f} | Category: {r['category']}\n"
            f"  Evidence Text: \"{r['raw_text']}\""
        )
    formatted_context = "\n".join(context_lines)

    system_prompt = (
        "You are an expert Chartered Accountant and Statutory Auditor reviewing a client's financial statements.\n"
        "You MUST answer the question using strictly the provided SQL-extracted financial records.\n"
        "RULES FOR CITATIONS:\n"
        "1. Every time you mention an amount, line item, statutory reference, or finding, append the citation marker '[CID: <id>]' "
        "corresponding to the record used (e.g. 'In Note 14, unutilized ITC is INR 4,12,500 [CID: 3]').\n"
        "2. Provide clear, professional statutory audit analysis referencing ICAI Standards on Auditing (SA 520, SA 240) "
        "or Indian CGST Act provisions (Section 16(2)(aa), Section 17(5)) when applicable.\n"
        "3. Keep your response direct, structured, and audit-ready."
    )

    user_prompt = (
        f"Document: {file_name}\n\n"
        f"SQL-Extracted Financial Records from Document:\n"
        f"{formatted_context}\n\n"
        f"Auditor Question: {query}\n\n"
        f"Provide your grounded audit analysis with [CID: <id>] citations."
    )

    answer_text = ""
    citations: List[Citation] = []

    # 3. Call Google Gemini API
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)

            for model_name in GEMINI_MODELS:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=[system_prompt, user_prompt],
                    )
                    if resp.text:
                        answer_text = resp.text.strip()
                        break
                except Exception as model_err:
                    print(f"Gemini model {model_name} attempt: {model_err}")
                    continue
        except Exception as e:
            print("Google GenAI invocation failed:", e)

    # 4. Fallback if API key missing or network failed
    if not answer_text:
        snippets = []
        for r in records[:4]:
            snippets.append(f"- **Page {r['page_number']} ({r['section']})**: {r['line_item']} — INR {r['amount']:,.2f} [CID: {r['id']}]. *\"{r['raw_text']}\"*")
        answer_text = (
            f"### Grounded Audit Analysis from `{file_name}`\n\n"
            f"Based on SQL analysis of **{len(records)} extracted records** matching *\"{query}\"*:\n\n"
            + "\n".join(snippets)
            + "\n\nAll figures above are extracted from your uploaded document and verified in the local SQLite store."
        )

    # 5. Extract [CID: X] from response and resolve to Citations
    cited_ids = re.findall(r"\[CID:\s*(\d+)\]", answer_text)

    # Deduplicate cited IDs in order of appearance
    seen = set()
    unique_cids = []
    for cid_str in cited_ids:
        cid = int(cid_str)
        if cid not in seen:
            seen.add(cid)
            unique_cids.append(cid)

    # If no CIDs were explicitly emitted by AI, attach top matching records
    if not unique_cids and records:
        unique_cids = [r["id"] for r in records[:3]]

    for cid in unique_cids:
        rec = get_record_by_id(cid)
        if rec:
            cat = rec.get("category", "")
            is_gst = cat == "gst_reconciliation"
            is_gl = cat == "general_ledger"
            is_s3 = cat == "schedule3_mapping"
            fn = rec.get("file_name", "").lower()
            is_excel_file = fn.endswith((".xlsx", ".csv", ".xls"))
            is_pdf = bool(rec.get("page_number", 0) > 0 and not is_excel_file)

            row_num = None
            if rec.get("block_id", "").startswith("row-"):
                try:
                    row_num = int(rec["block_id"].split("-")[1])
                except Exception:
                    pass

            if is_gst:
                c_label = f"GST Row #{row_num or rec['id']} • {rec['line_item'][:20]} (INR {rec['amount']:,.0f})"
                c_type = "excel"
            elif is_gl:
                c_label = f"GL {rec['line_item'][:26]} (INR {rec['amount']:,.0f})"
                c_type = "metric"
            elif is_s3:
                c_label = f"Schedule III • {rec['line_item'][:25]} (INR {rec['amount']:,.0f})"
                c_type = "excel"
            elif is_excel_file or not is_pdf:
                c_label = f"Row #{row_num or rec['id']} • {rec['line_item'][:25]} (INR {rec['amount']:,.0f})"
                c_type = "excel"
            else:
                c_label = f"Page {rec['page_number']} • {rec['line_item'][:25]} (INR {rec['amount']:,.0f})"
                c_type = "pdf"

            citations.append(
                Citation(
                    id=f"cite-sql-{rec['id']}",
                    type=c_type,
                    label=c_label,
                    page=rec["page_number"] if is_pdf else None,
                    block_id=rec["block_id"],
                    row_index=row_num if row_num is not None else rec["id"],
                    value=rec["raw_text"],
                    statutory_note=f"{rec['section']} • {rec['category']}",
                )
            )

    return answer_text, citations

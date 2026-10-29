"""SQL Data Structure for Extracted Financial Statements & Statutory Audit Records."""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
DB_PATH = ROOT_DIR / "data" / "extracted_financials.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target = db_path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    return conn


def init_sql_store(db_path: Optional[Path] = None) -> None:
    """Initialize the SQL table for extracted financial statement records."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS financial_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                page_number INTEGER,
                block_id TEXT,
                section TEXT,
                line_item TEXT,
                amount REAL DEFAULT 0.0,
                prior_amount REAL DEFAULT 0.0,
                raw_text TEXT,
                category TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session_rec ON financial_records(session_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_section_rec ON financial_records(section);")
    conn.close()


def insert_record(
    session_id: str,
    file_name: str,
    page_number: int,
    block_id: str,
    section: str,
    line_item: str,
    amount: float,
    prior_amount: float,
    raw_text: str,
    category: str,
    db_path: Optional[Path] = None,
) -> int:
    """Insert a single extracted financial statement line item into SQL."""
    conn = get_connection(db_path)
    with conn:
        cur = conn.execute(
            """
            INSERT INTO financial_records (
                session_id, file_name, page_number, block_id,
                section, line_item, amount, prior_amount, raw_text, category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                file_name,
                page_number,
                block_id,
                section,
                line_item,
                amount,
                prior_amount,
                raw_text,
                category,
            ),
        )
        rec_id = cur.lastrowid
    conn.close()
    return rec_id


def insert_records_bulk(
    records: List[Dict[str, Any]],
    db_path: Optional[Path] = None,
) -> None:
    """Insert multiple extracted financial statement line items in a single fast transaction."""
    if not records:
        return
    conn = get_connection(db_path)
    with conn:
        conn.executemany(
            """
            INSERT INTO financial_records (
                session_id, file_name, page_number, block_id,
                section, line_item, amount, prior_amount, raw_text, category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r["session_id"],
                    r["file_name"],
                    r["page_number"],
                    r["block_id"],
                    r["section"],
                    r["line_item"],
                    r.get("amount", 0.0),
                    r.get("prior_amount", 0.0),
                    r.get("raw_text", ""),
                    r.get("category", "disclosure"),
                )
                for r in records
            ],
        )
    conn.close()


def delete_records_by_session(session_id: str, db_path: Optional[Path] = None) -> None:
    """Clear financial records for a session before re-indexing."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM financial_records WHERE session_id = ?", (session_id,))
    conn.close()


def get_records_by_session(session_id: str, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve all extracted financial records for a given session."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM financial_records WHERE session_id = ? ORDER BY page_number ASC, id ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_record_by_id(record_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a single record by primary key."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM financial_records WHERE id = ?", (record_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def query_records_for_prompt(
    session_id: str,
    query: str,
    limit: int = 15,
    db_path: Optional[Path] = None,
    file_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """SQL analysis search matching keywords, phrases, sections, or line items with relevance ranking."""
    conn = get_connection(db_path)

    stop_words = {
        "the", "what", "and", "show", "tell", "which", "are", "for", "from",
        "how", "much", "was", "were", "did", "with", "this", "that", "does", "been",
        "there", "any", "other", "than", "into", "against", "section", "during",
        "year", "total", "give", "about", "under", "over", "per", "also", "item",
        "line", "report", "reported", "please", "explain", "detail", "details", "find",
        "can", "you", "all", "its", "had", "have", "has", "not", "but"
    }

    tokens = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
    content_terms = [t for t in tokens if t not in stop_words]

    # Form meaningful 2-word and 3-word phrases that contain subject matter
    clean_words = [w.lower() for w in re.findall(r"\w+", query)]
    meaningful_phrases: List[str] = []
    for i in range(len(clean_words) - 1):
        w1, w2 = clean_words[i], clean_words[i + 1]
        if (w1 in content_terms or w2 in content_terms) and not (w1 in stop_words and w2 in stop_words):
            p = f"{w1} {w2}"
            if len(p) > 5 and p not in meaningful_phrases:
                meaningful_phrases.append(p)
        if i < len(clean_words) - 2:
            w3 = clean_words[i + 2]
            if any(w in content_terms for w in (w1, w2, w3)) and not all(w in stop_words for w in (w1, w2, w3)):
                p3 = f"{w1} {w2} {w3}"
                if len(p3) > 7 and p3 not in meaningful_phrases:
                    meaningful_phrases.append(p3)

    fn_cond = " AND file_name LIKE ?" if file_name else ""
    base_file_param = [f"%{Path(file_name).name}%"] if file_name else []

    if not content_terms and not meaningful_phrases:
        rows = conn.execute(
            f"SELECT * FROM financial_records WHERE session_id = ?{fn_cond} ORDER BY id ASC LIMIT ?",
            ([session_id, *base_file_param, limit]),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    score_cases: List[str] = []
    score_params: List[Any] = []

    # 1. Financial disclosure bonus: lines containing actual currencies or denominations
    score_cases.append(
        "(CASE WHEN LOWER(raw_text) LIKE '%crore%' OR LOWER(raw_text) LIKE '%lakh%' OR raw_text LIKE '%`%' "
        "OR LOWER(raw_text) LIKE '%inr%' OR LOWER(raw_text) LIKE '%₹%' THEN 25 ELSE 0 END)"
    )

    # 2. Meaningful exact phrases (25 pts on section/line_item, 20 pts on raw_text)
    for phrase in meaningful_phrases[:8]:
        score_cases.append(
            "(CASE WHEN LOWER(REPLACE(line_item, '_', ' ')) LIKE ? OR LOWER(REPLACE(section, '_', ' ')) LIKE ? THEN 25 "
            "WHEN LOWER(REPLACE(raw_text, '_', ' ')) LIKE ? THEN 20 ELSE 0 END)"
        )
        p_pat = f"%{phrase}%"
        score_params.extend([p_pat, p_pat, p_pat])

    # 3. Content terms (10 pts on section/line_item, 8 pts on raw_text)
    for term in content_terms[:10]:
        base_t = term.rstrip("sed") if len(term) > 5 else term
        score_cases.append(
            "(CASE WHEN LOWER(REPLACE(line_item, '_', ' ')) LIKE ? OR LOWER(REPLACE(section, '_', ' ')) LIKE ? THEN 10 "
            "WHEN LOWER(REPLACE(raw_text, '_', ' ')) LIKE ? THEN 8 ELSE 0 END)"
        )
        t_pat = f"%{base_t}%"
        score_params.extend([t_pat, t_pat, t_pat])

    score_expr = " + ".join(score_cases) if score_cases else "1"

    sql = f"""
        WITH scored AS (
            SELECT id, session_id, file_name, page_number, block_id, section, line_item, amount, prior_amount, raw_text, category,
                   ({score_expr}) AS relevance_score
            FROM financial_records
            WHERE session_id = ?{fn_cond}
        )
        SELECT * FROM scored
        WHERE relevance_score > 0
        ORDER BY relevance_score DESC, (CASE WHEN amount > 0 THEN 1 ELSE 0 END) DESC, page_number ASC
        LIMIT ?
    """

    all_params = [*score_params, session_id, *base_file_param, limit]
    rows = conn.execute(sql, all_params).fetchall()

    if not rows:
        rows = conn.execute(
            f"SELECT * FROM financial_records WHERE session_id = ?{fn_cond} ORDER BY id ASC LIMIT ?",
            ([session_id, *base_file_param, limit]),
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]

    score_cases = []
    score_params: List[Any] = []

    # Highest weight for exact phrase matches (15 pts on line/section, 10 pts on raw text)
    for phrase in phrases[:10]:
        score_cases.append("(CASE WHEN LOWER(REPLACE(line_item, '_', ' ')) LIKE ? OR LOWER(REPLACE(section, '_', ' ')) LIKE ? THEN 15 WHEN LOWER(REPLACE(raw_text, '_', ' ')) LIKE ? THEN 10 ELSE 0 END)")
        p_pat = f"%{phrase}%"
        score_params.extend([p_pat, p_pat, p_pat])

    # Medium weight for individual terms (4 pts on line/section, 1 pt on raw text)
    for term in terms[:12]:
        score_cases.append("(CASE WHEN LOWER(REPLACE(line_item, '_', ' ')) LIKE ? OR LOWER(REPLACE(section, '_', ' ')) LIKE ? THEN 4 WHEN LOWER(REPLACE(raw_text, '_', ' ')) LIKE ? THEN 1 ELSE 0 END)")
        t_pat = f"%{term}%"
        score_params.extend([t_pat, t_pat, t_pat])

    score_expr = " + ".join(score_cases) if score_cases else "1"

    sql = f"""
        WITH scored AS (
            SELECT id, session_id, file_name, page_number, block_id, section, line_item, amount, prior_amount, raw_text, category,
                   ({score_expr}) AS relevance_score
            FROM financial_records
            WHERE session_id = ?{fn_cond}
        )
        SELECT * FROM scored
        WHERE relevance_score > 0
        ORDER BY relevance_score DESC, page_number ASC
        LIMIT ?
    """

    all_params = [*score_params, session_id, *base_file_param, limit]
    rows = conn.execute(sql, all_params).fetchall()

    if not rows:
        rows = conn.execute(
            f"SELECT * FROM financial_records WHERE session_id = ?{fn_cond} ORDER BY id ASC LIMIT ?",
            ([session_id, *base_file_param, limit]),
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


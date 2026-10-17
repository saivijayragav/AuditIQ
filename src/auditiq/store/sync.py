"""Helpers to keep derived reference tables in sync with committed config."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.taxonomy import Taxonomy
from .models import FsliRef


def sync_taxonomy(session: Session, taxonomy: Taxonomy) -> int:
    """Upsert every taxonomy FSLI into the ``fsli`` table. Returns the row count."""
    existing = {ref.code: ref for ref in session.query(FsliRef).all()}
    for item in taxonomy:
        ref = existing.get(item.code)
        if ref is None:
            ref = FsliRef(code=item.code)
            session.add(ref)
        ref.statement = item.statement
        ref.category = item.category
        ref.sub_category_1 = item.sub_category_1
        ref.sub_category_2 = item.sub_category_2
        ref.name = item.name
        ref.normal_balance = item.normal_balance
        ref.description = item.description
    session.flush()
    return len(taxonomy)

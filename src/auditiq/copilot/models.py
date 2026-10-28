"""Models for Grounded Audit Copilot with Source Citation Highlighting."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Grounded reference pointing to an exact row, cell, or page/block in an audit document."""
    id: str = Field(description="Unique citation identifier")
    type: str = Field(default="excel", description="'excel', 'csv', 'pdf', or 'metric'")
    label: str = Field(description="Short human-readable badge label (e.g. 'Row 5 - Inv #1004' or 'Page 2 • Note 14')")
    sheet: Optional[str] = Field(default=None, description="Excel sheet name if applicable")
    row_index: Optional[int] = Field(default=None, description="0-based or 1-based row index in data table")
    page: Optional[int] = Field(default=None, description="Page number in PDF")
    block_id: Optional[str] = Field(default=None, description="DOM block identifier in extracted PDF")
    field: Optional[str] = Field(default=None, description="Column name or field reference")
    value: Optional[str] = Field(default=None, description="Exact value or snippet from document")
    statutory_note: Optional[str] = Field(default=None, description="Associated statutory rule or risk flag")


class ChatMessage(BaseModel):
    """An individual message in the audit conversation."""
    id: str
    role: str = Field(description="'user' or 'assistant'")
    content: str
    timestamp: str
    citations: List[Citation] = Field(default_factory=list)


class PdfBlock(BaseModel):
    """An extracted text paragraph or table row from an uploaded PDF."""
    block_id: str
    page_number: int
    text: str
    type: str = Field(default="paragraph", description="'heading', 'paragraph', 'table_row'")


class PdfPage(BaseModel):
    """An extracted page from an uploaded PDF."""
    page_number: int
    text: str
    blocks: List[PdfBlock] = Field(default_factory=list)


class ExtractedPdf(BaseModel):
    """Full structured extraction from an uploaded PDF document."""
    file_name: str
    page_count: int
    pages: List[PdfPage] = Field(default_factory=list)


class CopilotSession(BaseModel):
    """A full interactive audit chat session with active grounded documents."""
    session_id: str
    title: str
    created_at: str
    files: List[Dict[str, Any]] = Field(default_factory=list)
    messages: List[ChatMessage] = Field(default_factory=list)
    active_rows: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Structured tabular rows for the split-screen document viewer"
    )
    pdf_doc: Optional[ExtractedPdf] = Field(
        default=None,
        description="Extracted PDF document if a PDF was uploaded"
    )
    pdf_url: Optional[str] = Field(
        default=None,
        description="URL to the raw visual PDF document for iframe rendering"
    )
    summary: Optional[Dict[str, Any]] = Field(default=None)


class ChatRequest(BaseModel):
    """Request payload for Copilot chat endpoint."""
    session_id: Optional[str] = None
    message: str
    session_type: Optional[str] = Field(default="gst", description="'gst', 'jet', or 'analytics'")


class ChatResponse(BaseModel):
    """Response payload with grounded answer and interactive citations."""
    session_id: str
    message: ChatMessage
    active_rows: Optional[List[Dict[str, Any]]] = None
    pdf_doc: Optional[ExtractedPdf] = None

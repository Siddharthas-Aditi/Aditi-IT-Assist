"""Ingestion services package.

Exposes the public API for document ingestion:
- ``extract_text``  — raw text from DOCX / PDF / PPTX / TXT / MD
- ``parse_document`` — structural parsing → list of CandidatePayload
- ``run_pipeline``  — end-to-end orchestrator
"""

from app.services.ingestion.extractor import ExtractionResult, extract_text
from app.services.ingestion.parser import CandidatePayload, parse_document
from app.services.ingestion.pipeline import run_pipeline

__all__ = [
    "ExtractionResult",
    "extract_text",
    "CandidatePayload",
    "parse_document",
    "run_pipeline",
]

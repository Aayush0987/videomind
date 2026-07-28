"""Deterministic verification agent: validates and repairs SegmentationOutput
against 12 rules (§11).

Must not import anything from `core/llm.py` — verification is rule-based,
not LLM-based, by design.
"""

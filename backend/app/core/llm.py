"""LLM provider abstraction (§7). The only module in the repo allowed to import litellm.

Exposes exactly two async functions, `generate` and `generate_structured`,
plus the `LLMConfig` model. Provider selection, retries, and structured
output repair are handled here.
"""

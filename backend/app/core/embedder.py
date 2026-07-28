"""Embedding backend abstraction (§12.2). The only module allowed to talk to an embedding backend.

Defines the `Embedder` protocol plus `GeminiEmbedder` (default, everywhere)
and `SentenceTransformerEmbedder` (offline-development escape hatch, the
`[local]` extra only). Query and passage embedding are separate methods
because the model is asymmetric.
"""

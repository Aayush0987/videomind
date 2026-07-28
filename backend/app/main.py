"""FastAPI application entrypoint: app instance, routers, and lifespan.

The lifespan handler performs schema init, embedder warm-up, and stale-job
cleanup on startup (§8.2), and configures CORS and the per-IP analyze rate
limiter (§14, §15).
"""

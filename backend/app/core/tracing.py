"""MLflow run/span helpers: `@traced(node_name)` decorator and `run_context` (§17).

A no-op when `MLFLOW_ENABLED=false`, so tests and the deployed instance can
run without an MLflow backend.
"""

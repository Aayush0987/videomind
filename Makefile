.PHONY: dev test lint mlflow

dev:
	cd backend && uvicorn app.main:app --reload --port 8000

test:
	pytest backend/tests -q

lint:
	cd backend && ruff check . && ruff format --check .

mlflow:
	cd backend && mlflow ui --backend-store-uri file:./data/mlruns

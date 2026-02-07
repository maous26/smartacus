web: uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: python -m src.scheduler.scheduler --daemon

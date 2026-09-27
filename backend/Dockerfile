FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Run migrations + seed demo accounts (idempotent), then start the API.
# Railway injects PORT; fall back to 8000 elsewhere (docker-compose, local).
CMD ["sh", "-c", "python -m app.bootstrap && alembic upgrade head && python -m seed.run && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

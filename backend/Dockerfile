FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY data/ /app/data/
RUN useradd --create-home bondmind && chown -R bondmind /app
USER bondmind
ENV BONDMIND_SEED_DIR=/app/data/seed
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed.load && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

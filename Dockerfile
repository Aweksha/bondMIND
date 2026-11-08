# Production image for the public website: one container serving the Angular app and the API.
# The demo database (SQLite) is built from the committed seed snapshots at image build time,
# so nothing needs a paid/expiring database and every deploy starts from known data.

FROM node:22-alpine AS web
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npx ng build --configuration production

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BONDMIND_ENV=production \
    BONDMIND_DATABASE_URL=sqlite+pysqlite:////app/db/bondmind.db \
    BONDMIND_SEED_DIR=/app/data/seed \
    BONDMIND_STATIC_DIR=/app/static \
    BONDMIND_RATE_LIMIT_PER_MINUTE=300
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY data/ /app/data/
COPY --from=web /app/dist/frontend/browser /app/static
RUN useradd --create-home bondmind && mkdir -p /app/db \
    && alembic upgrade head && python -m app.seed.load \
    && chown -R bondmind /app/db
USER bondmind
EXPOSE 8000
# Render (and most hosts) provide $PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]

# ---- 1. Build the React frontend ----
FROM node:22-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime serving API + built UI ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/frontend-dist

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /src/dist /app/frontend-dist

# Database + generated secret key live here; mount a volume to persist them.
RUN useradd --create-home --uid 1000 dose && mkdir -p /app/backend/data && chown -R dose /app/backend/data
USER dose
VOLUME ["/app/backend/data"]

EXPOSE 5733
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5733/health')" || exit 1

# One worker process: background work (collecting pictures) lives in-process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5733", "--proxy-headers"]

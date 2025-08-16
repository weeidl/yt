FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Python deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY . .

ENV CACHE_DIR=/tmp/yt_cache
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
# Railway sets $PORT
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop", "--http", "httptools"]

FROM python:3.11-slim

# ffmpeg for muxing/cutting
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install deps first (better Docker cache)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# app
COPY app.py /app/app.py

# default port (platforms often inject $PORT)
ENV PORT=8000
EXPOSE 8000

# run
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]

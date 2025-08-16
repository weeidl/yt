FROM python:3.11-slim

# ffmpeg for processing
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

ENV PORT=8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

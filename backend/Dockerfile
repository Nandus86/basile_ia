FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run with uvicorn - multiple workers for concurrent connections
# --workers 4: spawn 4 worker processes (adjust based on CPU cores)
# --limit-concurrency 100: max concurrent connections per worker
# --timeout-keep-alive 30: keep-alive timeout for idle connections
# --reload is intentionally removed for production stability
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--limit-concurrency", "100", "--timeout-keep-alive", "30"]

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg and compilation
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies first
COPY pyproject.toml .
COPY src/ src/

# Install the app (normal install, not editable for Docker)
RUN pip install --no-cache-dir .

# Copy remaining code (like migrations)
COPY . .

# Run the FastAPI server
CMD ["uvicorn", "ubid_fabric.app:app", "--host", "0.0.0.0", "--port", "8000"]

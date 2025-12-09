FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if needed (e.g., for pandas/numpy potentially, though wheels are preferred)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev \
#     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the internal port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

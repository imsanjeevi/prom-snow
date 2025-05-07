FROM python:3.13-alpine

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies and CA certs
RUN apk update && apk add --no-cache \
    ca-certificates \
    curl \
    vim \
    libffi-dev \
    gcc \
    musl-dev \
    python3-dev \
    && update-ca-certificates

# Copy Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app code
COPY . /app
WORKDIR /app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

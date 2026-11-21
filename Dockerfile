# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Install uv for reproducible, lockfile-based dependency installs
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /bin/

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    UV_LINK_MODE=copy

# Set work directory
WORKDIR /app

# Install only necessary system dependencies for now
# libpq-dev is required for PostgreSQL
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from the uv lockfile (cached separately from source)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy project files
COPY . /app/

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose the port (Render defaults to 10000)
EXPOSE 10000

# Start Gunicorn (Using $PORT from Render)
CMD gunicorn movies.wsgi:application --bind 0.0.0.0:$PORT

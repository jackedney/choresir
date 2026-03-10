FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Install venv outside /app so volume mount doesn't conflict
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Copy dependency files and README
COPY pyproject.toml uv.lock README.md ./

# Install dependencies only (project not yet available)
RUN uv sync --frozen --no-dev --no-install-project

# Copy the rest of the application
COPY . .

# Install the project package
RUN uv sync --frozen --no-dev --no-editable

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose the application port
EXPOSE 8001

# Start the application
CMD ["uvicorn", "choresir.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001", "--log-level", "warning"]

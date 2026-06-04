FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir fastmcp httpx python-dotenv

# Copy source
COPY src/ src/
COPY pyproject.toml .

# Run MCP server in stdio mode
ENTRYPOINT ["python3", "-m", "src.main"]

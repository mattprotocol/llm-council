FROM python:3.12-slim

WORKDIR /app

# Install git for cloning graphiti
RUN apt-get update && apt-get install -y git patch && rm -rf /var/lib/apt/lists/*

# Clone graphiti
RUN git clone --depth 1 https://github.com/getzep/graphiti.git /app/graphiti

WORKDIR /app/graphiti/mcp_server

# Copy patches and custom client
COPY factories.patch /app/patches/
COPY schema.patch /app/patches/
COPY lmstudio_client.py /app/graphiti/mcp_server/src/

# Apply patches (allow failures for partial matches)
RUN cd /app/graphiti && \
    patch -p1 < /app/patches/factories.patch 2>/dev/null || echo "factories.patch applied with warnings" && \
    patch -p1 < /app/patches/schema.patch 2>/dev/null || echo "schema.patch applied with warnings"

# Install dependencies
RUN pip install --no-cache-dir uv && \
    uv pip install --system -e . && \
    uv pip install --system graphiti-core[falkordb]

# Copy custom config
COPY config.yaml /app/graphiti/mcp_server/config/config.yaml

EXPOSE 8000

# Run the server
CMD ["python", "-m", "main"]

#!/bin/bash

# Graphiti Custom MCP Server - Start script
# Builds and runs the custom Graphiti MCP server with LM Studio support

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER_NAME="llm-council-mcp"
IMAGE_NAME="graphiti-custom"

echo "🚀 Starting Graphiti Custom MCP Server..."
echo ""

cd "$SCRIPT_DIR"

# Stop and remove existing container if running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "⚠️  Stopping existing container: $CONTAINER_NAME"
    docker stop "$CONTAINER_NAME" 2>/dev/null
    docker rm "$CONTAINER_NAME" 2>/dev/null
fi

# Build the image if it doesn't exist or if files changed
echo "📦 Building Docker image: $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

if [ $? -ne 0 ]; then
    echo "❌ Failed to build Docker image"
    exit 1
fi

# Run the container
echo "🐳 Starting container: $CONTAINER_NAME..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -p 8000:8000 \
    -e OPENAI_API_KEY="${OPENAI_API_KEY:-sk-dummy}" \
    --restart unless-stopped \
    "$IMAGE_NAME"

if [ $? -ne 0 ]; then
    echo "❌ Failed to start container"
    exit 1
fi

# Wait for server to be ready
echo "⏳ Waiting for server to start..."
sleep 5

# Check if container is running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo ""
    echo "✅ Graphiti MCP Server is running!"
    echo "   Container: $CONTAINER_NAME"
    echo "   MCP Endpoint: http://localhost:8000/mcp/"
    echo "   LLM: qwen2.5-14b-instruct @ http://192.168.1.111:11434/v1"
    echo "   Database: FalkorDB @ redis://192.168.1.111:6379"
    echo ""
    echo "📋 View logs: docker logs -f $CONTAINER_NAME"
    echo "🛑 Stop: docker stop $CONTAINER_NAME"
else
    echo "❌ Container failed to start. Check logs:"
    docker logs "$CONTAINER_NAME"
    exit 1
fi

#!/bin/bash

# Sales Intelligence Platform - Stop Script

echo "🛑 Stopping Sales Intelligence Platform..."

# Stop all services
docker-compose down

echo "🧹 Cleaning up..."

# Optional: Remove volumes (uncomment if you want to reset data)
# docker-compose down -v

echo ""
echo "✅ Sales Intelligence Platform stopped."
echo ""
echo "📋 To completely reset (delete all data):"
echo "   docker-compose down -v"
echo ""
echo "🚀 To start again:"
echo "   ./start.sh"
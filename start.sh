#!/bin/bash

# Sales Intelligence Platform - Start Script

echo "🚀 Starting Sales Intelligence Platform..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check for environment file
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Created .env file. Please add your COMPANIES_HOUSE_API_KEY and run again."
        exit 1
    else
        echo "❌ No .env.example file found. Please create .env file manually."
        exit 1
    fi
fi

# Check for Companies House API key
if ! grep -q "COMPANIES_HOUSE_API_KEY=" .env || grep -q "COMPANIES_HOUSE_API_KEY=$" .env; then
    echo "⚠️  No Companies House API key found in .env file."
    echo "   Get your free key from: https://developer.company-information.service.gov.uk/"
    echo "   Add it to .env file as: COMPANIES_HOUSE_API_KEY=your_key_here"
    exit 1
fi

echo "📦 Building and starting services..."

# Start all services
docker-compose up -d --build

echo "⏳ Waiting for services to be ready..."

# Wait for API to be healthy
for i in {1..30}; do
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ API is healthy"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ API failed to start. Check logs with: docker-compose logs api"
        exit 1
    fi
    sleep 2
done

# Wait for frontend to be ready
for i in {1..30}; do
    if curl -f http://localhost:3000 > /dev/null 2>&1; then
        echo "✅ Frontend is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Frontend failed to start. Check logs with: docker-compose logs frontend"
        exit 1
    fi
    sleep 2
done

echo ""
echo "🎉 Sales Intelligence Platform is ready!"
echo ""
echo "🔗 Access your platform:"
echo "   • Frontend:    http://localhost:3000"
echo "   • API:         http://localhost:8000"
echo "   • API Docs:    http://localhost:8000/docs"
echo ""
echo "🧪 Test the platform:"
echo "   curl http://localhost:8000/health"
echo ""
echo "📊 Try the demo:"
echo '   curl -X POST http://localhost:8000/demo/analyze -H "Content-Type: application/json" -d '"'"'{"company_name": "TechCorp Ltd"}'"'"
echo ""
echo "📚 View logs:"
echo "   docker-compose logs -f api"
echo ""
echo "🛑 Stop the platform:"
echo "   docker-compose down"
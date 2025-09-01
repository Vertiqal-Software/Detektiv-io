# frontend/setup.sh

#!/bin/bash

# detecktiv.io Frontend Setup Script
# This script will set up your frontend development environment

echo "🚀 Setting up detecktiv.io Frontend..."
echo "=================================="

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi

# Check Node.js version
NODE_VERSION=$(node -v | cut -c 2-3)
if [ "$NODE_VERSION" -lt "18" ]; then
    echo "❌ Node.js version 18+ required. Current version: $(node -v)"
    echo "Please update Node.js from https://nodejs.org/"
    exit 1
fi

echo "✅ Node.js $(node -v) detected"

# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not available. Please ensure npm is installed with Node.js"
    exit 1
fi

echo "✅ npm $(npm -v) detected"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
npm install

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo "✅ Dependencies installed successfully"

# Set up environment file
echo ""
echo "⚙️  Setting up environment..."

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✅ Environment file created (.env)"
else
    echo "✅ Environment file already exists"
fi

# Check if backend is running
echo ""
echo "🔍 Checking backend connection..."

if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ Backend is running at http://localhost:8000"
else
    echo "⚠️  Backend is not running at http://localhost:8000"
    echo "   Please start your backend with: docker compose up -d"
fi

echo ""
echo "🎉 Setup complete!"
echo "=================================="
echo ""
echo "To start the development server:"
echo "  npm run dev"
echo ""
echo "The frontend will be available at:"
echo "  http://localhost:5173"
echo ""
echo "Make sure your backend is running at:"
echo "  http://localhost:8000"
echo ""
echo "Happy coding! 🚀"
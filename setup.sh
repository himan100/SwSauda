#!/bin/bash

# SwSauda Quick Setup Script
# This script automates the setup process for the SwSauda project

set -e  # Exit on error

echo "=========================================="
echo "   SwSauda - Quick Setup Script"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}➜${NC} $1"
}

# Check if Docker is installed
print_info "Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    echo "Visit: https://docs.docker.com/get-docker/"
    exit 1
fi
print_success "Docker is installed"

# Check for docker compose (new) or docker-compose (legacy)
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
    print_success "Docker Compose is installed (v2)"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
    print_success "Docker Compose is installed (v1)"
else
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    echo "Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

# Check Python version
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
print_success "Python $PYTHON_VERSION is installed"

# Create .env file if it doesn't exist
print_info "Setting up environment configuration..."
if [ ! -f .env ]; then
    cp sample.env .env
    print_success "Created .env file from sample.env"
else
    print_info ".env file already exists, skipping..."
fi

# Create Backups directory if it doesn't exist
if [ ! -d "Backups" ]; then
    mkdir -p Backups
    print_success "Created Backups directory"
fi

# Start Docker services
print_info "Starting Docker services (MongoDB & Redis)..."
$DOCKER_COMPOSE up -d

# Wait for services to be healthy
print_info "Waiting for services to be ready..."
sleep 5

# Check if services are running
if $DOCKER_COMPOSE ps | grep -q "swsauda_mongodb.*Up"; then
    print_success "MongoDB is running on port 27017"
else
    print_error "MongoDB failed to start"
    $DOCKER_COMPOSE logs mongodb
    exit 1
fi

if $DOCKER_COMPOSE ps | grep -q "swsauda_redis.*Up"; then
    print_success "Redis is running on port 6379"
else
    print_error "Redis failed to start"
    $DOCKER_COMPOSE logs redis
    exit 1
fi

# Install Python dependencies
# Prefer venv if present; otherwise use system pip
if [ -d "venv" ] && [ -x "venv/bin/python" ]; then
    print_info "Detected Python virtual env at ./venv"
    print_info "Skipping dependency installation (as requested)"
else
    print_info "Installing Python dependencies..."
    if command -v pip3 &> /dev/null; then
        pip3 install -r requirements.txt --quiet
    elif command -v pip &> /dev/null; then
        pip install -r requirements.txt --quiet
    else
        print_error "pip is not installed. Please install pip first."
        exit 1
    fi
    print_success "Python dependencies installed"
fi

echo ""
echo "=========================================="
echo "   Setup Complete! 🎉"
echo "=========================================="
echo ""
echo "Services running:"
echo "  • MongoDB:          http://localhost:27017"
echo "  • Redis:            http://localhost:6379"
echo "  • MongoDB Express:  http://localhost:8081 (admin/admin123)"
echo "  • Redis Commander:  http://localhost:8082"
echo ""
echo "Default admin credentials:"
echo "  • Email:    admin@swsauda.com"
echo "  • Password: P@ssw0rd"
echo ""
echo "To start the application:"
echo "  python3 main.py"
echo ""
echo "To view service logs:"
echo "  $DOCKER_COMPOSE logs -f"
echo ""
echo "To stop services:"
echo "  $DOCKER_COMPOSE down"
echo ""
echo "For more details, see:"
echo "  • README.md"
echo "  • DOCKER_SETUP.md"
echo ""

#!/bin/bash
# SwSauda - Secret Key Generator Shell Script
# Wrapper script to generate SECRET_KEY for the application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}$1${NC}"
}

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed or not in PATH"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

print_header "🔐 SwSauda Secret Key Generator"
echo "========================================"

# Check if .env file exists and backup if needed
if [ -f ".env" ]; then
    print_warning ".env file already exists"
    read -p "Do you want to backup the existing .env file? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        print_status "Backup created: .env.backup.$(date +%Y%m%d_%H%M%S)"
    fi
fi

# Run the Python script
print_status "Generating secure secret key..."
python3 "$SCRIPT_DIR/generate_secret_key_simple.py"

if [ $? -eq 0 ]; then
    print_status "Secret key generation completed successfully!"
    print_warning "Make sure to keep your .env file secure and never commit it to version control."
else
    print_error "Failed to generate secret key"
    exit 1
fi

echo
print_header "Next steps:"
echo "1. Review the generated .env file"
echo "2. Start MongoDB: mongod"
echo "3. Run the application: python run.py"
echo "4. Access the app at: http://localhost:8000" 
#!/usr/bin/env python3
"""
SwSauda - FastAPI Business Management Platform
Startup script for easy application launching
"""

import uvicorn
import os
import sys

def main():
    """Main function to start the FastAPI application"""
    
    # Check if MongoDB is running (basic check)
    try:
        import pymongo
        client = pymongo.MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=5000)
        client.server_info()  # Will throw an exception if MongoDB is not running
        print("✅ MongoDB connection successful")
    except Exception as e:
        print("❌ MongoDB connection failed. Please make sure MongoDB is running.")
        print(f"Error: {e}")
        print("\nTo start MongoDB:")
        print("1. Install MongoDB if not already installed")
        print("2. Start MongoDB service: sudo systemctl start mongod")
        print("3. Or run: mongod")
        sys.exit(1)
    
    # Configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("RELOAD", "true").lower() == "true"
    
    print(f"🚀 Starting SwSauda on http://{host}:{port}")
    print(f"📚 API Documentation: http://{host}:{port}/docs")
    print(f"🔧 ReDoc Documentation: http://{host}:{port}/redoc")
    print(f"🔄 Auto-reload: {reload}")
    print("\n" + "="*50)
    
    # Start the application
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )

if __name__ == "__main__":
    main() 
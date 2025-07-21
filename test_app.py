#!/usr/bin/env python3
"""
Simple test script to verify SwSauda application setup
"""

import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_database_connection():
    """Test database connection"""
    try:
        from database import connect_to_mongo, close_mongo_connection
        await connect_to_mongo()
        print("✅ Database connection test passed")
        await close_mongo_connection()
        return True
    except Exception as e:
        print(f"❌ Database connection test failed: {e}")
        return False

async def test_super_admin_creation():
    """Test super admin creation"""
    try:
        from database import connect_to_mongo, close_mongo_connection
        from crud import create_super_admin
        
        await connect_to_mongo()
        await create_super_admin()
        print("✅ Super admin creation test passed")
        await close_mongo_connection()
        return True
    except Exception as e:
        print(f"❌ Super admin creation test failed: {e}")
        return False

def test_imports():
    """Test all imports"""
    try:
        import fastapi
        import motor
        import pymongo
        import pydantic
        import jose
        import passlib
        import jinja2
        print("✅ All required packages imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import test failed: {e}")
        return False

def test_configuration():
    """Test configuration loading"""
    try:
        from config import settings
        print(f"✅ Configuration loaded successfully")
        print(f"   Database: {settings.database_name}")
        print(f"   Algorithm: {settings.algorithm}")
        print(f"   Token expiry: {settings.access_token_expire_minutes} minutes")
        return True
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🧪 Running SwSauda application tests...")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Configuration Test", test_configuration),
        ("Database Connection Test", test_database_connection),
        ("Super Admin Creation Test", test_super_admin_creation),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}...")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! SwSauda is ready to run.")
        print("\nTo start the application:")
        print("  python run.py")
        print("  or")
        print("  uvicorn main:app --reload")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 
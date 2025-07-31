#!/usr/bin/env python3
"""
Test script to verify MongoDB views creation functionality
"""
import os
import sys
import asyncio
import subprocess

# Add the parent directory to the path to import from main.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_views_creation():
    """Test the MongoDB views creation function"""
    
    # Import the function we want to test
    try:
        from main import execute_mongo_views_script
    except ImportError as e:
        print(f"Error importing function: {e}")
        print("Make sure you're running this from the SwSauda directory")
        return False
    
    # Test database name (replace with actual test database)
    test_database = "test_database"
    
    print(f"Testing MongoDB views creation for database: {test_database}")
    print("=" * 50)
    
    # Check if MongoDB commands are available
    print("Checking MongoDB command availability...")
    mongo_commands = ["mongosh", "mongo"]
    available_commands = []
    
    for cmd in mongo_commands:
        try:
            result = subprocess.run([cmd, "--version"], 
                                   capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                available_commands.append(cmd)
                print(f"✓ {cmd} is available")
            else:
                print(f"✗ {cmd} failed with return code {result.returncode}")
        except FileNotFoundError:
            print(f"✗ {cmd} not found")
        except subprocess.TimeoutExpired:
            print(f"✗ {cmd} timed out")
        except Exception as e:
            print(f"✗ {cmd} error: {e}")
    
    if not available_commands:
        print("\n❌ No MongoDB commands available. Please install mongosh or mongo.")
        print("Installation instructions:")
        print("- Ubuntu/Debian: sudo apt-get install mongodb-mongosh")
        print("- Or download from: https://www.mongodb.com/try/download/shell")
        return False
    
    print(f"\n✓ Available MongoDB commands: {', '.join(available_commands)}")
    
    # Test the views creation function
    print(f"\nTesting views creation function...")
    try:
        success = await execute_mongo_views_script(test_database)
        if success:
            print("✓ Views creation function executed successfully")
            print("Note: This doesn't mean the database exists or views were actually created,")
            print("      just that the command executed without errors.")
        else:
            print("✗ Views creation function failed")
            print("This could be because:")
            print("- The test database doesn't exist")
            print("- MongoDB server is not running")
            print("- Required collections don't exist in the database")
    except Exception as e:
        print(f"✗ Exception during views creation: {e}")
        return False
    
    return success

async def test_mongodb_connection():
    """Test MongoDB connection"""
    print("\nTesting MongoDB connection...")
    
    mongo_commands = ["mongosh", "mongo"]
    
    for cmd in mongo_commands:
        try:
            # Test connection to MongoDB
            if cmd == "mongosh":
                test_cmd = [cmd, "--quiet", "--eval", "db.adminCommand('ismaster').ismaster"]
            else:
                test_cmd = [cmd, "--quiet", "--eval", "db.adminCommand('ismaster').ismaster"]
            
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print(f"✓ MongoDB connection successful using {cmd}")
                if "true" in result.stdout:
                    print("✓ MongoDB server is responding")
                return True
            else:
                print(f"✗ MongoDB connection failed using {cmd}")
                if result.stderr:
                    print(f"Error: {result.stderr}")
                
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            print(f"✗ MongoDB connection timed out using {cmd}")
        except Exception as e:
            print(f"✗ MongoDB connection error using {cmd}: {e}")
    
    print("❌ Could not connect to MongoDB")
    print("Make sure MongoDB server is running:")
    print("- Ubuntu/Debian: sudo systemctl start mongod")
    print("- macOS: brew services start mongodb/brew/mongodb-community")
    print("- Windows: net start MongoDB")
    return False

async def list_databases():
    """List available databases"""
    print("\nListing available databases...")
    
    mongo_commands = ["mongosh", "mongo"]
    
    for cmd in mongo_commands:
        try:
            if cmd == "mongosh":
                test_cmd = [cmd, "--quiet", "--eval", "db.adminCommand('listDatabases').databases.forEach(db => print(db.name))"]
            else:
                test_cmd = [cmd, "--quiet", "--eval", "db.adminCommand('listDatabases').databases.forEach(function(db) { print(db.name); })"]
            
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                databases = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                print(f"✓ Available databases: {', '.join(databases)}")
                return databases
            else:
                print(f"✗ Failed to list databases using {cmd}")
                
        except Exception as e:
            print(f"✗ Error listing databases using {cmd}: {e}")
    
    return []

def main():
    """Main test function"""
    print("MongoDB Views Integration Test")
    print("=" * 40)
    
    # Run async tests
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Test MongoDB connection first
        if not loop.run_until_complete(test_mongodb_connection()):
            print("\n❌ MongoDB connection failed. Cannot proceed with views test.")
            return False
        
        # List available databases
        databases = loop.run_until_complete(list_databases())
        
        # Test views creation
        success = loop.run_until_complete(test_views_creation())
        
        print("\n" + "=" * 50)
        if success:
            print("✅ Test completed successfully!")
            print("\nNext steps:")
            print("1. Make sure you have actual databases with the required collections")
            print("2. Test with a real database name from the list above")
            print("3. Start the FastAPI application and test the web interface")
        else:
            print("❌ Test failed!")
            print("\nTroubleshooting:")
            print("1. Ensure MongoDB is running")
            print("2. Check that mongosh or mongo is installed")
            print("3. Verify database permissions")
        
        return success
        
    finally:
        loop.close()

if __name__ == "__main__":
    main()

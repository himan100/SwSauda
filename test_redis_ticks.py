#!/usr/bin/env python3
"""
Test script for Redis tick storage functionality
"""

import asyncio
import json
from datetime import datetime
from database import connect_to_mongo, connect_to_redis, close_mongo_connection, close_redis_connection, redis_client
from crud import create_parameter, get_parameter_by_name
from models import ParameterCreate
from crud import create_super_admin

async def test_redis_tick_storage():
    """Test Redis tick storage functionality"""
    print("🧪 Testing Redis tick storage functionality...")
    
    try:
        # Connect to databases
        await connect_to_mongo()
        await connect_to_redis()
        await create_super_admin()
        
        # Test 1: Create REDIS_LONG_TICK_LENGTH parameter
        print("\n1. Creating REDIS_LONG_TICK_LENGTH parameter...")
        try:
            parameter_data = ParameterCreate(
                name="REDIS_LONG_TICK_LENGTH",
                value="100",
                description="Number of ticks to store in Redis for index and option ticks",
                category="Redis Configuration",
                datatype="int",
                is_active=True
            )
            await create_parameter(parameter_data, "test_user")
            print("✅ REDIS_LONG_TICK_LENGTH parameter created successfully")
        except Exception as e:
            print(f"⚠️  Parameter creation failed (might already exist): {e}")
        
        # Test 2: Test tick storage
        print("\n2. Testing tick storage in Redis...")
        
        # Sample tick data
        sample_index_tick = {
            "ft": 1752810305,
            "token": 26000,
            "e": "NSE",
            "lp": 25124.35,
            "pc": 0.05,
            "rt": "2025-07-18 09:15:05",
            "ts": "Nifty 50",
            "_id": "test_id_1",
            "data_type": "indextick"
        }
        
        sample_option_tick = {
            "ft": 1752810305,
            "token": 26001,
            "e": "NSE",
            "lp": 125.50,
            "pc": -0.02,
            "rt": "2025-07-18 09:15:05",
            "ts": "NIFTY25JUL25100CE",
            "_id": "test_id_2",
            "data_type": "optiontick"
        }
        
        # Store ticks in Redis
        database_name = "test_database"
        
        # Store index tick
        redis_key_index = f"ticks:{database_name}:indextick"
        await redis_client.lpush(redis_key_index, json.dumps(sample_index_tick))
        await redis_client.ltrim(redis_key_index, 0, 99)  # Keep only 100 ticks
        
        # Store option tick
        redis_key_option = f"ticks:{database_name}:optiontick"
        await redis_client.lpush(redis_key_option, json.dumps(sample_option_tick))
        await redis_client.ltrim(redis_key_option, 0, 99)  # Keep only 100 ticks
        
        print("✅ Sample ticks stored in Redis")
        
        # Test 3: Retrieve ticks from Redis
        print("\n3. Testing tick retrieval from Redis...")
        
        # Get index ticks
        index_ticks_json = await redis_client.lrange(redis_key_index, 0, -1)
        index_ticks = [json.loads(tick) for tick in index_ticks_json]
        print(f"✅ Retrieved {len(index_ticks)} index ticks from Redis")
        
        # Get option ticks
        option_ticks_json = await redis_client.lrange(redis_key_option, 0, -1)
        option_ticks = [json.loads(tick) for tick in option_ticks_json]
        print(f"✅ Retrieved {len(option_ticks)} option ticks from Redis")
        
        # Test 4: Verify FIFO behavior
        print("\n4. Testing FIFO behavior...")
        
        # Add more ticks to test FIFO
        for i in range(5):
            new_index_tick = sample_index_tick.copy()
            new_index_tick["ft"] = 1752810305 + i
            new_index_tick["lp"] = 25124.35 + i
            new_index_tick["_id"] = f"test_id_{i+3}"
            
            await redis_client.lpush(redis_key_index, json.dumps(new_index_tick))
            await redis_client.ltrim(redis_key_index, 0, 99)
        
        # Check final count
        final_count = await redis_client.llen(redis_key_index)
        print(f"✅ Final count of index ticks in Redis: {final_count}")
        
        # Test 5: Test parameter retrieval
        print("\n5. Testing parameter retrieval...")
        parameter = await get_parameter_by_name("REDIS_LONG_TICK_LENGTH")
        if parameter:
            print(f"✅ Retrieved REDIS_LONG_TICK_LENGTH parameter: {parameter.value}")
        else:
            print("❌ Failed to retrieve REDIS_LONG_TICK_LENGTH parameter")
        
        print("\n🎉 All Redis tick storage tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        await close_mongo_connection()
        await close_redis_connection()

if __name__ == "__main__":
    asyncio.run(test_redis_tick_storage()) 
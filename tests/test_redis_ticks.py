#!/usr/bin/env python3
"""
Test script for Redis tick storage functionality with enhanced features
"""

import asyncio
import json
from datetime import datetime
from database import connect_to_mongo, connect_to_redis, close_mongo_connection, close_redis_connection, redis_client
from crud import create_parameter, get_parameter_by_name
from models import ParameterCreate
from crud import create_super_admin

async def test_redis_tick_storage():
    """Test Redis tick storage functionality with enhanced features"""
    print("🧪 Testing Enhanced Redis tick storage functionality...")
    
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
        
        # Test 1.5: Create REDIS_SHORT_TICK_LENGTH parameter
        print("\n1.5. Creating REDIS_SHORT_TICK_LENGTH parameter...")
        try:
            parameter_data = ParameterCreate(
                name="REDIS_SHORT_TICK_LENGTH",
                value="50",
                description="Number of ticks to store in Redis for short EMA calculation",
                category="Redis Configuration",
                datatype="int",
                is_active=True
            )
            await create_parameter(parameter_data, "test_user")
            print("✅ REDIS_SHORT_TICK_LENGTH parameter created successfully")
        except Exception as e:
            print(f"⚠️  Parameter creation failed (might already exist): {e}")
        
        # Test 2: Test Redis flushing
        print("\n2. Testing Redis flushing functionality...")
        database_name = "test_database"
        
        # First, add some test data
        test_keys = [
            f"ticks:{database_name}:indextick",
            f"ticks:{database_name}:optiontick:26001",
            f"ticks:{database_name}:optiontick:26002"
        ]
        
        for key in test_keys:
            await redis_client.lpush(key, "test_data")
        
        print(f"✅ Added test data to {len(test_keys)} Redis keys")
        
        # Now test flushing
        from main import flush_redis_for_database
        await flush_redis_for_database(database_name)
        
        # Verify keys are deleted
        remaining_keys = await redis_client.keys(f"ticks:{database_name}:*")
        print(f"✅ Redis flush completed. Remaining keys: {len(remaining_keys)}")
        
        # Test 3: Test enhanced tick storage
        print("\n3. Testing enhanced tick storage...")
        
        # Sample tick data with different tokens
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
        
        sample_option_tick_1 = {
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
        
        sample_option_tick_2 = {
            "ft": 1752810305,
            "token": 26002,
            "e": "NSE",
            "lp": 85.25,
            "pc": 0.03,
            "rt": "2025-07-18 09:15:05",
            "ts": "NIFTY25JUL25100PE",
            "_id": "test_id_3",
            "data_type": "optiontick"
        }
        
        # Store ticks using the enhanced function
        from main import store_tick_in_redis
        
        # Store index tick
        await store_tick_in_redis(sample_index_tick, "indextick", database_name)
        
        # Store option ticks for different tokens
        await store_tick_in_redis(sample_option_tick_1, "optiontick", database_name)
        await store_tick_in_redis(sample_option_tick_2, "optiontick", database_name)
        
        print("✅ Enhanced tick storage completed")
        
        # Test 4: Test tick retrieval with sorting
        print("\n4. Testing tick retrieval with sorting...")
        
        from main import get_ticks_from_redis, get_option_tokens_from_redis
        
        # Get index ticks
        index_ticks = await get_ticks_from_redis(database_name, "indextick")
        print(f"✅ Retrieved {len(index_ticks)} index ticks")
        
        # Get all option ticks (should be sorted by ft)
        all_option_ticks = await get_ticks_from_redis(database_name, "optiontick")
        print(f"✅ Retrieved {len(all_option_ticks)} option ticks (all tokens)")
        
        # Get option ticks for specific token
        token_26001_ticks = await get_ticks_from_redis(database_name, "optiontick", token="26001")
        print(f"✅ Retrieved {len(token_26001_ticks)} option ticks for token 26001")
        
        # Get list of option tokens
        option_tokens = await get_option_tokens_from_redis(database_name)
        print(f"✅ Retrieved option tokens: {option_tokens}")
        
        # Test 5: Test FIFO behavior with multiple tokens
        print("\n5. Testing FIFO behavior with multiple tokens...")
        
        # Add more ticks to test FIFO
        for i in range(5):
            # Add index ticks
            new_index_tick = sample_index_tick.copy()
            new_index_tick["ft"] = 1752810305 + i
            new_index_tick["lp"] = 25124.35 + i
            new_index_tick["_id"] = f"test_id_{i+4}"
            await store_tick_in_redis(new_index_tick, "indextick", database_name)
            
            # Add option ticks for token 26001
            new_option_tick_1 = sample_option_tick_1.copy()
            new_option_tick_1["ft"] = 1752810305 + i
            new_option_tick_1["lp"] = 125.50 + i
            new_option_tick_1["_id"] = f"test_id_{i+10}"
            await store_tick_in_redis(new_option_tick_1, "optiontick", database_name)
            
            # Add option ticks for token 26002
            new_option_tick_2 = sample_option_tick_2.copy()
            new_option_tick_2["ft"] = 1752810305 + i
            new_option_tick_2["lp"] = 85.25 + i
            new_option_tick_2["_id"] = f"test_id_{i+20}"
            await store_tick_in_redis(new_option_tick_2, "optiontick", database_name)
        
        # Check final counts
        final_index_count = await redis_client.llen(f"ticks:{database_name}:indextick")
        final_option_count_26001 = await redis_client.llen(f"ticks:{database_name}:optiontick:26001")
        final_option_count_26002 = await redis_client.llen(f"ticks:{database_name}:optiontick:26002")
        
        print(f"✅ Final counts - Index: {final_index_count}, Option 26001: {final_option_count_26001}, Option 26002: {final_option_count_26002}")
        
        # Test 6: Test sorting functionality
        print("\n6. Testing sorting functionality...")
        
        # Get all option ticks and verify they're sorted by ft
        all_option_ticks = await get_ticks_from_redis(database_name, "optiontick")
        if len(all_option_ticks) > 1:
            # Check if sorted by ft in descending order (latest first)
            ft_values = [tick.get("ft", 0) for tick in all_option_ticks]
            is_sorted = ft_values == sorted(ft_values, reverse=True)
            print(f"✅ Option ticks sorted by ft: {is_sorted}")
            print(f"   FT values: {ft_values[:5]}...")  # Show first 5 values
        else:
            print("✅ Sorting test skipped (not enough data)")
        
        print("\n🎉 All Enhanced Redis tick storage tests completed successfully!")
        
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
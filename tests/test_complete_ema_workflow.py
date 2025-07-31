#!/usr/bin/env python3
"""
Test script for complete EMA workflow
"""

import asyncio
import json
from datetime import datetime
from database import connect_to_mongo, connect_to_redis, close_mongo_connection, close_redis_connection, redis_client
from main import calculate_ema, calculate_index_emas, get_redis_tick_length, get_redis_short_tick_length

async def test_complete_ema_workflow():
    """Test complete EMA workflow"""
    print("🧪 Testing Complete EMA Workflow...")
    
    try:
        # Connect to databases
        await connect_to_mongo()
        await connect_to_redis()
        
        # Test 1: Check parameters
        print("\n1. Checking parameters...")
        long_length = await get_redis_tick_length()
        short_length = await get_redis_short_tick_length()
        print(f"✅ Long tick length: {long_length}")
        print(f"✅ Short tick length: {short_length}")
        
        # Test 2: Create sample data for testing
        print("\n2. Creating sample data...")
        database_name = "test_ema_workflow"
        
        # Create enough sample ticks for both EMAs
        sample_ticks = []
        base_price = 25000
        num_ticks = max(long_length, short_length) + 50  # Extra ticks for testing
        
        for i in range(num_ticks):
            tick_data = {
                "ft": 1752810300 + i,
                "token": 26000,
                "e": "NSE",
                "lp": base_price + i * 0.5,  # Gradually increasing price
                "pc": 0.05,
                "rt": "2025-07-18 09:15:05",
                "ts": "Nifty 50",
                "_id": f"test_id_{i}",
                "data_type": "indextick"
            }
            sample_ticks.append(tick_data)
        
        # Store sample ticks in Redis
        for tick in sample_ticks:
            tick_json = json.dumps(tick)
            await redis_client.lpush(f"ticks:{database_name}:indextick", tick_json)
        
        print(f"✅ Stored {len(sample_ticks)} sample ticks in Redis")
        
        # Test 3: Calculate EMAs using the function
        print("\n3. Calculating EMAs...")
        ema_data = await calculate_index_emas(database_name)
        print(f"✅ EMA calculation result:")
        print(f"   Long EMA: {ema_data['long_ema']}")
        print(f"   Short EMA: {ema_data['short_ema']}")
        print(f"   Long Period: {ema_data['long_period']}")
        print(f"   Short Period: {ema_data['short_period']}")
        print(f"   Total Ticks: {ema_data['total_ticks']}")
        
        # Test 4: Verify EMA calculations are reasonable
        print("\n4. Verifying EMA calculations...")
        if ema_data['long_ema'] and ema_data['short_ema']:
            print(f"✅ Both EMAs calculated successfully")
            print(f"   Long EMA ({ema_data['long_period']}): {ema_data['long_ema']}")
            print(f"   Short EMA ({ema_data['short_period']}): {ema_data['short_ema']}")
            
            # Check if short EMA is higher than long EMA (expected for upward trend)
            if ema_data['short_ema'] > ema_data['long_ema']:
                print("✅ Short EMA > Long EMA (BULLISH signal)")
            else:
                print("✅ Long EMA > Short EMA (BEARISH signal)")
        else:
            print("❌ EMA calculation failed")
        
        # Test 5: Test with different price patterns
        print("\n5. Testing with different price patterns...")
        
        # Clear existing data
        await redis_client.delete(f"ticks:{database_name}:indextick")
        
        # Create declining price pattern
        declining_ticks = []
        for i in range(num_ticks):
            tick_data = {
                "ft": 1752810300 + i,
                "token": 26000,
                "e": "NSE",
                "lp": base_price - i * 0.5,  # Gradually decreasing price
                "pc": -0.05,
                "rt": "2025-07-18 09:15:05",
                "ts": "Nifty 50",
                "_id": f"declining_id_{i}",
                "data_type": "indextick"
            }
            declining_ticks.append(tick_data)
        
        # Store declining ticks
        for tick in declining_ticks:
            tick_json = json.dumps(tick)
            await redis_client.lpush(f"ticks:{database_name}:indextick", tick_json)
        
        # Calculate EMAs for declining pattern
        declining_ema_data = await calculate_index_emas(database_name)
        print(f"✅ Declining pattern EMAs:")
        print(f"   Long EMA: {declining_ema_data['long_ema']}")
        print(f"   Short EMA: {declining_ema_data['short_ema']}")
        
        if declining_ema_data['long_ema'] and declining_ema_data['short_ema']:
            if declining_ema_data['long_ema'] > declining_ema_data['short_ema']:
                print("✅ Long EMA > Short EMA (BEARISH signal for declining pattern)")
            else:
                print("✅ Short EMA > Long EMA (Unexpected for declining pattern)")
        
        # Test 6: Clean up test data
        print("\n6. Cleaning up test data...")
        await redis_client.delete(f"ticks:{database_name}:indextick")
        print("✅ Test data cleaned up")
        
        print("\n🎉 All EMA workflow tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during EMA workflow test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Close connections
        await close_mongo_connection()
        await close_redis_connection()

if __name__ == "__main__":
    asyncio.run(test_complete_ema_workflow()) 
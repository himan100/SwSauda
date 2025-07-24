#!/usr/bin/env python3
"""
Script to simulate order fills for testing the positions system
"""
import asyncio
import random
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

async def simulate_order_fills():
    """Simulate some order fills for testing"""
    # Connect to MongoDB
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.database_name]
    
    # Sample symbols
    symbols = ["NIFTY25800CE", "NIFTY25800PE", "BANKNIFTY51000CE", "BANKNIFTY51000PE"]
    
    # Create some test orders with fills
    test_orders = []
    
    for i in range(10):
        symbol = random.choice(symbols)
        side = random.choice(["buy", "sell"])
        quantity = random.randint(1, 5) * 50  # Multiples of 50
        price = round(random.uniform(50, 500), 2)
        
        order = {
            "symbol": symbol,
            "quantity": quantity,
            "side": side,
            "order_type": "limit",
            "price": price,
            "trigger_price": None,
            "user_id": "test_user_123",  # Replace with actual user ID
            "status": "filled",  # Mark as filled for testing
            "filled_quantity": quantity,
            "average_price": price + random.uniform(-5, 5),  # Slight variation from order price
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "filled_at": datetime.utcnow()
        }
        test_orders.append(order)
    
    # Insert the test orders
    if test_orders:
        result = await db.orders.insert_many(test_orders)
        print(f"Inserted {len(result.inserted_ids)} test orders")
    
    # Also create some pending orders
    pending_orders = []
    for i in range(5):
        symbol = random.choice(symbols)
        side = random.choice(["buy", "sell"])
        quantity = random.randint(1, 3) * 50
        price = round(random.uniform(50, 500), 2)
        
        order = {
            "symbol": symbol,
            "quantity": quantity,
            "side": side,
            "order_type": "limit",
            "price": price,
            "trigger_price": None,
            "user_id": "test_user_123",
            "status": "pending",
            "filled_quantity": 0,
            "average_price": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "filled_at": None
        }
        pending_orders.append(order)
    
    if pending_orders:
        result = await db.orders.insert_many(pending_orders)
        print(f"Inserted {len(result.inserted_ids)} pending orders")
    
    client.close()
    print("Order simulation completed!")

if __name__ == "__main__":
    asyncio.run(simulate_order_fills())

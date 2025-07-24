#!/usr/bin/env python3
"""
Script to check the positions and orders in the database
"""
import asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

async def check_database():
    """Check the orders and positions in the database"""
    # Connect to MongoDB
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.database_name]
    
    print("🔍 Checking Orders Collection:")
    print("=" * 50)
    
    # Count orders by status
    orders_count = await db.orders.count_documents({})
    print(f"Total Orders: {orders_count}")
    
    if orders_count > 0:
        # Group by status
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        
        async for result in db.orders.aggregate(pipeline):
            print(f"  {result['_id'].upper()}: {result['count']}")
        
        print("\n📈 Sample Orders:")
        print("-" * 30)
        async for order in db.orders.find().limit(3):
            print(f"  {order['symbol']} | {order['side'].upper()} {order['quantity']} @ {order.get('price', 'MARKET')} | {order['status'].upper()}")
    
    print("\n📊 Checking Positions View:")
    print("=" * 50)
    
    try:
        # Try to create the positions view
        await execute_positions_view(db)
        
        # Count positions
        positions_count = await db.v_positions.count_documents({})
        print(f"Total Positions: {positions_count}")
        
        if positions_count > 0:
            print("\n📍 Position Summary:")
            print("-" * 30)
            async for position in db.v_positions.find():
                net_pos = position.get('net_position', 0)
                status = "LONG" if net_pos > 0 else "SHORT" if net_pos < 0 else "FLAT"
                realized_pnl = position.get('realized_pnl', 0)
                print(f"  {position['symbol']} | {status} {abs(net_pos)} | P&L: ₹{realized_pnl:.2f}")
    except Exception as e:
        print(f"Error with positions view: {e}")
    
    client.close()
    print("\n✅ Database check completed!")

async def execute_positions_view(db):
    """Create the positions view"""
    try:
        # Drop existing view
        await db.drop_collection("v_positions")
    except:
        pass
    
    # Create the positions view
    pipeline = [
        {
            "$group": {
                "_id": {
                    "symbol": "$symbol",
                    "user_id": "$user_id"
                },
                "total_buy_quantity": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "filled"]}]},
                            "$filled_quantity",
                            0
                        ]
                    }
                },
                "total_sell_quantity": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "filled"]}]},
                            "$filled_quantity",
                            0
                        ]
                    }
                },
                "total_buy_value": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "filled"]}]},
                            {"$multiply": ["$filled_quantity", "$average_price"]},
                            0
                        ]
                    }
                },
                "total_sell_value": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "filled"]}]},
                            {"$multiply": ["$filled_quantity", "$average_price"]},
                            0
                        ]
                    }
                },
                "open_buy_orders": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$side", "buy"]}, {"$eq": ["$status", "pending"]}]},
                            1,
                            0
                        ]
                    }
                },
                "open_sell_orders": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$side", "sell"]}, {"$eq": ["$status", "pending"]}]},
                            1,
                            0
                        ]
                    }
                }
            }
        },
        {
            "$addFields": {
                "symbol": "$_id.symbol",
                "user_id": "$_id.user_id",
                "net_position": {"$subtract": ["$total_buy_quantity", "$total_sell_quantity"]},
                "average_buy_price": {
                    "$cond": [
                        {"$gt": ["$total_buy_quantity", 0]},
                        {"$divide": ["$total_buy_value", "$total_buy_quantity"]},
                        None
                    ]
                },
                "average_sell_price": {
                    "$cond": [
                        {"$gt": ["$total_sell_quantity", 0]},
                        {"$divide": ["$total_sell_value", "$total_sell_quantity"]},
                        None
                    ]
                },
                "realized_pnl": {
                    "$cond": [
                        {"$and": [{"$gt": ["$total_buy_quantity", 0]}, {"$gt": ["$total_sell_quantity", 0]}]},
                        {
                            "$multiply": [
                                {"$min": ["$total_buy_quantity", "$total_sell_quantity"]},
                                {
                                    "$subtract": [
                                        {"$divide": ["$total_sell_value", "$total_sell_quantity"]},
                                        {"$divide": ["$total_buy_value", "$total_buy_quantity"]}
                                    ]
                                }
                            ]
                        },
                        0
                    ]
                }
            }
        }
    ]
    
    await db.create_collection("v_positions", viewOn="orders", pipeline=pipeline)

if __name__ == "__main__":
    asyncio.run(check_database())

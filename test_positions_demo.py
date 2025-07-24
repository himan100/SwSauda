#!/usr/bin/env python3
"""
Demo script to test the positions and orders functionality
"""
import asyncio
import sys
import os
from datetime import datetime
import random
from decimal import Decimal

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import db, connect_to_mongo
from crud import create_order, get_user_by_email
from models import OrderCreate, OrderType, OrderSide
from config import settings

async def create_demo_orders():
    """Create demo orders to test positions functionality"""
    # Connect to MongoDB first
    await connect_to_mongo()
    database = db.client[settings.database_name]
    
    # Get test user (assuming one exists from previous setup)
    user = await get_user_by_email("admin@swsauda.com")
    if not user:
        print("❌ No test user found. Please create a user first.")
        return
    
    print(f"✅ Found user: {user.email}")
    
    # Sample symbols and realistic prices
    symbols_data = [
        {"symbol": "NIFTY", "base_price": 25100.0},
        {"symbol": "BANKNIFTY", "base_price": 51250.0},
        {"symbol": "RELIANCE", "base_price": 2850.0},
        {"symbol": "TCS", "base_price": 3950.0},
        {"symbol": "INFY", "base_price": 1875.0},
        {"symbol": "HDFCBANK", "base_price": 1720.0},
        {"symbol": "ICICIBANK", "base_price": 1285.0},
        {"symbol": "SBIN", "base_price": 840.0},
    ]
    
    # Clear existing orders first
    orders_collection = database["orders"]
    await orders_collection.delete_many({"user_id": user.id})
    print("🧹 Cleared existing demo orders")
    
    demo_orders = []
    order_id = 1
    
    for symbol_data in symbols_data:
        symbol = symbol_data["symbol"]
        base_price = symbol_data["base_price"]
        
        # Create a mix of filled and pending orders
        for i in range(3):  # 3 orders per symbol
            # Random buy/sell
            side = OrderSide.BUY if random.choice([True, False]) else OrderSide.SELL
            
            # Random order type
            order_type = random.choice([OrderType.MARKET, OrderType.LIMIT])
            
            # Random quantity
            quantity = random.randint(10, 100)
            
            # Price with some variation
            price_variation = random.uniform(-0.05, 0.05)  # ±5% variation
            price = base_price * (1 + price_variation) if order_type == OrderType.LIMIT else None
            
            # Random status - mostly filled for demo
            status = random.choice(["filled", "filled", "filled", "pending", "cancelled"])
            filled_quantity = quantity if status == "filled" else (random.randint(0, quantity) if status == "pending" else 0)
            
            order_data = OrderCreate(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                user_id=user.id
            )
            
            # Create the order
            order = await create_order(order_data)
            
            # Update status and filled quantity for demo
            if status != "pending":
                await orders_collection.update_one(
                    {"_id": order.id},
                    {
                        "$set": {
                            "status": status,
                            "filled_quantity": filled_quantity,
                            "filled_at": datetime.utcnow() if status == "filled" else None
                        }
                    }
                )
            
            demo_orders.append({
                "id": order.id,
                "symbol": symbol,
                "side": side.value,
                "type": order_type.value,
                "quantity": quantity,
                "filled_quantity": filled_quantity,
                "price": price,
                "status": status
            })
            
            order_id += 1
    
    print(f"✅ Created {len(demo_orders)} demo orders")
    
    # Print summary
    print("\n📊 Demo Orders Summary:")
    print("=" * 60)
    for order in demo_orders:
        price_str = f"₹{order['price']:.2f}" if order['price'] else "Market"
        print(f"{order['symbol']:<12} {order['side'].upper():<4} {order['type'].upper():<6} "
              f"Qty: {order['quantity']:<3} Filled: {order['filled_quantity']:<3} "
              f"Price: {price_str:<12} Status: {order['status'].upper()}")
    
    print("\n🎯 Position Summary (calculated from filled orders):")
    print("=" * 60)
    
    # Calculate positions from filled orders
    positions = {}
    for order in demo_orders:
        if order['status'] == 'filled' and order['filled_quantity'] > 0:
            symbol = order['symbol']
            if symbol not in positions:
                positions[symbol] = {'buy_qty': 0, 'sell_qty': 0, 'buy_value': 0, 'sell_value': 0}
            
            qty = order['filled_quantity']
            price = order['price'] or base_price  # Use base price for market orders
            
            if order['side'] == 'buy':
                positions[symbol]['buy_qty'] += qty
                positions[symbol]['buy_value'] += qty * price
            else:
                positions[symbol]['sell_qty'] += qty
                positions[symbol]['sell_value'] += qty * price
    
    for symbol, pos in positions.items():
        net_qty = pos['buy_qty'] - pos['sell_qty']
        avg_buy = pos['buy_value'] / pos['buy_qty'] if pos['buy_qty'] > 0 else 0
        avg_sell = pos['sell_value'] / pos['sell_qty'] if pos['sell_qty'] > 0 else 0
        
        if net_qty != 0:
            pnl = pos['sell_value'] - pos['buy_value']
            print(f"{symbol:<12} Net: {net_qty:>5} "
                  f"Avg Buy: ₹{avg_buy:>8.2f} Avg Sell: ₹{avg_sell:>8.2f} "
                  f"P&L: ₹{pnl:>8.2f}")
    
    print(f"\n🌐 You can now test the positions page at: http://localhost:8000/positions")
    print("📱 Features to test:")
    print("   • Real-time position calculations")
    print("   • Order filtering and status")
    print("   • WebSocket live updates")
    print("   • Create new orders via the modal")
    print("   • Cancel pending orders")

if __name__ == "__main__":
    asyncio.run(create_demo_orders())

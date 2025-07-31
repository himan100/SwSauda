# Positions & Orders Feature Documentation

## Overview

The SwSauda trading platform now includes a comprehensive Positions & Orders management system with real-time updates via WebSockets.

## New Features Added

### 1. Orders Collection
A new MongoDB collection `orders` has been created to store order details with the following structure:

- **Order Types**: Market, Limit, Stop Loss (SL), Stop Loss Market (SLM)
- **Order Sides**: Buy, Sell
- **Order Status**: Pending, Filled, Partially Filled, Cancelled, Rejected

### 2. Positions View
A MongoDB view `v_positions` automatically calculates position summaries including:

- Total buy/sell quantities and values
- Net position (long/short/flat)
- Average buy/sell prices  
- Open order counts and quantities
- Open order average prices
- Realized P&L calculations

### 3. Positions Page
A new `/positions` page provides:

- **Real-time Dashboard**: Live position and order updates via WebSocket
- **Position Summary Cards**: Overview of total positions, P&L, open orders, and active symbols
- **Positions Table**: Detailed view of all positions with P&L and open order information
- **Orders Table**: Complete order history with filtering options
- **Order Creation**: Modal form to place new orders with all order types

### 4. API Endpoints

#### Orders API
- `POST /api/orders` - Create new order
- `GET /api/orders` - Get orders (with filtering)
- `GET /api/orders/{order_id}` - Get specific order
- `PUT /api/orders/{order_id}` - Update order
- `DELETE /api/orders/{order_id}` - Delete order

#### Positions API  
- `GET /api/positions` - Get calculated positions

#### WebSocket Endpoints
- `ws://localhost:8000/ws/positions` - Real-time positions and orders updates

## Data Models

### Order Model
```python
{
    "symbol": "NIFTY25800CE",
    "quantity": 50,
    "side": "buy",
    "order_type": "limit", 
    "price": 150.50,
    "trigger_price": null,
    "user_id": "user123",
    "status": "pending",
    "filled_quantity": 0,
    "average_price": null,
    "created_at": "2025-01-24T10:30:00Z",
    "updated_at": "2025-01-24T10:30:00Z",
    "filled_at": null
}
```

### Position Summary Model
```python
{
    "symbol": "NIFTY25800CE",
    "total_buy_quantity": 100,
    "total_sell_quantity": 50,
    "net_position": 50,
    "total_buy_value": 15000.0,
    "total_sell_value": 7600.0,
    "average_buy_price": 150.0,
    "average_sell_price": 152.0,
    "open_buy_orders": 1,
    "open_sell_orders": 0,
    "open_buy_quantity": 25,
    "open_sell_quantity": 0,
    "open_buy_avg_price": 149.0,
    "open_sell_avg_price": null,
    "realized_pnl": 100.0,
    "unrealized_pnl": 0.0,
    "current_price": null
}
```

## Usage Instructions

### Accessing the Positions Page
1. Navigate to http://localhost:8000/positions
2. Login with your user credentials
3. View real-time positions and orders

### Creating Orders
1. Click "New Order" button on the positions page
2. Fill in order details:
   - Symbol (e.g., NIFTY25800CE)
   - Side (Buy/Sell)
   - Order Type (Market/Limit/SL/SLM)
   - Quantity
   - Price (for non-market orders)
   - Trigger Price (for SL orders)
3. Click "Create Order"

### Managing Orders
- **Cancel Orders**: Click "Cancel" for pending orders
- **Filter Orders**: Use the dropdown to filter by status
- **View Details**: Click "View" for detailed order information

## Real-time Features

The positions page automatically updates when:
- New orders are created
- Orders are filled or cancelled
- Position calculations change

## Testing

Use the included simulation script to create test data:
```bash
python scripts/simulate_orders.py
```

This creates sample filled and pending orders for testing the positions calculations.

## MongoDB Views

The system uses MongoDB aggregation views for efficient position calculations. The `v_positions` view is automatically created and maintained, providing real-time position summaries without requiring manual calculation.

## Security

- All API endpoints require authentication
- Users can only view and manage their own orders and positions
- Order ownership is validated on all operations

## Future Enhancements

- Market data integration for unrealized P&L
- Order modification capabilities
- Position closing shortcuts
- Advanced filtering and search
- Export functionality for reporting

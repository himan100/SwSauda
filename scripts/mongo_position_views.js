// MongoDB Views for Position Calculations

// Drop existing position view if it exists
try { 
    db.v_positions.drop(); 
} catch(e) { 
    print('v_positions view does not exist, continuing...'); 
}

// Create positions view
db.createView(
  'v_positions',
  'orders',
  [
    {
      $group: {
        _id: {
          symbol: "$symbol",
          user_id: "$user_id"
        },
        // Filled orders calculations
        total_buy_quantity: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "buy"] }, { $eq: ["$status", "filled"] }] },
              "$filled_quantity",
              0
            ]
          }
        },
        total_sell_quantity: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "sell"] }, { $eq: ["$status", "filled"] }] },
              "$filled_quantity",
              0
            ]
          }
        },
        total_buy_value: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "buy"] }, { $eq: ["$status", "filled"] }] },
              { $multiply: ["$filled_quantity", "$average_price"] },
              0
            ]
          }
        },
        total_sell_value: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "sell"] }, { $eq: ["$status", "filled"] }] },
              { $multiply: ["$filled_quantity", "$average_price"] },
              0
            ]
          }
        },
        // Open orders calculations
        open_buy_orders: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "buy"] }, { $eq: ["$status", "pending"] }] },
              1,
              0
            ]
          }
        },
        open_sell_orders: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "sell"] }, { $eq: ["$status", "pending"] }] },
              1,
              0
            ]
          }
        },
        open_buy_quantity: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "buy"] }, { $eq: ["$status", "pending"] }] },
              { $subtract: ["$quantity", "$filled_quantity"] },
              0
            ]
          }
        },
        open_sell_quantity: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "sell"] }, { $eq: ["$status", "pending"] }] },
              { $subtract: ["$quantity", "$filled_quantity"] },
              0
            ]
          }
        },
        open_buy_value: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "buy"] }, { $eq: ["$status", "pending"] }, { $ne: ["$price", null] }] },
              { $multiply: [{ $subtract: ["$quantity", "$filled_quantity"] }, "$price"] },
              0
            ]
          }
        },
        open_sell_value: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$side", "sell"] }, { $eq: ["$status", "pending"] }, { $ne: ["$price", null] }] },
              { $multiply: [{ $subtract: ["$quantity", "$filled_quantity"] }, "$price"] },
              0
            ]
          }
        },
        // For calculating average prices
        filled_buy_orders: {
          $push: {
            $cond: [
              { $and: [{ $eq: ["$side", "buy"] }, { $eq: ["$status", "filled"] }] },
              { quantity: "$filled_quantity", price: "$average_price" },
              null
            ]
          }
        },
        filled_sell_orders: {
          $push: {
            $cond: [
              { $and: [{ $eq: ["$side", "sell"] }, { $eq: ["$status", "filled"] }] },
              { quantity: "$filled_quantity", price: "$average_price" },
              null
            ]
          }
        },
        pending_buy_orders: {
          $push: {
            $cond: [
              { $and: [{ $eq: ["$side", "buy"] }, { $eq: ["$status", "pending"] }, { $ne: ["$price", null] }] },
              { quantity: { $subtract: ["$quantity", "$filled_quantity"] }, price: "$price" },
              null
            ]
          }
        },
        pending_sell_orders: {
          $push: {
            $cond: [
              { $and: [{ $eq: ["$side", "sell"] }, { $eq: ["$status", "pending"] }, { $ne: ["$price", null] }] },
              { quantity: { $subtract: ["$quantity", "$filled_quantity"] }, price: "$price" },
              null
            ]
          }
        }
      }
    },
    {
      $addFields: {
        symbol: "$_id.symbol",
        user_id: "$_id.user_id",
        net_position: { $subtract: ["$total_buy_quantity", "$total_sell_quantity"] },
        // Calculate average buy price
        average_buy_price: {
          $cond: [
            { $gt: ["$total_buy_quantity", 0] },
            { $divide: ["$total_buy_value", "$total_buy_quantity"] },
            null
          ]
        },
        // Calculate average sell price
        average_sell_price: {
          $cond: [
            { $gt: ["$total_sell_quantity", 0] },
            { $divide: ["$total_sell_value", "$total_sell_quantity"] },
            null
          ]
        },
        // Calculate open buy average price
        open_buy_avg_price: {
          $cond: [
            { $gt: ["$open_buy_quantity", 0] },
            { $divide: ["$open_buy_value", "$open_buy_quantity"] },
            null
          ]
        },
        // Calculate open sell average price
        open_sell_avg_price: {
          $cond: [
            { $gt: ["$open_sell_quantity", 0] },
            { $divide: ["$open_sell_value", "$open_sell_quantity"] },
            null
          ]
        },
        // Calculate realized P&L
        realized_pnl: {
          $cond: [
            { $and: [{ $gt: ["$total_buy_quantity", 0] }, { $gt: ["$total_sell_quantity", 0] }] },
            {
              $multiply: [
                { $min: ["$total_buy_quantity", "$total_sell_quantity"] },
                {
                  $subtract: [
                    { $divide: ["$total_sell_value", "$total_sell_quantity"] },
                    { $divide: ["$total_buy_value", "$total_buy_quantity"] }
                  ]
                }
              ]
            },
            0
          ]
        }
      }
    },
    {
      $project: {
        _id: 0,
        symbol: 1,
        user_id: 1,
        total_buy_quantity: 1,
        total_sell_quantity: 1,
        net_position: 1,
        total_buy_value: 1,
        total_sell_value: 1,
        average_buy_price: 1,
        average_sell_price: 1,
        open_buy_orders: 1,
        open_sell_orders: 1,
        open_buy_quantity: 1,
        open_sell_quantity: 1,
        open_buy_avg_price: 1,
        open_sell_avg_price: 1,
        realized_pnl: 1
      }
    }
  ]
);

print("Position view created successfully");

# Strategy Module Documentation

## Overview

The Strategy Module is a comprehensive trading strategy management system that allows users to design, create, and execute automated trading strategies with multiple steps. Strategies can be attached to trade runs and executed in real-time based on market conditions.

## Features

### 1. Strategy Design
- **Multi-step strategies**: Create strategies with multiple conditions and actions
- **Visual builder**: User-friendly interface for designing strategies
- **Step types**: Conditions, Actions, Loops, and Branches
- **Flexible configuration**: Support for various market conditions and trading actions

### 2. Strategy Management
- **CRUD operations**: Create, Read, Update, Delete strategies
- **Status management**: Draft, Active, Paused, Archived states
- **Version control**: Track strategy changes and updates
- **Symbol targeting**: Specify which symbols a strategy applies to

### 3. Strategy Execution
- **Real-time execution**: Execute strategies during active trade runs
- **Execution tracking**: Monitor strategy execution status and performance
- **Logging**: Comprehensive execution logs for debugging and analysis
- **Performance metrics**: Track positions opened, closed, and P&L

### 4. Integration
- **Trade run integration**: Attach strategies to active trade runs
- **Market data integration**: Access real-time tick data and indicators
- **Order system integration**: Place orders through the existing order system
- **WebSocket support**: Real-time strategy execution updates

## Architecture

### Data Models

#### Strategy
```python
class Strategy(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: StrategyStatus  # draft, active, paused, archived
    symbols: List[str]  # List of symbols this strategy applies to
    max_positions: Optional[int]  # Maximum concurrent positions
    risk_per_trade: Optional[float]  # Risk percentage per trade
    is_active: bool
    steps: List[StrategyStep]
    created_at: datetime
    updated_at: datetime
    created_by: str
```

#### StrategyStep
```python
class StrategyStep(BaseModel):
    step_id: str
    step_type: StrategyStepType  # condition, action, loop, branch
    step_order: int
    condition: Optional[StrategyCondition]
    action: Optional[StrategyAction]
    next_step_id: Optional[str]  # For branching
    loop_start_step_id: Optional[str]  # For loops
    loop_end_step_id: Optional[str]  # For loops
    loop_count: Optional[int]  # For loops
    description: Optional[str]
    is_enabled: bool
```

#### StrategyCondition
```python
class StrategyCondition(BaseModel):
    condition_type: StrategyConditionType
    symbol: Optional[str]
    value: float
    comparison_operator: str  # >=, <=, ==, !=, >, <
    time_value: Optional[str]  # For time-based conditions
    custom_indicator: Optional[str]  # For custom indicators
    description: Optional[str]
```

#### StrategyAction
```python
class StrategyAction(BaseModel):
    action_type: StrategyActionType
    symbol: Optional[str]
    quantity: Optional[int]
    price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    wait_seconds: Optional[int]  # For wait actions
    custom_action: Optional[str]  # For custom actions
    description: Optional[str]
```

### Condition Types

| Condition Type | Description | Parameters |
|----------------|-------------|------------|
| `price_above` | Price is above threshold | symbol, value |
| `price_below` | Price is below threshold | symbol, value |
| `price_crosses_above` | Price crosses above threshold | symbol, value |
| `price_crosses_below` | Price crosses below threshold | symbol, value |
| `ema_above` | EMA is above threshold | symbol, value |
| `ema_below` | EMA is below threshold | symbol, value |
| `ema_crosses_above` | EMA crosses above threshold | symbol, value |
| `ema_crosses_below` | EMA crosses below threshold | symbol, value |
| `volume_above` | Volume is above threshold | symbol, value |
| `volume_below` | Volume is below threshold | symbol, value |
| `time_after` | Time is after specified time | time_value |
| `time_before` | Time is before specified time | time_value |
| `custom_indicator` | Custom indicator condition | custom_indicator |

### Action Types

| Action Type | Description | Parameters |
|-------------|-------------|------------|
| `buy_market` | Buy at market price | symbol, quantity |
| `sell_market` | Sell at market price | symbol, quantity |
| `buy_limit` | Buy at limit price | symbol, quantity, price |
| `sell_limit` | Sell at limit price | symbol, quantity, price |
| `buy_stop` | Buy stop order | symbol, quantity, price |
| `sell_stop` | Sell stop order | symbol, quantity, price |
| `set_stop_loss` | Set stop loss | symbol, stop_loss |
| `set_take_profit` | Set take profit | symbol, take_profit |
| `close_position` | Close position | symbol |
| `wait` | Wait for specified time | wait_seconds |
| `custom_action` | Custom action | custom_action |

## API Endpoints

### Strategy Management

#### Create Strategy
```http
POST /api/strategies
Content-Type: application/json

{
  "name": "EMA Crossover Strategy",
  "description": "Simple EMA crossover strategy",
  "status": "active",
  "symbols": ["NIFTY"],
  "max_positions": 2,
  "risk_per_trade": 2.0,
  "is_active": true,
  "steps": [...]
}
```

#### Get Strategies
```http
GET /api/strategies?status=active&is_active=true
```

#### Get Strategy by ID
```http
GET /api/strategies/{strategy_id}
```

#### Update Strategy
```http
PUT /api/strategies/{strategy_id}
Content-Type: application/json

{
  "description": "Updated description",
  "risk_per_trade": 1.5
}
```

#### Delete Strategy
```http
DELETE /api/strategies/{strategy_id}
```

### Strategy Execution

#### Create Strategy Execution
```http
POST /api/strategy-executions
Content-Type: application/json

{
  "strategy_id": "strategy_id",
  "trade_run_id": "trade_run_id"
}
```

#### Get Strategy Executions
```http
GET /api/strategy-executions?strategy_id={id}&trade_run_id={id}
```

#### Start Strategy Execution
```http
POST /api/strategy-executions/{execution_id}/start
```

#### Stop Strategy Execution
```http
POST /api/strategy-executions/{execution_id}/stop
```

#### Add Execution Log
```http
POST /api/strategy-executions/{execution_id}/log
Content-Type: application/json

{
  "type": "condition_evaluated",
  "step_id": "step_1",
  "result": true
}
```

### Trade Run Integration

#### Attach Strategy to Trade Run
```http
POST /api/trade-run/attach-strategy?strategy_id={strategy_id}
```

#### Get Attached Strategies
```http
GET /api/trade-run/attached-strategies
```

## Usage Examples

### 1. Simple EMA Crossover Strategy

```python
strategy = StrategyCreate(
    name="EMA Crossover Strategy",
    description="Buy when short EMA crosses above long EMA",
    status=StrategyStatus.ACTIVE,
    symbols=["NIFTY"],
    steps=[
        StrategyStep(
            step_id="check_crossover",
            step_type=StrategyStepType.CONDITION,
            step_order=0,
            condition=StrategyCondition(
                condition_type=StrategyConditionType.EMA_CROSSES_ABOVE,
                symbol="NIFTY",
                value=0
            )
        ),
        StrategyStep(
            step_id="buy_action",
            step_type=StrategyStepType.ACTION,
            step_order=1,
            action=StrategyAction(
                action_type=StrategyActionType.BUY_MARKET,
                symbol="NIFTY",
                quantity=1
            )
        )
    ]
)
```

### 2. Multi-Condition Strategy

```python
strategy = StrategyCreate(
    name="Multi-Condition Strategy",
    description="Complex strategy with multiple conditions",
    status=StrategyStatus.DRAFT,
    symbols=["NIFTY", "BANKNIFTY"],
    steps=[
        # Wait for market open
        StrategyStep(
            step_id="wait_market",
            step_type=StrategyStepType.CONDITION,
            step_order=0,
            condition=StrategyCondition(
                condition_type=StrategyConditionType.TIME_AFTER,
                time_value="09:15:00"
            )
        ),
        # Check NIFTY price
        StrategyStep(
            step_id="check_nifty",
            step_type=StrategyStepType.CONDITION,
            step_order=1,
            condition=StrategyCondition(
                condition_type=StrategyConditionType.PRICE_ABOVE,
                symbol="NIFTY",
                value=25000
            )
        ),
        # Buy NIFTY
        StrategyStep(
            step_id="buy_nifty",
            step_type=StrategyStepType.ACTION,
            step_order=2,
            action=StrategyAction(
                action_type=StrategyActionType.BUY_MARKET,
                symbol="NIFTY",
                quantity=1,
                stop_loss=24800,
                take_profit=25200
            )
        )
    ]
)
```

## Frontend Integration

### Strategy Management UI (Removed)

The former web UI page (`/strategies`) has been removed from the platform. Strategy operations are now performed exclusively through the documented REST API endpoints. This change reduces maintenance overhead and encourages automated / programmatic strategy management.

If any legacy reference attempts to render `strategies.html`, remove that reference (the template file has been deleted). All functionality described below (CRUD, execution, attachment) remains available via the API.

### Trade Run Integration

The trade run page includes:

1. **Strategy Attachment**: Attach strategies to active trade runs
2. **Execution Monitoring**: View attached strategies and their execution status
3. **Real-time Updates**: Live updates of strategy execution status

## Execution Engine

### StrategyExecutionEngine

The execution engine handles:

1. **Step Execution**: Execute strategy steps in order
2. **Condition Evaluation**: Evaluate market conditions in real-time
3. **Action Execution**: Execute trading actions
4. **Logging**: Comprehensive logging of all execution events
5. **Error Handling**: Graceful error handling and recovery

### Execution Flow

1. **Initialization**: Load strategy and create execution context
2. **Step Processing**: Process each step in order
3. **Condition Evaluation**: Evaluate conditions using real-time market data
4. **Action Execution**: Execute actions (orders, waits, etc.)
5. **Logging**: Log all events for monitoring and debugging
6. **Completion**: Mark execution as completed or handle errors

## Database Schema

### Collections

#### strategies
```javascript
{
  _id: ObjectId,
  name: String,
  description: String,
  status: String,  // draft, active, paused, archived
  symbols: [String],
  max_positions: Number,
  risk_per_trade: Number,
  is_active: Boolean,
  steps: [Object],  // Array of strategy steps
  created_at: Date,
  updated_at: Date,
  created_by: String
}
```

#### strategy_executions
```javascript
{
  _id: ObjectId,
  strategy_id: String,
  trade_run_id: String,
  status: String,  // running, completed, stopped, error
  started_at: Date,
  completed_at: Date,
  current_step_id: String,
  execution_log: [Object],  // Array of log entries
  positions_opened: Number,
  positions_closed: Number,
  total_pnl: Number
}
```

## Security

### Authentication
- All API endpoints require authentication
- JWT token validation for all requests
- User-based strategy ownership

### Authorization
- Strategy access control based on user permissions
- Admin-only access to certain operations
- Strategy execution limited to authorized users

## Performance Considerations

### Optimization
- Efficient database queries with proper indexing
- Asynchronous execution for non-blocking operations
- Connection pooling for database operations
- Caching of frequently accessed data

### Scalability
- Horizontal scaling support for multiple execution engines
- Load balancing for strategy execution
- Database sharding for large datasets
- Microservice architecture support

## Monitoring and Logging

### Execution Logs
- Detailed logs of all strategy execution events
- Performance metrics and timing information
- Error tracking and debugging information
- Audit trail for compliance

### Metrics
- Strategy performance metrics
- Execution success/failure rates
- Response times and latency
- Resource utilization

## Future Enhancements

### Planned Features
1. **Backtesting**: Historical strategy testing capabilities
2. **Strategy Templates**: Pre-built strategy templates
3. **Advanced Indicators**: Support for custom technical indicators
4. **Risk Management**: Advanced risk management features
5. **Strategy Optimization**: Automated strategy optimization
6. **Machine Learning**: ML-based strategy generation
7. **Portfolio Management**: Multi-strategy portfolio management
8. **Real-time Alerts**: Strategy execution alerts and notifications

### Technical Improvements
1. **Performance Optimization**: Further performance improvements
2. **Scalability**: Enhanced scalability features
3. **Reliability**: Improved error handling and recovery
4. **Monitoring**: Enhanced monitoring and alerting
5. **Testing**: Comprehensive testing framework

## Troubleshooting

### Common Issues

1. **Strategy Not Executing**
   - Check if strategy is active and enabled
   - Verify trade run is active
   - Check execution logs for errors

2. **Conditions Not Met**
   - Verify market data availability
   - Check condition parameters
   - Review execution logs

3. **Orders Not Placed**
   - Check order system integration
   - Verify symbol and quantity parameters
   - Review execution logs

### Debugging

1. **Execution Logs**: Review detailed execution logs
2. **Market Data**: Verify real-time market data availability
3. **Strategy Configuration**: Check strategy step configuration
4. **System Status**: Monitor system resources and connections

## Support

For technical support and questions:

1. **Documentation**: Review this documentation
2. **Logs**: Check execution logs for detailed information
3. **Testing**: Use the test script for validation
4. **Community**: Check community forums and discussions

---

*This documentation is maintained as part of the SwSauda trading platform.* 
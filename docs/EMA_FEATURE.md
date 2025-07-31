# EMA (Exponential Moving Average) Feature

## Overview

The EMA (Exponential Moving Average) feature calculates long and short EMAs for index tick data stored in Redis. This provides real-time technical analysis indicators for trading decisions.

## Features

### 1. Dual EMA Calculation
- **Long EMA**: Calculated using `REDIS_LONG_TICK_LENGTH` parameter (default: 600 ticks)
- **Short EMA**: Calculated using `REDIS_SHORT_TICK_LENGTH` parameter (default: 30 ticks)
- **Real-time Updates**: EMAs are recalculated with each new tick

### 2. Trading Signal Generation
- **BULLISH Signal**: When Short EMA > Long EMA
- **BEARISH Signal**: When Long EMA > Short EMA
- **Visual Indicators**: Color-coded signals in the UI

### 3. Redis Integration
- **Data Source**: Uses index ticks stored in Redis
- **Automatic Updates**: EMAs update as new ticks are stored
- **Performance Optimized**: Efficient calculation using stored tick data

## Configuration Parameters

### REDIS_LONG_TICK_LENGTH
- **Purpose**: Number of ticks to use for long EMA calculation
- **Default Value**: 600
- **Category**: Redis Configuration
- **Description**: Number of ticks to store in Redis for long EMA calculation

### REDIS_SHORT_TICK_LENGTH
- **Purpose**: Number of ticks to use for short EMA calculation
- **Default Value**: 30
- **Category**: Redis Configuration
- **Description**: Number of ticks to store in Redis for short EMA calculation

## API Endpoints

### GET /api/index-emas
Retrieve long and short EMA calculations for index ticks.

**Response:**
```json
{
  "database_name": "N_20250718",
  "long_ema": 25174.75,
  "short_ema": 25317.25,
  "long_period": 600,
  "short_period": 30,
  "total_ticks": 600
}
```

**Error Response:**
```json
{
  "detail": "No active run. Please start a run first."
}
```

## Implementation Details

### EMA Calculation Algorithm
```python
def calculate_ema(prices: list, period: int) -> float:
    """
    Calculate Exponential Moving Average (EMA)
    
    Args:
        prices: List of prices in chronological order (oldest first)
        period: EMA period
    
    Returns:
        EMA value
    """
    if not prices or len(prices) < period:
        return None
    
    # Use Simple Moving Average (SMA) as the initial EMA value
    sma = sum(prices[:period]) / period
    
    # Multiplier for EMA calculation
    multiplier = 2 / (period + 1)
    
    # Calculate EMA
    ema = sma
    for price in prices[period:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    
    return round(ema, 2)
```

### Data Flow
1. **Tick Storage**: Index ticks are stored in Redis during trading runs
2. **Data Retrieval**: EMAs are calculated from stored Redis data
3. **Calculation**: Both long and short EMAs are calculated using the algorithm
4. **API Response**: Results are returned via REST API
5. **UI Display**: EMAs are displayed in the trade run interface

## UI Integration

### Trade Run Page
The EMA calculations are displayed in the Index Tick Data section:

- **EMA Section**: Purple-themed section showing both EMAs
- **Long EMA Display**: Shows long EMA value with period
- **Short EMA Display**: Shows short EMA value with period
- **Signal Indicator**: Shows BULLISH/BEARISH signal with color coding
- **Real-time Updates**: EMAs update automatically with new ticks

### Visual Elements
- **Loading State**: Spinner while calculating EMAs
- **Color Coding**: 
  - Green for BULLISH signals
  - Red for BEARISH signals
- **Period Display**: Shows the number of ticks used for each EMA

## Usage Examples

### Starting a Trading Run with EMA
1. **Select Database**: Choose a database from the dropdown
2. **Start Run**: Click "Start Trading Run" button
3. **View EMAs**: EMAs will appear in the Index Tick Data section
4. **Monitor Signals**: Watch for BULLISH/BEARISH signal changes

### API Usage
```bash
# Get EMA calculations
curl -X GET "http://localhost:8000/api/index-emas" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Response
{
  "database_name": "N_20250718",
  "long_ema": 25174.75,
  "short_ema": 25317.25,
  "long_period": 600,
  "short_period": 30,
  "total_ticks": 600
}
```

## Testing

### Test Scripts
- `test_ema_calculation.py`: Basic EMA calculation tests
- `test_complete_ema_workflow.py`: Complete workflow testing

### Test Scenarios
1. **Basic Calculation**: Verify EMA algorithm works correctly
2. **Insufficient Data**: Test with fewer ticks than required
3. **Upward Trend**: Test with increasing prices (BULLISH signal)
4. **Downward Trend**: Test with decreasing prices (BEARISH signal)
5. **Parameter Validation**: Verify parameter retrieval works

### Sample Test Results
```
✅ Long EMA (600): 25174.75
✅ Short EMA (30): 25317.25
✅ Short EMA > Long EMA (BULLISH signal)

✅ Declining pattern EMAs:
   Long EMA: 24825.25
   Short EMA: 24682.75
✅ Long EMA > Short EMA (BEARISH signal)
```

## Performance Considerations

### Memory Usage
- **Redis Storage**: ~300KB for 600 ticks
- **Calculation Overhead**: Minimal CPU usage for EMA calculation
- **API Response**: Small JSON payload

### Optimization
- **Caching**: EMAs are calculated on-demand
- **Efficient Algorithm**: O(n) time complexity for EMA calculation
- **Redis Integration**: Fast data retrieval from Redis

## Error Handling

### Common Errors
1. **No Active Run**: Returns 400 error if no trading run is active
2. **Insufficient Data**: Returns None for EMAs if not enough ticks
3. **Redis Connection**: Handles Redis connection failures gracefully
4. **Parameter Issues**: Falls back to default values if parameters missing

### Error Responses
```json
{
  "detail": "No active run. Please start a run first."
}
```

## Future Enhancements

### Planned Features
- **Multiple Timeframes**: Support for different EMA periods
- **Additional Indicators**: RSI, MACD, Bollinger Bands
- **Historical Analysis**: EMA trends over time
- **Alert System**: Notifications for signal changes
- **Backtesting**: Historical EMA performance analysis

### Integration Opportunities
- **Trading Bots**: Automated trading based on EMA signals
- **Risk Management**: Position sizing based on EMA trends
- **Portfolio Analysis**: Multi-asset EMA analysis
- **Performance Metrics**: EMA accuracy tracking

## Troubleshooting

### Common Issues

#### EMAs Not Calculating
```
Issue: EMAs show as "N/A"
Solution: Check if enough ticks are available in Redis
```

#### Wrong Signal Direction
```
Issue: Signal doesn't match price trend
Solution: Verify tick data quality and calculation parameters
```

#### Performance Issues
```
Issue: Slow EMA updates
Solution: Check Redis performance and tick storage efficiency
```

### Debug Steps
1. **Check Redis Data**: Verify ticks are being stored
2. **Validate Parameters**: Confirm tick length parameters
3. **Test Calculation**: Run test scripts to verify algorithm
4. **Monitor Logs**: Check application logs for errors
5. **Verify API**: Test API endpoint directly

## Security

### Authentication
- **JWT Required**: All API endpoints require valid JWT token
- **Admin Access**: EMA calculations require admin privileges
- **Database Isolation**: Only access to authorized databases

### Data Protection
- **Redis Security**: Redis connection uses authentication
- **Parameter Validation**: All inputs are validated
- **Error Handling**: No sensitive data in error messages

## Monitoring

### Key Metrics
- **EMA Calculation Time**: Time to calculate EMAs
- **API Response Time**: Time to return EMA data
- **Signal Accuracy**: Percentage of correct signals
- **Data Quality**: Number of valid ticks available

### Logging
- **Calculation Logs**: EMA calculation events
- **Error Logs**: Calculation and API errors
- **Performance Logs**: Timing and performance metrics
- **Access Logs**: API access and authentication events 
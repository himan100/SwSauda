# Redis Tick Storage Feature

## Overview

The Redis Tick Storage feature automatically stores tick data in Redis when a trading run is started on the `/trade-run` route. This provides fast access to recent tick data and implements a FIFO (First In, First Out) behavior with configurable limits.

## Features

### 1. Automatic Tick Storage
- **Index Ticks**: All IndexTick data is automatically stored in Redis when streaming
- **Option Ticks**: All OptionTick data is automatically stored in Redis when streaming
- **Real-time Storage**: Ticks are stored as they are streamed via WebSocket
- **Database Isolation**: Ticks are stored per database to avoid conflicts

### 2. Configurable Storage Limits
- **Parameter-based**: Storage limit is controlled by `REDIS_LONG_TICK_LENGTH` parameter
- **Default Value**: 1000 ticks if parameter is not set
- **FIFO Behavior**: When limit is reached, oldest ticks are automatically removed
- **Separate Limits**: Index and option ticks have separate storage limits

### 3. Redis Data Structure
- **Key Format**: `ticks:{database_name}:{tick_type}`
  - Example: `ticks:N_20250718:indextick`
  - Example: `ticks:N_20250718:optiontick`
- **Data Format**: JSON strings stored in Redis lists
- **Ordering**: Latest ticks are at the beginning of the list (LPUSH)

### 4. API Endpoints
- **GET /api/redis-ticks/{tick_type}**: Retrieve ticks from Redis
  - `tick_type`: `indextick` or `optiontick`
  - `limit`: Number of ticks to retrieve (default: 100)

## Configuration

### Redis Setup
1. **Install Redis**: Ensure Redis server is running
2. **Environment Variables**: Add to `.env` file:
   ```
   REDIS_URL=redis://localhost:6379
   REDIS_DB=0
   ```

### Parameter Configuration
1. **Create Parameter**: Add `REDIS_LONG_TICK_LENGTH` parameter via the Parameters page
2. **Parameter Details**:
   - **Name**: `REDIS_LONG_TICK_LENGTH`
   - **Value**: Number of ticks to store (e.g., `1000`)
   - **Category**: `Redis Configuration`
   - **Data Type**: `int`
   - **Active**: `true`

## Implementation Details

### Storage Process
1. **Tick Reception**: When a tick is received during streaming
2. **JSON Serialization**: Tick data is converted to JSON string
3. **Redis Storage**: JSON is pushed to Redis list using LPUSH
4. **Limit Enforcement**: List is trimmed to maintain configured limit
5. **FIFO Maintenance**: Oldest ticks are automatically removed

### Retrieval Process
1. **Key Construction**: Redis key is built from database name and tick type
2. **Data Retrieval**: JSON strings are retrieved from Redis list
3. **JSON Parsing**: Strings are parsed back to Python dictionaries
4. **Error Handling**: Invalid JSON is skipped gracefully

### Error Handling
- **Redis Connection**: Graceful handling of Redis connection failures
- **JSON Parsing**: Invalid JSON data is skipped
- **Parameter Errors**: Default values used if parameter is invalid
- **Storage Errors**: Errors are logged but don't stop tick streaming

## Usage Examples

### Starting a Trading Run
```bash
# Start a trading run (automatically enables Redis storage)
POST /api/start-run
{
  "database_name": "N_20250718",
  "interval_seconds": 1.0
}
```

### Retrieving Index Ticks
```bash
# Get latest 100 index ticks
GET /api/redis-ticks/indextick?limit=100

# Response
{
  "ticks": [
    {
      "ft": 1752810305,
      "token": 26000,
      "e": "NSE",
      "lp": 25124.35,
      "pc": 0.05,
      "rt": "2025-07-18 09:15:05",
      "ts": "Nifty 50",
      "_id": "...",
      "data_type": "indextick"
    }
  ],
  "total_count": 1,
  "database_name": "N_20250718",
  "tick_type": "indextick"
}
```

### Retrieving Option Ticks
```bash
# Get latest 50 option ticks
GET /api/redis-ticks/optiontick?limit=50
```

## Performance Considerations

### Memory Usage
- **Storage Size**: Each tick is approximately 200-300 bytes in JSON format
- **Memory Calculation**: 1000 ticks × 300 bytes = ~300KB per tick type
- **Total Memory**: ~600KB for both index and option ticks per database

### Redis Operations
- **Write Operations**: LPUSH + LTRIM for each tick (2 operations)
- **Read Operations**: LRANGE for retrieval
- **Performance**: Redis lists provide O(1) push/pop operations

### Scalability
- **Database Isolation**: Each database has separate Redis keys
- **Memory Management**: Automatic cleanup via LTRIM
- **Connection Pooling**: Efficient Redis connection handling

## Monitoring and Debugging

### Redis Commands
```bash
# Check Redis keys
redis-cli KEYS "ticks:*"

# Get tick count for a specific database and type
redis-cli LLEN "ticks:N_20250718:indextick"

# View latest ticks
redis-cli LRANGE "ticks:N_20250718:indextick" 0 4

# Clear all tick data
redis-cli DEL "ticks:N_20250718:indextick"
redis-cli DEL "ticks:N_20250718:optiontick"
```

### Logging
- **Storage Logs**: Success/failure messages for each tick storage
- **Error Logs**: Detailed error information for debugging
- **Performance Logs**: Storage timing and memory usage

## Testing

### Test Script
Run the test script to verify Redis functionality:
```bash
python test_redis_ticks.py
```

### Manual Testing
1. **Start Trading Run**: Start a run on `/trade-run` page
2. **Monitor Logs**: Check console for Redis storage messages
3. **Verify Storage**: Use Redis CLI to check stored data
4. **Test API**: Use API endpoints to retrieve stored ticks

## Troubleshooting

### Common Issues

#### Redis Connection Failed
```
Error: Failed to connect to Redis
Solution: Ensure Redis server is running and accessible
```

#### Parameter Not Found
```
Error: REDIS_LONG_TICK_LENGTH parameter not found
Solution: Create the parameter via Parameters page
```

#### Memory Issues
```
Error: Redis memory usage too high
Solution: Reduce REDIS_LONG_TICK_LENGTH parameter value
```

### Debug Steps
1. **Check Redis Status**: `redis-cli ping`
2. **Verify Parameter**: Check Parameters page for `REDIS_LONG_TICK_LENGTH`
3. **Monitor Logs**: Check application logs for error messages
4. **Test Connection**: Run test script to verify functionality

## Future Enhancements

### Planned Features
- **Tick Compression**: Compress tick data to reduce memory usage
- **TTL Support**: Automatic expiration of old tick data
- **Analytics**: Tick storage statistics and monitoring
- **Backup/Restore**: Redis data backup and restoration
- **Clustering**: Redis cluster support for high availability

### Integration Opportunities
- **Real-time Analytics**: Use stored ticks for real-time analysis
- **Alert System**: Trigger alerts based on tick patterns
- **Historical Analysis**: Combine with MongoDB for comprehensive analysis
- **Performance Monitoring**: Track tick storage performance metrics 
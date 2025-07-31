# Enhanced Redis Tick Storage Feature

## Overview

The Enhanced Redis Tick Storage feature automatically stores tick data in Redis when a trading run is started on the `/trade-run` route. This provides fast access to recent tick data with improved functionality including automatic flushing, proper sorting, and per-token option tick storage.

## Enhanced Features

### 1. Automatic Redis Flushing
- **Clean Start**: Redis data is automatically flushed when a trading run starts
- **Database Isolation**: Only data for the specific database is cleared
- **Fresh Data**: Ensures only current trading session data is stored

### 2. Proper Tick Sorting
- **Index Ticks**: Stored in chronological order (latest first)
- **Option Ticks**: Sorted by feed time (ft) in descending order when retrieved
- **Multi-token Sorting**: All option ticks across tokens are properly sorted

### 3. Per-Token Option Tick Storage
- **Separate Storage**: Each option token has its own Redis key
- **Individual Limits**: Each token maintains its own FIFO limit
- **Token Isolation**: Option ticks for different tokens are stored separately

### 4. Enhanced Data Structure
- **Index Ticks**: `ticks:{database_name}:indextick`
- **Option Ticks**: `ticks:{database_name}:optiontick:{token}`
- **Example Keys**:
  - `ticks:N_20250718:indextick`
  - `ticks:N_20250718:optiontick:26001`
  - `ticks:N_20250718:optiontick:26002`

## API Endpoints

### GET /api/redis-ticks/{tick_type}
Retrieve tick data from Redis for a specific tick type.

**Parameters:**
- `tick_type`: `indextick` or `optiontick`
- `limit`: Number of ticks to retrieve (default: 100)
- `token`: For option ticks, specify token to get ticks for that token only

**Examples:**
```bash
# Get index ticks
GET /api/redis-ticks/indextick?limit=100

# Get all option ticks (all tokens, sorted by ft)
GET /api/redis-ticks/optiontick?limit=100

# Get option ticks for specific token
GET /api/redis-ticks/optiontick?limit=100&token=26001
```

### GET /api/redis-option-tokens
Get list of option tokens that have data in Redis.

**Response:**
```json
{
  "tokens": ["26001", "26002", "26003"],
  "total_count": 3,
  "database_name": "N_20250718"
}
```

## Implementation Details

### Redis Flushing Process
1. **Trade Run Start**: When `/api/start-run` is called
2. **Pattern Matching**: Find all keys matching `ticks:{database_name}:*`
3. **Bulk Deletion**: Delete all matching keys using Redis DEL command
4. **Clean Slate**: Ensure fresh start for new trading session

### Enhanced Storage Process
1. **Index Ticks**: Stored in single key with LPUSH + LTRIM
2. **Option Ticks**: Stored per token with separate keys
3. **FIFO Maintenance**: Each key maintains its own limit
4. **Automatic Cleanup**: Oldest ticks removed when limit reached

### Retrieval and Sorting Process
1. **Index Ticks**: Direct retrieval from single key
2. **Option Ticks**: 
   - Single token: Direct retrieval from token-specific key
   - All tokens: Collect from all token keys, then sort by ft
3. **Sorting**: Option ticks sorted by feed time (ft) in descending order
4. **Limit Application**: Apply limit after sorting for accurate results

## Usage Examples

### Starting a Trading Run (with Redis Flushing)
```bash
POST /api/start-run
{
  "database_name": "N_20250718",
  "interval_seconds": 1.0
}

# This automatically:
# 1. Flushes existing Redis data for N_20250718
# 2. Starts tick streaming with Redis storage
# 3. Stores index ticks in ticks:N_20250718:indextick
# 4. Stores option ticks per token in ticks:N_20250718:optiontick:{token}
```

### Retrieving Index Ticks
```bash
GET /api/redis-ticks/indextick?limit=50

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
  "tick_type": "indextick",
  "token": null
}
```

### Retrieving All Option Ticks (Sorted)
```bash
GET /api/redis-ticks/optiontick?limit=100

# Response includes ticks from all tokens, sorted by ft (latest first)
{
  "ticks": [
    {
      "ft": 1752810305,
      "token": 26001,
      "e": "NSE",
      "lp": 125.50,
      "pc": -0.02,
      "rt": "2025-07-18 09:15:05",
      "ts": "NIFTY25JUL25100CE",
      "_id": "...",
      "data_type": "optiontick"
    }
  ],
  "total_count": 1,
  "database_name": "N_20250718",
  "tick_type": "optiontick",
  "token": null
}
```

### Retrieving Option Ticks for Specific Token
```bash
GET /api/redis-ticks/optiontick?limit=50&token=26001

# Response includes only ticks for token 26001
{
  "ticks": [...],
  "total_count": 1,
  "database_name": "N_20250718",
  "tick_type": "optiontick",
  "token": "26001"
}
```

### Getting Available Option Tokens
```bash
GET /api/redis-option-tokens

# Response
{
  "tokens": ["26001", "26002", "26003"],
  "total_count": 3,
  "database_name": "N_20250718"
}
```

## Performance Considerations

### Memory Usage
- **Index Ticks**: ~300KB for 1000 ticks
- **Option Ticks**: ~300KB per token for 1000 ticks
- **Total Memory**: Depends on number of active option tokens

### Redis Operations
- **Write Operations**: LPUSH + LTRIM for each tick (2 operations)
- **Flush Operations**: KEYS + DEL for database cleanup
- **Read Operations**: LRANGE for retrieval, additional sorting for multi-token option ticks

### Scalability
- **Token Isolation**: Each option token has independent storage
- **Memory Management**: Automatic cleanup per token
- **Efficient Sorting**: Only when retrieving all option ticks

## Monitoring and Debugging

### Redis Commands
```bash
# Check all keys for a database
redis-cli KEYS "ticks:N_20250718:*"

# Get tick count for index
redis-cli LLEN "ticks:N_20250718:indextick"

# Get tick count for specific option token
redis-cli LLEN "ticks:N_20250718:optiontick:26001"

# View latest index ticks
redis-cli LRANGE "ticks:N_20250718:indextick" 0 4

# View latest option ticks for specific token
redis-cli LRANGE "ticks:N_20250718:optiontick:26001" 0 4

# Clear all data for a database
redis-cli KEYS "ticks:N_20250718:*" | xargs redis-cli DEL
```

### Logging
- **Flush Logs**: Database flush confirmation with key count
- **Storage Logs**: Success/failure messages for each tick storage
- **Token Logs**: Option token storage confirmation
- **Error Logs**: Detailed error information for debugging

## Testing

### Test Script
Run the enhanced test script to verify all functionality:
```bash
python test_redis_ticks.py
```

### Manual Testing
1. **Start Trading Run**: Start a run on `/trade-run` page
2. **Monitor Flush**: Check console for Redis flush messages
3. **Verify Storage**: Use Redis CLI to check stored data
4. **Test API**: Use API endpoints to retrieve stored ticks
5. **Check Sorting**: Verify option ticks are properly sorted
6. **Test Tokens**: Verify per-token storage and retrieval

## Troubleshooting

### Common Issues

#### Redis Flush Not Working
```
Error: Redis flush failed
Solution: Check Redis connection and permissions
```

#### Option Ticks Not Sorted
```
Error: Option ticks appear in wrong order
Solution: Verify ft field values and sorting logic
```

#### Token-Specific Retrieval Failing
```
Error: Cannot retrieve ticks for specific token
Solution: Check token parameter and key format
```

### Debug Steps
1. **Check Redis Status**: `redis-cli ping`
2. **Verify Keys**: `redis-cli KEYS "ticks:*"`
3. **Check Token Keys**: `redis-cli KEYS "ticks:*:optiontick:*"`
4. **Monitor Logs**: Check application logs for error messages
5. **Test API**: Use API endpoints to verify functionality

## Future Enhancements

### Planned Features
- **Compression**: Compress tick data to reduce memory usage
- **TTL Support**: Automatic expiration of old tick data
- **Analytics**: Tick storage statistics and monitoring
- **Backup/Restore**: Redis data backup and restoration
- **Clustering**: Redis cluster support for high availability

### Integration Opportunities
- **Real-time Analytics**: Use stored ticks for real-time analysis
- **Alert System**: Trigger alerts based on tick patterns
- **Historical Analysis**: Combine with MongoDB for comprehensive analysis
- **Performance Monitoring**: Track tick storage performance metrics 
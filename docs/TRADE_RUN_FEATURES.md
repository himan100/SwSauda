# Trade Run Features

## Overview
The Trade Run page provides functionality to start trading runs and view real-time tick data from the IndexTick collection in MongoDB databases using WebSocket connections for live streaming with configurable intervals.

## Features

### 1. Database Selection
- Select from databases with the configured prefix (e.g., `N_` for Nifty databases)
- View currently selected database
- Unset selected database

### 2. Start Run with Configurable Intervals
- Click "Start Run" button in the Configuration section
- **Configurable Stream Interval**: Choose from 0.1s to 5.0s intervals
  - 0.1s (Very Fast) - Maximum responsiveness, higher CPU usage
  - 0.5s (Fast) - Good balance of speed and performance
  - 1.0s (Normal) - Default setting, optimal performance
  - 2.0s (Slow) - Lower CPU usage, slower updates
  - 5.0s (Very Slow) - Minimal resource usage
- Requires a database to be selected first
- Starts a trading run with the selected database
- Automatically connects to WebSocket for real-time tick data streaming

### 3. Complete Real-time Tick Data Display
- **WebSocket-powered real-time streaming** of ALL tick data from the IndexTick collection
- **No artificial limits**: Streams all available ticks (up to 1000 displayed for performance)
- Shows the following fields:
  - **Symbol**: Trading symbol (e.g., "Nifty 50")
  - **Price**: Last price (lp field)
  - **Change**: Price change (pc field) - green for positive, red for negative
  - **Exchange**: Exchange name (e.g., "NSE")
  - **Token**: Token number
  - **Time**: Record time (rt field)
- **Live updates**: New ticks appear instantly as they arrive
- **Visual indicators**: Latest tick is highlighted with green border and "⚡ Latest Tick" label
- **Connection status**: Real-time WebSocket connection indicator
- **Performance optimized**: Efficient streaming with configurable intervals

### 4. Advanced WebSocket Streaming
- **Automatic connection**: WebSocket connects when run starts
- **Complete historical data**: Streams ALL historical ticks (not just 50)
- **Live monitoring**: Continuously monitors for new tick data
- **Sorted by feed time**: Data is sorted by `ft` (feed time) field
- **Configurable intervals**: Adjustable polling frequency (0.1s to 5.0s)
- **Performance optimized**: Smart throttling to prevent overwhelming clients
- **Automatic reconnection**: Handles connection drops gracefully

### 5. Stop Run
- Click "Stop Run" button to stop the current trading run
- Disconnects WebSocket and stops data streaming
- Clears tick data display

## API Endpoints

### POST /api/start-run
Start a trading run with a specific database.
```json
{
  "database_name": "N_20250718"
}
```

### POST /api/stop-run
Stop the current trading run.

### GET /api/tick-data
Get tick data from the active run's database (legacy endpoint).
- Query parameters: `skip` (default: 0), `limit` (default: 100)
- Returns paginated tick data from IndexTick collection

### GET /api/run-status
Get the current run status.
```json
{
  "is_running": true,
  "database_name": "N_20250718"
}
```

### WebSocket /ws/tick-data
Real-time tick data streaming endpoint with configurable intervals.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/tick-data');
```

**Start Stream with Interval:**
```javascript
ws.send(JSON.stringify({
  type: 'start_stream',
  database_name: 'N_20250718',
  interval_seconds: 0.5  // Configurable interval
}));
```

**Stop Stream:**
```javascript
ws.send(JSON.stringify({
  type: 'stop_stream'
}));
```

**Received Messages:**
- Connection confirmation: `{"type": "connection", "message": "Connected to tick data stream"}`
- Stream started: `{"type": "stream_started", "database": "N_20250718", "interval_seconds": 0.5}`
- Stream stopped: `{"type": "stream_stopped"}`
- Tick data: `{"ft": 1752810305, "token": 26000, "e": "NSE", "lp": 25124.35, "pc": 0.05, "rt": "2025-07-18 09:15:05", "ts": "Nifty 50", "_id": "..."}`

## Data Structure

The IndexTick collection contains documents with the following structure:
```json
{
  "_id": "ObjectId",
  "ft": 1752810305,        // Feed time (Unix timestamp)
  "token": 26000,          // Token number
  "e": "NSE",              // Exchange
  "lp": 25124.35,          // Last price
  "pc": 0.05,              // Price change
  "rt": "2025-07-18 09:15:05",  // Record time
  "ts": "Nifty 50"         // Trading symbol
}
```

## Usage Instructions

1. **Select Database**: Choose a database from the dropdown in the left panel
2. **Configure Interval**: Select desired stream interval (0.1s to 5.0s)
3. **Start Run**: Click "Start Run" in the Configuration section
4. **View Complete Data**: ALL historical ticks stream automatically via WebSocket
5. **Monitor Live Updates**: New ticks appear instantly with visual indicators
6. **Check Connection**: Green dot indicates active WebSocket connection
7. **Adjust Performance**: Change interval based on your needs (faster = more CPU usage)
8. **Stop**: Click "Stop Run" when finished

## Technical Details

### Frontend
- **Vue.js 3**: Reactive interface with real-time updates
- **WebSocket API**: Native browser WebSocket for real-time communication
- **Visual Feedback**: Connection status, loading states, and tick highlighting
- **Performance**: Displays up to 1000 ticks for optimal performance
- **Interval Configuration**: Dropdown selection for stream frequency
- **Error Handling**: Graceful handling of connection drops and errors

### Backend
- **FastAPI WebSocket**: Async WebSocket endpoint for real-time streaming
- **MongoDB Integration**: Efficient queries with sorting by feed time
- **Connection Management**: Handles multiple client connections
- **Streaming Logic**: 
  - Complete historical data streaming (ALL ticks)
  - Continuous monitoring for new data
  - Automatic sorting by `ft` field
  - Configurable polling intervals
- **Performance Optimization**: Smart throttling and batch processing
- **Error Recovery**: Automatic retry logic for database queries

### WebSocket Flow
1. **Connection**: Client connects to `/ws/tick-data`
2. **Authentication**: Connection established (no auth required for demo)
3. **Stream Start**: Client sends `start_stream` message with database name and interval
4. **Complete Historical Data**: Server streams ALL historical ticks
5. **Live Monitoring**: Server continuously checks for new ticks at specified interval
6. **Real-time Updates**: New ticks are immediately broadcast to all clients
7. **Stream Stop**: Client sends `stop_stream` message

### Interval Configuration
- **0.1s (Very Fast)**: Maximum responsiveness, suitable for high-frequency trading
- **0.5s (Fast)**: Good balance for most trading scenarios
- **1.0s (Normal)**: Default setting, optimal performance
- **2.0s (Slow)**: Lower resource usage, suitable for monitoring
- **5.0s (Very Slow)**: Minimal resource usage, for background monitoring

## Security

- All HTTP endpoints require admin authentication
- JWT token validation for API endpoints
- WebSocket connections are open (can be secured with token validation)
- Database access restricted to authorized users
- Input validation for database names and interval parameters

## Performance Considerations

- **Complete Data**: Streams ALL available ticks (no artificial limits)
- **Display Limit**: Maximum 1000 ticks displayed to prevent UI lag
- **Interval Control**: Configurable polling frequency to balance performance vs responsiveness
- **WebSocket Efficiency**: Single connection per client
- **Database Queries**: Optimized with proper indexing on `ft` field
- **Memory Management**: Automatic cleanup of old tick data
- **Connection Pooling**: Efficient handling of multiple WebSocket connections
- **Smart Throttling**: Prevents overwhelming clients with too much data 
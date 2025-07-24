# MongoDB Views Integration

## Overview
This document describes the integration of MongoDB analysis views creation with the trade run functionality. When a database is selected for a trading run, the system automatically executes MongoDB views script to create analytical views for data processing.

## Features

### 1. Automatic Views Creation
- **Trigger**: When starting a trading run via `/api/start-run`
- **Action**: Automatically executes MongoDB views script for the selected database
- **Views Created**: 
  - `v_index_base`: Base index data view with calculated ibase and itop values
  - `v_option_pair_base`: Option pair analysis view with risk calculations

### 2. Manual Views Creation
- **Button**: "Create MongoDB Views" button in the trade run interface
- **Location**: Left panel, under database selection (only shows when database is selected)
- **API Endpoint**: `POST /api/execute-views/{database_name}`
- **Purpose**: Allows manual creation of views without starting a trading run

## Implementation Details

### Backend Changes (main.py)

#### New Function: `execute_mongo_views_script(database_name: str)`
- Creates temporary MongoDB script with the selected database name
- Tries `mongosh` first, falls back to `mongo` command
- Executes the views creation script
- Returns success/failure status
- Includes proper error handling and cleanup

#### Modified Endpoint: `POST /api/start-run`
- Now calls `execute_mongo_views_script()` before starting the trading run
- Continues with run even if views creation fails (with warning)
- Updates response message to indicate views creation status

#### New Endpoint: `POST /api/execute-views/{database_name}`
- Standalone endpoint for manual views creation
- Validates database existence
- Executes views script and returns result

### Frontend Changes (trade_run.html)

#### New UI Elements
- "Create MongoDB Views" button (only visible when database is selected)
- Loading state indicator during views creation
- Status messages for views creation results

#### New Vue.js Properties
- `loadingViews`: Boolean to track views creation loading state

#### New Vue.js Methods
- `executeViews()`: Calls the manual views creation API endpoint
- Proper error handling and user feedback

## MongoDB Views Details

### v_index_base View
- **Source Collection**: IndexTick
- **Purpose**: Creates base index data with calculated strike levels
- **Key Fields**:
  - `ibase`: Base strike level (floor division of lp by strkstep)
  - `itop`: Top strike level (ceiling division of lp by strkstep)
  - Merged with Index collection data

### v_option_pair_base View
- **Source Collection**: IndexTick
- **Purpose**: Creates option pair analysis with risk calculations
- **Key Features**:
  - Generates 10 levels of CE/PE strike pairs
  - Looks up option data from Option collection
  - Retrieves option tick data from OptionTick collection
  - Calculates risk percentage: `100 - ((diff/sum_lp) * 100)`
  - **Key Fields**:
    - `level`: Strike level (0-9)
    - `ce_strike`, `pe_strike`: Call and Put strike prices
    - `ce_lp`, `pe_lp`: Call and Put last prices
    - `sum_lp`: Sum of CE and PE last prices
    - `risk_prec`: Risk percentage calculation

## Usage Instructions

### Automatic Views Creation (Recommended)
1. Select a database from the dropdown in the trade run page
2. Configure stream interval
3. Click "Start Run"
4. Views will be automatically created before the run starts
5. Check the response message for views creation status

### Manual Views Creation
1. Select a database from the dropdown in the trade run page
2. Click "Create MongoDB Views" button (appears under database selection)
3. Wait for the process to complete
4. Check the status message for results

## Error Handling

### MongoDB Command Availability
- System tries `mongosh` first (MongoDB Shell v2.0+)
- Falls back to `mongo` (legacy MongoDB shell)
- Returns error if neither command is available

### Database Validation
- Validates database existence before attempting views creation
- Returns appropriate error messages for missing databases

### Script Execution
- 60-second timeout for script execution
- Proper cleanup of temporary script files
- Detailed logging of execution results

## Technical Requirements

### System Dependencies
- MongoDB Shell (`mongosh`) or legacy MongoDB shell (`mongo`)
- MongoDB server running and accessible
- Appropriate database permissions for view creation

### Database Structure
The views expect the following collections to exist in the selected database:
- `IndexTick`: Main tick data
- `Index`: Index metadata
- `Option`: Options contract data
- `OptionTick`: Options tick data

## Troubleshooting

### Views Creation Fails
1. **Check MongoDB shell availability**:
   ```bash
   mongosh --version
   # or
   mongo --version
   ```

2. **Check MongoDB connection**:
   ```bash
   mongosh --eval "db.adminCommand('ismaster')"
   ```

3. **Verify database exists**:
   ```bash
   mongosh --eval "show dbs"
   ```

4. **Check collection existence**:
   ```bash
   mongosh [database_name] --eval "show collections"
   ```

### Trading Run Continues Despite Views Failure
- The system is designed to continue with the trading run even if views creation fails
- This ensures that data streaming is not interrupted by views creation issues
- Check the logs for specific error messages about views creation

## Performance Considerations

### Views Creation Time
- Views creation typically takes 10-30 seconds depending on data size
- The process runs synchronously during run startup
- Consider pre-creating views for frequently used databases

### Database Load
- Views creation involves complex aggregation pipelines
- May temporarily increase database load during creation
- Views are stored and don't need to be recreated unless data structure changes

## Security Notes

### API Endpoints
- All views creation endpoints require admin authentication
- Database name validation prevents unauthorized access
- Temporary script files are automatically cleaned up

### MongoDB Commands
- Script execution is isolated to the specific database
- No system-level MongoDB commands are executed
- Proper error handling prevents information disclosure

## Future Enhancements

### Possible Improvements
1. **Async Views Creation**: Execute views creation in background
2. **Views Status Check**: API to check if views exist for a database
3. **Batch Views Creation**: Create views for multiple databases
4. **Custom Views**: Allow configuration of custom views
5. **Views Update**: Refresh existing views with new data

# Trade Parameters Feature

## Overview

The Trade Parameters feature provides a comprehensive CRUD (Create, Read, Update, Delete) interface for managing trading parameters and configurations. It includes Excel/CSV import functionality and a modern web interface for easy parameter management.

## Features

### Core Functionality
- **Create Parameters**: Add new trading parameters with name, value, description, category, data type, and active status
- **Read Parameters**: View all parameters with filtering by category, status, and search functionality
- **Update Parameters**: Modify existing parameters
- **Delete Parameters**: Remove parameters from the system
- **Parameter Categories**: Organize parameters into categories for better management
- **Data Type Support**: Specify data types (int, double, string, boolean, date, datetime, json) for parameters
- **Data Type Validation**: Automatic validation that parameter values match their specified data types

### Import/Export Features
- **Excel Import**: Import parameters from Excel (.xlsx, .xls) files
- **CSV Import**: Import parameters from CSV files
- **Template Download**: Download a sample Excel template with example data
- **Batch Import**: Import multiple parameters at once with validation

### User Interface
- **Modern UI**: Clean, responsive interface built with Vue.js and Tailwind CSS
- **Real-time Filtering**: Filter parameters by category, status, and search terms
- **Modal Forms**: Inline editing and creation forms
- **Status Indicators**: Visual indicators for active/inactive parameters
- **Responsive Design**: Works on desktop and mobile devices

## Database Schema

### Parameters Collection
```javascript
{
  _id: ObjectId,
  name: String,           // Required: Parameter name (unique)
  value: String,          // Required: Parameter value
  description: String,    // Optional: Parameter description
  category: String,       // Optional: Parameter category
  datatype: String,       // Optional: Data type (int, double, string, boolean, date, datetime, json)
  is_active: Boolean,     // Default: true
  created_at: Date,       // Auto-generated
  updated_at: Date,       // Auto-updated
  created_by: String      // User ID who created the parameter
}
```

## API Endpoints

### Parameters CRUD
- `POST /api/parameters` - Create a new parameter
- `GET /api/parameters` - Get all parameters (with optional filtering)
- `GET /api/parameters/{parameter_id}` - Get a specific parameter
- `PUT /api/parameters/{parameter_id}` - Update a parameter
- `DELETE /api/parameters/{parameter_id}` - Delete a parameter

### Categories
- `GET /api/parameters/categories` - Get all parameter categories

### Import/Export
- `POST /api/parameters/import` - Import parameters from Excel/CSV file
- `GET /api/parameters/template` - Download Excel template

### Web Interface
- `GET /parameters` - Parameters management page

## File Import Format

### Required Columns
- `name` - Parameter name (must be unique)
- `value` - Parameter value

### Optional Columns
- `description` - Parameter description
- `category` - Parameter category
- `datatype` - Data type (string, int, double, boolean, date, datetime, json)
- `is_active` - true/false (default: true)

### Example CSV Format
```csv
name,value,description,category,datatype,is_active
max_position_size,1000,Maximum position size for any trade,Risk Management,int,true
stop_loss_percentage,2.5,Stop loss percentage for trades,Risk Management,double,true
trading_hours_start,09:15,Trading session start time,Trading Schedule,string,true
enable_auto_trading,true,Enable automatic trading,Trading Settings,boolean,true
```

### Example Excel Format
The Excel template includes sample data with the same structure as the CSV format.

## Usage Examples

### Creating Parameters via API
```python
import requests

# Create a new parameter
parameter_data = {
    "name": "max_position_size",
    "value": "1000",
    "description": "Maximum position size for any trade",
    "category": "Risk Management",
    "datatype": "int",
    "is_active": True
}

response = requests.post("/api/parameters", json=parameter_data)
```

### Getting Parameters with Filters
```python
# Get all parameters
response = requests.get("/api/parameters")

# Get parameters by category
response = requests.get("/api/parameters?category=Risk Management")

# Get active parameters
response = requests.get("/api/parameters?status=true")
```

### Importing Parameters
```python
import requests

# Upload Excel/CSV file
with open("parameters.xlsx", "rb") as f:
    files = {"file": f}
    response = requests.post("/api/parameters/import", files=files)
```

## Web Interface Features

### Navigation
- Access via "Parameters" link in the main navigation
- Located between "Positions" and "Profile" in the navigation menu

### Main Interface
1. **Header Section**: Title, description, and action buttons
2. **Filters Section**: Category, status, and search filters
3. **Parameters Grid**: Card-based display of all parameters
4. **Action Buttons**: Add, Import, and Download Template

### Parameter Cards
Each parameter is displayed in a card showing:
- Parameter name and description
- Category, data type, and status badges
- Parameter value in a highlighted box
- Edit and delete action buttons
- Creation date

### Modals
- **Create/Edit Modal**: Form for creating or editing parameters
- **Import Modal**: File upload interface with format instructions

## Security

### Authentication
- All endpoints require user authentication
- Parameters are associated with the user who created them
- Admin users can manage all parameters

### Validation
- Parameter names must be unique
- Required fields are validated
- File uploads are validated for format and content
- Data type validation ensures values match their specified types:
  - **int**: Must be a valid integer
  - **double**: Must be a valid number
  - **boolean**: Must be true, false, 1, 0, yes, or no
  - **date**: Must be in YYYY-MM-DD format
  - **datetime**: Must be in YYYY-MM-DD HH:MM:SS format
  - **json**: Must be valid JSON format
  - **string**: No validation (accepts any text)

## Error Handling

### API Errors
- 400: Bad Request (validation errors)
- 401: Unauthorized (authentication required)
- 404: Not Found (parameter not found)
- 500: Internal Server Error

### Import Errors
- File format validation
- Required field validation
- Duplicate name handling
- Detailed error reporting for failed imports

## Testing

Run the test script to verify functionality:
```bash
python test_parameters.py
```

This will test:
- Parameter creation
- Parameter retrieval
- Parameter updates
- Parameter deletion
- Category management
- Database operations

## Dependencies

### Python Dependencies
- `pandas` - Excel/CSV file processing
- `openpyxl` - Excel file support
- `fastapi` - Web framework
- `motor` - MongoDB async driver

### Frontend Dependencies
- `Vue.js` - JavaScript framework
- `Tailwind CSS` - Styling
- `Axios` - HTTP client

## Future Enhancements

### Planned Features
- Parameter versioning and history
- Parameter templates and presets
- Bulk export functionality
- Parameter validation rules
- Parameter dependencies
- Audit logging for parameter changes
- Parameter usage analytics

### Integration Opportunities
- Integration with trading strategies
- Real-time parameter updates
- Parameter-based alerts
- Automated parameter optimization 
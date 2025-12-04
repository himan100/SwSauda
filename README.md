# FastAPI MongoDb Redis Trade Run With User and Roles Module - Trade Run from Mongo Backups

A comprehensive FastAPI-based business management platform with advanced user management, role-based access control, and secure authentication.

<img width="957" height="584" alt="image" src="https://github.com/user-attachments/assets/b77a422f-0f79-4a0b-b037-d1a44bc54b23" />


## Features

### 🔐 Authentication & Security
- JWT-based authentication with secure token handling
- Password hashing using bcrypt
- Role-based access control (RBAC)
- Session management with configurable timeouts

### 👥 User Management
- User registration and profile management
- Role assignment (Super Admin, Admin, User)
- User status management (Active/Inactive)
- Password change functionality
- User activity tracking

### 🎨 Modern UI
- Beautiful, responsive interface built with Tailwind CSS
- Modern design with intuitive navigation
- Mobile-friendly responsive layout
- Interactive components and real-time updates

### 🔧 System Features
- MongoDB database with async operations
- RESTful API endpoints
- Comprehensive error handling
- Logging and monitoring capabilities
- Backup and maintenance features

### 🗄️ Database Management
- View all MongoDB databases
- Create database backups using mongodump
- Restore databases from backups using mongorestore
- Delete databases and backup folders
- Real-time database status monitoring
- Backup folder management with empty folder detection
- Legacy backup support: `Backups/DDMMYYYY/Pinaka/` (Pinaka is the database name)
- New backup format: `Backups/DDMMYYYY/Pinaka/` (same as legacy)
- Restore format: `prefix_YYYYMMDD` (converts DDMMYYYY to YYYYMMDD)
- Date display in DD/MM/YYYY format for user-friendly reading
- Database prefix for restored databases (configurable via DATABASE_PREFIX in .env)

### 📊 Trade Run & MongoDB Views Integration
- **Real-time Trading Data**: Stream IndexTick and OptionTick data via WebSocket
- **Configurable Intervals**: Adjustable streaming frequency (0.1s to 5.0s)
- **Automatic Views Creation**: MongoDB analysis views are automatically created when starting a trading run
- **Manual Views Creation**: Create MongoDB views manually via web interface
- **Analytics Views**: 
  - `v_index_base`: Base index data with calculated strike levels
  - `v_option_pair_base`: Option pair analysis with risk calculations
- **Multi-MongoDB Shell Support**: Compatible with both `mongosh` (v2.0+) and legacy `mongo` shell
- **Error Handling**: Graceful fallback and detailed error reporting
- **See [MONGODB_VIEWS_INTEGRATION.md](docs/MONGODB_VIEWS_INTEGRATION.md) for detailed documentation**

## Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: MongoDB with Motor (async driver)
- **Authentication**: JWT tokens with Python-Jose
- **Password Hashing**: Passlib with bcrypt
- **Frontend**: HTML templates with Tailwind CSS
- **HTTP Client**: Axios for API calls
- **Validation**: Pydantic models

## Installation & Setup

### Quick Start (Automated Setup)

For the fastest setup experience, use the automated setup script:

```bash
# Make the script executable and run it
chmod +x setup.sh
./setup.sh
```

This will:
- Check prerequisites (Docker, Python)
- Create `.env` configuration file
- Start MongoDB and Redis with Docker
- Install Python dependencies
- Verify all services are running

Then start the application:
```bash
python3 main.py
```

### Manual Setup

If you prefer manual setup, follow these steps:

### Prerequisites
- Python 3.8+
- **Option 1 (Recommended): Docker & Docker Compose** for MongoDB and Redis
- **Option 2: Local Installation**
  - MongoDB (local or cloud instance)
  - Redis server
- pip (Python package manager)
- MongoDB Database Tools (for backup/restore functionality)
  - `mongodump` and `mongorestore` commands must be available in PATH
  - Install from: https://docs.mongodb.com/database-tools/installation/
- MongoDB Shell (for views creation functionality)
  - `mongosh` (recommended - MongoDB Shell v2.0+) OR `mongo` (legacy shell)
  - Install mongosh from: https://www.mongodb.com/try/download/shell
  - Ubuntu/Debian: `sudo apt-get install mongodb-mongosh`

### 1. Clone the Repository
```bash
git clone <repository-url>
cd SwSauda
```

### 2. Setup MongoDB and Redis

#### Option A: Using Docker (Recommended)
```bash
# Start MongoDB and Redis with Docker Compose
docker-compose up -d

# Verify services are running
docker-compose ps
```

This will start:
- MongoDB on port 27017
- Redis on port 6379
- MongoDB Express UI on port 8081 (optional)
- Redis Commander UI on port 8082 (optional)

See [DOCKER_SETUP.md](DOCKER_SETUP.md) for detailed Docker documentation.

#### Option B: Local Installation
Install and start MongoDB and Redis locally:
```bash
# Start MongoDB
mongod

# Start Redis (in another terminal)
redis-server
```

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment

#### Option A: Use the Secret Key Generator (Recommended)
```bash
# Generate secret key and create .env file automatically
./scripts/generate_key.sh

# Or use the interactive generator
python scripts/generate_secret_key.py

# Or use the simple generator
python scripts/generate_secret_key_simple.py
```

#### Option B: Manual Configuration
Create a `.env` file in the root directory:
```env
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=swsauda
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
SUPER_ADMIN_EMAIL=admin@swsauda.com
SUPER_ADMIN_PASSWORD=admin123
DATABASE_PREFIX=nifty
```

### 5. Run the Application
```bash
python main.py
```

The application will be available at `http://localhost:8000`

## API Endpoints

### Authentication
- `POST /api/login` - User login
- `POST /api/logout` - User logout

### User Management (Admin Only)
- `GET /api/users` - Get all users
- `POST /api/users` - Create new user
- `PUT /api/users/{user_id}` - Update user
- `DELETE /api/users/{user_id}` - Delete user

### Profile Management
- `GET /api/profile` - Get current user profile
- `PUT /api/profile` - Update profile
- `PUT /api/profile/password` - Change password

### Database Management (Admin Only)
- `GET /api/databases` - Get all MongoDB databases
- `DELETE /api/databases/{database_name}` - Delete a database
- `GET /api/backups` - Get list of backup folders
- `POST /api/backups/{database_name}` - Create backup of a database
- `POST /api/restore/{database_name}` - Restore database from backup
- `DELETE /api/backups/{backup_folder}` - Delete a backup folder

### Frontend Pages
- `GET /` - Landing page
- `GET /login` - Login page
- `GET /dashboard` - Dashboard
- `GET /profile` - Profile page
- `GET /settings` - Settings page
- `GET /users` - Users management
- `GET /roles` - Roles management
- `GET /databases` - Database management

## User Roles & Permissions

### Super Admin
- Full system access
- Create, edit, delete users
- Manage all roles and permissions
- Access system settings
- View all system data
- Manage backups and maintenance
- Full database management access

### Admin
- User management access
- Create, edit, delete users
- View user profiles
- Manage user roles (except super admin)
- Access basic settings
- View system reports
- Database management access

### User
- Basic access
- View own profile
- Edit own profile
- Change own password
- Access dashboard
- View basic reports

## Default Credentials

**Super Admin Account:**
- Email: `admin@swsauda.com`
- Password: `admin123`

## Project Structure

```
SwSauda/
├── main.py              # FastAPI application entry point
├── config.py            # Configuration settings
├── database.py          # Database connection and utilities
├── models.py            # Pydantic models for data validation
├── auth.py              # Authentication and authorization
├── crud.py              # Database CRUD operations
├── requirements.txt     # Python dependencies
├── run.py               # Application startup script
├── test_app.py          # Application testing script
├── scripts/             # Utility scripts
│   ├── generate_secret_key.py        # Interactive secret key generator
│   ├── generate_secret_key_simple.py # Non-interactive secret key generator
│   ├── generate_key.sh               # Shell script wrapper
│   └── README.md                     # Scripts documentation
├── templates/           # HTML templates
│   ├── base.html        # Base template
│   ├── landing.html     # Landing page
│   ├── login.html       # Login page
│   ├── dashboard.html   # Dashboard
│   ├── profile.html     # Profile page
│   ├── settings.html    # Settings page
│   ├── users.html       # Users management
│   ├── roles.html       # Roles management
│   └── databases.html   # Database management
├── Backups/             # Backup storage directory
│   └── DDMMYYYY/        # Date-based backup folders (legacy format)
│       └── Pinaka/      # Database backup (Pinaka is the database name)
└── static/              # Static files (CSS, JS)
    ├── css/
    └── js/
```

## Development

### Running in Development Mode
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### API Documentation
Once the application is running, you can access:
- Interactive API docs: `http://localhost:8000/docs`
- ReDoc documentation: `http://localhost:8000/redoc`

### Database Operations
The application uses MongoDB with the following collections:
- `users` - User accounts and profiles

## Security Features

- **Password Security**: Bcrypt hashing with salt
- **JWT Tokens**: Secure token-based authentication
- **Role-Based Access**: Granular permission system
- **Input Validation**: Pydantic model validation
- **CORS Protection**: Configurable CORS settings
- **Rate Limiting**: Built-in rate limiting capabilities

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For support and questions, please open an issue in the repository.

---

**SwSauda** - Empowering businesses with modern management solutions.

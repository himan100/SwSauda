# SwSauda Scripts

This folder contains utility scripts for the SwSauda application.

## Secret Key Generation Scripts

### 🔐 `generate_secret_key.py` - Interactive Secret Key Generator

A comprehensive, interactive script that generates secure secret keys with multiple options.

**Features:**
- Generates both Base64 and alphanumeric secret keys
- Interactive menu for key selection
- Option to save directly to `.env` file
- Creates complete `.env` template if file doesn't exist
- Updates existing `.env` files safely

**Usage:**
```bash
# From project root
python scripts/generate_secret_key.py

# Or directly
./scripts/generate_secret_key.py
```

**Options:**
1. **Base64 key** (recommended) - Cryptographically secure, base64 encoded
2. **Alphanumeric key** - Human-readable, includes special characters
3. **Both** - Save base64 to `.env`, show both for reference

### 🔐 `generate_secret_key_simple.py` - Non-Interactive Generator

A simple, automation-friendly script that generates and saves a secret key without user interaction.

**Features:**
- Generates Base64 encoded secret key
- Automatically saves to `.env` file
- Creates `.env` template if file doesn't exist
- Updates existing `.env` files
- Perfect for CI/CD pipelines and automation

**Usage:**
```bash
# From project root
python scripts/generate_secret_key_simple.py

# Or directly
./scripts/generate_secret_key_simple.py
```

### 🔐 `generate_key.sh` - Shell Script Wrapper

A convenient shell script wrapper that provides additional features and better user experience.

**Features:**
- Colored output for better readability
- Automatic backup of existing `.env` files
- Python availability check
- Project root detection
- Helpful next steps guidance

**Usage:**
```bash
# From project root
bash scripts/generate_key.sh

# Or directly
./scripts/generate_key.sh
```

## Security Best Practices

### 🔒 Secret Key Requirements

- **Length**: Minimum 32 bytes (256 bits)
- **Entropy**: Use cryptographically secure random generation
- **Storage**: Never commit to version control
- **Rotation**: Change regularly in production

### 🔒 Environment File Security

1. **Never commit `.env` files** to version control
2. **Use `.env.example`** for documentation
3. **Backup existing files** before generation
4. **Set proper file permissions** (600 recommended)
5. **Use different keys** for different environments

## Example Usage

### Quick Setup (Recommended)
```bash
# Generate secret key and create .env file
./scripts/generate_key.sh

# Start the application
python run.py
```

### Manual Setup
```bash
# Generate secret key interactively
python scripts/generate_secret_key.py

# Or generate non-interactively
python scripts/generate_secret_key_simple.py

# Start the application
python run.py
```

### Automation/CI Setup
```bash
# For automated deployments
python scripts/generate_secret_key_simple.py
```

## Generated .env Template

The scripts will create or update a `.env` file with the following structure:

```env
# MongoDB Configuration
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=swsauda

# Security Configuration
SECRET_KEY=your-generated-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Super Admin Configuration
SUPER_ADMIN_EMAIL=admin@swsauda.com
SUPER_ADMIN_PASSWORD=admin123

# Server Configuration (optional)
HOST=0.0.0.0
PORT=8000
RELOAD=true
```

## Troubleshooting

### Common Issues

1. **Permission Denied**
   ```bash
   chmod +x scripts/*.py scripts/*.sh
   ```

2. **Python Not Found**
   ```bash
   # Install Python 3
   sudo apt-get install python3  # Ubuntu/Debian
   brew install python3          # macOS
   ```

3. **MongoDB Not Running**
   ```bash
   # Start MongoDB
   sudo systemctl start mongod   # Linux
   brew services start mongodb   # macOS
   ```

### File Permissions

For production environments, set secure file permissions:

```bash
# Set restrictive permissions on .env file
chmod 600 .env

# Set executable permissions on scripts
chmod 755 scripts/*.py scripts/*.sh
```

## Contributing

When adding new scripts to this folder:

1. Follow the existing naming convention
2. Add proper documentation
3. Include error handling
4. Make scripts executable
5. Update this README

---

**Note**: Always keep your secret keys secure and never share them publicly! 
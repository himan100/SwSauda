#!/usr/bin/env python3
"""
SwSauda - Simple Secret Key Generator
Non-interactive script to generate and save SECRET_KEY to .env file
"""

import secrets
import base64
import sys
from pathlib import Path

def generate_secret_key(length=32):
    """Generate a secure secret key using cryptographically strong random bytes"""
    random_bytes = secrets.token_bytes(length)
    return base64.b64encode(random_bytes).decode('utf-8')

def save_to_env_file(secret_key, env_file=".env"):
    """Save the secret key to .env file"""
    env_path = Path(env_file)
    
    if env_path.exists():
        # Read existing content
        with open(env_path, 'r') as f:
            content = f.read()
        
        # Check if SECRET_KEY already exists
        if 'SECRET_KEY=' in content:
            # Replace existing SECRET_KEY
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if line.startswith('SECRET_KEY='):
                    new_lines.append(f'SECRET_KEY={secret_key}')
                else:
                    new_lines.append(line)
            content = '\n'.join(new_lines)
        else:
            # Add SECRET_KEY to existing content
            content += f'\nSECRET_KEY={secret_key}\n'
    else:
        # Create new .env file with template
        content = f"""# MongoDB Configuration
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=swsauda

# Security Configuration
SECRET_KEY={secret_key}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Super Admin Configuration
SUPER_ADMIN_EMAIL=admin@swsauda.com
SUPER_ADMIN_PASSWORD=admin123

# Server Configuration (optional)
HOST=0.0.0.0
PORT=8000
RELOAD=true
"""
    
    # Write to .env file
    with open(env_path, 'w') as f:
        f.write(content)
    
    return True

def main():
    """Main function"""
    # Generate secret key
    secret_key = generate_secret_key()
    
    # Save to .env file
    if save_to_env_file(secret_key):
        print(f"✅ Secret key generated and saved to .env file")
        print(f"🔑 Key: {secret_key}")
    else:
        print("❌ Failed to save secret key")
        sys.exit(1)

if __name__ == "__main__":
    main() 
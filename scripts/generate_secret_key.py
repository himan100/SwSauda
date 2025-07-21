#!/usr/bin/env python3
"""
SwSauda - Secret Key Generator
Generates a secure SECRET_KEY for JWT token signing
"""

import secrets
import string
import os
import sys
from pathlib import Path

def generate_secret_key(length=32):
    """
    Generate a secure secret key using cryptographically strong random bytes
    
    Args:
        length (int): Length of the secret key (default: 32)
    
    Returns:
        str: Base64 encoded secret key
    """
    # Generate random bytes
    random_bytes = secrets.token_bytes(length)
    
    # Convert to base64 for better readability and storage
    import base64
    secret_key = base64.b64encode(random_bytes).decode('utf-8')
    
    return secret_key

def generate_alternative_key(length=50):
    """
    Generate an alternative secret key using alphanumeric characters
    
    Args:
        length (int): Length of the secret key (default: 50)
    
    Returns:
        str: Alphanumeric secret key
    """
    # Define character set
    characters = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    # Generate random string
    secret_key = ''.join(secrets.choice(characters) for _ in range(length))
    
    return secret_key

def save_to_env_file(secret_key, env_file=".env"):
    """
    Save the secret key to .env file
    
    Args:
        secret_key (str): The generated secret key
        env_file (str): Path to .env file
    """
    env_path = Path(env_file)
    
    # Check if .env file exists
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
    
    print(f"✅ Secret key saved to {env_file}")

def main():
    """Main function"""
    print("🔐 SwSauda Secret Key Generator")
    print("=" * 40)
    
    # Generate secret key
    print("Generating secure secret key...")
    secret_key = generate_secret_key()
    
    print(f"\n🔑 Generated Secret Key (Base64):")
    print(f"   {secret_key}")
    
    # Generate alternative key
    alt_key = generate_alternative_key()
    print(f"\n🔑 Alternative Secret Key (Alphanumeric):")
    print(f"   {alt_key}")
    
    # Ask user which key to use
    print(f"\nWhich key would you like to use?")
    print("1. Base64 key (recommended)")
    print("2. Alphanumeric key")
    print("3. Both (save base64 to .env, show both)")
    
    try:
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == "1":
            selected_key = secret_key
            print(f"\n✅ Using Base64 key")
        elif choice == "2":
            selected_key = alt_key
            print(f"\n✅ Using Alphanumeric key")
        elif choice == "3":
            selected_key = secret_key
            print(f"\n✅ Using Base64 key (saving to .env)")
            print(f"📝 Alphanumeric key (for reference): {alt_key}")
        else:
            print("❌ Invalid choice. Using Base64 key by default.")
            selected_key = secret_key
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled.")
        sys.exit(1)
    
    # Ask if user wants to save to .env file
    if choice in ["1", "2", "3"]:
        try:
            save_choice = input("\nSave to .env file? (y/n): ").strip().lower()
            if save_choice in ['y', 'yes']:
                save_to_env_file(selected_key)
            else:
                print("📝 Secret key not saved to .env file")
                print("   You can manually add it to your .env file:")
                print(f"   SECRET_KEY={selected_key}")
        except KeyboardInterrupt:
            print("\n\n❌ Operation cancelled.")
            sys.exit(1)
    
    print(f"\n🎉 Secret key generation completed!")
    print(f"   Make sure to keep this key secure and never commit it to version control.")

if __name__ == "__main__":
    main() 
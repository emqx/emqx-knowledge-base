#!/usr/bin/env python
"""
Generate a JWT token for local testing.

This script reads the JWT_SECRET from your .env file and generates a valid
JWT token that can be used for testing protected endpoints in production mode.
"""

import sys
import os
import jwt
import time
import uuid
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get JWT secret from environment
jwt_secret = os.getenv("JWT_SECRET")
if not jwt_secret:
    print("ERROR: JWT_SECRET not found in .env file")
    print("Please set JWT_SECRET in your .env file")
    sys.exit(1)

# Set token expiration (default: 24 hours)
expiration_hours = int(os.getenv("TOKEN_EXPIRATION_HOURS", "24"))
expiration = datetime.now(timezone.utc) + timedelta(hours=expiration_hours)

# Create payload
payload = {
    "sub": f"user-{uuid.uuid4()}",  # Subject (user ID)
    "name": "Test User",  # Name for display
    "email": "test@example.com",  # Email for display
    "iat": int(time.time()),  # Issued at
    "exp": int(expiration.timestamp()),  # Expiration time
}

# Generate token
token = jwt.encode(payload, jwt_secret, algorithm="HS256")

# Print token
print("\n=== JWT Token for Testing ===")
print(f"\nToken: {token}\n")
print(f"Expires: {expiration.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"Valid for: {expiration_hours} hours")
print("\nFor WebSocket testing, add this token as a query parameter:")
print(f"ws://localhost:8000/ws/analyze-log?token={token}")
print("\nFor API testing, add this as a header:")
print(f'Authorization: Bearer {token}')
print("\n============================\n") 
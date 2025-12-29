import jwt
import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify

# Secret key for JWT - use environment variable
# In development, use a default key; in production, this MUST be set
JWT_SECRET = os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_DAYS = 7

# Warning: In production, ensure JWT_SECRET_KEY is set to a secure random value


def generate_token(user_id: str) -> str:
    """Generate a JWT token for a user"""
    now = datetime.now(timezone.utc)
    payload = {
        'user_id': user_id,
        'iat': now,
        'exp': now + timedelta(days=JWT_EXPIRY_DAYS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Verify a JWT token and return the payload, or None if invalid"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_user_id_from_token(token: str) -> str | None:
    """Extract user_id from a valid token"""
    payload = verify_token(token)
    if payload:
        return payload.get('user_id')
    return None


def require_auth(f):
    """Decorator to require JWT authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({'error': 'Authorization header is required'}), 401

        # Expected format: "Bearer <token>"
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({'error': 'Invalid authorization header format'}), 401

        token = parts[1]
        payload = verify_token(token)

        if payload is None:
            return jsonify({'error': 'Invalid or expired token'}), 401

        # Add user_id to request context
        request.user_id = payload.get('user_id')

        return f(*args, **kwargs)

    return decorated

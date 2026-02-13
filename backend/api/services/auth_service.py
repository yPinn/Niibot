"""JWT authentication service"""

import logging
from datetime import UTC, datetime, timedelta

import jwt

logger = logging.getLogger(__name__)


class AuthService:
    """Handle JWT token creation and validation"""

    def __init__(self, secret_key: str, algorithm: str = "HS256", expire_days: int = 30):
        if not secret_key:
            raise ValueError("JWT secret key cannot be empty")

        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expire_days = expire_days

    def create_access_token(self, user_id: str, platform: str, platform_user_id: str) -> str:
        """Create a JWT access token for a user"""
        expire = datetime.now(UTC) + timedelta(days=self.expire_days)

        payload = {
            "sub": user_id,
            "platform": platform,
            "platform_user_id": platform_user_id,
            "exp": expire,
            "iat": datetime.now(UTC),
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.debug(f"JWT created for user: {user_id} ({platform}:{platform_user_id})")

        return token

    def verify_token(self, token: str) -> dict | None:
        """Verify a JWT token and return the payload if valid"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id = payload.get("sub")

            if user_id is None:
                logger.warning("Token missing sub")
                return None

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

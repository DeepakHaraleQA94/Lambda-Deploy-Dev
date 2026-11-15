import base64
import hashlib
import hmac
import json
import os
import time
import uuid

from base_service import ApiError


class AuthService:
    """PBKDF2 password verification and HMAC-signed bearer tokens."""

    def __init__(self, user_service):
        self.users = user_service
        self.secret = os.environ.get("AUTH_TOKEN_SECRET", "")
        self.admin_username = os.environ.get("ADMIN_USERNAME", "")
        self.admin_password = os.environ.get("ADMIN_PASSWORD", "")
        self.token_ttl = int(os.environ.get("AUTH_TOKEN_TTL_SECONDS", "3600"))

    @staticmethod
    def hash_password(password: str, salt: str = None) -> dict:
        if not isinstance(password, str) or len(password) < 10:
            raise ApiError(400, "Password must contain at least 10 characters")
        salt = salt or base64.urlsafe_b64encode(os.urandom(16)).decode()
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000)
        return {"passwordSalt": salt, "passwordHash": base64.urlsafe_b64encode(digest).decode()}

    @staticmethod
    def verify_password(password: str, salt: str, expected_hash: str) -> bool:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000)
        actual = base64.urlsafe_b64encode(digest).decode()
        return hmac.compare_digest(actual, expected_hash)

    def _token(self, subject: str, role: str) -> str:
        if len(self.secret) < 32:
            raise ApiError(503, "Set AUTH_TOKEN_SECRET to a random value of at least 32 characters")
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"sub": subject, "role": role, "iat": now, "exp": now + self.token_ttl,
                   "jti": str(uuid.uuid4())}
        encode = lambda obj: base64.urlsafe_b64encode(
            json.dumps(obj, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        unsigned = encode(header) + "." + encode(payload)
        signature = hmac.new(self.secret.encode(), unsigned.encode(), hashlib.sha256).digest()
        return unsigned + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def login(self, username: str, password: str) -> dict:
        if not username or not password:
            raise ApiError(400, "username and password are required")
        if self.admin_username and hmac.compare_digest(username, self.admin_username) and self.admin_password and hmac.compare_digest(password, self.admin_password):
            return {"accessToken": self._token(username, "admin"), "tokenType": "Bearer",
                    "expiresIn": self.token_ttl, "role": "admin"}
        matches = self.users.find_by_username(username)
        if not matches:
            raise ApiError(401, "Invalid username or password")
        user = matches[0]
        if user.get("status", "ACTIVE") != "ACTIVE":
            raise ApiError(403, "User account is inactive")
        if not self.verify_password(password, user.get("passwordSalt", ""), user.get("passwordHash", "")):
            raise ApiError(401, "Invalid username or password")
        return {"accessToken": self._token(user["userId"], user.get("role", "user")),
                "tokenType": "Bearer", "expiresIn": self.token_ttl,
                "role": user.get("role", "user")}

    def verify_token(self, token: str) -> dict:
        if len(self.secret) < 32:
            raise ApiError(503, "Authentication is not configured")
        try:
            head, payload, signature = token.split(".")
            unsigned = head + "." + payload
            expected = hmac.new(self.secret.encode(), unsigned.encode(), hashlib.sha256).digest()
            supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
            if not hmac.compare_digest(expected, supplied):
                raise ValueError("signature")
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            if int(claims["exp"]) <= int(time.time()):
                raise ApiError(401, "Token expired")
            return claims
        except ApiError:
            raise
        except Exception as exc:
            raise ApiError(401, "Invalid bearer token") from exc

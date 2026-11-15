import json
import logging
import os

import boto3

from access_service import AccessService
from auth_service import AuthService
from base_service import ApiError
from expiry_service import AccessExpiryService
from media_service import MediaService
from notification_service import NotificationService
from playlist_service import PlaylistService
from s3_service import S3MediaService
from user_service import UserService

logger = logging.getLogger(__name__)


class CloudMediaAPI:
    """CloudMedia REST API. Admin routes require an admin bearer token."""

    def __init__(self):
        dynamodb = boto3.resource(
            "dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        )
        self.users = UserService(dynamodb)
        self.access = AccessService(dynamodb)
        self.services = {
            "users": self.users,
            "media": MediaService(dynamodb),
            "access": self.access,
            "playlists": PlaylistService(dynamodb),
        }
        self.auth = AuthService(self.users)
        self.s3 = S3MediaService()
        self.expiry = AccessExpiryService(self.access)
        self.notifications = NotificationService()

    @staticmethod
    def _response(status, data):
        return {
            "statusCode": status,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
                "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
            },
            "body": json.dumps(data),
        }

    @staticmethod
    def _body(event):
        raw = event.get("body")
        if not raw:
            return {}
        if event.get("isBase64Encoded"):
            import base64
            raw = base64.b64decode(raw).decode("utf-8")
        try:
            body = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError) as exc:
            raise ApiError(400, "Request body must be valid JSON") from exc
        if not isinstance(body, dict):
            raise ApiError(400, "Request body must be a JSON object")
        return body

    def _claims(self, event):
        headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
        auth_header = headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise ApiError(401, "Bearer token required")
        return self.auth.verify_token(auth_header[7:].strip())

    def _admin(self, event):
        claims = self._claims(event)
        if claims.get("role") != "admin":
            raise ApiError(403, "Administrator access required")
        return claims

    def handle(self, event):
        method = (
            event.get("requestContext", {}).get("http", {}).get("method")
            or event.get("httpMethod") or "GET"
        ).upper()
        path = (event.get("rawPath") or event.get("path") or "/").rstrip("/") or "/"
        if method == "OPTIONS":
            return self._response(200, {"message": "CORS preflight OK"})

        try:
            body = self._body(event)
            query = event.get("queryStringParameters") or {}
            parts = [part for part in path.split("/") if part]
            route = [part.lower() for part in parts]

            # Public login; the configured bootstrap administrator can log in from env vars.
            if route == ["auth", "login"] and method == "POST":
                return self._response(200, self.auth.login(body.get("username"), body.get("password")))

            if route == ["auth", "me"] and method == "GET":
                claims = self._claims(event)
                return self._response(200, {"userId": claims["sub"], "role": claims["role"]})

            # Users may request playback only for media to which their access is active.
            if route == ["media", "playback-url"] and method == "POST":
                claims = self._claims(event)
                media_id = body.get("mediaID")
                if not media_id:
                    raise ApiError(400, "mediaID is required")
                user_id = body.get("userId") if claims.get("role") == "admin" else claims.get("sub")
                if claims.get("role") != "admin":
                    access_result = self.expiry.check_user_access(user_id, media_id)
                    if not access_result.get("allowed"):
                        raise ApiError(403, "Media access is missing or expired")
                media_item = self.services["media"].get(media_id)
                return self._response(200, self.s3.create_playback_url(media_item.get("objectKey")))

            if route == ["access", "check"] and method == "GET":
                claims = self._claims(event)
                user_id = query.get("userId") or claims.get("sub")
                if claims.get("role") != "admin" and user_id != claims.get("sub"):
                    raise ApiError(403, "You can only check your own access")
                media_id = query.get("mediaID")
                if not media_id:
                    raise ApiError(400, "mediaID query parameter is required")
                return self._response(200, self.expiry.check_user_access(user_id, media_id))

            self._admin(event)

            if route == ["media", "upload-url"] and method == "POST":
                return self._response(200, self.s3.create_upload_url(
                    body.get("filename"), body.get("mediaType"), body.get("contentType")
                ))
            if route == ["notifications", "expiry"] and method == "POST":
                return self._response(200, self.notifications.send_expiry_notice(
                    body.get("email"), body.get("username", "")
                ))

            if not route:
                raise ApiError(404, "Route not found")
            resource = route[0]
            service = self.services.get(resource)
            if service is None:
                raise ApiError(404, "Route not found")

            if resource == "access":
                if len(parts) == 1:
                    if method == "POST":
                        return self._response(201, service.create(body))
                    if method == "GET":
                        user_id = query.get("userId")
                        if not user_id:
                            raise ApiError(400, "userId query parameter is required")
                        return self._response(200, service.list(user_id, query.get("limit", 50)))
                elif len(parts) == 3:
                    user_id, media_id = parts[1], parts[2]
                    if method == "GET":
                        return self._response(200, service.get(user_id, media_id))
                    if method == "PATCH":
                        return self._response(200, service.update(user_id, body, media_id))
                    if method == "DELETE":
                        return self._response(200, service.delete(user_id, media_id))
                raise ApiError(405, "Method not allowed")

            if len(parts) == 1:
                if method == "GET":
                    return self._response(200, service.list(limit=query.get("limit", 50)))
                if method == "POST":
                    return self._response(201, service.create(body))
                raise ApiError(405, "Method not allowed")

            if len(parts) == 2:
                record_id = parts[1]
                if method == "GET":
                    return self._response(200, service.get(record_id))
                if method == "PATCH":
                    return self._response(200, service.update(record_id, body))
                if method == "DELETE":
                    return self._response(200, service.delete(record_id))
            raise ApiError(405, "Method not allowed")
        except ApiError as exc:
            return self._response(exc.status_code, {"message": exc.message})
        except Exception:
            logger.exception("CloudMedia API request failed")
            return self._response(500, {"message": "Internal server error"})

import hmac
import json
import logging
import os
from typing import Any, Dict

import boto3

from access_service import AccessService
from base_service import ApiError
from media_service import MediaService
from playlist_service import PlaylistService
from user_service import UserService

logger = logging.getLogger(__name__)


class CloudMediaAPI:
    """Admin-key protected CRUD API for users, media, access, and playlists."""

    def __init__(self):
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        self.services = {
            "users": UserService(dynamodb),
            "media": MediaService(dynamodb),
            "access": AccessService(dynamodb),
            "playlists": PlaylistService(dynamodb),
        }

    @staticmethod
    def _response(status: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "statusCode": status,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Admin-Api-Key",
                "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
            },
            "body": json.dumps(data),
        }

    @staticmethod
    def _body(event: Dict[str, Any]) -> Dict[str, Any]:
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

    @staticmethod
    def _authorize(event: Dict[str, Any]) -> None:
        expected = os.environ.get("ADMIN_API_KEY")
        if not expected:
            raise ApiError(503, "API is not configured: set ADMIN_API_KEY in Lambda environment variables")
        headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
        supplied = headers.get("x-admin-api-key", "")
        if not supplied or not hmac.compare_digest(str(supplied), expected):
            raise ApiError(401, "Unauthorized")

    def handle(self, event: Dict[str, Any]) -> Dict[str, Any]:
        method = (
            event.get("requestContext", {}).get("http", {}).get("method")
            or event.get("httpMethod") or "GET"
        ).upper()
        path = (event.get("rawPath") or event.get("path") or "/").rstrip("/") or "/"
        if method == "OPTIONS":
            return self._response(200, {"message": "CORS preflight OK"})

        try:
            self._authorize(event)
            body = self._body(event)
            query = event.get("queryStringParameters") or {}
            parts = [part for part in path.split("/") if part]
            if not parts:
                raise ApiError(404, "Route not found")

            resource = parts[0].lower()
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

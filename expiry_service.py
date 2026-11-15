from datetime import datetime, timezone

from base_service import ApiError


class AccessExpiryService:
    """Evaluate and expire user-media access records (userId + mediaID key)."""

    def __init__(self, access_service):
        self.access = access_service

    @staticmethod
    def is_expired(item: dict, now=None) -> bool:
        now = now or datetime.now(timezone.utc)
        raw = item.get("expiresAt")
        if not raw:
            return False
        try:
            expiry = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            return expiry <= now
        except ValueError as exc:
            raise ApiError(400, "expiresAt must be an ISO-8601 date/time") from exc

    def check_user_access(self, user_id: str, media_id: str) -> dict:
        item = self.access.get(user_id, media_id)
        expired = self.is_expired(item)
        if expired and item.get("status") != "EXPIRED":
            self.access.update(user_id, {"status": "EXPIRED"}, media_id)
            item["status"] = "EXPIRED"
        allowed = item.get("status", "ACTIVE") == "ACTIVE" and not expired
        return {"allowed": allowed, "status": item.get("status", "ACTIVE"), "access": item}

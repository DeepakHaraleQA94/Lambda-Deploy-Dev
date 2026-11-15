import logging
import os
from datetime import datetime, timezone

import boto3

from base_service import ApiError

logger = logging.getLogger(__name__)


class NotificationService:
    """SES expiry notices and EventBridge-triggered expiry processing."""

    def __init__(self, ses=None, dynamodb=None):
        region = os.environ.get("AWS_REGION", "ap-south-1")
        self.ses = ses or boto3.client("ses", region_name=region)
        self.dynamodb = dynamodb or boto3.resource("dynamodb", region_name=region)
        self.sender = os.environ.get("SES_FROM_EMAIL", "")
        self.access_table = self.dynamodb.Table(
            os.environ.get("ACCESS_TABLE", "CloudMedia-Access-DEV")
        )
        self.users_table = self.dynamodb.Table(
            os.environ.get("USERS_TABLE", "CloudMedia-Users-DEV")
        )

    def send_expiry_notice(self, recipient: str, username: str = "") -> dict:
        if not self.sender:
            raise ApiError(503, "Set SES_FROM_EMAIL and verify it in Amazon SES")
        if not recipient or "@" not in recipient:
            raise ApiError(400, "A valid recipient email is required")
        display = username or "User"
        result = self.ses.send_email(
            Source=self.sender,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": "CloudMedia access expired"},
                "Body": {"Text": {"Data": f"Hello {display}, your CloudMedia access has expired today. Please contact the administrator."}},
            },
        )
        return {"sent": True, "messageId": result.get("MessageId")}

    def process_expired_access(self) -> dict:
        """EventBridge worker: mark expired records and send each user one email."""
        now = datetime.now(timezone.utc)
        scanned = expired = notified = skipped = 0
        params = {}
        while True:
            result = self.access_table.scan(**params)
            for item in result.get("Items", []):
                scanned += 1
                raw = item.get("expiresAt")
                if not raw or item.get("notificationSentAt"):
                    continue
                try:
                    expiry = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                except ValueError:
                    logger.warning("Skipping invalid expiresAt on userId=%s", item.get("userId"))
                    continue
                if expiry > now:
                    continue
                key = {"userId": item["userId"], "mediaID": item["mediaID"]}
                self.access_table.update_item(
                    Key=key,
                    UpdateExpression="SET #status = :expired",
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues={":expired": "EXPIRED"},
                )
                expired += 1
                user = self.users_table.get_item(Key={"userId": item["userId"]}).get("Item", {})
                email = user.get("email")
                if not email or not self.sender:
                    skipped += 1
                    continue
                try:
                    self.send_expiry_notice(email, user.get("username", "User"))
                    self.access_table.update_item(
                        Key=key,
                        UpdateExpression="SET notificationSentAt = :sent",
                        ExpressionAttributeValues={":sent": now.isoformat()},
                    )
                    notified += 1
                except Exception:
                    logger.exception("Expiry email failed for userId=%s", item.get("userId"))
            last_key = result.get("LastEvaluatedKey")
            if not last_key:
                break
            params["ExclusiveStartKey"] = last_key
        return {"scanned": scanned, "expired": expired, "notified": notified, "skipped": skipped}

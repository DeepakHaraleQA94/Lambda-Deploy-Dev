import os

import boto3

from base_service import ApiError


class NotificationService:
    """Send expiry notifications using Amazon SES (verified sender required)."""

    def __init__(self, ses=None):
        self.ses = ses or boto3.client(
            "ses", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        )
        self.sender = os.environ.get("SES_FROM_EMAIL", "")

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

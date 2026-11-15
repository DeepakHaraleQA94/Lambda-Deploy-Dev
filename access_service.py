import calendar
import os
from datetime import datetime, timezone

import boto3

from base_service import ApiError, DynamoService


class AccessService(DynamoService):
    """User-to-media/playlist access; table key is userId + mediaID."""

    DURATIONS = {
        "3_months": 3,
        "1_year": 12,
        "3_years": 36,
        "5_years": 60,
    }

    def __init__(self, dynamodb=None):
        dynamodb = dynamodb or boto3.resource(
            "dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        )
        table = dynamodb.Table(os.environ.get("ACCESS_TABLE", "CloudMedia-Access-DEV"))
        super().__init__(table, partition_key="userId", sort_key="mediaID")

    @staticmethod
    def _add_months(value, months):
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)

    def create(self, item):
        item = dict(item)
        now = datetime.now(timezone.utc)
        item.setdefault("grantedAt", now.isoformat())
        item.setdefault("status", "ACTIVE")
        duration = item.pop("duration", None)
        if duration in self.DURATIONS:
            item["expiresAt"] = self._add_months(now, self.DURATIONS[duration]).isoformat()
        elif duration == "custom":
            if not item.get("expiresAt"):
                raise ApiError(400, "expiresAt is required for custom duration")
        elif duration:
            raise ApiError(400, "duration must be 3_months, 1_year, 3_years, 5_years, or custom")
        elif not item.get("expiresAt"):
            raise ApiError(400, "Provide duration or expiresAt")
        if item.get("resourceType", "media") not in ("media", "playlist"):
            raise ApiError(400, "resourceType must be media or playlist")
        return super().create(item)

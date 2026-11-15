import os
import re
import uuid

import boto3

from base_service import ApiError


class S3MediaService:
    """Generate short-lived S3 upload and playback URLs; files remain private in S3."""

    def __init__(self, client=None):
        self.client = client or boto3.client(
            "s3", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        )
        self.bucket = os.environ.get("MEDIA_BUCKET", "cloudmedia-assets-dev-01")
        self.url_ttl = int(os.environ.get("S3_URL_TTL_SECONDS", "300"))

    def create_upload_url(self, filename: str, media_type: str, content_type: str) -> dict:
        if media_type not in ("video", "audio"):
            raise ApiError(400, "mediaType must be video or audio")
        if not filename or not content_type:
            raise ApiError(400, "filename and contentType are required")
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:120]
        key = f"{media_type}/{uuid.uuid4().hex}/{safe_name}"
        url = self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=self.url_ttl,
        )
        return {"bucket": self.bucket, "objectKey": key, "uploadUrl": url,
                "method": "PUT", "expiresIn": self.url_ttl,
                "requiredHeaders": {"Content-Type": content_type}}

    def create_playback_url(self, object_key: str) -> dict:
        if not object_key or object_key.startswith("/") or ".." in object_key.split("/"):
            raise ApiError(400, "Invalid objectKey")
        url = self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=self.url_ttl,
        )
        return {"playbackUrl": url, "expiresIn": self.url_ttl}

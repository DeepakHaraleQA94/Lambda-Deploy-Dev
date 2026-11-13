import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from cloudmedia_api import CloudMediaAPI

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
USERS_TABLE = os.environ.get("USERS_TABLE", "CloudMedia-Users-DEV")
MEDIA_TABLE = os.environ.get("MEDIA_TABLE", "CloudMedia-Media-DEV")
ACCESS_TABLE = os.environ.get("ACCESS_TABLE", "CloudMedia-Access-DEV")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "cloudmedia-assets-dev-01")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)


def response(status_code, payload):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Admin-Api-Key",
            "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
        },
        "body": json.dumps(payload),
    }


def lambda_handler(event, context):
    """CloudMedia Lambda entry point. GET /health is public; CRUD routes require admin API key."""
    event = event or {}
    method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "GET"
    ).upper()
    path = event.get("rawPath") or event.get("path") or "/health"

    if method == "OPTIONS":
        return response(200, {"message": "CORS preflight OK"})

    if method == "GET" and path.rstrip("/") in ("", "/", "/health"):
        try:
            table_status = {}
            for table_name in (USERS_TABLE, MEDIA_TABLE, ACCESS_TABLE):
                table_status[table_name] = dynamodb.Table(table_name).table_status
            s3.head_bucket(Bucket=MEDIA_BUCKET)
            return response(200, {
                "message": "CloudMedia Lambda is running",
                "region": AWS_REGION,
                "dynamodb": table_status,
                "s3": "connected",
                "bucket": MEDIA_BUCKET,
            })
        except ClientError:
            logger.exception("AWS resource health check failed")
            return response(500, {"message": "AWS resource health check failed"})

    return CloudMediaAPI().handle(event)

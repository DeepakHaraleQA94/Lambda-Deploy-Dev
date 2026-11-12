import json
import os
import logging
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
USERS_TABLE = os.environ.get("USERS_TABLE", "CloudMedia-Users-DEV")
MEDIA_TABLE = os.environ.get("MEDIA_TABLE", "CloudMedia-Media-DEV")
ACCESS_TABLE = os.environ.get("ACCESS_TABLE", "CloudMedia-Access-DEV")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "cloudmedia-assets-dev-01")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)


def response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(payload),
    }


def lambda_handler(event, context):
    """Starter API handler. GET /health verifies configured AWS resources."""
    event = event or {}
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", "GET"))
    )
    path = event.get("rawPath", event.get("path", "/health"))

    if method == "OPTIONS":
        return response(200, {"message": "CORS preflight OK"})

    if path in ("/", "/health") and method == "GET":
        table_status = {}
        try:
            for table_name in (USERS_TABLE, MEDIA_TABLE, ACCESS_TABLE):
                table = dynamodb.Table(table_name)
                table_status[table_name] = table.table_status

            s3.head_bucket(Bucket=MEDIA_BUCKET)

            return response(200, {
                "message": "CloudMedia Lambda is running",
                "region": AWS_REGION,
                "dynamodb": table_status,
                "s3": "connected",
                "bucket": MEDIA_BUCKET,
            })
        except (ClientError, Exception) as exc:
            logger.exception("AWS resource health check failed")
            return response(500, {
                "message": "AWS resource health check failed",
                "error": str(exc),
            })

    return response(404, {"message": "Route not found", "path": path})

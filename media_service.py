import os
import boto3
from base_service import DynamoService


class MediaService(DynamoService):
    """CRUD operations for CloudMedia-Media-DEV (partition key: mediaID)."""
    def __init__(self, dynamodb=None):
        dynamodb = dynamodb or boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        table = dynamodb.Table(os.environ.get("MEDIA_TABLE", "CloudMedia-Media-DEV"))
        super().__init__(table, partition_key="mediaID")

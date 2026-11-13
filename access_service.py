import os
import boto3
from base_service import DynamoService


class AccessService(DynamoService):
    """CRUD operations for CloudMedia-Access-DEV (userId + mediaID composite key)."""
    def __init__(self, dynamodb=None):
        dynamodb = dynamodb or boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        table = dynamodb.Table(os.environ.get("ACCESS_TABLE", "CloudMedia-Access-DEV"))
        super().__init__(table, partition_key="userId", sort_key="mediaID")

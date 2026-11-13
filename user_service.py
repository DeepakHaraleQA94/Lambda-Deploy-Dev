import os
import boto3
from base_service import DynamoService


class UserService(DynamoService):
    """CRUD operations for CloudMedia-Users-DEV (partition key: userId)."""
    def __init__(self, dynamodb=None):
        dynamodb = dynamodb or boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        table = dynamodb.Table(os.environ.get("USERS_TABLE", "CloudMedia-Users-DEV"))
        super().__init__(table, partition_key="userId")

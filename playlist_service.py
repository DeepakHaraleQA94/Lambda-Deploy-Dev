import os
import boto3
from base_service import DynamoService


class PlaylistService(DynamoService):
    """CRUD operations for the planned CloudMedia-Playlists-DEV table (partition key: playlistId)."""
    def __init__(self, dynamodb=None):
        dynamodb = dynamodb or boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        table = dynamodb.Table(os.environ.get("PLAYLISTS_TABLE", "CloudMedia-Playlists-DEV"))
        super().__init__(table, partition_key="playlistId")

import os
import boto3

from base_service import ApiError, DynamoService, json_safe


class UserService(DynamoService):
    """User records. Password hashes are never returned by public CRUD methods."""

    def __init__(self, dynamodb=None):
        dynamodb = dynamodb or boto3.resource(
            "dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        )
        table = dynamodb.Table(os.environ.get("USERS_TABLE", "CloudMedia-Users-DEV"))
        super().__init__(table, partition_key="userId")

    def find_by_username(self, username: str):
        # Username currently has no GSI in the supplied table schema; scan is correct
        # for the present schema but should be replaced with a UsernameIndex at scale.
        result = self.table.scan(
            FilterExpression="#username = :username",
            ExpressionAttributeNames={"#username": "username"},
            ExpressionAttributeValues={":username": username},
            Limit=2,
        )
        return result.get("Items", [])

    @staticmethod
    def _public(item):
        safe = dict(item)
        safe.pop("passwordHash", None)
        safe.pop("passwordSalt", None)
        return json_safe(safe)

    def get(self, user_id, sort_value=None):
        return self._public(super().get(user_id))

    def list(self, partition_value=None, limit=50):
        result = super().list(partition_value, limit)
        result["items"] = [self._public(item) for item in result["items"]]
        return result

    def create_user(self, item):
        if not isinstance(item, dict):
            raise ApiError(400, "A JSON object is required")
        if not item.get("username") or not item.get("password"):
            raise ApiError(400, "username and password are required")
        if self.find_by_username(item["username"]):
            raise ApiError(409, "Username already exists")
        from auth_service import AuthService
        password_fields = AuthService.hash_password(item.pop("password"))
        item.update(password_fields)
        item.setdefault("role", "user")
        item.setdefault("status", "ACTIVE")
        return self._public(super().create(item))

    def create(self, item):
        return self.create_user(item)

    def update(self, user_id, changes, sort_value=None):
        changes = dict(changes)
        if "password" in changes:
            from auth_service import AuthService
            password_fields = AuthService.hash_password(changes.pop("password"))
            changes.update(password_fields)
        if "role" in changes and changes["role"] not in ("admin", "user"):
            raise ApiError(400, "role must be admin or user")
        return self._public(super().update(user_id, changes))

    def delete(self, user_id, sort_value=None):
        return super().delete(user_id)

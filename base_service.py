from decimal import Decimal
from typing import Any, Dict, Optional

from boto3.dynamodb.conditions import Key


class ApiError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


class DynamoService:
    def __init__(self, table, partition_key: str, sort_key: Optional[str] = None):
        self.table = table
        self.partition_key = partition_key
        self.sort_key = sort_key

    def _key(self, partition_value: str, sort_value: Optional[str] = None) -> Dict[str, Any]:
        if not partition_value:
            raise ApiError(400, f"{self.partition_key} is required")
        key = {self.partition_key: partition_value}
        if self.sort_key:
            if not sort_value:
                raise ApiError(400, f"{self.sort_key} is required")
            key[self.sort_key] = sort_value
        return key

    def get(self, partition_value: str, sort_value: Optional[str] = None) -> Dict[str, Any]:
        item = self.table.get_item(Key=self._key(partition_value, sort_value)).get("Item")
        if item is None:
            raise ApiError(404, "Record not found")
        return json_safe(item)

    def list(self, partition_value: Optional[str] = None, limit: int = 50):
        limit = max(1, min(int(limit), 100))
        if partition_value is None:
            result = self.table.scan(Limit=limit)
        else:
            result = self.table.query(
                KeyConditionExpression=Key(self.partition_key).eq(partition_value),
                Limit=limit,
            )
        return {"items": json_safe(result.get("Items", []))}

    def create(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(item, dict) or not item:
            raise ApiError(400, "A JSON object is required")
        key = self._key(
            item.get(self.partition_key),
            item.get(self.sort_key) if self.sort_key else None,
        )
        names = {f"#k{i}": name for i, name in enumerate(key)}
        condition = " AND ".join(f"attribute_not_exists(#k{i})" for i in range(len(names)))
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression=condition,
                ExpressionAttributeNames=names,
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise ApiError(409, "Record already exists") from exc
        return json_safe(item)

    def update(self, partition_value: str, changes: Dict[str, Any], sort_value: Optional[str] = None):
        key = self._key(partition_value, sort_value)
        if not isinstance(changes, dict) or not changes:
            raise ApiError(400, "At least one field to update is required")
        if set(changes).intersection(key):
            raise ApiError(400, "Primary key attributes cannot be changed")

        names = {"#pk": self.partition_key}
        values = {}
        assignments = []
        if self.sort_key:
            names["#sk"] = self.sort_key
        for index, (name, value) in enumerate(changes.items()):
            names[f"#n{index}"] = name
            values[f":v{index}"] = value
            assignments.append(f"#n{index} = :v{index}")

        try:
            result = self.table.update_item(
                Key=key,
                UpdateExpression="SET " + ", ".join(assignments),
                ConditionExpression="attribute_exists(#pk)",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise ApiError(404, "Record not found") from exc
        return json_safe(result.get("Attributes", {}))

    def delete(self, partition_value: str, sort_value: Optional[str] = None):
        try:
            result = self.table.delete_item(
                Key=self._key(partition_value, sort_value),
                ConditionExpression="attribute_exists(#pk)",
                ExpressionAttributeNames={"#pk": self.partition_key},
                ReturnValues="ALL_OLD",
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise ApiError(404, "Record not found") from exc
        item = result.get("Attributes")
        if item is None:
            raise ApiError(404, "Record not found")
        return {"deleted": True, "item": json_safe(item)}

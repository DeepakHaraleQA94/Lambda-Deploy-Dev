import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

from base_service import ApiError, json_safe
from s3_service import S3MediaService
from location_service import LocationService


class ProfileService:
    """Private user profile and identity/education documents stored in DynamoDB + S3."""

    PROFILE_FIELDS = {
        "firstName", "middleName", "lastName", "qualification", "currentAddress",
        "permanentAddress", "mobileNumber", "alternativeMobileNumber", "passingYear",
        "designation", "yearGap", "previousCompanyName", "previousCompanyAddress",
        "currentCountryCode", "currentStateCode", "currentCity",
        "permanentCountryCode", "permanentStateCode", "permanentCity",
        "aadhaarDocumentKey", "panDocumentKey", "degreeDocumentKeys",
        "profilePhotoKey", "passportPhotoKey", "profileUpdatedAt",
    }
    DOCUMENT_TYPES = {
        "aadhaar": {"application/pdf", "image/jpeg", "image/png"},
        "pan": {"application/pdf", "image/jpeg", "image/png"},
        "degree": {"application/pdf", "image/jpeg", "image/png"},
        "profile": {"image/jpeg", "image/png"},
        "passport": {"image/jpeg", "image/png"},
    }

    def __init__(self, users, access_table=None, s3_service=None, rekognition=None):
        self.users = users
        self.access_table = access_table or boto3.resource(
            "dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        ).Table(os.environ.get("ACCESS_TABLE", "CloudMedia-Access-DEV"))
        self.s3 = s3_service or S3MediaService()
        self.rekognition = rekognition or boto3.client(
            "rekognition", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        )
        self.bucket = self.s3.bucket
        self.locations = LocationService()

    def _has_active_access(self, user_id):
        params = {"FilterExpression": Attr("userId").eq(user_id)}
        while True:
            result = self.access_table.scan(**params)
            now = datetime.now(timezone.utc)
            for item in result.get("Items", []):
                if item.get("status", "ACTIVE") != "ACTIVE":
                    continue
                expiry = item.get("expiresAt")
                if not expiry:
                    return True
                try:
                    dt = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt > now:
                        return True
                except ValueError:
                    continue
            if "LastEvaluatedKey" not in result:
                return False
            params["ExclusiveStartKey"] = result["LastEvaluatedKey"]

    def _profile(self, user_id):
        user = self.users.get(user_id)
        return user.get("profile", {})

    def get_profile(self, user_id, viewer_is_admin=False):
        if not viewer_is_admin and not self._has_active_access(user_id):
            raise ApiError(403, "Profile viewing is available only while your access is active")
        return json_safe(self._profile(user_id))

    def update_profile(self, user_id, changes):
        if not isinstance(changes, dict) or not changes:
            raise ApiError(400, "Profile fields are required")
        unknown = set(changes) - self.PROFILE_FIELDS
        if unknown:
            raise ApiError(400, "Unsupported profile fields: " + ", ".join(sorted(unknown)))
        # File keys are only written by the upload-completion endpoint.
        protected = {"aadhaarDocumentKey", "panDocumentKey", "degreeDocumentKeys",
                     "profilePhotoKey", "passportPhotoKey", "profileUpdatedAt"}
        if protected.intersection(changes):
            raise ApiError(400, "Document and photo fields must be updated through secure upload")
        for field in ("mobileNumber", "alternativeMobileNumber"):
            if field in changes and changes[field] and not re.fullmatch(r"[0-9+ -]{7,20}", str(changes[field])):
                raise ApiError(400, f"{field} format is invalid")
        if "passingYear" in changes and changes["passingYear"] not in ("", None):
            year = int(changes["passingYear"])
            if year < 1950 or year > datetime.now().year + 1:
                raise ApiError(400, "passingYear is outside the allowed range")
        # Validate hierarchical current/permanent address selections.
        for prefix in ("current", "permanent"):
            keys = (prefix + "CountryCode", prefix + "StateCode", prefix + "City")
            if any(key in changes for key in keys):
                merged = dict(self._profile(user_id))
                merged.update(changes)
                if not all(merged.get(key) for key in keys):
                    raise ApiError(400, "Select country, state and city for " + prefix + " address")
                selected = self.locations.validate_selection(
                    merged[keys[0]], merged[keys[1]], merged[keys[2]]
                )
                changes[keys[0]] = selected["countryCode"]
                changes[keys[1]] = selected["stateCode"]
                changes[keys[2]] = selected["city"]
        current = self._profile(user_id)
        current.update(changes)
        current["profileUpdatedAt"] = datetime.now(timezone.utc).isoformat()
        self.users.update(user_id, {"profile": current})
        return json_safe(current)

    def create_document_upload(self, user_id, doc_type, filename, content_type):
        if doc_type not in self.DOCUMENT_TYPES:
            raise ApiError(400, "Unsupported document type")
        if content_type not in self.DOCUMENT_TYPES[doc_type]:
            raise ApiError(400, "Unsupported file content type for this document")
        if not filename:
            raise ApiError(400, "filename is required")
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:100]
        key = f"private-profiles/{user_id}/{doc_type}/{uuid.uuid4().hex}-{safe}"
        params = {"Bucket": self.bucket, "Key": key, "ContentType": content_type,
                  "ServerSideEncryption": "AES256"}
        url = self.s3.client.generate_presigned_url(
            "put_object", Params=params, ExpiresIn=self.s3.url_ttl
        )
        return {"objectKey": key, "uploadUrl": url, "method": "PUT",
                "requiredHeaders": {"Content-Type": content_type,
                                    "x-amz-server-side-encryption": "AES256"},
                "expiresIn": self.s3.url_ttl}

    def complete_document_upload(self, user_id, doc_type, object_key):
        prefix = f"private-profiles/{user_id}/{doc_type}/"
        if doc_type not in self.DOCUMENT_TYPES or not object_key or not object_key.startswith(prefix):
            raise ApiError(400, "Invalid profile document key")
        try:
            head = self.s3.client.head_object(Bucket=self.bucket, Key=object_key)
        except Exception as exc:
            raise ApiError(400, "Uploaded document could not be found") from exc
        content_type = head.get("ContentType", "")
        if content_type not in self.DOCUMENT_TYPES[doc_type]:
            raise ApiError(400, "Uploaded document content type is not allowed")
        profile = self._profile(user_id)
        field = {"aadhaar": "aadhaarDocumentKey", "pan": "panDocumentKey",
                 "degree": "degreeDocumentKeys", "profile": "profilePhotoKey",
                 "passport": "passportPhotoKey"}[doc_type]
        if doc_type in ("profile", "passport"):
            if head.get("ContentLength", 0) > 5 * 1024 * 1024:
                raise ApiError(400, "Photo must be 5 MB or smaller")
            try:
                face_result = self.rekognition.detect_faces(
                    Image={"S3Object": {"Bucket": self.bucket, "Name": object_key}},
                    Attributes=["DEFAULT"],
                )
            except Exception as exc:
                raise ApiError(422, "Photo face-quality check failed; upload a clear JPG or PNG") from exc
            faces = face_result.get("FaceDetails", [])
            if len(faces) != 1:
                raise ApiError(422, "Photo must contain exactly one clearly visible face")
            face = faces[0]
            quality = face.get("Quality", {})
            if face.get("Confidence", 0) < 90 or quality.get("Sharpness", 0) < 60 or quality.get("Brightness", 0) < 35:
                raise ApiError(422, "Face is not clear enough; upload a sharp, well-lit front-facing photo")
            if face.get("Pose", {}).get("Yaw", 99) > 25 or face.get("Pose", {}).get("Yaw", -99) < -25:
                raise ApiError(422, "Please upload a front-facing photo")
        if doc_type == "degree":
            profile.setdefault(field, []).append(object_key)
        else:
            profile[field] = object_key
        profile["profileUpdatedAt"] = datetime.now(timezone.utc).isoformat()
        self.users.update(user_id, {"profile": profile})
        return {"uploaded": True, "documentType": doc_type,
                "faceQualityChecked": doc_type in ("profile", "passport")}

    def create_view_url(self, viewer_id, target_user_id, object_key, viewer_is_admin=False):
        if not viewer_is_admin:
            if viewer_id != target_user_id:
                raise ApiError(403, "You can view only your own profile documents")
            if not self._has_active_access(target_user_id):
                raise ApiError(403, "Profile documents are available only while your access is active")
        profile = self._profile(target_user_id)
        allowed = {profile.get("aadhaarDocumentKey"), profile.get("panDocumentKey"),
                   profile.get("profilePhotoKey"), profile.get("passportPhotoKey")}
        allowed.update(profile.get("degreeDocumentKeys", []))
        if object_key not in allowed or not object_key.startswith(f"private-profiles/{target_user_id}/"):
            raise ApiError(403, "Document does not belong to this profile")
        url = self.s3.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=min(self.s3.url_ttl, 300),
        )
        return {"viewUrl": url, "expiresIn": min(self.s3.url_ttl, 300)}

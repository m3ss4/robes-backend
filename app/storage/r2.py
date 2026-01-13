import os
from typing import Tuple, Dict

import boto3
from botocore.client import Config

R2_BUCKET = os.environ.get("R2_BUCKET", "")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_REGION = os.environ.get("R2_REGION", "auto")
R2_CDN_BASE = os.environ.get("R2_CDN_BASE", "").rstrip("/")


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
        region_name=R2_REGION,
        config=Config(signature_version="s3v4"),
    )


def object_url(key: str) -> str:
    if R2_CDN_BASE:
        return f"{R2_CDN_BASE}/{key}"
    base = R2_ENDPOINT.rstrip("/")
    return f"{base}/{R2_BUCKET}/{key}"


def presign_put(key: str, content_type: str, expires: int = 900) -> Tuple[str, Dict[str, str]]:
    s3 = r2_client()
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": R2_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )
    headers = {"Content-Type": content_type}
    return url, headers


def presign_get(key: str, expires: int = 900, bucket: str | None = None) -> str:
    s3 = r2_client()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket or R2_BUCKET, "Key": key},
        ExpiresIn=expires,
    )
    return url

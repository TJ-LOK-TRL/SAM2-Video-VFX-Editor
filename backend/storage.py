"""S3-compatible object storage client (MinIO or Cloudflare R2).

Used to share files (uploaded videos, generated masks) between the Flask API,
the Celery worker and the SAM2 job, which run in separate pods with no shared disk.
"""

import os

import boto3
from botocore.client import Config

VIDEOS_BUCKET = os.getenv('R2_BUCKET_VIDEOS', 'videos')
OUTPUTS_BUCKET = os.getenv('R2_BUCKET_OUTPUTS', 'outputs')


def get_storage_client():
    provider = os.getenv('STORAGE_PROVIDER', 'minio').lower()

    if provider == 'r2':
        return boto3.client(
            's3',
            endpoint_url=os.environ['R2_ENDPOINT'],
            aws_access_key_id=os.environ['R2_ACCESS_KEY'],
            aws_secret_access_key=os.environ['R2_SECRET_KEY'],
            config=Config(signature_version='s3v4'),
        )

    return boto3.client(
        's3',
        endpoint_url=os.getenv('MINIO_URL', 'http://minio:9000'),
        aws_access_key_id=os.environ['MINIO_USER'],
        aws_secret_access_key=os.environ['MINIO_PASSWORD'],
        config=Config(signature_version='s3v4'),
    )


def upload_file(local_path: str, bucket: str, key: str) -> None:
    get_storage_client().upload_file(local_path, bucket, key)


def download_file(bucket: str, key: str, local_path: str) -> None:
    get_storage_client().download_file(bucket, key, local_path)


def put_bytes(bucket: str, key: str, data: bytes) -> None:
    get_storage_client().put_object(Bucket=bucket, Key=key, Body=data)


def get_bytes(bucket: str, key: str) -> bytes:
    return get_storage_client().get_object(Bucket=bucket, Key=key)['Body'].read()


def delete_object(bucket: str, key: str) -> None:
    get_storage_client().delete_object(Bucket=bucket, Key=key)

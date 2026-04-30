from minio import Minio
from minio.error import S3Error
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# ── Client ────────────────────────────────────────────────────────────────────

minio_client = Minio(
    endpoint=settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def ensure_bucket_exists() -> None:
    """Create the MinIO bucket if it does not exist. Called at startup."""
    bucket = settings.minio_bucket_name
    try:
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
            logger.info(f"MinIO bucket '{bucket}' created.")
        else:
            logger.info(f"MinIO bucket '{bucket}' already exists.")
    except S3Error as e:
        logger.error(f"MinIO bucket setup failed: {e}")
        raise


def upload_file(file_id: str, filename: str, file_path: str, content_type: str) -> str:
    """
    Upload a file to MinIO.
    Returns the object path: '{file_id}/{filename}'
    """
    object_name = f"{file_id}/{filename}"
    minio_client.fput_object(
        bucket_name=settings.minio_bucket_name,
        object_name=object_name,
        file_path=file_path,
        content_type=content_type,
    )
    return object_name


def download_file(object_name: str, dest_path: str) -> None:
    """Download a file from MinIO to a local path."""
    minio_client.fget_object(
        bucket_name=settings.minio_bucket_name,
        object_name=object_name,
        file_path=dest_path,
    )


def delete_file(object_name: str) -> None:
    """Delete a file from MinIO."""
    try:
        minio_client.remove_object(
            bucket_name=settings.minio_bucket_name,
            object_name=object_name,
        )
    except S3Error as e:
        logger.warning(f"MinIO delete failed for '{object_name}': {e}")

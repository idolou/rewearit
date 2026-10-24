"""S3 / MinIO object storage helper for garment photos."""
import io
import uuid
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from app.core.config import settings
from app.core.logging import logger


class S3Storage:
    """Manages raw and studio-enhanced image assets in MinIO S3."""

    def __init__(self) -> None:
        self.endpoint_url = settings.S3_ENDPOINT
        self.bucket = settings.S3_BUCKET_GARMENTS
        self._config = Config(
            connect_timeout=1.0,
            read_timeout=1.0,
            retries={"max_attempts": 1},
        )
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name="us-east-1",
            config=self._config,
        )
        self._bucket_verified = False
        self._s3_available: bool | None = None

    def _ensure_bucket(self) -> None:
        if self._bucket_verified:
            return
        try:
            self._client.create_bucket(Bucket=self.bucket)
            self._bucket_verified = True
            self._s3_available = True
        except (ClientError, EndpointConnectionError, Exception) as e:
            logger.debug(f"S3 bucket creation or check note ({self.bucket}): {e}")
            self._bucket_verified = True
            self._s3_available = False

    def upload_bytes(
        self,
        data: bytes,
        filename: str | None = None,
        content_type: str = "image/jpeg",
        prefix: str = "garments",
    ) -> str:
        """Upload image bytes and return public URL."""
        if not filename:
            ext = "png" if "png" in content_type else "jpg"
            filename = f"{prefix}/{uuid.uuid4().hex[:12]}.{ext}"

        self._ensure_bucket()
        if self._s3_available is not False:
            try:
                self._client.put_object(
                    Bucket=self.bucket,
                    Key=filename,
                    Body=io.BytesIO(data),
                    ContentType=content_type,
                )
            except Exception as e:
                logger.warning(f"Could not upload image {filename} to MinIO ({e}). Returning direct URL.")
                self._s3_available = False

        return f"{self.endpoint_url}/{self.bucket}/{filename}"

import os
import uuid
import logging
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


def _s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )


def upload_resume(file, user_id: int) -> str:
    """
    Upload a resume PDF and return its S3 key.
    In dev (USE_S3=False), saves to /tmp/resumes/ and returns a fake key.
    """
    key = f'resumes/user_{user_id}/{uuid.uuid4()}.pdf'

    if not settings.USE_S3:
        dev_path = Path('/tmp') / key
        dev_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dev_path, 'wb') as f:
            for chunk in file.chunks():
                f.write(chunk)
        logger.debug('DEV: resume saved to %s', dev_path)
        return key

    try:
        _s3_client().upload_fileobj(
            file,
            settings.AWS_S3_BUCKET,
            key,
            ExtraArgs={'ContentType': 'application/pdf'},
        )
        logger.info('Resume uploaded to S3: %s', key)
        return key
    except (BotoCoreError, ClientError) as e:
        logger.exception('S3 upload failed for user %s: %s', user_id, e)
        raise


def delete_resume(s3_key: str) -> None:
    """Delete a resume from S3 (or /tmp in dev)."""
    if not settings.USE_S3:
        dev_path = Path('/tmp') / s3_key
        dev_path.unlink(missing_ok=True)
        return

    try:
        _s3_client().delete_object(Bucket=settings.AWS_S3_BUCKET, Key=s3_key)
        logger.info('Resume deleted from S3: %s', s3_key)
    except (BotoCoreError, ClientError) as e:
        logger.exception('S3 delete failed for key %s: %s', s3_key, e)
        raise


def get_resume_url(s3_key: str, expires_in: int = 3600) -> str:
    """
    Generate a presigned GET URL for a resume.
    Useful for letting the user preview/download their own resume.
    Returns a /tmp path in dev.
    """
    if not settings.USE_S3:
        return f'file:///tmp/{s3_key}'

    try:
        url = _s3_client().generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.AWS_S3_BUCKET, 'Key': s3_key},
            ExpiresIn=expires_in,
        )
        return url
    except (BotoCoreError, ClientError) as e:
        logger.exception('Failed to generate presigned URL for %s: %s', s3_key, e)
        raise
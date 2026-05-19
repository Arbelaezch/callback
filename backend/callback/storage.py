import os
import uuid
from pathlib import Path
from django.conf import settings

# S3 SCAFFOLD:
# import boto3
# from django.conf import settings
# s3 = boto3.client(
#     's3',
#     aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
#     aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
#     region_name=os.environ['AWS_REGION'],
# )


def upload_resume(file, user_id: int) -> str:
    """
    Upload a resume PDF and return its S3 key.
    In dev, saves to /tmp/resumes/ and returns a fake key.

    S3 SCAFFOLD:
    Replace the dev block with:
        key = f'resumes/user_{user_id}/{uuid.uuid4()}.pdf'
        s3.upload_fileobj(
            file,
            os.environ['AWS_S3_BUCKET'],
            key,
            ExtraArgs={'ContentType': 'application/pdf'},
        )
        return key
    """
    key = f'resumes/user_{user_id}/{uuid.uuid4()}.pdf'

    if settings.DEBUG:
        dev_path = Path('/tmp') / key
        dev_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dev_path, 'wb') as f:
            for chunk in file.chunks():
                f.write(chunk)
        return key

    # S3 SCAFFOLD: replace above with real S3 upload
    raise NotImplementedError('S3 upload not configured for production yet.')


def delete_resume(s3_key: str) -> None:
    """
    Delete a resume from S3 by key.

    S3 SCAFFOLD:
    Replace with:
        s3.delete_object(Bucket=os.environ['AWS_S3_BUCKET'], Key=s3_key)
    """
    if os.environ.get('DEBUG', 'True') == 'True':
        dev_path = Path('/tmp') / s3_key
        dev_path.unlink(missing_ok=True)
        return

    # S3 SCAFFOLD: replace above with real S3 delete
    raise NotImplementedError('S3 delete not configured for production yet.')
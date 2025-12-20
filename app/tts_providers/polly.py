"""AWS Polly TTS provider implementation"""

import logging
import os
from typing import Optional, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError

DISPLAY_NAME = "AWS Polly"

logger = logging.getLogger(__name__)

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_POLLY_REGION = os.getenv("AWS_POLLY_REGION", "us-east-1")


def is_configured() -> Tuple[bool, Optional[str]]:
    """Check whether the provider can be used"""
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        return False, "AWS credentials not configured"
    return True, None


async def generate_audio(text: str) -> Tuple[bytes, str]:
    """Convert text to speech using AWS Polly with Amy voice

    Returns:
        tuple: (audio_content, error_message)
        - audio_content: MP3 audio bytes if successful, empty bytes if failed
        - error_message: Empty string if successful, error description if failed
    """
    configured, reason = is_configured()
    if not configured:
        logger.warning(reason)
        return b"", reason or "AWS Polly provider unavailable"

    try:
        # Create Polly client
        polly_client = boto3.client(
            'polly',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_POLLY_REGION
        )

        # Wrap text in SSML with prosody for medium rate and 1 second pause
        ssml_text = f'<speak><break time="1s"/><prosody rate="medium">{text}</prosody></speak>'

        logger.info(f"AWS Polly Request: Voice=Amy, Engine=neural")

        # Synthesize speech
        response = polly_client.synthesize_speech(
            Text=ssml_text,
            TextType='ssml',
            OutputFormat='mp3',
            VoiceId='Amy',
            Engine='neural',
            SampleRate='24000'
        )

        # Read audio stream
        audio_content = response['AudioStream'].read()

        logger.info(f"AWS Polly Response: Success, {len(audio_content)} bytes")
        return audio_content, ""

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"AWS Polly ClientError: {error_code} - {error_msg}")
        return b"", f"AWS Polly error: {error_code} - {error_msg}"
    except BotoCoreError as e:
        logger.error(f"AWS Polly BotoCoreError: {str(e)}")
        return b"", f"AWS Polly connection error: {str(e)}"
    except Exception as e:
        logger.error(f"AWS Polly Unexpected Error: {str(e)}")
        return b"", f"AWS Polly unexpected error: {str(e)}"

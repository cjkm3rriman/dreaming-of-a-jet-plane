"""Provider registry for text-to-speech services"""

from typing import Awaitable, Callable, Dict, Any, Optional, Tuple

from .elevenlabs import (
    generate_audio as generate_elevenlabs_audio,
    is_configured as elevenlabs_is_configured,
    DISPLAY_NAME as ELEVENLABS_DISPLAY_NAME,
)
from .polly import (
    generate_audio as generate_polly_audio,
    is_configured as polly_is_configured,
    DISPLAY_NAME as POLLY_DISPLAY_NAME,
)
from .google import (
    generate_audio as generate_google_audio,
    is_configured as google_is_configured,
    DISPLAY_NAME as GOOGLE_DISPLAY_NAME,
)
from .inworld import (
    generate_audio as generate_inworld_audio,
    is_configured as inworld_is_configured,
    DISPLAY_NAME as INWORLD_DISPLAY_NAME,
)

AudioResult = Tuple[bytes, str]
AudioGenerator = Callable[[str], Awaitable[AudioResult]]
ProviderConfigCheck = Callable[[], Tuple[bool, Optional[str]]]


class ProviderDefinition(Dict[str, Any]):
    """Typed dict alias for provider metadata"""


TTS_PROVIDERS: Dict[str, ProviderDefinition] = {
    "elevenlabs": {
        "display_name": ELEVENLABS_DISPLAY_NAME,
        "generate_audio": generate_elevenlabs_audio,
        "is_configured": elevenlabs_is_configured,
        "file_extension": "mp3",
        "mime_type": "audio/mpeg",
        "voice_folder": "edward",
    },
    "polly": {
        "display_name": POLLY_DISPLAY_NAME,
        "generate_audio": generate_polly_audio,
        "is_configured": polly_is_configured,
        "file_extension": "mp3",
        "mime_type": "audio/mpeg",
        "voice_folder": "amy",
    },
    "google": {
        "display_name": GOOGLE_DISPLAY_NAME,
        "generate_audio": generate_google_audio,
        "is_configured": google_is_configured,
        "file_extension": "mp3",
        "mime_type": "audio/mpeg",
        "voice_folder": "sadachbia",
    },
    "inworld": {
        "display_name": INWORLD_DISPLAY_NAME,
        "generate_audio": generate_inworld_audio,
        "is_configured": inworld_is_configured,
        "file_extension": "mp3",
        "mime_type": "audio/mpeg",
        "voice_folder": "hamish",
    },
}


def get_provider_names() -> list[str]:
    """Return all registered provider keys"""
    return list(TTS_PROVIDERS.keys())


def get_provider_definition(name: str) -> Optional[ProviderDefinition]:
    """Return the provider definition if registered"""
    return TTS_PROVIDERS.get(name)


def get_audio_format(provider: str) -> Tuple[str, str]:
    """Get the audio file extension and MIME type for a provider

    Args:
        provider: Provider name (e.g., "elevenlabs", "polly", "google")

    Returns:
        tuple: (file_extension, mime_type)
        - file_extension: "mp3" or "ogg"
        - mime_type: "audio/mpeg" or "audio/ogg"
    """
    provider_def = get_provider_definition(provider.lower())
    if provider_def:
        return provider_def["file_extension"], provider_def["mime_type"]
    return "mp3", "audio/mpeg"


def get_voice_folder(provider: str) -> str:
    """Get the voice folder name for a provider

    Args:
        provider: Provider name (e.g., "elevenlabs", "polly", "google")

    Returns:
        str: Voice folder name (e.g., "edward", "amy", "sadachbia")
    """
    provider_def = get_provider_definition(provider.lower())
    if provider_def:
        return provider_def["voice_folder"]
    return "edward"  # Default fallback

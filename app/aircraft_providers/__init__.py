"""Provider registry for live aircraft data sources"""

from typing import Awaitable, Callable, Dict, Any, List, Optional, Tuple

from .fr24 import (
    fetch_aircraft as fetch_fr24_aircraft,
    is_configured as fr24_is_configured,
    DISPLAY_NAME as FR24_DISPLAY_NAME,
)
from .airlabs import (
    fetch_aircraft as fetch_airlabs_aircraft,
    is_configured as airlabs_is_configured,
    DISPLAY_NAME as AIRLABS_DISPLAY_NAME,
)

ProviderResult = Tuple[List[Dict[str, Any]], str]
ProviderFetcher = Callable[[float, float, float, int], Awaitable[ProviderResult]]
ProviderConfigCheck = Callable[[], Tuple[bool, Optional[str]]]


class ProviderDefinition(Dict[str, Any]):
    """Typed dict alias for provider metadata"""


AIRCRAFT_PROVIDERS: Dict[str, ProviderDefinition] = {
    "fr24": {
        "display_name": FR24_DISPLAY_NAME,
        "fetch": fetch_fr24_aircraft,
        "is_configured": fr24_is_configured,
    },
    "airlabs": {
        "display_name": AIRLABS_DISPLAY_NAME,
        "fetch": fetch_airlabs_aircraft,
        "is_configured": airlabs_is_configured,
    },
}


def get_provider_names() -> List[str]:
    """Return all registered provider keys"""
    return list(AIRCRAFT_PROVIDERS.keys())


def get_provider_definition(name: str) -> Optional[ProviderDefinition]:
    """Return the provider definition if registered"""
    return AIRCRAFT_PROVIDERS.get(name)

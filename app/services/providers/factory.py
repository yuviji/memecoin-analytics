"""
Provider factory for creating market data provider instances.
"""

from typing import Dict, Type
from app.services.providers.base import BaseMarketDataProvider
from app.services.providers.helius import HeliusProvider


# Registry of available providers
PROVIDERS: Dict[str, Type[BaseMarketDataProvider]] = {
    "helius": HeliusProvider,
}

DEFAULT_PROVIDER = "helius"


def get_provider(provider_name: str) -> BaseMarketDataProvider:
    """
    Get a provider instance by name.
    
    Args:
        provider_name: Name of the provider
        
    Returns:
        Provider instance
        
    Raises:
        ValueError: If provider is not found
    """
    if provider_name not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_name}")
    
    provider_class = PROVIDERS[provider_name]
    return provider_class()


def get_default_provider() -> BaseMarketDataProvider:
    """Get the default provider instance."""
    return get_provider(DEFAULT_PROVIDER)


def get_available_providers() -> list[str]:
    """Get list of available provider names."""
    return list(PROVIDERS.keys()) 
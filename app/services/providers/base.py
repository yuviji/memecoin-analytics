"""
Base provider class and common exceptions for market data providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass


class MarketDataProviderError(Exception):
    """Base exception for market data provider errors."""
    pass


class RateLimitError(MarketDataProviderError):
    """Exception raised when rate limit is exceeded."""
    pass


class SymbolNotFoundError(MarketDataProviderError):
    """Exception raised when symbol is not found."""
    pass


class ProviderUnavailableError(MarketDataProviderError):
    """Exception raised when provider is unavailable."""
    pass


@dataclass
class PriceData:
    """Data class for price information."""
    symbol: str
    price: float
    timestamp: datetime
    provider: str
    volume: Optional[float] = None
    market_cap: Optional[float] = None
    change_24h: Optional[float] = None
    raw_data: Optional[Dict[str, Any]] = None


class BaseMarketDataProvider(ABC):
    """Base class for all market data providers."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def get_latest_price(self, symbol: str) -> PriceData:
        """Get the latest price for a symbol."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available."""
        pass
    
    @abstractmethod
    async def get_supported_symbols(self) -> list[str]:
        """Get list of supported symbols."""
        pass 
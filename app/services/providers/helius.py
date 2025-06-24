"""
Helius provider for Solana token market data.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.services.providers.base import (
    BaseMarketDataProvider, PriceData, 
    SymbolNotFoundError, RateLimitError, ProviderUnavailableError
)
from app.services.solana.helius_client import HeliusRPCClient


class HeliusProvider(BaseMarketDataProvider):
    """Helius API provider for Solana token data."""
    
    def __init__(self):
        super().__init__("helius")
        self.client = HeliusRPCClient()
    
    async def get_latest_price(self, symbol: str) -> PriceData:
        """Get the latest price for a token symbol."""
        try:
            # Use the actual Helius client integration
            async with self.client as client:
                # Convert symbol to token address lookup (this would need a symbol->address mapping)
                # For now, treat symbol as address if it looks like a Solana address
                token_address = symbol if len(symbol) > 32 else None
                
                if not token_address:
                    raise SymbolNotFoundError(f"Cannot resolve symbol to token address: {symbol}")
                
                # Get real price data from Jupiter via Helius
                price_data = await client.get_token_price_jupiter(token_address)
                
                if not price_data:
                    raise SymbolNotFoundError(f"Token price not found: {symbol}")
                
                return PriceData(
                    symbol=symbol.upper(),
                    price=price_data["price"],
                    timestamp=price_data["timestamp"],
                    provider=self.name,
                    volume=None,  # Volume would come from transaction analysis
                    raw_data=price_data
                )
                
        except SymbolNotFoundError:
            raise
        except Exception as e:
            if "not found" in str(e).lower():
                raise SymbolNotFoundError(f"Symbol {symbol} not found")
            elif "rate limit" in str(e).lower():
                raise RateLimitError(f"Rate limit exceeded for {symbol}")
            else:
                raise ProviderUnavailableError(f"Provider error: {str(e)}")
    
    async def is_available(self) -> bool:
        """Check if the Helius provider is available."""
        try:
            # Test with a known token address (SOL)
            async with self.client as client:
                test_result = await client.get_token_price_jupiter("So11111111111111111111111111111111111111112")
                return test_result is not None
        except Exception:
            return False
    
    async def get_supported_symbols(self) -> list[str]:
        """Get list of supported symbols."""
        # Return common Solana token addresses instead of symbols
        return [
            "So11111111111111111111111111111111111111112",  # SOL
            "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
            "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
            "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",  # RAY
        ] 
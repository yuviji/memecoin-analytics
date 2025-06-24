"""
Helius-enhanced Solana RPC client for token analytics.
Implements core Solana RPC methods with Helius infrastructure for improved reliability and enhanced data.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Union
from decimal import Decimal

import httpx
from solders.pubkey import Pubkey

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SolanaRPCError(Exception):
    """Base exception for Solana RPC errors."""
    pass


class TokenNotFoundError(SolanaRPCError):
    """Raised when token is not found."""
    pass


class RateLimitError(SolanaRPCError):
    """Raised when rate limit is exceeded."""
    pass


class HeliusRPCClient:
    """
    Helius-enhanced Solana RPC client implementing core methods for token analytics.
    
    This client implements the essential Solana RPC methods using Helius infrastructure:
    - getTokenSupply: Get token supply information
    - getTokenAccountsByOwner: Get token holders
    - getTokenLargestAccounts: Get largest token accounts  
    - getSignaturesForAddress: Get transaction signatures
    - getTransaction: Get detailed transaction data
    - getAccountInfo: Get account information
    - getBlock: Get block data for timing
    
    Plus WebSocket subscriptions for real-time updates.
    """
    
    def __init__(self):
        self.api_key = settings.helius_api_key
        self.rpc_url = f"{settings.helius_rpc_url}?api-key={self.api_key}"
        self.websocket_url = f"{settings.helius_websocket_url}?api-key={self.api_key}"
        
        self.session: Optional[httpx.AsyncClient] = None
        self._request_id = 0
        
        if not self.api_key:
            raise ValueError("Helius API key is required")
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.aclose()
    
    def _get_request_id(self) -> int:
        """Get next request ID for RPC calls."""
        self._request_id += 1
        return self._request_id
    
    async def _make_rpc_request(self, method: str, params: Union[List[Any], Dict[str, Any]]) -> Dict[str, Any]:
        """Make a JSON-RPC request to Helius."""
        if not self.session:
            raise SolanaRPCError("Client session not initialized")
        
        payload = {
            "jsonrpc": "2.0",
            "id": self._get_request_id(),
            "method": method,
            "params": params
        }
        print(f'=======================\nPayload for {method}\n{payload}\n\n========================')
        
        try:
            logger.debug("Making RPC request", extra={
                "method": method,
                "request_id": payload["id"]
            })
            
            response = await self.session.post(
                self.rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("RPC rate limit exceeded", extra={"method": method})
                raise RateLimitError(f"Rate limit exceeded for {method}")
            
            response.raise_for_status()
            result = response.json()

            print(f'******************\nResult for {method}\n{result}\n\n******************')
            
            if "error" in result:
                error = result["error"]
                error_code = error.get("code", 0)
                error_message = error.get("message", "Unknown error")
                
                logger.error("RPC error", extra={
                    "method": method,
                    "error_code": error_code,
                    "error_message": error_message
                })
                
                if "not found" in error_message.lower() or error_code == -32602:
                    raise TokenNotFoundError(f"Resource not found: {error_message}")
                elif "rate" in error_message.lower() or error_code == -32600:
                    raise RateLimitError(f"Rate limit: {error_message}")
                else:
                    raise SolanaRPCError(f"RPC error {error_code}: {error_message}")
            
            return result.get("result", {})
            
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error in RPC request", extra={
                "method": method,
                "status_code": e.response.status_code
            })
            raise SolanaRPCError(f"HTTP error {e.response.status_code}")
        
        except httpx.RequestError as e:
            logger.error("Request error in RPC", extra={
                "method": method,
                "error": str(e)
            })
            raise SolanaRPCError(f"Request error: {str(e)}")
    
    # Core Token Supply and Metadata Methods
    
    async def get_token_supply(self, token_mint: str) -> Dict[str, Any]:
        """
        Get token supply information.
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Dict with token supply data including amount, decimals, uiAmount
        """
        try:
            pubkey = Pubkey.from_string(token_mint)
            result = await self._make_rpc_request("getTokenSupply", [str(pubkey)])
            
            value = result.get("value", {})
            return {
                "total_supply": value.get("uiAmount", 0.0),
                "decimals": value.get("decimals", 9),
                "ui_amount": value.get("uiAmount", 0.0),
                "ui_amount_string": value.get("uiAmountString", "0"),
                "raw_amount": int(value.get("amount", 0))
            }
            
        except Exception as e:
            logger.error("Error getting token supply", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            raise
    
    async def get_account_info(self, account_address: str, encoding: str = "base58") -> Dict[str, Any]:
        """
        Get account information.
        
        Args:
            account_address: Account address to query
            encoding: Data encoding ("jsonParsed", "base58", "base64")
            
        Returns:
            Dict with account information
        """
        try:
            params = [
                account_address,
                {"encoding": encoding}
            ]
            
            result = await self._make_rpc_request("getAccountInfo", params)
            return result.get("value", {}) if result else {}
            
        except Exception as e:
            logger.error("Error getting account info", extra={
                "account": account_address,
                "error": str(e)
            })
            raise
    
    # Token Holder and Concentration Methods
    
    async def get_token_largest_accounts(self, token_mint: str) -> List[Dict[str, Any]]:
        """
        Get largest token accounts for concentration analysis.
        
        Note: This method returns up to 20 largest accounts as per Helius API limits.
        
        Args:
            token_mint: Token mint address
            
        Returns:
            List of largest token accounts with balances (max 20)
        """
        try:
            params = [token_mint, {"commitment": "finalized"}]
            result = await self._make_rpc_request("getTokenLargestAccounts", params)
            
            accounts = result.get("value", []) if result else []
            
            # Structure the largest accounts data
            largest_accounts = []
            for account in accounts:
                ui_amount = account.get("uiAmount", 0)
                if ui_amount and ui_amount > 0:
                    largest_accounts.append({
                        "address": account.get("address", ""),
                        "balance": ui_amount,
                        "amount": account.get("amount", "0"),
                        "decimals": account.get("decimals", 9)
                    })
            
            logger.debug("Retrieved largest token accounts", extra={
                "token_mint": token_mint,
                "accounts_found": len(largest_accounts)
            })
            
            return largest_accounts
            
        except RateLimitError:
            logger.warning("Rate limited getting largest accounts, returning empty", extra={
                "token_mint": token_mint,
                "note": "Will retry after rate limit period"
            })
            return []
        except TokenNotFoundError:
            logger.info("Token not found for largest accounts", extra={
                "token_mint": token_mint
            })
            return []
        except Exception as e:
            logger.error("Error getting largest token accounts", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            # Return empty instead of raising to allow graceful degradation
            return []
    
    async def get_token_holders_comprehensive(self, token_mint: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get comprehensive token holder information combining multiple methods.
        
        Note: Limited to top 20 token accounts due to Helius API constraints.
        This method gets the largest accounts and resolves their owner addresses.
        
        Args:
            token_mint: Token mint address
            limit: Maximum number of holders to return (capped at 20 by API)
            
        Returns:
            List of token holders with wallet addresses and balances (max 20)
        """
        try:
            # Step 1: Get largest token accounts (max 15 per API)
            largest_accounts = await self.get_token_largest_accounts(token_mint)
            
            if not largest_accounts:
                logger.info("No largest accounts found", extra={
                    "token_mint": token_mint,
                    "reason": "empty_result_or_rate_limited"
                })
                return []
            
            # Step 2: Get owner information for each token account
            holders = []
            total_accounts = len(largest_accounts)
            effective_limit = min(limit, len(largest_accounts), 15)  # API max is 15
            
            # Process accounts in smaller batches to respect rate limits
            batch_size = 5  # Smaller batches for better rate limit compliance
            
            for i in range(0, effective_limit, batch_size):
                batch = largest_accounts[i:i+batch_size]
                
                # Add delay between batches for rate limiting
                if i > 0:
                    await asyncio.sleep(0.2)  # Increased delay for better rate limit compliance
                
                # Get account info for each token account to find the owner
                for account in batch:
                    try:
                        account_address = account["address"]
                        account_info = await self.get_account_info(account_address)
                        
                        if account_info:
                            data = account_info.get("data", {})
                            
                            if isinstance(data, dict) and "parsed" in data:
                                owner = data["parsed"]["info"].get("owner")
                                if owner:
                                    holders.append({
                                        "address": owner,  # Wallet address of the holder
                                        "token_account": account_address,  # Token account address
                                        "balance": account["balance"],
                                        "amount": account["amount"],
                                        "decimals": account["decimals"],
                                        "rank": len(holders) + 1
                                    })
                    
                    except (RateLimitError, TokenNotFoundError) as e:
                        logger.debug("Expected error processing account", extra={
                            "account": account.get("address", ""),
                            "error_type": type(e).__name__,
                            "error": str(e)
                        })
                        # Continue processing other accounts
                        continue
                    except Exception as account_error:
                        logger.debug("Unexpected error processing account", extra={
                            "account": account.get("address", ""),
                            "error": str(account_error)
                        })
                        continue
            
            logger.info("Token holders retrieved", extra={
                "token_mint": token_mint,
                "holders_found": len(holders),
                "requested_limit": limit,
                "api_constraint": "max_15_accounts",
                "total_accounts": total_accounts
            })
            
            return holders
            
        except Exception as e:
            logger.error("Error getting comprehensive token holders", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            # Return empty list instead of raising to allow graceful degradation
            return []
    
    # Transaction and Volume Methods
    
    async def get_signatures_for_address(
        self, 
        address: str, 
        limit: int = 1000,
        before: Optional[str] = None,
        until: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get transaction signatures for an address.
        
        Args:
            address: Address to get signatures for
            limit: Maximum number of signatures (max 1000)
            before: Start searching backwards from this signature
            until: Search until this signature is reached
            
        Returns:
            List of transaction signature information
        """
        try:
            params = [address, {"limit": min(limit, 1000), "commitment": "finalized"}]
            
            if before:
                params[1]["before"] = before
            if until:
                params[1]["until"] = until
            
            result = await self._make_rpc_request("getSignaturesForAddress", params)
            return result if result else []
            
        except Exception as e:
            logger.error("Error getting signatures for address", extra={
                "address": address,
                "error": str(e)
            })
            raise
    
    async def get_transaction(self, signature: str, max_supported_version: int = 0) -> Dict[str, Any]:
        """
        Get detailed transaction information.
        
        Args:
            signature: Transaction signature
            max_supported_version: Maximum transaction version to support
            
        Returns:
            Dict with transaction details
        """
        try:
            params = [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "finalized",
                    "maxSupportedTransactionVersion": max_supported_version
                }
            ]
            
            result = await self._make_rpc_request("getTransaction", params)
            return result if result else {}
            
        except Exception as e:
            logger.error("Error getting transaction", extra={
                "signature": signature,
                "error": str(e)
            })
            raise
    
    async def get_block(self, slot: int, encoding: str = "jsonParsed") -> Dict[str, Any]:
        """
        Get block information.
        
        Args:
            slot: Slot number
            encoding: Block encoding format
            
        Returns:
            Dict with block information
        """
        try:
            params = [
                slot,
                {
                    "encoding": encoding,
                    "commitment": "finalized",
                    "transactionDetails": "signatures",
                    "rewards": False
                }
            ]
            
            result = await self._make_rpc_request("getBlock", params)
            return result if result else {}
            
        except Exception as e:
            logger.error("Error getting block", extra={
                "slot": slot,
                "error": str(e)
            })
            raise
    
    # Market Data Integration
    
    async def get_token_price_jupiter(self, token_mint: str) -> Optional[Dict[str, Any]]:
        """
        Get token price from Jupiter API.
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Price data from Jupiter or None if not found
        """
        try:
            if not self.session:
                raise SolanaRPCError("Client session not initialized")
            
            jupiter_url = f"https://lite-api.jup.ag/price/v2?ids={token_mint}"
            
            response = await self.session.get(jupiter_url)
            response.raise_for_status()
            
            price_data = response.json()
            print(f'******************\nPrice data for {token_mint}\n{price_data}\n\n******************')
            
            if "data" in price_data and token_mint in price_data["data"]:
                token_price = price_data["data"][token_mint]
                return {
                    "price": float(token_price.get("price", 0)),
                    "timestamp": datetime.now(timezone.utc),
                    "source": "jupiter",
                    "vs_token": "USDC"
                }
            
            return None
            
        except Exception as e:
            logger.error("Error getting Jupiter price", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            return None
    
    async def get_token_metadata_helius(self, token_mint: str) -> Optional[Dict[str, Any]]:
        """
        Get token metadata using Helius Digital Asset Standard (DAS) getAsset API.
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Token metadata including name, symbol, and other details
        """
        try:
            if not self.session:
                raise SolanaRPCError("Client session not initialized")
            
            if not self.api_key:
                logger.warning("No Helius API key provided for metadata fetch")
                return None
            
            # Use DAS getAsset method for comprehensive token metadata
            result = await self._make_rpc_request("getAsset", {"id": token_mint})
            
            if not result:
                logger.info("No asset data returned", extra={"token_mint": token_mint})
                return None
            
            # Extract metadata from DAS response
            content = result.get("content", {})
            metadata = content.get("metadata", {})
            token_info = result.get("token_info", {})
            
            # Get name and symbol from metadata
            name = metadata.get("name", "").strip()
            symbol = metadata.get("symbol", "").strip()
            
            # Clean up empty strings
            name = name if name and name != "" else None
            symbol = symbol if symbol and symbol != "" else None
            
            # Get token info
            supply = token_info.get("supply", 0)
            decimals = token_info.get("decimals", 9)
            mint_authority = token_info.get("mint_authority")
            freeze_authority = token_info.get("freeze_authority")
            
            # Get price info if available
            price_info = token_info.get("price_info", {})
            price_per_token = price_info.get("price_per_token")
            price_currency = price_info.get("currency")
            
            # Additional metadata
            description = metadata.get("description", "").strip()
            description = description if description and description != "" else None
            
            # Get links and image
            links = content.get("links", {})
            image_url = links.get("image")
            external_url = links.get("external_url")
            
            # Get collection info if available
            grouping = result.get("grouping", [])
            collection_address = None
            for group in grouping:
                if group.get("group_key") == "collection":
                    collection_address = group.get("group_value")
                    break
            
            logger.info("Successfully retrieved token metadata via DAS getAsset", extra={
                "token_mint": token_mint,
                "name": name,
                "symbol": symbol,
                "has_image": bool(image_url),
                "has_collection": bool(collection_address)
            })
            
            return {
                "address": token_mint,
                "name": name,
                "symbol": symbol,
                "description": description,
                "decimals": decimals,
                "supply": supply,
                "mint_authority": mint_authority,
                "freeze_authority": freeze_authority,
                "image_url": image_url,
                "external_url": external_url,
                "collection_address": collection_address,
                "token_standard": metadata.get("token_standard"),
                "is_mutable": result.get("mutable", False),
                "is_burnt": result.get("burnt", False),
                "price_per_token": price_per_token,
                "price_currency": price_currency,
                "metadata_source": "helius_das_getasset"
            }
            
        except TokenNotFoundError:
            logger.info("Token not found via DAS getAsset", extra={
                "token_mint": token_mint
            })
            return None
        except RateLimitError:
            logger.warning("Rate limited getting token metadata via DAS", extra={
                "token_mint": token_mint
            })
            return None
        except Exception as e:
            logger.error("Error getting token metadata from Helius DAS", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            return None
    
    async def get_comprehensive_token_metadata(self, token_mint: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive token metadata trying multiple sources.
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Most complete token metadata available
        """
        try:
            # Try Helius Enhanced API first
            metadata = await self.get_token_metadata_helius(token_mint)
            
            if metadata and (metadata.get("name") or metadata.get("symbol")):
                logger.info("Got token metadata from Helius Enhanced API", extra={
                    "token_mint": token_mint,
                    "name": metadata.get("name"),
                    "symbol": metadata.get("symbol")
                })
                return metadata
            return None
            
        except Exception as e:
            logger.error("Error getting comprehensive token metadata", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            return None
    
    # Analytics Calculations
    
    def calculate_market_cap(self, price: float, total_supply: float) -> float:
        """Calculate market cap from price and supply."""
        return price * total_supply
    
    def calculate_token_velocity(self, volume_24h: float, market_cap: float) -> float:
        """Calculate token velocity (how fast tokens change hands)."""
        if market_cap <= 0:
            return 0.0
        return volume_24h / market_cap
    
    def calculate_concentration_ratios(self, holders: List[Dict[str, Any]], total_supply: float) -> Dict[str, float]:
        """Calculate holder concentration ratios."""
        if not holders or total_supply <= 0:
            return {"top_10": 0.0, "top_50": 0.0, "top_100": 0.0}
        
        # Sort holders by balance (descending)
        sorted_holders = sorted(holders, key=lambda x: x.get("balance", 0), reverse=True)
        
        top_10_balance = sum(h.get("balance", 0) for h in sorted_holders[:10])
        top_50_balance = sum(h.get("balance", 0) for h in sorted_holders[:50])
        top_100_balance = sum(h.get("balance", 0) for h in sorted_holders[:100])
        
        return {
            "top_10": (top_10_balance / total_supply) * 100,
            "top_50": (top_50_balance / total_supply) * 100,
            "top_100": (top_100_balance / total_supply) * 100
        }
    
    # Additional Token Analysis Methods
    
    async def get_program_accounts(
        self, 
        program_id: str, 
        filters: Optional[List[Dict[str, Any]]] = None,
        encoding: str = "jsonParsed"
    ) -> List[Dict[str, Any]]:
        """
        Get program accounts (useful for comprehensive token holder analysis).
        
        Args:
            program_id: Program ID to query (e.g., SPL Token program)
            filters: Optional filters for the query
            encoding: Data encoding format
            
        Returns:
            List of program accounts
        """
        try:
            params = [
                program_id,
                {
                    "encoding": encoding,
                    "commitment": "finalized"
                }
            ]
            
            if filters:
                params[1]["filters"] = filters
            
            result = await self._make_rpc_request("getProgramAccounts", params)
            return result if result else []
            
        except Exception as e:
            logger.error("Error getting program accounts", extra={
                "program_id": program_id,
                "error": str(e)
            })
            raise
    
    async def get_token_accounts_by_owner(
        self, 
        owner_address: str, 
        token_mint: Optional[str] = None,
        program_id: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    ) -> List[Dict[str, Any]]:
        """
        Get token accounts owned by a specific address.
        
        Args:
            owner_address: Owner's wallet address
            token_mint: Optional specific token mint to filter by
            program_id: Token program ID (defaults to SPL Token)
            
        Returns:
            List of token accounts owned by the address
        """
        try:
            filter_param = {"programId": program_id}
            if token_mint:
                filter_param = {"mint": token_mint}
            
            params = [
                owner_address,
                filter_param,
                {
                    "encoding": "jsonParsed",
                    "commitment": "finalized"
                }
            ]
            
            result = await self._make_rpc_request("getTokenAccountsByOwner", params)
            
            accounts = result.get("value", []) if result else []
            
            # Structure the token accounts data
            token_accounts = []
            for account in accounts:
                account_info = account.get("account", {})
                data = account_info.get("data", {})
                
                if isinstance(data, dict) and "parsed" in data:
                    parsed_data = data["parsed"]["info"]
                    token_amount = parsed_data.get("tokenAmount", {})
                    
                    token_accounts.append({
                        "address": account.get("pubkey", ""),
                        "mint": parsed_data.get("mint", ""),
                        "owner": parsed_data.get("owner", ""),
                        "balance": float(token_amount.get("uiAmount", 0)),
                        "amount": token_amount.get("amount", "0"),
                        "decimals": token_amount.get("decimals", 9)
                    })
            
            return token_accounts
            
        except Exception as e:
            logger.error("Error getting token accounts by owner", extra={
                "owner": owner_address,
                "token_mint": token_mint,
                "error": str(e)
            })
            raise
    
    async def get_token_account_balance(self, token_account: str) -> Dict[str, Any]:
        """
        Get balance of a specific token account.
        
        Args:
            token_account: Token account address
            
        Returns:
            Dict with token account balance information
        """
        try:
            params = [token_account, {"commitment": "finalized"}]
            result = await self._make_rpc_request("getTokenAccountBalance", params)
            
            value = result.get("value", {}) if result else {}
            return {
                "balance": float(value.get("uiAmount", 0)),
                "amount": value.get("amount", "0"),
                "decimals": value.get("decimals", 9),
                "ui_amount_string": value.get("uiAmountString", "0")
            }
            
        except Exception as e:
            logger.error("Error getting token account balance", extra={
                "token_account": token_account,
                "error": str(e)
            })
            raise


# Global client instance with proper lifecycle management
class HeliusClientManager:
    """Singleton manager for HeliusRPCClient with proper lifecycle."""
    
    def __init__(self):
        self._client: Optional[HeliusRPCClient] = None
        self._session_active = False
        self._shutdown_requested = False
        self._reference_count = 0
        self._lock = asyncio.Lock()
    
    async def get_client(self) -> HeliusRPCClient:
        """Get or create the global client instance with reference counting."""
        async with self._lock:
            if self._shutdown_requested:
                raise SolanaRPCError("Client shutting down, no new requests accepted")
                
            if not self._client:
                self._client = HeliusRPCClient()
            
            if not self._session_active:
                await self._client.__aenter__()
                self._session_active = True
            
            # Increment reference count
            self._reference_count += 1
            
            return self._client
    
    async def release_client(self):
        """Release a reference to the client."""
        async with self._lock:
            if self._reference_count > 0:
                self._reference_count -= 1
            
            # Only close if no active references and shutdown was requested
            if self._reference_count == 0 and self._shutdown_requested and self._session_active:
                try:
                    await self._client.__aexit__(None, None, None)
                    self._session_active = False
                    logger.info("HTTP client session closed after all references released")
                except Exception as e:
                    logger.warning(f"Error closing client session: {e}")
    
    async def shutdown(self):
        """Request shutdown and close when no active references."""
        async with self._lock:
            self._shutdown_requested = True
            logger.info(f"Shutdown requested, active references: {self._reference_count}")
            
            # If no active references, close immediately
            if self._reference_count == 0 and self._session_active:
                try:
                    await self._client.__aexit__(None, None, None)
                    self._session_active = False
                    logger.info("HTTP client session closed immediately")
                except Exception as e:
                    logger.warning(f"Error closing client session: {e}")

# Global manager instance
_helius_manager = HeliusClientManager()

class HeliusContextManager:
    """Context manager that properly tracks client usage."""
    
    def __init__(self):
        self.client = None
        
    async def __aenter__(self):
        self.client = await _helius_manager.get_client()
        return self.client
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await _helius_manager.release_client()

async def get_helius_client() -> HeliusContextManager:
    """Get a context-managed Helius client with proper reference counting."""
    return HeliusContextManager()

async def shutdown_helius_client():
    """Shutdown the global Helius client manager."""
    await _helius_manager.shutdown()

# Backwards compatibility - but this should be deprecated
helius_client = HeliusRPCClient() 
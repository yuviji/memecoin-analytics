"""
Token analytics service implementing the four core bounty metrics.

This service calculates:
1. Market cap updates - Real-time token supply * price
2. Token velocity - Volume / Market cap ratio 
3. Concentration ratios - Top holder percentage distribution
4. Paperhand ratio - Analysis of weak vs strong holder behavior

Uses the new HeliusRPCClient for data and SolanaWebSocketManager for real-time updates.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_async_db
from app.models.market_data import Token, TokenMetrics, TokenTransaction, TokenHolder
from app.services.solana.helius_client import get_helius_client
from app.services.websocket_manager import solana_websocket_manager
from app.services.cache import cache

logger = get_logger(__name__)


class TokenAnalyticsService:
    """
    Core token analytics service implementing bounty requirements.
    
    Provides real-time calculations for:
    - Market cap monitoring and updates
    - Token velocity analysis (trading speed)
    - Holder concentration distribution analysis
    - Paperhand vs diamond hand behavior analysis
    """
    
    def __init__(self):
        self.cache_ttl = 300  # 5 minutes cache TTL for expensive calculations
        self.velocity_window = 24  # 24 hours for velocity calculations
        self.paperhand_threshold_hours = 24  # Transactions within 24h indicate paperhands
        
    async def get_comprehensive_metrics(self, token_mint: str) -> Dict[str, Any]:
        """
        Get all four core bounty metrics for a token.
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Dict containing market_cap, velocity, concentration, paperhand metrics
        """
        cache_key = f"comprehensive_metrics:{token_mint}"
        
        # Try cache first
        cached_result = await cache.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
        
        try:
            # Validate token address format
            if not self._validate_token_address(token_mint):
                raise ValueError(f"Invalid token address format: {token_mint}")
            
            # Get or create token in database with metadata
            token = await self.get_or_create_token(token_mint)
            
            # Gather all metrics in parallel for efficiency with timeout
            tasks = [
                asyncio.wait_for(self.get_market_cap_metrics(token_mint), timeout=30),
                asyncio.wait_for(self.get_velocity_metrics(token_mint), timeout=45),
                asyncio.wait_for(self.get_concentration_metrics(token_mint), timeout=30),
                asyncio.wait_for(self.get_paperhand_metrics(token_mint), timeout=60)
            ]
            
            # Execute with error recovery
            results = await asyncio.gather(*tasks, return_exceptions=True)
            market_cap, velocity, concentration, paperhand = results
            
            # Handle partial failures gracefully
            market_cap = market_cap if not isinstance(market_cap, Exception) else self._get_fallback_market_cap()
            velocity = velocity if not isinstance(velocity, Exception) else self._get_fallback_velocity()
            concentration = concentration if not isinstance(concentration, Exception) else self._get_fallback_concentration()
            paperhand = paperhand if not isinstance(paperhand, Exception) else self._get_fallback_paperhand()
            
            # Log any errors for monitoring
            for i, (name, result) in enumerate([
                ("market_cap", market_cap), ("velocity", velocity), 
                ("concentration", concentration), ("paperhand", paperhand)
            ]):
                if isinstance(result, Exception):
                    logger.warning(f"Metric calculation failed: {name}", extra={
                        "token_mint": token_mint,
                        "error": str(result),
                        "metric": name
                    })
            
            # Combine all metrics with token information
            comprehensive_metrics = {
                "token_mint": token_mint,
                "token_info": {
                    "name": token.name if token else None,
                    "symbol": token.symbol if token else None,
                    "decimals": token.decimals if token else 9,
                    "address": token_mint,
                    "description": getattr(token, 'description', None) if token else None,
                    "image_url": getattr(token, 'image_url', None) if token else None,
                    "external_url": getattr(token, 'external_url', None) if token else None,
                    "collection_address": getattr(token, 'collection_address', None) if token else None,
                    "token_standard": getattr(token, 'token_standard', None) if token else None
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "market_cap": market_cap,
                "velocity": velocity,
                "concentration": concentration,
                "paperhand": paperhand,
                "metadata": {
                    "data_freshness": "real-time",
                    "calculation_version": "v2.0",
                    "next_update": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                    "partial_failure": any(isinstance(r, Exception) for r in results),
                    "success_rate": sum(1 for r in results if not isinstance(r, Exception)) / len(results),
                    "database_stored": False  # Will be updated if stored
                }
            }
            
            # Store metrics in database if we have a valid token
            if token and comprehensive_metrics["metadata"]["success_rate"] >= 0.5:
                try:
                    stored = await self.store_token_metrics(str(token.id), comprehensive_metrics)
                    comprehensive_metrics["metadata"]["database_stored"] = stored
                except Exception as store_error:
                    logger.warning("Failed to store metrics in database", extra={
                        "token_mint": token_mint,
                        "error": str(store_error)
                    })
            
            # Cache successful results only
            if comprehensive_metrics["metadata"]["success_rate"] >= 0.5:  # At least 50% success
                await cache.set(cache_key, json.dumps(comprehensive_metrics, default=str), ttl=self.cache_ttl)
            
            return comprehensive_metrics
            
        except Exception as e:
            logger.error("Error calculating comprehensive metrics", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            # Return cached data if available, otherwise minimal response
            cached_fallback = await cache.get(cache_key)
            if cached_fallback:
                cached_data = json.loads(cached_fallback)
                cached_data["metadata"]["stale"] = True
                return cached_data
            
            # Last resort: minimal error response
            return {
                "token_mint": token_mint,
                "token_info": {
                    "name": None,
                    "symbol": None,
                    "decimals": 9,
                    "address": token_mint
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "market_cap": self._get_fallback_market_cap(),
                "velocity": self._get_fallback_velocity(),
                "concentration": self._get_fallback_concentration(),
                "paperhand": self._get_fallback_paperhand(),
                "metadata": {
                    "error": True,
                    "message": "Unable to fetch complete metrics"
                }
            }
    
    def _validate_token_address(self, token_address: str) -> bool:
        """Validate Solana token address format."""
        if not token_address or len(token_address) < 32 or len(token_address) > 44:
            return False
        # Additional validation could be added here
        return True
    
    def _get_fallback_market_cap(self) -> Dict[str, Any]:
        """Return fallback market cap data."""
        return {
            "current_price_usd": 0.0,
            "total_supply": 0,
            "circulating_supply": 0,
            "market_cap_usd": 0.0,
            "error": "Data unavailable",
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    def _get_fallback_velocity(self) -> Dict[str, Any]:
        """Return fallback velocity data."""
        return {
            "volume_24h_usd": 0.0,
            "velocity_ratio": 0.0,
            "velocity_category": "unknown",
            "error": "Data unavailable",
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    def _get_fallback_concentration(self) -> Dict[str, Any]:
        """Return fallback concentration data."""
        return {
            "concentration_ratios": {"top_1": 0.0, "top_5": 0.0, "top_15": 0.0},
            "total_holders": 0,
            "error": "Data unavailable",
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    def _get_fallback_paperhand(self) -> Dict[str, Any]:
        """Return fallback paperhand data."""
        return {
            "paperhand_ratio_percent": 0.0,
            "behavior_category": "unknown",
            "error": "Data unavailable",
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    async def get_market_cap_metrics(self, token_mint: str) -> Dict[str, Any]:
        """
        Calculate real-time market cap metrics.
        
        Market Cap = Token Supply × Current Price
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Dict with market cap, price, supply, and change data
        """
        try:
            async with await get_helius_client() as client:
                # Get comprehensive metadata (includes supply, price, and currency)
                metadata = await client.get_comprehensive_token_metadata(token_mint)
                
                if not metadata:
                    logger.warning("No metadata available", extra={"token_mint": token_mint})
                    return self._get_fallback_market_cap()
                
                # Extract price and supply from metadata
                price_per_token = metadata.get("price_per_token", 0.0) or 0.0
                price_currency = metadata.get("price_currency", "USD")
                raw_supply = metadata.get("supply", 0)
                decimals = metadata.get("decimals", 9)
                
                # Convert raw supply to UI amount
                ui_supply = float(raw_supply) / (10 ** decimals) if raw_supply > 0 else 0.0
                
                # Calculate market cap
                market_cap_usd = client.calculate_market_cap(price_per_token, ui_supply)
                
                # Get historical data for comparison
                historical_data = await self._get_historical_market_cap(token_mint)
                
                # Calculate changes
                change_24h = self._calculate_percentage_change(
                    market_cap_usd, 
                    historical_data.get("market_cap_24h_ago", market_cap_usd)
                )
                
                return {
                    "current_price_usd": price_per_token,
                    "total_supply": ui_supply,
                    "circulating_supply": ui_supply,
                    "decimals": decimals,
                    "market_cap_usd": market_cap_usd,
                    "market_cap_rank": await self._get_market_cap_rank(market_cap_usd),
                    "price_change_24h_percent": historical_data.get("price_change_24h", 0.0),
                    "market_cap_change_24h_percent": change_24h,
                    "price_source": "helius_getasset",
                    "price_currency": price_currency,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error("Error calculating market cap metrics", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            raise
    
    async def get_velocity_metrics(self, token_mint: str) -> Dict[str, Any]:
        """
        Calculate token velocity metrics.
        
        Token Velocity = Trading Volume (24h) / Market Cap
        Higher velocity = tokens changing hands more frequently
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Dict with velocity ratios and trading activity metrics
        """
        try:
            async with await get_helius_client() as client:
                # Get recent transaction signatures
                signatures = await client.get_signatures_for_address(
                    token_mint, 
                    limit=10
                )
                
                # Filter to last 24 hours
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.velocity_window)
                recent_signatures = [
                    sig for sig in signatures 
                    if datetime.fromtimestamp(sig.get("blockTime", 0), timezone.utc) > cutoff_time
                ]
                
                # Analyze transactions for volume calculation
                total_volume_24h = 0.0
                transaction_count_24h = len(recent_signatures)
                unique_traders = set()
                
                # Process transactions in batches to avoid rate limits
                batch_size = 10
                for i in range(0, min(len(recent_signatures), 100), batch_size):  # Limit to 100 for performance
                    batch = recent_signatures[i:i+batch_size]
                    
                    for sig_info in batch:
                        try:
                            signature = sig_info["signature"]
                            transaction = await client.get_transaction(signature)
                            
                            # Extract volume and trader info from transaction
                            volume, traders = self._extract_transaction_volume(transaction, token_mint)
                            total_volume_24h += volume
                            unique_traders.update(traders)
                            
                        except Exception as tx_error:
                            logger.debug("Error processing transaction", extra={
                                "signature": sig_info.get("signature", ""),
                                "error": str(tx_error)
                            })
                            continue
                    
                    # Rate limiting
                    if i + batch_size < min(len(recent_signatures), 100):
                        await asyncio.sleep(0.1)
                
                # Get market cap for velocity calculation
                market_cap_data = await self.get_market_cap_metrics(token_mint)
                market_cap_usd = market_cap_data["market_cap_usd"]
                
                # Calculate velocity
                velocity_ratio = client.calculate_token_velocity(total_volume_24h, market_cap_usd)
                
                return {
                    "volume_24h_usd": total_volume_24h,
                    "transaction_count_24h": transaction_count_24h,
                    "unique_traders_24h": len(unique_traders),
                    "velocity_ratio": velocity_ratio,
                    "velocity_category": self._categorize_velocity(velocity_ratio),
                    "avg_transaction_size_usd": total_volume_24h / max(transaction_count_24h, 1),
                    "trading_frequency": transaction_count_24h / self.velocity_window,  # transactions per hour
                    "market_cap_usd": market_cap_usd,
                    "calculation_window_hours": self.velocity_window,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error("Error calculating velocity metrics", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            raise
    
    async def get_concentration_metrics(self, token_mint: str) -> Dict[str, Any]:
        """
        Calculate holder concentration ratios.
        
        Shows what percentage of tokens are held by top holders.
        Higher concentration = more centralized ownership.
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Dict with concentration ratios and distribution metrics
        """
        try:
            async with await get_helius_client() as client:
                # Get comprehensive holder data
                holders = await client.get_token_holders_comprehensive(token_mint, limit=20)
                
                if not holders:
                    return {
                        "error": "No holder data available - likely due to rate limiting or token not found",
                        "token_mint": token_mint,
                        "concentration_ratios": {"top_1": None, "top_5": None, "top_15": None},
                        "total_holders": 0,
                        "data_quality": "insufficient",
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                
                # Get total supply for percentage calculations
                supply_data = await client.get_token_supply(token_mint)
                total_supply = supply_data["ui_amount"]
                
                if total_supply <= 0:
                    return {
                        "error": "Invalid total supply data",
                        "token_mint": token_mint,
                        "concentration_ratios": {"top_1": None, "top_5": None, "top_15": None},
                        "total_holders": len(holders) if holders else 0,
                        "data_quality": "insufficient",
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                
                # Calculate concentration ratios with available data
                # Note: Helius API typically returns max 15-20 largest accounts
                available_accounts = min(len(holders), 20)
                
                # Calculate what we can with available data
                top_1_balance = sum(h.get("balance", 0) for h in holders[:min(1, available_accounts)])
                top_5_balance = sum(h.get("balance", 0) for h in holders[:min(5, available_accounts)])
                top_15_balance = sum(h.get("balance", 0) for h in holders[:min(15, available_accounts)])
                
                # Calculate percentages
                top_1_percent = (top_1_balance / total_supply) * 100 if total_supply > 0 else 0
                top_5_percent = (top_5_balance / total_supply) * 100 if total_supply > 0 else 0
                top_15_percent = (top_15_balance / total_supply) * 100 if total_supply > 0 else 0
                
                # These ratios align with our available data
                concentration_ratios = {
                    "top_1": round(top_1_percent, 2) if available_accounts >= 1 else None,
                    "top_5": round(top_5_percent, 2) if available_accounts >= 5 else None,
                    "top_15": round(top_15_percent, 2) if available_accounts >= 15 else None
                }
                
                # Additional distribution analysis with available data
                holder_count = len(holders)
                median_balance = self._calculate_median_balance(holders)
                gini_coefficient = self._calculate_gini_coefficient(holders) if len(holders) >= 5 else None
                
                # Categorize top holders
                whale_threshold = total_supply * 0.01  # 1% of supply
                whales = [h for h in holders if h["balance"] >= whale_threshold]
                
                # Determine data quality based on available accounts
                data_quality = "excellent" if available_accounts >= 15 else "good" if available_accounts >= 10 else "limited"
                
                return {
                    "total_holders": holder_count,
                    "available_top_accounts": available_accounts,
                    "concentration_ratios": concentration_ratios,
                    "whale_count": len(whales),
                    "whale_threshold_percent": 1.0,
                    "median_balance": round(median_balance, 4) if median_balance > 0 else 0,
                    "gini_coefficient": round(gini_coefficient, 3) if gini_coefficient is not None else None,
                    "distribution_category": self._categorize_concentration(concentration_ratios["top_1"] or 0),
                    "top_holders": [
                        {
                            "rank": h["rank"],
                            "address": h["address"],
                            "balance": round(h["balance"], 4),
                            "percentage": round((h["balance"] / total_supply) * 100, 3)
                        }
                        for h in holders[:min(10, available_accounts)]  # Show available top holders
                    ],
                    "total_supply": round(total_supply, 2),
                    "data_quality": data_quality,
                    "api_limitation_note": "Refactored to show top_1, top_5, top_15 based on available data from Helius API.",
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error("Error calculating concentration metrics", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            raise
    
    async def get_paperhand_metrics(self, token_mint: str) -> Dict[str, Any]:
        """
        Calculate paperhand vs diamond hand behavior analysis.
        
        Paperhand = Holders who sell quickly (weak hands)
        Diamond hands = Holders who hold long-term (strong hands)
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Dict with paperhand ratio and holder behavior analysis
        """
        try:
            async with await get_helius_client() as client:
                # Get recent transaction data for behavioral analysis
                signatures = await client.get_signatures_for_address(
                    token_mint,
                    limit=10
                )
                
                if not signatures:
                    return {
                        "error": "No transaction data available for analysis",
                        "paperhand_ratio_percent": None,
                        "diamond_hand_ratio_percent": None,
                        "behavior_category": "insufficient_data",
                        "data_quality": "insufficient",
                        "analysis_note": "No recent transactions found for behavioral analysis",
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                
                # Analyze transaction patterns
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.paperhand_threshold_hours)
                
                quick_sellers = set()
                long_holders = set()
                total_volume_paperhands = 0.0
                total_volume_diamond = 0.0
                
                # Track buying and selling patterns
                trader_actions = {}  # address -> list of actions
                
                # Process transactions to identify behavior patterns
                batch_size = 10
                processed_count = 0
                
                for i in range(0, min(len(signatures), 200), batch_size):  # Limit for performance
                    batch = signatures[i:i+batch_size]
                    
                    for sig_info in batch:
                        try:
                            signature = sig_info["signature"]
                            block_time = datetime.fromtimestamp(sig_info.get("blockTime", 0), timezone.utc)
                            
                            transaction = await client.get_transaction(signature)
                            
                            # Analyze transaction for buy/sell patterns
                            actions = self._analyze_transaction_behavior(transaction, token_mint, block_time)
                            
                            for action in actions:
                                trader = action["trader"]
                                action_type = action["type"]  # "buy" or "sell"
                                amount = action["amount"]
                                
                                if trader not in trader_actions:
                                    trader_actions[trader] = []
                                
                                trader_actions[trader].append({
                                    "type": action_type,
                                    "amount": amount,
                                    "timestamp": block_time,
                                    "signature": signature
                                })
                            
                            processed_count += 1
                            
                        except Exception as tx_error:
                            logger.debug("Error processing transaction for paperhand analysis", extra={
                                "signature": sig_info.get("signature", ""),
                                "error": str(tx_error)
                            })
                            continue
                    
                    # Rate limiting
                    if i + batch_size < min(len(signatures), 200):
                        await asyncio.sleep(0.1)
                
                # Check if we have sufficient data for analysis
                if processed_count < 5:
                    return {
                        "error": "Insufficient transaction data for reliable analysis",
                        "paperhand_ratio_percent": None,
                        "diamond_hand_ratio_percent": None,
                        "behavior_category": "insufficient_data",
                        "data_quality": "insufficient",
                        "transactions_analyzed": processed_count,
                        "analysis_note": f"Only {processed_count} transactions processed. Minimum 5 required for reliable analysis.",
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                
                # Analyze trader behavior patterns
                for trader, actions in trader_actions.items():
                    behavior = self._classify_trader_behavior(actions, cutoff_time)
                    
                    if behavior["type"] == "paperhand":
                        quick_sellers.add(trader)
                        total_volume_paperhands += behavior["volume"]
                    elif behavior["type"] == "diamond":
                        long_holders.add(trader)
                        total_volume_diamond += behavior["volume"]
                
                # Calculate paperhand ratio
                total_traders = len(trader_actions)
                paperhand_count = len(quick_sellers)
                diamond_count = len(long_holders)
                
                if total_traders == 0:
                    return {
                        "error": "No meaningful trader patterns detected",
                        "paperhand_ratio_percent": None,
                        "diamond_hand_ratio_percent": None,
                        "behavior_category": "insufficient_data",
                        "data_quality": "insufficient",
                        "analysis_note": "No clear trading patterns detected in recent transactions",
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                
                paperhand_ratio = (paperhand_count / total_traders) * 100
                diamond_ratio = (diamond_count / total_traders) * 100
                
                # Determine data quality
                confidence_score = min(processed_count / 50, 1.0)  # Based on transaction sample size
                data_quality = "excellent" if confidence_score >= 0.8 else "good" if confidence_score >= 0.5 else "limited"
                
                return {
                    "paperhand_ratio_percent": round(paperhand_ratio, 2) if paperhand_ratio > 0 else None,
                    "diamond_hand_ratio_percent": round(diamond_ratio, 2) if diamond_ratio > 0 else None,
                    "total_analyzed_traders": total_traders,
                    "paperhand_traders": paperhand_count,
                    "diamond_hand_traders": diamond_count,
                    "paperhand_volume_usd": round(total_volume_paperhands, 2),
                    "diamond_volume_usd": round(total_volume_diamond, 2),
                    "behavior_category": self._categorize_paperhand_ratio(paperhand_ratio),
                    "analysis_threshold_hours": self.paperhand_threshold_hours,
                    "confidence_score": confidence_score,
                    "data_quality": data_quality,
                    "transactions_analyzed": processed_count,
                    "analysis_note": f"Analysis based on {processed_count} recent transactions with {confidence_score:.1%} confidence",
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error("Error calculating paperhand metrics", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            raise
    
    # Helper methods for calculations
    
    def _extract_transaction_volume(self, transaction: Dict[str, Any], token_mint: str) -> Tuple[float, List[str]]:
        """Extract volume and traders from a transaction."""
        volume = 0.0
        traders = []
        
        try:
            # Parse transaction for token transfers
            meta = transaction.get("meta", {})
            if meta.get("err"):
                return volume, traders  # Skip failed transactions
            
            # Look for token transfers in the transaction
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])
            account_keys = transaction.get("transaction", {}).get("message", {}).get("accountKeys", [])
            
            # Simplified volume calculation - this would need more sophisticated parsing
            # For now, estimate based on balance changes
            for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
                if i < len(account_keys):
                    balance_change = abs(post - pre) / 10**9  # Convert lamports to SOL
                    if balance_change > 0:
                        volume += balance_change * 0.1  # Rough estimate
                        traders.append(account_keys[i])
            
        except Exception as e:
            logger.debug("Error extracting transaction volume", extra={"error": str(e)})
        
        return volume, traders
    
    def _analyze_transaction_behavior(self, transaction: Dict[str, Any], token_mint: str, block_time: datetime) -> List[Dict[str, Any]]:
        """Analyze a transaction for buy/sell behavior patterns."""
        actions = []
        
        try:
            # Simplified behavioral analysis
            # In a real implementation, you'd parse SPL token transfer instructions
            meta = transaction.get("meta", {})
            if meta.get("err"):
                return actions
            
            # Extract account keys and balance changes
            account_keys = transaction.get("transaction", {}).get("message", {}).get("accountKeys", [])
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])
            
            for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
                if i < len(account_keys):
                    balance_change = post - pre
                    
                    if abs(balance_change) > 1000000:  # Minimum threshold (0.001 SOL)
                        action_type = "buy" if balance_change > 0 else "sell"
                        amount = abs(balance_change) / 10**9  # Convert to SOL
                        
                        actions.append({
                            "trader": account_keys[i],
                            "type": action_type,
                            "amount": amount,
                            "timestamp": block_time
                        })
        
        except Exception as e:
            logger.debug("Error analyzing transaction behavior", extra={"error": str(e)})
        
        return actions
    
    def _classify_trader_behavior(self, actions: List[Dict[str, Any]], cutoff_time: datetime) -> Dict[str, Any]:
        """Classify a trader's behavior as paperhand or diamond hand."""
        if not actions:
            return {"type": "unknown", "volume": 0.0}
        
        # Sort actions by timestamp
        sorted_actions = sorted(actions, key=lambda x: x["timestamp"])
        
        # Look for quick buy-sell patterns (paperhands)
        total_volume = sum(action["amount"] for action in actions)
        
        for i, action in enumerate(sorted_actions):
            if action["type"] == "buy":
                # Look for a sell within the threshold period
                for j in range(i+1, len(sorted_actions)):
                    next_action = sorted_actions[j]
                    if next_action["type"] == "sell":
                        time_diff = next_action["timestamp"] - action["timestamp"]
                        if time_diff <= timedelta(hours=self.paperhand_threshold_hours):
                            return {"type": "paperhand", "volume": total_volume}
                        break
        
        # If no quick sell pattern found, consider diamond hands
        # Also consider if they've been holding for a long time
        if sorted_actions:
            first_action = sorted_actions[0]
            time_since_first = datetime.now(timezone.utc) - first_action["timestamp"]
            
            if time_since_first > timedelta(days=7):  # Held for more than a week
                return {"type": "diamond", "volume": total_volume}
        
        return {"type": "neutral", "volume": total_volume}
    
    def _calculate_percentage_change(self, current: float, previous: float) -> float:
        """Calculate percentage change between two values."""
        if previous == 0:
            return 0.0
        return ((current - previous) / previous) * 100
    
    def _calculate_median_balance(self, holders: List[Dict[str, Any]]) -> float:
        """Calculate median balance among holders."""
        if not holders:
            return 0.0
        
        balances = sorted([h["balance"] for h in holders])
        n = len(balances)
        
        if n % 2 == 0:
            return (balances[n//2 - 1] + balances[n//2]) / 2
        else:
            return balances[n//2]
    
    def _calculate_gini_coefficient(self, holders: List[Dict[str, Any]]) -> float:
        """Calculate Gini coefficient for wealth distribution."""
        if not holders:
            return 0.0
        
        balances = sorted([h["balance"] for h in holders])
        n = len(balances)
        
        if n == 0:
            return 0.0
        
        cumsum = sum(balances)
        if cumsum == 0:
            return 0.0
        
        # Gini coefficient calculation
        index = list(range(1, n + 1))
        return (2 * sum(index[i] * balances[i] for i in range(n))) / (n * cumsum) - (n + 1) / n
    
    def _categorize_velocity(self, velocity_ratio: float) -> str:
        """Categorize velocity ratio into descriptive categories."""
        if velocity_ratio > 5.0:
            return "extremely_high"
        elif velocity_ratio > 2.0:
            return "high"
        elif velocity_ratio > 1.0:
            return "moderate"
        elif velocity_ratio > 0.5:
            return "low"
        else:
            return "very_low"
    
    def _categorize_concentration(self, top_1_percent: float) -> str:
        """Categorize concentration ratio into descriptive categories based on top holder."""
        if top_1_percent > 50:
            return "extremely_concentrated"
        elif top_1_percent > 30:
            return "highly_concentrated"
        elif top_1_percent > 15:
            return "moderately_concentrated"
        elif top_1_percent > 5:
            return "somewhat_distributed"
        else:
            return "well_distributed"
    
    def _categorize_paperhand_ratio(self, paperhand_percent: float) -> str:
        """Categorize paperhand ratio into descriptive categories."""
        if paperhand_percent > 70:
            return "extremely_weak_hands"
        elif paperhand_percent > 50:
            return "weak_hands"
        elif paperhand_percent > 30:
            return "mixed_hands"
        elif paperhand_percent > 15:
            return "strong_hands"
        else:
            return "diamond_hands"
    
    async def _get_historical_market_cap(self, token_mint: str) -> Dict[str, Any]:
        """Get historical market cap data for comparison."""
        # This would typically query a database of historical data
        # For now, return placeholder values
        return {
            "market_cap_24h_ago": 0.0,
            "price_change_24h": 0.0
        }
    
    async def _get_market_cap_rank(self, market_cap_usd: float) -> int:
        """Get approximate market cap rank among all tokens."""
        # This would typically query a ranking database
        # For now, return a placeholder
        if market_cap_usd > 1000000:  # $1M+
            return 1000
        elif market_cap_usd > 100000:  # $100K+
            return 5000
        else:
            return 10000
    
    # Real-time update methods
    
    async def start_real_time_tracking(self, token_mint: str, max_accounts_to_monitor: int = 10):
        """Start real-time tracking for a token using WebSocket subscriptions."""
        try:
            # Start WebSocket manager if not already running
            if not solana_websocket_manager._running:
                await solana_websocket_manager.start()
            
            # Subscribe to token accounts for holder changes
            await solana_websocket_manager.subscribe_to_token_accounts(token_mint, max_accounts_to_monitor)
            
            # Subscribe to program logs for transaction analysis
            await solana_websocket_manager.subscribe_to_program_logs(token_mint)
            
            logger.info("Started real-time tracking", extra={
                "token_mint": token_mint,
                "max_accounts": max_accounts_to_monitor
            })
            
        except Exception as e:
            logger.error("Error starting real-time tracking", extra={
                "token_mint": token_mint,
                "max_accounts": max_accounts_to_monitor,
                "error": str(e)
            })
            raise
    
    async def get_real_time_update(self, token_mint: str) -> Dict[str, Any]:
        """Get the latest real-time metrics for a token."""
        return await self.get_comprehensive_metrics(token_mint)

    async def get_or_create_token(self, token_mint: str) -> Optional[Token]:
        """
        Get token from database or create if it doesn't exist.
        
        Args:
            token_mint: Token mint address
            
        Returns:
            Token model instance
        """
        try:
            async for db_session in get_async_db():
                try:
                    # First, try to get existing token
                    stmt = select(Token).where(Token.address == token_mint)
                    result = await db_session.execute(stmt)
                    token = result.scalar_one_or_none()
                    
                    if token:
                        logger.info("Found existing token in database", extra={
                            "token_mint": token_mint,
                            "name": token.name,
                            "symbol": token.symbol
                        })
                        return token
                    
                    # Token doesn't exist, fetch metadata and create
                    logger.info("Token not found in database, fetching metadata", extra={
                        "token_mint": token_mint
                    })
                    
                    async with await get_helius_client() as client:
                        metadata = await client.get_comprehensive_token_metadata(token_mint)
                        
                        if not metadata:
                            logger.warning("Could not fetch token metadata", extra={
                                "token_mint": token_mint
                            })
                            # Create with minimal info
                            metadata = {
                                "address": token_mint,
                                "name": None,
                                "symbol": None,
                                "decimals": 9
                            }
                    
                    # Create new token record
                    # Convert raw supply to UI amount to prevent database overflow
                    raw_supply = metadata.get("supply")
                    decimals = metadata.get("decimals", 9)
                    ui_supply = None
                    if raw_supply is not None and raw_supply > 0:
                        ui_supply = float(raw_supply) / (10 ** decimals)
                    
                    new_token = Token(
                        address=token_mint,
                        name=metadata.get("name"),
                        symbol=metadata.get("symbol"),
                        decimals=decimals,
                        total_supply=ui_supply,
                        creator=metadata.get("mint_authority"),
                        is_active=True,
                        currency=metadata.get("price_currency"),
                        description=metadata.get("description"),
                        image_url=metadata.get("image_url"),
                        external_url=metadata.get("external_url"),
                        collection_address=metadata.get("collection_address"),
                        token_standard=metadata.get("token_standard"),
                        is_mutable=metadata.get("is_mutable"),
                        is_burnt=metadata.get("is_burnt")
                    )
                    
                    db_session.add(new_token)
                    await db_session.commit()
                    await db_session.refresh(new_token)
                    
                    logger.info("Created new token in database", extra={
                        "token_mint": token_mint,
                        "name": new_token.name,
                        "symbol": new_token.symbol,
                        "token_id": str(new_token.id)
                    })
                    
                    return new_token
                    
                except Exception as e:
                    await db_session.rollback()
                    logger.error("Database error in get_or_create_token", extra={
                        "token_mint": token_mint,
                        "error": str(e)
                    })
                    raise
                
                break  # Exit the async generator loop
                
        except Exception as e:
            logger.error("Error in get_or_create_token", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            return None
    
    async def update_token_metadata(self, token_mint: str, force_refresh: bool = False) -> Optional[Token]:
        """
        Update token metadata from external sources.
        
        Args:
            token_mint: Token mint address
            force_refresh: Whether to force refresh even if recently updated
            
        Returns:
            Updated token model instance
        """
        try:
            async for db_session in get_async_db():
                try:
                    # Get existing token
                    stmt = select(Token).where(Token.address == token_mint)
                    result = await db_session.execute(stmt)
                    token = result.scalar_one_or_none()
                    
                    if not token:
                        return await self.get_or_create_token(token_mint)
                    
                    # Check if we need to refresh
                    if not force_refresh and token.updated_at:
                        time_since_update = datetime.now(timezone.utc) - token.updated_at.replace(tzinfo=timezone.utc)
                        if time_since_update < timedelta(hours=1):  # Don't refresh more than once per hour
                            return token
                    
                    # Fetch fresh metadata
                    async with await get_helius_client() as client:
                        metadata = await client.get_comprehensive_token_metadata(token_mint)
                        
                        if metadata:
                            # Update token with new metadata
                            if metadata.get("name") and not token.name:
                                token.name = metadata["name"]
                            if metadata.get("symbol") and not token.symbol:
                                token.symbol = metadata["symbol"]
                            if metadata.get("decimals") is not None:
                                token.decimals = metadata["decimals"]
                            if metadata.get("supply") is not None:
                                # Convert raw supply to UI amount to prevent database overflow
                                raw_supply = metadata["supply"]
                                decimals = metadata.get("decimals", token.decimals)
                                if raw_supply > 0:
                                    ui_supply = float(raw_supply) / (10 ** decimals)
                                    token.total_supply = ui_supply
                                else:
                                    token.total_supply = 0
                            
                            # Update enhanced metadata fields
                            if metadata.get("price_currency"):
                                token.currency = metadata["price_currency"]
                            if metadata.get("description"):
                                token.description = metadata["description"]
                            if metadata.get("image_url"):
                                token.image_url = metadata["image_url"]
                            if metadata.get("external_url"):
                                token.external_url = metadata["external_url"]
                            if metadata.get("collection_address"):
                                token.collection_address = metadata["collection_address"]
                            if metadata.get("token_standard"):
                                token.token_standard = metadata["token_standard"]
                            if metadata.get("is_mutable") is not None:
                                token.is_mutable = metadata["is_mutable"]
                            if metadata.get("is_burnt") is not None:
                                token.is_burnt = metadata["is_burnt"]
                            
                            await db_session.commit()
                            await db_session.refresh(token)
                            
                            logger.info("Updated token metadata", extra={
                                "token_mint": token_mint,
                                "name": token.name,
                                "symbol": token.symbol
                            })
                    
                    return token
                    
                except Exception as e:
                    await db_session.rollback()
                    logger.error("Database error in update_token_metadata", extra={
                        "token_mint": token_mint,
                        "error": str(e)
                    })
                    raise
                
                break  # Exit the async generator loop
                
        except Exception as e:
            logger.error("Error in update_token_metadata", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            return None
    
    async def store_token_metrics(self, token_id: str, metrics_data: Dict[str, Any]) -> bool:
        """
        Store calculated metrics in the database.
        
        Args:
            token_id: Token UUID
            metrics_data: Calculated metrics data
            
        Returns:
            True if stored successfully
        """
        try:
            async for db_session in get_async_db():
                try:
                    # Extract metrics from the comprehensive data
                    market_cap = metrics_data.get("market_cap", {})
                    velocity = metrics_data.get("velocity", {})
                    concentration = metrics_data.get("concentration", {})
                    paperhand = metrics_data.get("paperhand", {})
                    concentration_ratios = concentration.get("concentration_ratios", {})
                    
                    # Handle concentration ratios properly - use available data or NULL
                    top_1_concentration = concentration_ratios.get("top_1")
                    top_5_concentration = concentration_ratios.get("top_5") 
                    top_15_concentration = concentration_ratios.get("top_15")
                    
                    # For database storage, map our new metrics to the old column names for compatibility
                    # This allows us to store the new metrics in the existing database structure
                    
                    # Calculate turnover rate safely
                    volume_24h = velocity.get("volume_24h_usd", 0) or 0
                    market_cap_value = market_cap.get("market_cap_usd", 0) or 0
                    turnover_rate = (volume_24h / market_cap_value) if market_cap_value > 0 else None
                    
                    # Create new metrics record
                    token_metrics = TokenMetrics(
                        token_id=token_id,
                        price_usd=market_cap.get("current_price_usd"),
                        market_cap=market_cap.get("market_cap_usd"),
                        volume_24h=volume_24h if volume_24h > 0 else None,
                        price_change_24h=market_cap.get("price_change_24h_percent"),
                        token_velocity=velocity.get("velocity_ratio"),
                        turnover_rate=turnover_rate,
                        concentration_top_1=top_1_concentration,
                        concentration_top_5=top_5_concentration,
                        concentration_top_15=top_15_concentration,  
                        holder_count=concentration.get("total_holders"),
                        paperhand_ratio=paperhand.get("paperhand_ratio_percent") if paperhand.get("paperhand_ratio_percent", 0) > 0 else None,
                        diamond_hand_ratio=paperhand.get("diamond_hand_ratio_percent") if paperhand.get("diamond_hand_ratio_percent", 0) > 0 else None,
                        avg_holding_time=None,  # Would need historical data
                        transaction_count_24h=velocity.get("transaction_count_24h") if velocity.get("transaction_count_24h", 0) > 0 else None,
                        unique_traders_24h=velocity.get("unique_traders_24h") if velocity.get("unique_traders_24h", 0) > 0 else None,
                        avg_transaction_size=velocity.get("avg_transaction_size_usd") if velocity.get("avg_transaction_size_usd", 0) > 0 else None,
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    db_session.add(token_metrics)
                    await db_session.commit()
                    
                    logger.info("Stored token metrics in database", extra={
                        "token_id": token_id,
                        "market_cap": market_cap.get("market_cap_usd"),
                        "velocity": velocity.get("velocity_ratio"),
                        "top_1_concentration": top_1_concentration,
                        "data_quality": concentration.get("data_quality", "unknown")
                    })
                    
                    return True
                    
                except Exception as e:
                    await db_session.rollback()
                    logger.error("Database error storing token metrics", extra={
                        "token_id": token_id,
                        "error": str(e)
                    })
                    return False
                
                break  # Exit the async generator loop
                
        except Exception as e:
            logger.error("Error storing token metrics", extra={
                "token_id": token_id,
                "error": str(e)
            })
            return False


# Global analytics service instance
token_analytics_service = TokenAnalyticsService() 
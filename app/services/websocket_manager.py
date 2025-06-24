"""
Solana WebSocket manager for real-time token analytics updates.
Implements Solana RPC WebSocket subscriptions for live blockchain data.
"""

import json
import asyncio
import websockets
from typing import Dict, List, Set, Any, Optional, Callable
from datetime import datetime, timezone
from uuid import uuid4
import traceback

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_async_db
from app.models.market_data import Token, TokenMetrics
from app.schemas.market_data import TokenUpdateMessage, WebSocketMessage
from app.services.cache import cache

logger = get_logger(__name__)


class SolanaWebSocketManager:
    """
    Manages Solana RPC WebSocket subscriptions for real-time token analytics.
    
    Implements the following Solana WebSocket methods:
    - accountSubscribe: Monitor token account changes for holder analytics
    - logsSubscribe: Monitor program logs for transaction analysis
    - programSubscribe: Monitor DEX programs for trading activity
    - slotSubscribe: Monitor slot updates for timing analysis
    """
    
    def __init__(self):
        self.api_key = settings.helius_api_key
        self.websocket_url = f"{settings.helius_websocket_url}?api-key={self.api_key}"
        
        # WebSocket connections
        self.solana_websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.client_connections: Dict[str, WebSocket] = {}
        
        # Subscription management
        self.active_subscriptions: Dict[int, Dict[str, Any]] = {}
        self.token_subscriptions: Dict[str, Set[int]] = {}  # token_address -> subscription_ids
        self.subscription_callbacks: Dict[int, Callable] = {}
        
        # Request tracking
        self._request_id = 0
        self._running = False
        
        # Token tracking
        self.tracked_tokens: Set[str] = set()
        
        if not self.api_key:
            raise ValueError("Helius API key is required for WebSocket connections")
    
    def _get_request_id(self) -> int:
        """Get next request ID for WebSocket requests."""
        self._request_id += 1
        return self._request_id
    
    def _is_connection_healthy(self) -> bool:
        """Check if the WebSocket connection is healthy."""
        return (
            self.solana_websocket is not None 
            and not self.solana_websocket.closed 
            and self.solana_websocket.state.name == 'OPEN'
        )
    
    async def start(self):
        """Start the WebSocket manager and connect to Solana."""
        if self._running:
            return
        
        self._running = True
        
        try:
            # Connect to Solana WebSocket
            await self._connect_to_solana()
            
            # Start the message handling loop
            asyncio.create_task(self._handle_solana_messages())
            
            logger.info("Solana WebSocket manager started successfully")
            
        except Exception as e:
            logger.error("Failed to start WebSocket manager", extra={"error": str(e)})
            self._running = False
            raise
    
    async def stop(self):
        """Stop the WebSocket manager and close all connections."""
        self._running = False
        
        try:
            # Close Solana WebSocket first to avoid sending unsubscribe requests
            if self.solana_websocket and not self.solana_websocket.closed:
                try:
                    await self.solana_websocket.close()
                except:
                    pass  # Ignore errors during close
                self.solana_websocket = None
            
            # Close all client connections
            for client_id, websocket in list(self.client_connections.items()):
                try:
                    await websocket.close()
                except:
                    pass
            
            # Clear all data structures
            self.client_connections.clear()
            self.active_subscriptions.clear()
            self.token_subscriptions.clear()
            self.subscription_callbacks.clear()
            self.tracked_tokens.clear()
            
            logger.info("Solana WebSocket manager stopped")
            
        except Exception as e:
            logger.error("Error stopping WebSocket manager", extra={"error": str(e)})
    
    async def _connect_to_solana(self):
        """Connect to Solana WebSocket."""
        try:
            self.solana_websocket = await websockets.connect(
                self.websocket_url,
                max_size=10**7,  # 10MB max message size
                ping_interval=20,  # Send ping every 20 seconds (more frequent)
                ping_timeout=15,   # Wait 15 seconds for pong response
                close_timeout=10,  # Close timeout
                max_queue=32       # Maximum queue size for incoming messages
            )
            logger.info("Connected to Solana WebSocket", extra={"url": self.websocket_url})
            
        except Exception as e:
            logger.error("Failed to connect to Solana WebSocket", extra={
                "url": self.websocket_url,
                "error": str(e)
            })
            raise
    
    async def _handle_solana_messages(self):
        """Handle incoming messages from Solana WebSocket."""
        while self._running:
            try:
                # Check connection health before attempting to receive
                if not self._is_connection_healthy():
                    if self._running:
                        logger.warning("WebSocket connection unhealthy, attempting to reconnect...")
                        await self._reconnect_to_solana()
                    else:
                        break
                    continue
                
                # Use shorter timeout to detect connection issues faster
                message = await asyncio.wait_for(
                    self.solana_websocket.recv(), 
                    timeout=25.0  # Slightly less than ping interval
                )
                data = json.loads(message)
                
                # Handle different message types
                if "method" in data:
                    # Subscription notification
                    await self._handle_subscription_notification(data)
                elif "id" in data and "result" in data:
                    # Subscription response
                    await self._handle_subscription_response(data)
                elif "error" in data:
                    # Error response
                    await self._handle_error_response(data)
                
            except asyncio.TimeoutError:
                # Timeout might indicate connection issues
                logger.debug("Message receive timeout, checking connection health...")
                if not self._is_connection_healthy() and self._running:
                    logger.warning("Connection unhealthy after timeout, reconnecting...")
                    await self._reconnect_to_solana()
                continue
            except websockets.exceptions.ConnectionClosed as e:
                if self._running:
                    logger.warning("Solana WebSocket connection closed", extra={
                        "close_code": getattr(e, 'code', None),
                        "close_reason": getattr(e, 'reason', None)
                    })
                    await self._reconnect_to_solana()
                break
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON from Solana WebSocket", extra={"error": str(e)})
                continue
            except Exception as e:
                if self._running:  # Only log if not shutting down
                    logger.error("Error handling Solana WebSocket message", extra={
                        "error": str(e),
                        "traceback": traceback.format_exc()
                    })
                await asyncio.sleep(1)
    
    async def _reconnect_to_solana(self):
        """Reconnect to Solana WebSocket and restore subscriptions."""
        if not self._running:
            return
        
        try:
            # Close existing connection
            if self.solana_websocket:
                await self.solana_websocket.close()
            
            # Wait before reconnecting
            await asyncio.sleep(5)
            
            # Reconnect
            await self._connect_to_solana()
            
            # Restore all subscriptions
            old_subscriptions = dict(self.active_subscriptions)
            self.active_subscriptions.clear()
            
            for sub_data in old_subscriptions.values():
                try:
                    await self._create_subscription(
                        sub_data["method"],
                        sub_data["params"],
                        sub_data["callback"]
                    )
                except Exception as e:
                    logger.error("Failed to restore subscription", extra={
                        "method": sub_data["method"],
                        "error": str(e)
                    })
            
            logger.info("Solana WebSocket reconnected and subscriptions restored")
            
        except Exception as e:
            logger.error("Failed to reconnect to Solana WebSocket", extra={"error": str(e)})
            # Schedule another reconnect attempt
            if self._running:
                await asyncio.sleep(10)
                await self._reconnect_to_solana()
    
    async def _create_subscription(self, method: str, params: List[Any], callback: Callable) -> int:
        """Create a new Solana WebSocket subscription."""
        request_id = self._get_request_id()
        
        # Store subscription info
        self.active_subscriptions[request_id] = {
            "method": method,
            "params": params,
            "callback": callback,
            "created_at": datetime.now(timezone.utc)
        }
        self.subscription_callbacks[request_id] = callback
        
        # Send subscription request
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        try:
            # Check if connection is still open before sending
            if not self._is_connection_healthy():
                logger.warning("WebSocket connection closed, attempting to reconnect before subscription", extra={
                    "method": method,
                    "request_id": request_id
                })
                
                # Attempt to reconnect
                try:
                    await self._connect_to_solana()
                    logger.info("Successfully reconnected before subscription", extra={
                        "method": method,
                        "request_id": request_id
                    })
                except Exception as reconnect_error:
                    logger.error("Failed to reconnect WebSocket for subscription", extra={
                        "method": method,
                        "request_id": request_id,
                        "reconnect_error": str(reconnect_error)
                    })
                    # Clean up and raise the original error
                    self.active_subscriptions.pop(request_id, None)
                    self.subscription_callbacks.pop(request_id, None)
                    raise
            
            await self.solana_websocket.send(json.dumps(request))
            logger.debug("Sent subscription request", extra={
                "method": method,
                "request_id": request_id,
                "params": params
            })
            return request_id
            
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning("WebSocket connection closed during subscription, will retry", extra={
                "method": method,
                "request_id": request_id,
                "error": str(e)
            })
            
            # Try to reconnect and retry once
            try:
                await self._connect_to_solana()
                await self.solana_websocket.send(json.dumps(request))
                logger.info("Successfully retried subscription after reconnection", extra={
                    "method": method,
                    "request_id": request_id
                })
                return request_id
            except Exception as retry_error:
                logger.error("Failed to retry subscription after reconnection", extra={
                    "method": method,
                    "request_id": request_id,
                    "retry_error": str(retry_error)
                })
                # Clean up on failure
                self.active_subscriptions.pop(request_id, None)
                self.subscription_callbacks.pop(request_id, None)
                raise
            
        except Exception as e:
            # Clean up on failure
            self.active_subscriptions.pop(request_id, None)
            self.subscription_callbacks.pop(request_id, None)
            logger.error("Failed to send subscription request", extra={
                "method": method,
                "request_id": request_id,
                "error": str(e)
            })
            raise
    
    async def _unsubscribe(self, request_id: int):
        """Unsubscribe from a Solana WebSocket subscription using request ID."""
        if request_id not in self.active_subscriptions:
            return
        
        sub_data = self.active_subscriptions[request_id]
        method = sub_data["method"]
        actual_subscription_id = sub_data.get("subscription_id")
        
        # Only try to unsubscribe if we have the actual subscription ID
        if actual_subscription_id is not None:
            # Determine unsubscribe method
            unsubscribe_method = method.replace("Subscribe", "Unsubscribe")
            
            request = {
                "jsonrpc": "2.0",
                "id": self._get_request_id(),
                "method": unsubscribe_method,
                "params": [actual_subscription_id]
            }
            
            try:
                if self.solana_websocket and not self.solana_websocket.closed:
                    await self.solana_websocket.send(json.dumps(request))
                    logger.debug("Sent unsubscribe request", extra={
                        "method": unsubscribe_method,
                        "subscription_id": actual_subscription_id
                    })
                
            except Exception as e:
                logger.error("Failed to send unsubscribe request", extra={
                    "subscription_id": actual_subscription_id,
                    "error": str(e)
                })
        
        # Clean up regardless of success
        self.active_subscriptions.pop(request_id, None)
        if actual_subscription_id is not None:
            self.subscription_callbacks.pop(actual_subscription_id, None)
    
    async def _handle_subscription_notification(self, data: Dict[str, Any]):
        """Handle subscription notification from Solana."""
        try:
            method = data.get("method")
            params = data.get("params", {})
            
            # Extract subscription ID and result
            subscription_id = params.get("subscription")
            result = params.get("result")
            
            if subscription_id in self.subscription_callbacks:
                callback = self.subscription_callbacks[subscription_id]
                await callback(subscription_id, result)
            else:
                logger.warning("Received notification for unknown subscription", extra={
                    "subscription_id": subscription_id,
                    "method": method
                })
                
        except Exception as e:
            logger.error("Error handling subscription notification", extra={
                "data": data,
                "error": str(e)
            })
    
    async def _handle_subscription_response(self, data: Dict[str, Any]):
        """Handle subscription response from Solana."""
        request_id = data.get("id")
        result = data.get("result")  # This is the actual subscription ID
        
        if request_id in self.active_subscriptions:
            sub_data = self.active_subscriptions[request_id]
            logger.info("Subscription confirmed", extra={
                "method": sub_data["method"],
                "request_id": request_id,
                "subscription_id": result
            })
            
            # Move the callback to use the actual subscription ID
            callback = sub_data["callback"]
            self.subscription_callbacks[result] = callback
            
            # Update subscription data with actual subscription ID
            sub_data["subscription_id"] = result
            
            # Keep the request_id mapping for unsubscribe operations
            
        else:
            logger.warning("Received response for unknown request", extra={
                "request_id": request_id,
                "result": result
            })
    
    async def _handle_error_response(self, data: Dict[str, Any]):
        """Handle error response from Solana."""
        request_id = data.get("id")
        error = data.get("error", {})
        
        logger.error("Solana WebSocket error", extra={
            "request_id": request_id,
            "error_code": error.get("code"),
            "error_message": error.get("message"),
            "error_data": error.get("data")
        })
        
        # Clean up failed subscription
        if request_id in self.active_subscriptions:
            self.active_subscriptions.pop(request_id, None)
            self.subscription_callbacks.pop(request_id, None)
    
    # Token-specific subscription methods
    
    async def subscribe_to_token_accounts(self, token_mint: str, max_accounts_to_monitor: int = 10) -> List[int]:
        """
        Subscribe to token account changes for holder analysis.
        
        Note: Uses getTokenLargestAccounts which returns max 20 accounts per Helius API.
        
        Args:
            token_mint: Token mint address to monitor
            max_accounts_to_monitor: Maximum number of accounts to monitor (must be >1 and <total available accounts)
            
        Returns:
            List of subscription IDs
        """
        subscription_ids = []
        
        try:
            # Validate max_accounts_to_monitor parameter
            if max_accounts_to_monitor <= 1:
                raise ValueError("max_accounts_to_monitor must be greater than 1")
            
            # Get largest token accounts to monitor
            from app.services.solana.helius_client import get_helius_client
            
            try:
                async with await get_helius_client() as client:
                    largest_accounts = await client.get_token_largest_accounts(token_mint)
            except Exception as e:
                logger.error("Failed to get largest accounts for WebSocket", extra={
                    "token_mint": token_mint,
                    "error": str(e)
                })
                return []
            
            if not largest_accounts:
                logger.info("No accounts to monitor for token", extra={
                    "token_mint": token_mint,
                    "reason": "no_large_accounts_or_rate_limited"
                })
                return []
            
            # Validate that max_accounts_to_monitor is less than total available accounts
            total_available_accounts = len(largest_accounts)           
            # Select accounts to monitor based on the frontend parameter
            accounts_to_monitor = largest_accounts[:min(max_accounts_to_monitor, total_available_accounts)]
            
            for i, account in enumerate(accounts_to_monitor):
                account_address = account["address"]
                
                # Account subscription for balance changes
                callback = self._create_account_callback(token_mint, account_address)
                
                try:
                    sub_id = await self._create_subscription(
                        "accountSubscribe",
                        [
                            account_address,
                            {
                                "encoding": "jsonParsed",
                                "commitment": "finalized"
                            }
                        ],
                        callback
                    )
                    
                    subscription_ids.append(sub_id)
                    
                    # Track token subscriptions
                    if token_mint not in self.token_subscriptions:
                        self.token_subscriptions[token_mint] = set()
                    self.token_subscriptions[token_mint].add(sub_id)
                    
                    # Small delay between subscriptions for rate limiting
                    if i > 0 and i % 5 == 0:  # Delay every 5 subscriptions
                        await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.warning("Failed to subscribe to account", extra={
                        "account": account_address,
                        "error": str(e)
                    })
            
            self.tracked_tokens.add(token_mint)
            
            logger.info("Subscribed to token accounts", extra={
                "token_mint": token_mint,
                "accounts_monitored": len(subscription_ids),
                "requested_max": max_accounts_to_monitor,
                "total_available": len(largest_accounts),
            })
            
            return subscription_ids
            
        except Exception as e:
            logger.error("Failed to subscribe to token accounts", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            # Clean up partial subscriptions
            for sub_id in subscription_ids:
                try:
                    await self._unsubscribe(sub_id)
                except:
                    pass
            return []
    
    async def subscribe_to_program_logs(self, token_mint: str) -> int:
        """
        Subscribe to program logs for transaction analysis.
        
        Args:
            token_mint: Token mint address to monitor
            
        Returns:
            Subscription ID
        """
        try:
            callback = self._create_logs_callback(token_mint)
            
            # Subscribe to SPL Token program logs mentioning this token
            sub_id = await self._create_subscription(
                "logsSubscribe",
                [
                    {
                        "mentions": [token_mint]
                    },
                    {
                        "commitment": "finalized"
                    }
                ],
                callback
            )
            
            # Track token subscriptions
            if token_mint not in self.token_subscriptions:
                self.token_subscriptions[token_mint] = set()
            self.token_subscriptions[token_mint].add(sub_id)
            
            logger.info("Subscribed to program logs", extra={
                "token_mint": token_mint,
                "subscription_id": sub_id
            })
            
            return sub_id
            
        except Exception as e:
            logger.error("Failed to subscribe to program logs", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
            raise
    
    def _create_account_callback(self, token_mint: str, account_address: str) -> Callable:
        """Create callback for account subscription notifications."""
        
        async def account_callback(subscription_id: int, result: Dict[str, Any]):
            try:
                # Extract account data
                value = result.get("value", {})
                account_info = value.get("data", {})
                
                if isinstance(account_info, dict) and "parsed" in account_info:
                    parsed_data = account_info["parsed"]["info"]
                    
                    # Extract balance information
                    token_amount = parsed_data.get("tokenAmount", {})
                    balance = float(token_amount.get("uiAmount", 0))
                    owner = parsed_data.get("owner", "")
                    
                    # Create update message
                    update_data = {
                        "type": "account_update",
                        "token_mint": token_mint,
                        "account_address": account_address,
                        "owner": owner,
                        "balance": balance,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Broadcast to subscribed clients
                    await self._broadcast_token_update(token_mint, update_data)
                    
                    # Update cache
                    await self._update_token_cache(token_mint)
                    
                    logger.debug("Account update processed", extra={
                        "token_mint": token_mint,
                        "account": account_address,
                        "balance": balance,
                        "owner": owner
                    })
                    
            except Exception as e:
                logger.error("Error in account callback", extra={
                    "subscription_id": subscription_id,
                    "token_mint": token_mint,
                    "account": account_address,
                    "error": str(e)
                })
        
        return account_callback
    
    def _create_logs_callback(self, token_mint: str) -> Callable:
        """Create callback for logs subscription notifications."""
        
        async def logs_callback(subscription_id: int, result: Dict[str, Any]):
            try:
                # Extract log information
                signature = result.get("signature", "")
                logs = result.get("logs", [])
                err = result.get("err")
                
                # Filter for relevant token operations
                relevant_logs = [
                    log for log in logs 
                    if token_mint in log or "Transfer" in log or "Mint" in log
                ]
                
                if relevant_logs:
                    # Create transaction update message
                    update_data = {
                        "type": "transaction_update",
                        "token_mint": token_mint,
                        "signature": signature,
                        "logs": relevant_logs,
                        "status": "success" if err is None else "failed",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Broadcast to subscribed clients
                    await self._broadcast_token_update(token_mint, update_data)
                    
                    # Trigger analytics update
                    await self._process_transaction_update(token_mint, signature)
                    
                    logger.debug("Transaction update processed", extra={
                        "token_mint": token_mint,
                        "signature": signature,
                        "status": "success" if err is None else "failed"
                    })
                    
            except Exception as e:
                logger.error("Error in logs callback", extra={
                    "subscription_id": subscription_id,
                    "token_mint": token_mint,
                    "error": str(e)
                })
        
        return logs_callback
    
    async def _broadcast_token_update(self, token_mint: str, update_data: Dict[str, Any]):
        """Broadcast update to all clients subscribed to this token."""
        try:
            # Find clients subscribed to this token
            message = TokenUpdateMessage(
                token_address=token_mint,
                metrics=update_data,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Broadcast to all connected clients
            # (In a real implementation, you'd filter by client subscriptions)
            dead_connections = []
            
            for client_id, websocket in self.client_connections.items():
                try:
                    await websocket.send_text(json.dumps(message.dict(), default=str))
                except Exception as e:
                    logger.debug("Client connection failed", extra={
                        "client_id": client_id,
                        "error": str(e)
                    })
                    dead_connections.append(client_id)
            
            # Clean up dead connections
            for client_id in dead_connections:
                self.client_connections.pop(client_id, None)
                
        except Exception as e:
            logger.error("Error broadcasting token update", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
    
    async def _update_token_cache(self, token_mint: str):
        """Update cached token metrics after real-time updates."""
        try:
            # Trigger cache refresh for this token
            cache_key = f"metrics:{token_mint}"
            await cache.delete(cache_key)
            
            # Could trigger a background task to recalculate metrics
            logger.debug("Token cache invalidated", extra={"token_mint": token_mint})
            
        except Exception as e:
            logger.debug("Error updating token cache", extra={
                "token_mint": token_mint,
                "error": str(e)
            })
    
    async def _process_transaction_update(self, token_mint: str, signature: str):
        """Process a transaction update for analytics."""
        try:
            # This could trigger background analytics calculations
            # For now, just log the transaction
            logger.debug("Processing transaction update", extra={
                "token_mint": token_mint,
                "signature": signature
            })
            
            # Could enqueue for background processing:
            # - Update velocity calculations
            # - Update paperhand analysis
            # - Update volume metrics
            
        except Exception as e:
            logger.debug("Error processing transaction update", extra={
                "token_mint": token_mint,
                "signature": signature,
                "error": str(e)
            })
    
    # Client connection management
    
    async def add_client(self, websocket: WebSocket, client_id: str = None) -> str:
        """Add a client WebSocket connection."""
        if not client_id:
            client_id = str(uuid4())
        
        await websocket.accept()
        self.client_connections[client_id] = websocket
        
        logger.info("Client connected", extra={"client_id": client_id})
        return client_id
    
    async def remove_client(self, client_id: str):
        """Remove a client WebSocket connection."""
        websocket = self.client_connections.pop(client_id, None)
        if websocket:
            try:
                await websocket.close()
            except:
                pass
        
        logger.info("Client disconnected", extra={"client_id": client_id})
    
    async def subscribe_client_to_token(self, client_id: str, token_mint: str, max_accounts_to_monitor: int = 15):
        """Subscribe a client to token updates."""
        if token_mint not in self.tracked_tokens:
            # Start tracking this token
            await self.subscribe_to_token_accounts(token_mint, max_accounts_to_monitor)
            await self.subscribe_to_program_logs(token_mint)
        
        logger.info("Client subscribed to token", extra={
            "client_id": client_id,
            "token_mint": token_mint,
            "max_accounts": max_accounts_to_monitor
        })
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket manager statistics."""
        connection_healthy = self._is_connection_healthy()
        return {
            "connected_clients": len(self.client_connections),
            "active_subscriptions": len(self.active_subscriptions),
            "tracked_tokens": len(self.tracked_tokens),
            "solana_connected": connection_healthy,
            "connection_state": self.solana_websocket.state.name if self.solana_websocket else "DISCONNECTED",
            "running": self._running,
            "websocket_url": self.websocket_url if connection_healthy else None
        }


# Global WebSocket manager instance
solana_websocket_manager = SolanaWebSocketManager() 
"""
Redis-based caching service for market data.
Provides caching for price data, moving averages, and provider responses.
"""

import json
import pickle
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List, Union

import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CacheService:
    """Redis-based cache service for market data."""
    
    def __init__(self):
        self.pool: Optional[ConnectionPool] = None
        self.redis: Optional[redis.Redis] = None
        self._connected = False
        self.default_ttl = settings.redis_cache_ttl  # Add default TTL property
    
    async def connect(self):
        """Initialize Redis connection."""
        try:
            self.pool = ConnectionPool.from_url(
                settings.redis_url,
                decode_responses=True,
                max_connections=20,
                retry_on_timeout=True,
            )
            self.redis = redis.Redis(connection_pool=self.pool)
            
            # Test connection
            await self.redis.ping()
            self._connected = True
            logger.info("Redis cache connected successfully")
            
        except Exception as e:
            logger.error("Failed to connect to Redis", extra={"error": str(e)})
            self._connected = False
            raise
    
    async def disconnect(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.aclose()
        if self.pool:
            await self.pool.aclose()
        self._connected = False
        logger.info("Redis connection closed")
    
    async def _ensure_connection(self):
        """Ensure Redis connection is active."""
        if not self._connected or not self.redis:
            await self.connect()
    
    def _make_key(self, prefix: str, *args: str) -> str:
        """Create a cache key with consistent formatting."""
        parts = [prefix] + [str(arg).upper() for arg in args]
        return ":".join(parts)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        await self._ensure_connection()
        
        try:
            value = await self.redis.get(key)
            if value is None:
                return None
            
            # Try to deserialize as JSON first, then pickle
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                try:
                    return pickle.loads(value.encode('latin1'))
                except Exception:
                    return value
                    
        except Exception as e:
            logger.error("Cache get error", extra={"key": key, "error": str(e)})
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None, 
        serialize_json: bool = True
    ) -> bool:
        """Set value in cache with optional TTL."""
        await self._ensure_connection()
        
        try:
            ttl = ttl or settings.redis_cache_ttl
            
            # Serialize value
            if serialize_json:
                try:
                    serialized_value = json.dumps(value, default=str)
                except (TypeError, ValueError):
                    serialized_value = pickle.dumps(value).decode('latin1')
            else:
                serialized_value = str(value)
            
            await self.redis.setex(key, ttl, serialized_value)
            logger.debug("Cache set", extra={"key": key, "ttl": ttl})
            return True
            
        except Exception as e:
            logger.error("Cache set error", extra={"key": key, "error": str(e)})
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        await self._ensure_connection()
        
        try:
            result = await self.redis.delete(key)
            logger.debug("Cache delete", extra={"key": key, "existed": bool(result)})
            return bool(result)
            
        except Exception as e:
            logger.error("Cache delete error", extra={"key": key, "error": str(e)})
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        await self._ensure_connection()
        
        try:
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.error("Cache exists error", extra={"key": key, "error": str(e)})
            return False
    
    async def ttl(self, key: str) -> Optional[int]:
        """Get TTL for a key."""
        await self._ensure_connection()
        
        try:
            ttl_value = await self.redis.ttl(key)
            return ttl_value if ttl_value >= 0 else None
        except Exception as e:
            logger.error("Cache TTL error", extra={"key": key, "error": str(e)})
            return None
    
    async def increment(self, key: str, amount: int = 1, ttl: Optional[int] = None) -> Optional[int]:
        """Increment a numeric value in cache."""
        await self._ensure_connection()
        
        try:
            pipe = self.redis.pipeline()
            pipe.incr(key, amount)
            if ttl:
                pipe.expire(key, ttl)
            results = await pipe.execute()
            return results[0]
            
        except Exception as e:
            logger.error("Cache increment error", extra={"key": key, "error": str(e)})
            return None
    
    # Market data specific methods
    async def get_price(self, symbol: str, provider: str) -> Optional[Dict[str, Any]]:
        """Get cached price data for a symbol."""
        key = self._make_key("price", symbol, provider)
        return await self.get(key)
    
    async def set_price(
        self, 
        symbol: str, 
        provider: str, 
        price_data: Dict[str, Any], 
        ttl: Optional[int] = None
    ) -> bool:
        """Cache price data for a symbol."""
        key = self._make_key("price", symbol, provider)
        return await self.set(key, price_data, ttl)
    
    async def get_moving_average(
        self, 
        symbol: str, 
        window_size: int
    ) -> Optional[Dict[str, Any]]:
        """Get cached moving average data."""
        key = self._make_key("ma", symbol, str(window_size))
        return await self.get(key)
    
    async def set_moving_average(
        self, 
        symbol: str, 
        window_size: int, 
        ma_data: Dict[str, Any], 
        ttl: Optional[int] = None
    ) -> bool:
        """Cache moving average data."""
        key = self._make_key("ma", symbol, str(window_size))
        return await self.set(key, ma_data, ttl)
    
    async def invalidate_symbol_cache(self, symbol: str) -> int:
        """Invalidate all cache entries for a symbol."""
        await self._ensure_connection()
        
        try:
            pattern = f"*:{symbol.upper()}:*"
            keys = await self.redis.keys(pattern)
            
            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info("Invalidated symbol cache", extra={
                    "symbol": symbol, 
                    "keys_deleted": deleted
                })
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error("Cache invalidation error", extra={"symbol": symbol, "error": str(e)})
            return 0
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        await self._ensure_connection()
        
        try:
            info = await self.redis.info()
            
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0), 
                    info.get("keyspace_misses", 0)
                ),
                "total_commands_processed": info.get("total_commands_processed", 0),
            }
            
        except Exception as e:
            logger.error("Cache stats error", extra={"error": str(e)})
            return {}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage."""
        total = hits + misses
        return (hits / total * 100) if total > 0 else 0.0
    
    async def warm_token_cache(self, token_address: str) -> bool:
        """Pre-populate cache with commonly accessed token data."""
        try:
            logger.info("Warming cache for token", extra={"token_address": token_address})
            
            # Import here to avoid circular imports
            from app.services.token_analytics_service import token_analytics_service
            
            # Pre-load frequently accessed data
            cache_tasks = []
            
            # 1. Comprehensive metrics (this includes all the metrics we need)
            metrics_task = token_analytics_service.get_comprehensive_metrics(token_address)
            cache_tasks.append(metrics_task)
            
            # Execute cache warming tasks
            import asyncio
            results = await asyncio.gather(*cache_tasks, return_exceptions=True)
            
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            
            logger.info("Cache warming completed", extra={
                "token_address": token_address,
                "success_count": success_count,
                "total_tasks": len(cache_tasks)
            })
            
            return success_count > 0
            
        except Exception as e:
            logger.error("Cache warming failed", extra={
                "token_address": token_address,
                "error": str(e)
            })
            return False
    
    async def batch_set(self, items: Dict[str, Any], ttl: Optional[int] = None) -> int:
        """Set multiple cache items in a single operation."""
        try:
            await self._ensure_connection()
            
            if not items:
                return 0
            
            # Use Redis pipeline for batch operations
            pipe = self.redis.pipeline()
            
            ttl_to_use = ttl or self.default_ttl
            
            for key, value in items.items():
                serialized_value = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
                pipe.setex(key, ttl_to_use, serialized_value)
            
            results = await pipe.execute()
            success_count = sum(1 for r in results if r)
            
            logger.debug("Batch cache set completed", extra={
                "items_set": success_count,
                "total_items": len(items)
            })
            
            return success_count
            
        except Exception as e:
            logger.error("Batch cache set failed", extra={"error": str(e)})
            return 0
    
    async def batch_get(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple cache items in a single operation."""
        try:
            await self._ensure_connection()
            
            if not keys:
                return {}
            
            # Use Redis pipeline for batch operations
            pipe = self.redis.pipeline()
            
            for key in keys:
                pipe.get(key)
            
            results = await pipe.execute()
            
            # Process results
            cache_data = {}
            for key, result in zip(keys, results):
                if result:
                    try:
                        # Try to deserialize as JSON first
                        cache_data[key] = json.loads(result)
                    except json.JSONDecodeError:
                        # Fallback to string value
                        cache_data[key] = result
            
            hit_count = len(cache_data)
            miss_count = len(keys) - hit_count
            
            logger.debug("Batch cache get completed", extra={
                "hits": hit_count,
                "misses": miss_count,
                "hit_rate": hit_count / len(keys) * 100 if keys else 0
            })
            
            return cache_data
            
        except Exception as e:
            logger.error("Batch cache get failed", extra={"error": str(e)})
            return {}
    
    async def invalidate_token_cache(self, token_address: str) -> int:
        """Invalidate all cache entries for a specific token."""
        try:
            await self._ensure_connection()
            
            # Pattern for token-related cache keys
            patterns = [
                f"metrics:{token_address}",
                f"price:{token_address}:*",
                f"concentration:{token_address}:*",
                f"velocity:{token_address}:*",
                f"paperhand:{token_address}:*",
                f"holders:{token_address}:*",
                f"transactions:{token_address}:*"
            ]
            
            deleted_count = 0
            
            for pattern in patterns:
                # Find keys matching pattern
                keys = await self.redis.keys(pattern)
                if keys:
                    deleted = await self.redis.delete(*keys)
                    deleted_count += deleted
            
            logger.info("Token cache invalidated", extra={
                "token_address": token_address,
                "keys_deleted": deleted_count
            })
            
            return deleted_count
            
        except Exception as e:
            logger.error("Cache invalidation failed", extra={
                "token_address": token_address,
                "error": str(e)
            })
            return 0
    
    async def get_token_metrics_cached(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get token metrics with intelligent caching."""
        cache_key = f"metrics:{token_address}"
        
        # Try to get from cache first
        cached_data = await self.get(cache_key)
        if cached_data:
            # Check if data is recent enough (under 5 minutes)
            cached_time = cached_data.get("timestamp")
            if cached_time:
                from datetime import datetime, timezone, timedelta
                try:
                    cached_dt = datetime.fromisoformat(cached_time.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) - cached_dt < timedelta(minutes=5):
                        return cached_data
                except Exception:
                    pass  # Invalid timestamp, continue to refresh
        
        # Cache miss or stale data - refresh in background
        try:
            from app.services.token_analytics_service import token_analytics_service
            fresh_data = await token_analytics_service.get_comprehensive_metrics(token_address)
            
            if fresh_data:
                # Cache the fresh data
                await self.set(cache_key, fresh_data, ttl=300)  # 5 minutes
                return fresh_data
            
        except Exception as e:
            logger.warning("Failed to refresh token metrics", extra={
                "token_address": token_address,
                "error": str(e)
            })
            # Return stale data if available
            if cached_data:
                return cached_data
        
        return None
    
    async def set_with_tags(self, key: str, value: Any, tags: List[str], ttl: Optional[int] = None) -> bool:
        """Set cache item with tags for group invalidation."""
        try:
            await self._ensure_connection()
            
            # Set the main cache item
            success = await self.set(key, value, ttl)
            
            if success and tags:
                # Add key to tag sets for group invalidation
                pipe = self.redis.pipeline()
                
                for tag in tags:
                    tag_key = f"tag:{tag}"
                    pipe.sadd(tag_key, key)
                    if ttl:
                        # Set expiration for tag slightly longer than cache item
                        pipe.expire(tag_key, ttl + 60)
                
                await pipe.execute()
            
            return success
            
        except Exception as e:
            logger.error("Tagged cache set failed", extra={"key": key, "error": str(e)})
            return False
    
    async def invalidate_by_tag(self, tag: str) -> int:
        """Invalidate all cache items with a specific tag."""
        try:
            await self._ensure_connection()
            
            tag_key = f"tag:{tag}"
            
            # Get all keys with this tag
            keys = await self.redis.smembers(tag_key)
            
            if not keys:
                return 0
            
            # Delete all tagged keys
            deleted = await self.redis.delete(*keys)
            
            # Delete the tag set itself
            await self.redis.delete(tag_key)
            
            logger.info("Cache invalidated by tag", extra={
                "tag": tag,
                "keys_deleted": deleted
            })
            
            return deleted
            
        except Exception as e:
            logger.error("Tag-based cache invalidation failed", extra={
                "tag": tag,
                "error": str(e)
            })
            return 0


# Global cache instance
cache = CacheService() 
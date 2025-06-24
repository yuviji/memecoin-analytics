"""
System metrics and monitoring endpoints.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.logging import get_logger
from app.schemas.market_data import (
    HealthCheckResponse, ServiceMetricsResponse
)
from app.models.market_data import Token, TokenTransaction, TrackingJob
from app.services.cache import cache
from app.services.solana.helius_client import helius_client
from app.services.kafka.producer import kafka_producer
from app.core.config import settings

logger = get_logger(__name__)
router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Get service health status.
    
    **Returns:**
    - Service status and version
    - Database connectivity
    - External service status
    """
    try:
        async for db_session in get_async_db():
            try:
                # Test database connection
                await db_session.execute(select(1))
                database_status = "healthy"
                break
            except Exception as e:
                logger.error("Database health check failed", extra={"error": str(e)})
                database_status = "unhealthy"
    
        # Test Redis connection
        try:
            if hasattr(cache, 'redis') and cache.redis:
                await cache.redis.ping()
                redis_status = "healthy"
            else:
                redis_status = "disconnected"
        except Exception as e:
            logger.error("Redis health check failed", extra={"error": str(e)})
            redis_status = "unhealthy"
        
        # Test Helius API
        try:
            # Simple RPC call to test connectivity using getHealth
            async with helius_client as client:
                await client._make_rpc_request("getHealth", [])
            helius_status = "healthy"
        except Exception as e:
            logger.error("Helius health check failed", extra={"error": str(e)})
            helius_status = "unhealthy"
        
        # Determine overall status
        overall_status = "healthy"
        if database_status != "healthy" or redis_status != "healthy":
            overall_status = "degraded"
        if helius_status != "healthy":
            overall_status = "degraded"
        
        return HealthCheckResponse(
            status=overall_status,
            version=settings.version,
            database=database_status,
            redis=redis_status,
            kafka="not_monitored",  # Kafka monitoring can be added later
            helius=helius_status
        )
        
    except Exception as e:
        logger.error("Health check failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "health_check_failed",
                    "message": "Unable to perform health check"}
        )


@router.get("/service", response_model=ServiceMetricsResponse)
async def get_service_metrics():
    """
    Get comprehensive service metrics.
    
    **Includes:**
    - Token tracking statistics
    - Transaction counts
    - Job status
    - Performance metrics
    """
    try:
        async for db_session in get_async_db():
            try:
                # Count total tracked tokens
                total_tokens_result = await db_session.execute(
                    select(func.count(Token.id)).where(Token.is_active == True)
                )
                total_tokens_tracked = total_tokens_result.scalar() or 0
                
                # Count transactions in last 24h
                twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
                transactions_24h_result = await db_session.execute(
                    select(func.count(TokenTransaction.id)).where(
                        TokenTransaction.timestamp >= twenty_four_hours_ago
                    )
                )
                total_transactions_24h = transactions_24h_result.scalar() or 0
                
                # Count active tracking jobs
                active_jobs_result = await db_session.execute(
                    select(func.count(TrackingJob.id)).where(
                        TrackingJob.status.in_(["pending", "running"])
                    )
                )
                active_tracking_jobs = active_jobs_result.scalar() or 0
                
                # Get cache statistics
                cache_stats = await cache.get_cache_stats()
                cache_hit_rate = cache_stats.get("hit_rate", 0.0)
                
                # Get error count from last hour
                one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                # This could be implemented with error tracking
                errors_last_hour = 0
                
                # Estimate Helius requests (could be tracked via service metrics)
                helius_requests_last_hour = 0
                
                # Calculate average response time (placeholder - implement with actual monitoring)
                average_response_time = 0.0
                
                return ServiceMetricsResponse(
                    total_tokens_tracked=total_tokens_tracked,
                    total_transactions_24h=total_transactions_24h,
                    active_tracking_jobs=active_tracking_jobs,
                    cache_hit_rate=cache_hit_rate,
                    average_response_time=average_response_time,
                    errors_last_hour=errors_last_hour,
                    helius_requests_last_hour=helius_requests_last_hour
                )
                
                break
                
            except Exception as e:
                logger.error("Error getting service metrics", extra={"error": str(e)})
                raise
    
    except Exception as e:
        logger.error("Service metrics failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "metrics_failed",
                    "message": "Unable to retrieve service metrics"}
        )


@router.get("/cache", response_model=Dict[str, Any])
async def get_cache_metrics():
    """
    Get detailed cache performance metrics.
    
    **Returns:**
    - Hit/miss ratios
    - Memory usage
    - Key counts by type
    """
    try:
        cache_stats = await cache.get_cache_stats()
        
        # Get kafka producer stats if available
        kafka_stats = {}
        try:
            if kafka_producer:
                kafka_stats = kafka_producer.get_metrics()
        except Exception as e:
            logger.debug("Could not get kafka stats", extra={"error": str(e)})
            kafka_stats = {"status": "unavailable"}
        
        return {
            "status": "healthy",
            "cache_stats": cache_stats,
            "kafka_stats": kafka_stats,
            "timestamp": datetime.now(timezone.utc)
        }
        
    except Exception as e:
        logger.error("Cache metrics failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "cache_metrics_failed",
                    "message": "Unable to retrieve cache metrics"}
        ) 
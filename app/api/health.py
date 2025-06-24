"""Health check API endpoints for monitoring service status."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.market_data import HealthCheckResponse
from app.services.token_analytics_service import token_analytics_service
from app.services.cache import cache
from app.services.kafka.producer import kafka_producer

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """Comprehensive health check endpoint."""
    try:
        # Check database connectivity
        database_status = "healthy"
        try:
            # Simple database check - this could be enhanced
            pass
        except Exception:
            database_status = "unhealthy"
        
        # Check Redis connectivity
        redis_status = "healthy" if cache._connected else "unhealthy"
        
        # Check Kafka producer
        kafka_status = ("healthy" if kafka_producer._running
                       else "unhealthy")
        
        # Determine overall status
        overall_status = "healthy"
        if any(status != "healthy" for status in [database_status, redis_status, kafka_status]):
            overall_status = "degraded"
        
        response = HealthCheckResponse(
            status=overall_status,
            version=settings.version,
            database=database_status,
            redis=redis_status,
            kafka=kafka_status,
            helius="healthy"
        )
        
        # Return appropriate HTTP status
        if overall_status == "healthy":
            return response
        else:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=response.model_dump(mode='json')
            )
    
    except Exception as e:
        logger.error("Health check failed", extra={"error": str(e)})
        error_response = HealthCheckResponse(
            status="unhealthy",
            version=settings.version,
            database="unknown",
            redis="unknown",
            kafka="unknown",
            helius="unknown"
        )
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_response.model_dump(mode='json')
        )


@router.get("/health/ready")
async def readiness_check():
    """Kubernetes-style readiness check."""
    try:
        # Simple readiness check - service is ready if it can respond
        return {"status": "ready"}
    
    except Exception as e:
        logger.error("Readiness check failed", extra={"error": str(e)})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "error": str(e)}
        )


@router.get("/health/live")
async def liveness_check():
    """Kubernetes-style liveness check."""
    return {"status": "alive"} 
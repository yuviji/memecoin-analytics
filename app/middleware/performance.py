"""
Performance monitoring middleware for tracking API metrics.
Collects real-time performance data for monitoring and optimization.
"""

import time
from typing import Dict, Any
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, Gauge

from app.core.logging import get_logger

logger = get_logger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

ERROR_COUNT = Counter(
    'http_errors_total',
    'Total HTTP errors',
    ['method', 'endpoint', 'error_type']
)

CACHE_OPERATIONS = Counter(
    'cache_operations_total',
    'Total cache operations',
    ['operation', 'result']
)

TOKEN_ANALYTICS_REQUESTS = Counter(
    'token_analytics_requests_total',
    'Total token analytics requests',
    ['endpoint_type', 'token_address']
)

HELIUS_API_CALLS = Counter(
    'helius_api_calls_total',
    'Total Helius API calls',
    ['endpoint', 'status']
)

class PerformanceMetrics:
    """In-memory performance metrics collector."""
    
    def __init__(self, max_history_size: int = 1000):
        self.max_history_size = max_history_size
        
        # Request metrics
        self.request_times = deque(maxlen=max_history_size)
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        
        # Endpoint-specific metrics
        self.endpoint_metrics = defaultdict(lambda: {
            'count': 0,
            'total_time': 0.0,
            'errors': 0,
            'last_access': None
        })
        
        # Real-time counters
        self.hourly_stats = defaultdict(lambda: {
            'requests': 0,
            'errors': 0,
            'avg_response_time': 0.0
        })
        
        self.start_time = datetime.now(timezone.utc)
    
    def record_request(self, method: str, path: str, status_code: int, duration: float):
        """Record a request's performance metrics."""
        current_time = datetime.now(timezone.utc)
        
        # Add to request times for rolling average
        self.request_times.append({
            'timestamp': current_time,
            'duration': duration,
            'status_code': status_code,
            'path': path
        })
        
        # Update endpoint metrics
        endpoint_key = f"{method}:{path}"
        endpoint_stats = self.endpoint_metrics[endpoint_key]
        endpoint_stats['count'] += 1
        endpoint_stats['total_time'] += duration
        endpoint_stats['last_access'] = current_time
        
        if status_code >= 400:
            endpoint_stats['errors'] += 1
            
        # Update hourly stats
        hour_key = current_time.replace(minute=0, second=0, microsecond=0)
        hourly_stats = self.hourly_stats[hour_key]
        hourly_stats['requests'] += 1
        
        if status_code >= 400:
            hourly_stats['errors'] += 1
        
        # Update rolling average response time
        recent_requests = [r for r in self.request_times 
                          if current_time - r['timestamp'] <= timedelta(minutes=5)]
        if recent_requests:
            hourly_stats['avg_response_time'] = sum(r['duration'] for r in recent_requests) / len(recent_requests)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary."""
        current_time = datetime.now(timezone.utc)
        
        # Calculate overall stats
        total_requests = len(self.request_times)
        total_errors = sum(1 for r in self.request_times if r['status_code'] >= 400)
        
        # Recent performance (last 5 minutes)
        recent_cutoff = current_time - timedelta(minutes=5)
        recent_requests = [r for r in self.request_times if r['timestamp'] >= recent_cutoff]
        
        avg_response_time = 0.0
        if recent_requests:
            avg_response_time = sum(r['duration'] for r in recent_requests) / len(recent_requests)
        
        # Error rate calculation
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
        
        # Requests per second (last minute)
        last_minute = current_time - timedelta(minutes=1)
        recent_minute_requests = [r for r in self.request_times if r['timestamp'] >= last_minute]
        rps = len(recent_minute_requests) / 60.0
        
        # Top endpoints by request count
        top_endpoints = sorted(
            [(endpoint, stats['count']) for endpoint, stats in self.endpoint_metrics.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Slowest endpoints
        slow_endpoints = []
        for endpoint, stats in self.endpoint_metrics.items():
            if stats['count'] > 0:
                avg_time = stats['total_time'] / stats['count']
                slow_endpoints.append((endpoint, avg_time))
        slow_endpoints.sort(key=lambda x: x[1], reverse=True)
        
        return {
            'total_requests': total_requests,
            'total_errors': total_errors,
            'error_rate_percent': error_rate,
            'avg_response_time_ms': avg_response_time * 1000,
            'requests_per_second': rps,
            'uptime_seconds': (current_time - self.start_time).total_seconds(),
            'top_endpoints': top_endpoints[:5],
            'slowest_endpoints': slow_endpoints[:5],
            'recent_requests_5min': len(recent_requests),
            'timestamp': current_time.isoformat()
        }

# Global metrics collector
performance_metrics = PerformanceMetrics()

class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware to track API performance metrics."""
    
    async def dispatch(self, request: Request, call_next):
        # Start timing
        start_time = time.time()
        ACTIVE_REQUESTS.inc()
        
        # Extract endpoint info
        method = request.method
        path = request.url.path
        endpoint_label = self._get_endpoint_label(path)
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            status_code = response.status_code
            
            # Record metrics
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint_label,
                status_code=status_code
            ).inc()
            
            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint_label
            ).observe(duration)
            
            # Record in our custom metrics
            performance_metrics.record_request(method, path, status_code, duration)
            
            # Add performance headers
            response.headers["X-Response-Time"] = f"{duration:.3f}s"
            response.headers["X-Request-ID"] = str(id(request))
            
            # Log slow requests
            if duration > 1.0:
                logger.warning("Slow request detected", extra={
                    "method": method,
                    "path": path,
                    "duration": duration,
                    "status_code": status_code
                })
            
            # Record specific analytics
            if path.startswith('/api/v1/tokens/'):
                self._record_token_analytics(path, status_code)
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Record error metrics
            ERROR_COUNT.labels(
                method=method,
                endpoint=endpoint_label,
                error_type=type(e).__name__
            ).inc()
            
            performance_metrics.record_request(method, path, 500, duration)
            
            logger.error("Request processing error", extra={
                "method": method,
                "path": path,
                "duration": duration,
                "error": str(e)
            })
            
            raise
        
        finally:
            ACTIVE_REQUESTS.dec()
    
    def _get_endpoint_label(self, path: str) -> str:
        """Convert path to endpoint label for metrics."""
        # Group similar endpoints together for better metrics
        if path.startswith('/api/v1/tokens/'):
            if path.endswith('/metrics'):
                return 'token_metrics'
            elif path.endswith('/concentration'):
                return 'token_concentration'
            elif path.endswith('/velocity'):
                return 'token_velocity'
            elif path.endswith('/paperhand'):
                return 'token_paperhand'
            elif path.endswith('/price'):
                return 'token_price'
            elif path.endswith('/transactions'):
                return 'token_transactions'
            elif path.endswith('/holders'):
                return 'token_holders'
            elif '/ws/' in path:
                return 'token_websocket'
            else:
                return 'token_other'
        elif path == '/health':
            return 'health'
        elif path == '/metrics':
            return 'prometheus_metrics'
        elif path == '/metrics/app':
            return 'app_metrics'
        else:
            return 'other'
    
    def _record_token_analytics(self, path: str, status_code: int):
        """Record token-specific analytics metrics."""
        # Extract token address from path
        path_parts = path.split('/')
        token_address = 'unknown'
        
        if len(path_parts) >= 4:
            token_address = path_parts[4]  # /api/v1/tokens/{address}/...
        
        endpoint_type = self._get_endpoint_label(path)
        
        TOKEN_ANALYTICS_REQUESTS.labels(
            endpoint_type=endpoint_type,
            token_address=token_address[:10] + "..." if len(token_address) > 10 else token_address
        ).inc()

def record_helius_api_call(endpoint: str, success: bool):
    """Record Helius API call metrics."""
    status = 'success' if success else 'error'
    HELIUS_API_CALLS.labels(endpoint=endpoint, status=status).inc()

def record_cache_operation(operation: str, hit: bool):
    """Record cache operation metrics."""
    result = 'hit' if hit else 'miss'
    CACHE_OPERATIONS.labels(operation=operation, result=result).inc() 
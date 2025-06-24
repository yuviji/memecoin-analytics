"""
FastAPI main application for Trojan Trading Analytics.

Provides REST API + WebSocket support for real-time memecoin trading analytics.
Implements the four core bounty metrics with Solana RPC integration.
"""

from contextlib import asynccontextmanager
from typing import Dict, Any
import os
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import health, metrics, prices
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging, get_logger
from app.services.websocket_manager import solana_websocket_manager
from app.middleware.performance import PerformanceMiddleware

# Setup logging
setup_logging()
logger = get_logger(__name__)


class TimingMiddleware(BaseHTTPMiddleware):
    """Middleware to track request timing."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log slow requests
        if process_time > 1.0:
            logger.warning("Slow request detected", extra={
                "path": request.url.path,
                "method": request.method,
                "process_time": process_time
            })
        
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Trojan Trading Analytics API")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized successfully")
        
        # Token analytics service initialization removed - using async context managers instead
        
        # Start WebSocket manager for real-time updates
        await solana_websocket_manager.start()
        logger.info("WebSocket manager started")
        
    except Exception as e:
        logger.error("Failed to initialize application", extra={"error": str(e)})
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Trojan Trading Analytics API")
    
    try:
        # Stop WebSocket manager first to prevent new requests
        await solana_websocket_manager.stop()
        logger.info("WebSocket manager stopped")
        
        # Shutdown the global Helius client to prevent race conditions
        from app.services.solana.helius_client import shutdown_helius_client
        await shutdown_helius_client()
        logger.info("Helius client shutdown completed")
        
    except Exception as e:
        logger.error("Error during shutdown", extra={"error": str(e)})


# Create FastAPI application
app = FastAPI(
    title="Trojan Trading Analytics",
    description="""
    **Microservice for Memecoin Trading Analytics**

    🎯 **Bounty Submission**: Real-time token analytics with four core metrics

    ## Core Features

    ### 📈 **Market Cap Updates**
    - Real-time token supply × price calculations
    - Historical change tracking

    ### ⚡ **Token Velocity**
    - Trading volume vs market cap ratio
    - Measures how fast tokens change hands
    - 24-hour rolling window analysis

    ### 🏦 **Concentration Ratios**
    - Top holder percentage distribution
    - Whale detection and analysis
    - Gini coefficient for inequality measurement

    ### 💎 **Paperhand Ratio**
    - Weak vs strong holder behavior analysis
    - Quick sell detection algorithms
    - Diamond hand classification

    ## Real-time Features

    - **WebSocket Support**: Live updates via Solana RPC subscriptions
    - **Account Monitoring**: Real-time holder balance changes
    - **Transaction Analysis**: Live trade detection and analysis
    - **Batch Processing**: Multi-token analytics in single requests

    ## Data Sources

    - **Helius**: Enhanced Solana RPC with rate limiting
    - **Solana RPC**: Direct blockchain data access

    ## Endpoints

    - `GET /api/v1/tokens/{token_mint}/analytics` - All four metrics
    - `GET /api/v1/tokens/{token_mint}/market-cap` - Market cap only
    - `GET /api/v1/tokens/{token_mint}/velocity` - Velocity only  
    - `GET /api/v1/tokens/{token_mint}/concentration` - Concentration only
    - `GET /api/v1/tokens/{token_mint}/paperhand` - Paperhand analysis only
    - `POST /api/v1/tokens/{token_mint}/track` - Start real-time tracking
    - `WS /ws/tokens/{token_mint}` - WebSocket for live updates

    ---
    **Built for the Trojan Trading Bounty** | Efficiency at Scale | Real-time Responsiveness
    """,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add performance middleware
app.add_middleware(PerformanceMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add timing middleware
app.add_middleware(TimingMiddleware)

# Include API routers
app.include_router(health.router)
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(prices.router, prefix="/api/v1")

# Mount static files for UI
ui_directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")
if os.path.exists(ui_directory):
    app.mount("/ui", StaticFiles(directory=ui_directory, html=True), name="ui")


# WebSocket endpoint for real-time token updates
@app.websocket("/ws/tokens/{token_mint}")
async def websocket_token_updates(websocket: WebSocket, token_mint: str):
    """
    WebSocket endpoint for real-time token analytics updates.
    
    Provides live streaming of:
    - Market cap changes
    - Velocity updates  
    - Holder concentration changes
    - Transaction analysis
    
    Protocol:
    1. Client must send initial subscription message:
       {"max_accounts_to_monitor": <int between 1-15>}
    2. Server validates and confirms subscription
    3. Server sends initial data and ongoing updates
    
    Args:
        token_mint: Solana token mint address to monitor
    """
    client_id = None
    
    try:
        # Accept WebSocket connection
        client_id = await solana_websocket_manager.add_client(websocket)
        logger.info("WebSocket client connected", extra={
            "client_id": client_id,
            "token_mint": token_mint
        })
        
        # Wait for initial subscription message with parameters
        subscription_message = await websocket.receive_json()
        max_accounts_to_monitor = subscription_message.get("max_accounts_to_monitor", 10)
        
        # Validate max_accounts_to_monitor parameter
        if max_accounts_to_monitor <= 1 or max_accounts_to_monitor > 15:
            await websocket.send_json({
                "type": "error",
                "message": "max_accounts_to_monitor must be greater than 1 and less than or equal to 15",
                "code": "INVALID_PARAMETER"
            })
            await websocket.close(code=1008, reason="Invalid parameter")
            return
        
        # Subscribe client to token updates with specified parameters
        await solana_websocket_manager.subscribe_client_to_token(client_id, token_mint, max_accounts_to_monitor)
        
        # Send initial analytics data
        from app.services.token_analytics_service import token_analytics_service
        initial_data = await token_analytics_service.get_comprehensive_metrics(token_mint)
        
        await websocket.send_json({
            "type": "initial_data",
            "data": initial_data,
            "max_accounts_to_monitor": max_accounts_to_monitor
        })
        
        # Send subscription confirmation
        await websocket.send_json({
            "type": "subscription_confirmed",
            "token_mint": token_mint,
            "max_accounts_to_monitor": max_accounts_to_monitor
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for client messages (ping/pong, subscriptions, etc.)
                message = await websocket.receive_json()
                
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "subscribe_metrics":
                    # Client can request specific metric subscriptions
                    requested_metrics = message.get("metrics", [])
                    await websocket.send_json({
                        "type": "subscription_confirmed",
                        "metrics": requested_metrics
                    })
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("Error in WebSocket message handling", extra={
                    "client_id": client_id,
                    "error": str(e)
                })
                break
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected", extra={
            "client_id": client_id,
            "token_mint": token_mint
        })
    except Exception as e:
        logger.error("WebSocket error", extra={
            "client_id": client_id,
            "token_mint": token_mint,
            "error": str(e)
        })
    finally:
        # Clean up client connection
        if client_id:
            await solana_websocket_manager.remove_client(client_id)


# WebSocket endpoint for general system updates
@app.websocket("/ws/system")
async def websocket_system_updates(websocket: WebSocket):
    """
    WebSocket endpoint for system-wide updates and statistics.
    
    Provides live streaming of:
    - Active token count
    - WebSocket connection stats
    - System health metrics
    """
    client_id = None
    
    try:
        client_id = await solana_websocket_manager.add_client(websocket)
        logger.info("System WebSocket client connected", extra={"client_id": client_id})
        
        # Send initial system stats
        stats = solana_websocket_manager.get_stats()
        await websocket.send_json({
            "type": "system_stats",
            "data": stats
        })
        
        # Keep connection alive
        while True:
            try:
                message = await websocket.receive_json()
                
                if message.get("type") == "get_stats":
                    stats = solana_websocket_manager.get_stats()
                    await websocket.send_json({
                        "type": "system_stats",
                        "data": stats
                    })
                elif message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("Error in system WebSocket", extra={
                    "client_id": client_id,
                    "error": str(e)
                })
                break
                
    except WebSocketDisconnect:
        logger.info("System WebSocket client disconnected", extra={"client_id": client_id})
    except Exception as e:
        logger.error("System WebSocket error", extra={
            "client_id": client_id,
            "error": str(e)
        })
    finally:
        if client_id:
            await solana_websocket_manager.remove_client(client_id)


# Root endpoint
@app.get("/", response_model=Dict[str, Any])
async def root():
    """
    Root endpoint with API information.
    
    Returns:
        API metadata and available endpoints
    """
    return {
        "service": "Trojan Trading Analytics",
        "version": "2.0.0",
        "description": "Microservice for Memecoin Trading Analytics",
        "bounty_features": {
            "market_cap_updates": "✅ Real-time token supply × price",
            "token_velocity": "✅ Volume/MarketCap ratio analysis", 
            "concentration_ratios": "✅ Top holder distribution",
            "paperhand_ratio": "✅ Weak vs strong holder behavior"
        },
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "metrics": "/api/v1/metrics/health",
            "token_analytics": "/api/v1/tokens/{token_mint}/analytics",
            "websocket": "/ws/tokens/{token_mint}",
            "batch_analytics": "/api/v1/tokens/batch/analytics"
        },
        "real_time_features": {
            "websocket_subscriptions": "✅ Solana account monitoring",
            "live_updates": "✅ Real-time metrics streaming",
            "transaction_analysis": "✅ Live trade detection",
            "batch_processing": "✅ Multi-token support"
        },
        "data_sources": ["helius", "jupiter", "solana_rpc"],
        "status": "operational"
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error("Unhandled exception", extra={
        "url": str(request.url),
        "method": request.method,
        "error": str(exc)
    })
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.debug else "An error occurred"
        }
    )


# Health check endpoint handled by the dedicated health router


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    ) 
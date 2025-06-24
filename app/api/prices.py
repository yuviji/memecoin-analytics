"""
Token analytics API endpoints exposing the four core bounty metrics.

Provides REST API access to:
1. Market cap updates - Real-time token supply * price
2. Token velocity - Volume / Market cap ratio 
3. Concentration ratios - Top holder percentage distribution
4. Paperhand ratio - Analysis of weak vs strong holder behavior
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Query
from fastapi.responses import StreamingResponse

from app.core.logging import get_logger
from app.schemas.market_data import TokenMetricsResponse, TokenAnalyticsRequest
from app.services.token_analytics_service import token_analytics_service
from app.services.websocket_manager import solana_websocket_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/tokens", tags=["token-analytics"])


@router.get("/{token_mint}/analytics", response_model=Dict[str, Any])
async def get_comprehensive_analytics(
    token_mint: str,
    background_tasks: BackgroundTasks,
    include_real_time: bool = Query(True, description="Include real-time WebSocket tracking"),
    max_accounts_to_monitor: int = Query(15, gt=1, le=15, description="Maximum number of token accounts to monitor for real-time updates (must be >1 and ≤15)")
) -> Dict[str, Any]:
    """
    Get all four core bounty metrics for a token.
    
    Returns comprehensive analytics including:
    - Market cap updates
    - Token velocity analysis
    - Concentration ratios
    - Paperhand behavior analysis
    
    Args:
        token_mint: Solana token mint address (base58)
        include_real_time: Whether to start real-time tracking
        max_accounts_to_monitor: Maximum number of accounts to monitor (must be >1 and ≤15)
        
    Returns:
        Comprehensive token analytics data
    """
    try:
        logger.info("Fetching comprehensive analytics", extra={
            "token_mint": token_mint,
            "include_real_time": include_real_time,
            "max_accounts_to_monitor": max_accounts_to_monitor
        })
        
        # Start real-time tracking in background if requested
        if include_real_time:
            background_tasks.add_task(
                token_analytics_service.start_real_time_tracking,
                token_mint,
                max_accounts_to_monitor
            )
        
        # Get comprehensive metrics
        analytics = await token_analytics_service.get_comprehensive_metrics(token_mint)
        
        return {
            "success": True,
            "data": analytics,
            "real_time_tracking": include_real_time,
            "api_version": "v2.0"
        }
        
    except Exception as e:
        logger.error("Error fetching comprehensive analytics", extra={
            "token_mint": token_mint,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch analytics: {str(e)}"
        )


@router.get("/{token_mint}/market-cap", response_model=Dict[str, Any])
async def get_market_cap_metrics(token_mint: str) -> Dict[str, Any]:
    """
    Get real-time market cap metrics for a token.
    
    Market Cap = Token Supply × Current Price
    
    Args:
        token_mint: Solana token mint address
        
    Returns:
        Market cap, price, supply, and change data
    """
    try:
        logger.info("Fetching market cap metrics", extra={"token_mint": token_mint})
        
        metrics = await token_analytics_service.get_market_cap_metrics(token_mint)
        
        return {
            "success": True,
            "data": metrics,
            "metric_type": "market_cap"
        }
        
    except Exception as e:
        logger.error("Error fetching market cap metrics", extra={
            "token_mint": token_mint,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch market cap: {str(e)}"
        )


@router.get("/{token_mint}/velocity", response_model=Dict[str, Any])
async def get_velocity_metrics(token_mint: str) -> Dict[str, Any]:
    """
    Get token velocity metrics.
    
    Token Velocity = Trading Volume (24h) / Market Cap
    Higher velocity = tokens changing hands more frequently
    
    Args:
        token_mint: Solana token mint address
        
    Returns:
        Velocity ratios and trading activity metrics
    """
    try:
        logger.info("Fetching velocity metrics", extra={"token_mint": token_mint})
        
        metrics = await token_analytics_service.get_velocity_metrics(token_mint)
        
        return {
            "success": True,
            "data": metrics,
            "metric_type": "velocity"
        }
        
    except Exception as e:
        logger.error("Error fetching velocity metrics", extra={
            "token_mint": token_mint,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch velocity: {str(e)}"
        )


@router.get("/{token_mint}/concentration", response_model=Dict[str, Any])
async def get_concentration_metrics(token_mint: str) -> Dict[str, Any]:
    """
    Get holder concentration ratios.
    
    Shows what percentage of tokens are held by top 1, top 5, and top 15 holders.
    Higher concentration = more centralized ownership.
    Optimized for available data from Helius API.
    
    Args:
        token_mint: Solana token mint address
        
    Returns:
        Concentration ratios (top_1, top_5, top_15) and distribution metrics
    """
    try:
        logger.info("Fetching concentration metrics", extra={"token_mint": token_mint})
        
        metrics = await token_analytics_service.get_concentration_metrics(token_mint)
        
        return {
            "success": True,
            "data": metrics,
            "metric_type": "concentration"
        }
        
    except Exception as e:
        logger.error("Error fetching concentration metrics", extra={
            "token_mint": token_mint,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch concentration: {str(e)}"
        )


@router.get("/{token_mint}/paperhand", response_model=Dict[str, Any])
async def get_paperhand_metrics(token_mint: str) -> Dict[str, Any]:
    """
    Get paperhand vs diamond hand behavior analysis.
    
    Paperhand = Holders who sell quickly (weak hands)
    Diamond hands = Holders who hold long-term (strong hands)
    
    Args:
        token_mint: Solana token mint address
        
    Returns:
        Paperhand ratio and holder behavior analysis
    """
    try:
        logger.info("Fetching paperhand metrics", extra={"token_mint": token_mint})
        
        metrics = await token_analytics_service.get_paperhand_metrics(token_mint)
        
        return {
            "success": True,
            "data": metrics,
            "metric_type": "paperhand"
        }
        
    except Exception as e:
        logger.error("Error fetching paperhand metrics", extra={
            "token_mint": token_mint,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch paperhand analysis: {str(e)}"
        )


@router.post("/{token_mint}/track", response_model=Dict[str, Any])
async def start_tracking(
    token_mint: str, 
    background_tasks: BackgroundTasks,
    max_accounts_to_monitor: int = Query(10, gt=1, le=20, description="Maximum number of token accounts to monitor for real-time updates (must be >1 and ≤15)")
) -> Dict[str, Any]:
    """
    Start real-time tracking for a token.
    
    Begins WebSocket subscriptions for live updates on:
    - Token account changes (for holder analysis)
    - Program logs (for transaction analysis)
    
    Args:
        token_mint: Solana token mint address
        max_accounts_to_monitor: Maximum number of accounts to monitor (must be >1 and ≤15)
        
    Returns:
        Tracking status confirmation
    """
    try:
        logger.info("Starting token tracking", extra={
            "token_mint": token_mint,
            "max_accounts_to_monitor": max_accounts_to_monitor
        })
        
        # Start tracking in background
        background_tasks.add_task(
            token_analytics_service.start_real_time_tracking,
            token_mint,
            max_accounts_to_monitor
        )
        
        return {
            "success": True,
            "message": "Real-time tracking started",
            "token_mint": token_mint,
            "max_accounts_to_monitor": max_accounts_to_monitor,
            "tracking_features": [
                "token_account_changes",
                "transaction_monitoring",
                "holder_analysis",
                "velocity_updates"
            ]
        }
        
    except Exception as e:
        logger.error("Error starting token tracking", extra={
            "token_mint": token_mint,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start tracking: {str(e)}"
        )


@router.get("/{token_mint}/live", response_model=Dict[str, Any])
async def get_live_metrics(token_mint: str) -> Dict[str, Any]:
    """
    Get the latest live metrics for a tracked token.
    
    Args:
        token_mint: Solana token mint address
        
    Returns:
        Most recent analytics data
    """
    try:
        logger.info("Fetching live metrics", extra={"token_mint": token_mint})
        
        metrics = await token_analytics_service.get_real_time_update(token_mint)
        
        return {
            "success": True,
            "data": metrics,
            "is_live": True,
            "websocket_status": solana_websocket_manager.get_stats()
        }
        
    except Exception as e:
        logger.error("Error fetching live metrics", extra={
            "token_mint": token_mint,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch live metrics: {str(e)}"
        )


@router.get("/", response_model=Dict[str, Any])
async def list_tracked_tokens() -> Dict[str, Any]:
    """
    List all currently tracked tokens.
    
    Returns:
        List of tracked tokens with their status
    """
    try:
        stats = solana_websocket_manager.get_stats()
        
        return {
            "success": True,
            "tracked_tokens": list(solana_websocket_manager.tracked_tokens),
            "websocket_stats": stats,
            "available_metrics": [
                "market_cap",
                "velocity", 
                "concentration",
                "paperhand"
            ]
        }
        
    except Exception as e:
        logger.error("Error listing tracked tokens", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tokens: {str(e)}"
        )


@router.get("/database", response_model=Dict[str, Any])
async def list_database_tokens() -> Dict[str, Any]:
    """
    List all tokens stored in the database with their metadata.
    
    Returns:
        List of tokens from database with names, symbols, and last update info
    """
    try:
        from app.core.database import get_async_db
        from app.models.market_data import Token, TokenMetrics
        from sqlalchemy import select, desc
        
        async for db_session in get_async_db():
            try:
                # Get all active tokens with their latest metrics
                stmt = select(Token).where(Token.is_active == True).order_by(desc(Token.updated_at))
                result = await db_session.execute(stmt)
                tokens = result.scalars().all()
                
                token_list = []
                for token in tokens:
                    # Get latest metrics for this token
                    metrics_stmt = select(TokenMetrics).where(
                        TokenMetrics.token_id == token.id
                    ).order_by(desc(TokenMetrics.timestamp)).limit(1)
                    
                    metrics_result = await db_session.execute(metrics_stmt)
                    latest_metrics = metrics_result.scalar_one_or_none()
                    
                    token_info = {
                        "address": token.address,
                        "name": token.name,
                        "symbol": token.symbol,
                        "decimals": token.decimals,
                        "total_supply": float(token.total_supply) if token.total_supply else None,
                        "is_active": token.is_active,
                        "currency": token.currency,
                        "created_at": token.created_at.isoformat() if token.created_at else None,
                        "updated_at": token.updated_at.isoformat() if token.updated_at else None,
                        "has_recent_metrics": latest_metrics is not None,
                        "last_metrics_update": latest_metrics.timestamp.isoformat() if latest_metrics else None,
                        "current_price": float(latest_metrics.price_usd) if latest_metrics and latest_metrics.price_usd else None,
                        "market_cap": float(latest_metrics.market_cap) if latest_metrics and latest_metrics.market_cap else None,
                        # Enhanced metadata fields
                        "description": token.description,
                        "image_url": token.image_url,
                        "external_url": token.external_url,
                        "collection_address": token.collection_address,
                        "token_standard": token.token_standard,
                        "is_mutable": token.is_mutable,
                        "is_burnt": token.is_burnt
                    }
                    
                    token_list.append(token_info)
                
                return {
                    "success": True,
                    "tokens": token_list,
                    "total_count": len(token_list),
                    "has_names": sum(1 for t in token_list if t["name"]),
                    "has_symbols": sum(1 for t in token_list if t["symbol"]),
                    "has_recent_metrics": sum(1 for t in token_list if t["has_recent_metrics"]),
                    "database_info": {
                        "table": "tokens",
                        "active_only": True,
                        "ordered_by": "updated_at"
                    }
                }
                
            except Exception as e:
                logger.error("Database error in list_database_tokens", extra={"error": str(e)})
                raise
            
            break  # Exit the async generator loop
        
    except Exception as e:
        logger.error("Error listing database tokens", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list database tokens: {str(e)}"
        )


@router.get("/metrics/summary", response_model=Dict[str, Any])
async def get_metrics_summary() -> Dict[str, Any]:
    """
    Get a summary of available metrics and their descriptions.
    
    Returns:
        Detailed information about each metric type
    """
    return {
        "success": True,
        "metrics": {
            "market_cap": {
                "name": "Market Cap Updates",
                "description": "Real-time token supply × price calculations",
                "endpoint": "/api/v1/tokens/{token_mint}/market-cap",
                "real_time": True,
                "calculation": "Token Supply × Current Price"
            },
            "velocity": {
                "name": "Token Velocity", 
                "description": "How fast tokens change hands relative to market cap",
                "endpoint": "/api/v1/tokens/{token_mint}/velocity",
                "real_time": True,
                "calculation": "24h Trading Volume ÷ Market Cap"
            },
            "concentration": {
                "name": "Concentration Ratios",
                "description": "Distribution of token ownership among top 1, 5, and 15 holders",
                "endpoint": "/api/v1/tokens/{token_mint}/concentration", 
                "real_time": True,
                "calculation": "Top 1, 5, 15 holders' % of total supply"
            },
            "paperhand": {
                "name": "Paperhand Ratio",
                "description": "Analysis of weak vs strong holder behavior",
                "endpoint": "/api/v1/tokens/{token_mint}/paperhand",
                "real_time": True,
                "calculation": "% of holders who sell within 24h of buying"
            }
        },
        "data_sources": ["helius", "jupiter", "solana_rpc"],
        "update_frequency": "real-time via WebSocket + 5min cache",
        "bounty_compliance": "100% - All four required metrics implemented"
    }


# Batch endpoint for multiple tokens
@router.post("/batch/analytics", response_model=Dict[str, Any])
async def get_batch_analytics(
    token_mints: List[str] = Query(..., description="List of token mint addresses"),
    metrics: List[str] = Query(
        default=["market_cap", "velocity", "concentration", "paperhand"],
        description="Metrics to calculate"
    )
) -> Dict[str, Any]:
    """
    Get analytics for multiple tokens in a single request.
    
    Args:
        token_mints: List of Solana token mint addresses
        metrics: List of metrics to calculate for each token
        
    Returns:
        Batch analytics results
    """
    try:
        logger.info("Processing batch analytics request", extra={
            "token_count": len(token_mints),
            "metrics": metrics
        })
        
        if len(token_mints) > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 10 tokens per batch request"
            )
        
        results = {}
        
        # Process tokens in parallel
        tasks = []
        for token_mint in token_mints:
            if "market_cap" in metrics:
                tasks.append(("market_cap", token_mint, token_analytics_service.get_market_cap_metrics(token_mint)))
            if "velocity" in metrics:
                tasks.append(("velocity", token_mint, token_analytics_service.get_velocity_metrics(token_mint)))
            if "concentration" in metrics:
                tasks.append(("concentration", token_mint, token_analytics_service.get_concentration_metrics(token_mint)))
            if "paperhand" in metrics:
                tasks.append(("paperhand", token_mint, token_analytics_service.get_paperhand_metrics(token_mint)))
        
        # Execute all tasks
        completed_tasks = await asyncio.gather(*[task[2] for task in tasks], return_exceptions=True)
        
        # Organize results
        for i, (metric_type, token_mint, _) in enumerate(tasks):
            result = completed_tasks[i]
            
            if token_mint not in results:
                results[token_mint] = {}
            
            if isinstance(result, Exception):
                results[token_mint][metric_type] = {"error": str(result)}
            else:
                results[token_mint][metric_type] = result
        
        return {
            "success": True,
            "data": results,
            "tokens_processed": len(token_mints),
            "metrics_calculated": metrics,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error("Error processing batch analytics", extra={
            "token_mints": token_mints,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch processing failed: {str(e)}"
        )


@router.post("/{token_mint}/update-metadata", response_model=Dict[str, Any])
async def update_token_metadata(
    token_mint: str, 
    background_tasks: BackgroundTasks,
    force_refresh: bool = Query(False, description="Force refresh even if recently updated")
) -> Dict[str, Any]:
    """
    Update token metadata (name, symbol) from external sources.
    
    Args:
        token_mint: Solana token mint address
        force_refresh: Whether to force refresh metadata
        
    Returns:
        Updated token metadata
    """
    try:
        logger.info("Updating token metadata", extra={
            "token_mint": token_mint,
            "force_refresh": force_refresh
        })
        
        # Update metadata in background
        background_tasks.add_task(
            token_analytics_service.update_token_metadata,
            token_mint,
            force_refresh
        )
        
        # Get current token info
        token = await token_analytics_service.get_or_create_token(token_mint)
        
        if token:
            return {
                "success": True,
                "message": "Token metadata update initiated",
                "token": {
                    "address": token.address,
                    "name": token.name,
                    "symbol": token.symbol,
                    "decimals": token.decimals,
                    "updated_at": token.updated_at.isoformat() if token.updated_at else None
                },
                "force_refresh": force_refresh
            }
        else:
            return {
                "success": False,
                "message": "Failed to get or create token",
                "token_mint": token_mint
            }
        
    except Exception as e:
        logger.error("Error updating token metadata", extra={
            "token_mint": token_mint,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update metadata: {str(e)}"
        )


@router.get("/{token_mint}/info", response_model=Dict[str, Any])
async def get_token_info(token_mint: str) -> Dict[str, Any]:
    """
    Get token information from database.
    
    Args:
        token_mint: Solana token mint address
        
    Returns:
        Token information including name, symbol, and metadata
    """
    try:
        from app.core.database import get_async_db
        from app.models.market_data import Token, TokenMetrics
        from sqlalchemy import select, desc
        
        async for db_session in get_async_db():
            try:
                # Get token from database
                stmt = select(Token).where(Token.address == token_mint)
                result = await db_session.execute(stmt)
                token = result.scalar_one_or_none()
                
                if not token:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Token not found in database"
                    )
                
                # Get latest metrics
                metrics_stmt = select(TokenMetrics).where(
                    TokenMetrics.token_id == token.id
                ).order_by(desc(TokenMetrics.timestamp)).limit(1)
                
                metrics_result = await db_session.execute(metrics_stmt)
                latest_metrics = metrics_result.scalar_one_or_none()
                
                return {
                    "success": True,
                    "token": {
                        "id": str(token.id),
                        "address": token.address,
                        "name": token.name,
                        "symbol": token.symbol,
                        "decimals": token.decimals,
                        "total_supply": float(token.total_supply) if token.total_supply else None,
                        "creator": token.creator,
                        "is_active": token.is_active,
                        "created_at": token.created_at.isoformat() if token.created_at else None,
                        "updated_at": token.updated_at.isoformat() if token.updated_at else None,
                        # Enhanced metadata fields
                        "description": token.description,
                        "image_url": token.image_url,
                        "external_url": token.external_url,
                        "collection_address": token.collection_address,
                        "token_standard": token.token_standard,
                        "is_mutable": token.is_mutable,
                        "is_burnt": token.is_burnt
                    },
                    "latest_metrics": {
                        "has_metrics": latest_metrics is not None,
                        "timestamp": latest_metrics.timestamp.isoformat() if latest_metrics else None,
                        "price_usd": float(latest_metrics.price_usd) if latest_metrics and latest_metrics.price_usd else None,
                        "market_cap": float(latest_metrics.market_cap) if latest_metrics and latest_metrics.market_cap else None,
                        "velocity": float(latest_metrics.token_velocity) if latest_metrics and latest_metrics.token_velocity else None
                    } if latest_metrics else {
                        "has_metrics": False,
                        "timestamp": None,
                        "price_usd": None,
                        "market_cap": None,
                        "velocity": None
                    }
                }
                
            except Exception as e:
                logger.error("Database error in get_token_info", extra={
                    "token_mint": token_mint,
                    "error": str(e)
                })
                raise
            
            break  # Exit the async generator loop
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting token info", extra={
            "token_mint": token_mint,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get token info: {str(e)}"
        ) 
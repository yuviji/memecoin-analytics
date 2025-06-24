"""
Pydantic schemas for the Memecoin Trading Analytics API.
"""

import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, validator


class BaseTokenSchema(BaseModel):
    """Base schema for token-related models."""
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class TokenCreateRequest(BaseTokenSchema):
    """Request schema for adding a new token to track."""
    
    address: str = Field(..., description="Solana token address", min_length=32, max_length=44)
    name: Optional[str] = Field(None, description="Token name")
    symbol: Optional[str] = Field(None, description="Token symbol")
    
    @validator("address")
    def validate_address(cls, v):
        """Validate Solana address format."""
        if not v or len(v) < 32:
            raise ValueError("Invalid Solana address")
        return v.strip()


class TokenAnalyticsRequest(BaseTokenSchema):
    """Request schema for token analytics operations."""
    
    token_address: str = Field(..., description="Solana token address", min_length=32, max_length=44)
    metrics: Optional[List[str]] = Field(
        default=["market_cap", "velocity", "concentration", "paperhand"],
        description="List of metrics to calculate"
    )
    include_historical: bool = Field(default=False, description="Include historical data")
    
    @validator("token_address")
    def validate_address(cls, v):
        """Validate Solana address format."""
        if not v or len(v) < 32:
            raise ValueError("Invalid Solana address")
        return v.strip()


class TokenResponse(BaseTokenSchema):
    """Response schema for token information."""
    
    id: UUID
    address: str
    name: Optional[str]
    symbol: Optional[str]
    decimals: int
    total_supply: Optional[float]
    creator: Optional[str]
    is_active: bool
    currency: Optional[str] = Field(None, description="Currency for price (e.g., USDC, SOL)")
    created_at: datetime
    updated_at: datetime


class TokenMetricsResponse(BaseTokenSchema):
    """Response schema for token metrics."""
    
    id: UUID
    token_id: UUID
    
    # Market data
    price_usd: Optional[float] = Field(None, description="Current price in USD")
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    volume_24h: Optional[float] = Field(None, description="24h trading volume")
    price_change_24h: Optional[float] = Field(None, description="24h price change %")
    
    # Velocity metrics
    token_velocity: Optional[float] = Field(None, description="Token velocity (volume/market_cap)")
    turnover_rate: Optional[float] = Field(None, description="Daily turnover rate")
    
    # Concentration metrics
    concentration_top_10: Optional[float] = Field(None, description="% held by top 10 holders")
    concentration_top_50: Optional[float] = Field(None, description="% held by top 50 holders")
    concentration_top_100: Optional[float] = Field(None, description="% held by top 100 holders")
    holder_count: Optional[int] = Field(None, description="Total number of holders")
    
    # Trading behavior metrics
    paperhand_ratio: Optional[float] = Field(None, description="% of quick sellers")
    diamond_hand_ratio: Optional[float] = Field(None, description="% of long-term holders")
    avg_holding_time: Optional[float] = Field(None, description="Average holding time in hours")
    
    # Transaction metrics
    transaction_count_24h: Optional[int] = Field(None, description="24h transaction count")
    unique_traders_24h: Optional[int] = Field(None, description="24h unique traders")
    avg_transaction_size: Optional[float] = Field(None, description="Average transaction size")
    
    timestamp: datetime
    created_at: datetime


class TokenHolderResponse(BaseTokenSchema):
    """Response schema for token holder information."""
    
    id: UUID
    token_id: UUID
    wallet_address: str
    balance: float
    percentage_of_supply: Optional[float]
    rank: Optional[int]
    first_acquired: Optional[datetime]
    last_transaction: Optional[datetime]
    transaction_count: int
    is_active: bool
    updated_at: datetime


class TokenTransactionResponse(BaseTokenSchema):
    """Response schema for token transaction data."""
    
    id: UUID
    token_id: UUID
    signature: str
    from_address: Optional[str]
    to_address: Optional[str]
    amount: float
    transaction_type: str
    timestamp: datetime
    fee: Optional[float]
    block_height: Optional[int]
    created_at: datetime


class TrackingJobRequest(BaseTokenSchema):
    """Request schema for creating tracking jobs."""
    
    token_addresses: List[str] = Field(..., min_items=1, max_items=50, 
                                      description="List of token addresses to track")
    interval: int = Field(..., ge=60, le=3600, 
                         description="Tracking interval in seconds (60-3600)")
    
    @validator("token_addresses")
    def validate_addresses(cls, v):
        """Validate token addresses format."""
        validated_addresses = []
        for address in v:
            address = address.strip()
            if len(address) < 32:
                raise ValueError(f"Invalid token address: {address}")
            validated_addresses.append(address)
        return validated_addresses


class TrackingJobResponse(BaseTokenSchema):
    """Response schema for tracking job creation."""
    
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status")
    config: Dict[str, Any] = Field(..., description="Job configuration")
    created_at: datetime = Field(..., description="Job creation timestamp")


class TrackingJobStatus(BaseTokenSchema):
    """Schema for tracking job status information."""
    
    id: UUID
    job_id: str
    token_addresses: List[str]
    interval_seconds: int
    status: str
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    error_message: Optional[str]
    run_count: int
    success_count: int
    error_count: int
    created_at: datetime
    updated_at: datetime


# Analytics schemas
class ConcentrationAnalysisResponse(BaseTokenSchema):
    """Response schema for concentration analysis."""
    
    token_address: str
    top_10_percentage: float
    top_50_percentage: float
    top_100_percentage: float
    total_holders: int
    gini_coefficient: Optional[float] = Field(None, description="Wealth distribution metric")
    timestamp: datetime


class VelocityAnalysisResponse(BaseTokenSchema):
    """Response schema for velocity analysis."""
    
    token_address: str
    velocity_24h: float
    velocity_7d: float
    velocity_30d: float
    turnover_rate: float
    avg_transaction_size: float
    timestamp: datetime


class PaperhandAnalysisResponse(BaseTokenSchema):
    """Response schema for paperhand analysis."""
    
    token_address: str
    paperhand_ratio_24h: float
    paperhand_ratio_7d: float
    diamond_hand_ratio: float
    avg_holding_time_hours: float
    timestamp: datetime


# Market data schemas  
class TokenPriceResponse(BaseTokenSchema):
    """Response schema for token price data."""
    
    token_address: str
    price_usd: float
    market_cap: Optional[float]
    volume_24h: Optional[float]
    price_change_24h: Optional[float]
    timestamp: datetime
    source: str = Field(default="helius", description="Data source")


class PriceResponse(BaseTokenSchema):
    """Response schema for price data from providers."""
    
    symbol: str
    price: float
    volume: Optional[float] = None
    timestamp: datetime
    provider: str
    market_cap: Optional[float] = None
    change_24h: Optional[float] = None


class TokenHistoryResponse(BaseTokenSchema):
    """Response schema for historical token data."""
    
    token_address: str
    data_points: List[Dict[str, Any]]
    start_date: datetime
    end_date: datetime
    interval: str = Field(description="Data interval (1h, 4h, 1d)")


# WebSocket schemas
class WebSocketMessage(BaseTokenSchema):
    """Schema for WebSocket messages."""
    
    type: str = Field(..., description="Message type")
    data: Dict[str, Any] = Field(..., description="Message data")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TokenUpdateMessage(BaseTokenSchema):
    """Schema for real-time token updates."""
    
    type: str = Field(default="token_update")
    token_address: str
    metrics: Dict[str, Any] = Field(..., description="Token metrics data")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Error schemas
class ErrorResponse(BaseTokenSchema):
    """Standard error response schema."""
    
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Error timestamp")


# Health check schemas
class HealthCheckResponse(BaseTokenSchema):
    """Health check response schema."""
    
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Service version")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    database: str = Field(..., description="Database status")
    redis: str = Field(..., description="Redis status")
    kafka: str = Field(..., description="Kafka status")
    helius: str = Field(..., description="Helius API status")


class ServiceMetricsResponse(BaseTokenSchema):
    """Service metrics response schema."""
    
    total_tokens_tracked: int
    total_transactions_24h: int
    active_tracking_jobs: int
    cache_hit_rate: float
    average_response_time: float
    errors_last_hour: int
    helius_requests_last_hour: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) 
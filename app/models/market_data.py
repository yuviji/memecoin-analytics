"""
Database models for memecoin trading analytics.
Includes models for tokens, transactions, holders, and computed metrics.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Float, DateTime, Text, Integer, Boolean, 
    ForeignKey, Index, JSON, UUID, Numeric
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Token(Base):
    """Token information and metadata."""
    
    __tablename__ = "tokens"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    address = Column(String(44), nullable=False, unique=True, index=True)  # Solana address
    name = Column(String(100), nullable=True)
    symbol = Column(String(20), nullable=True)
    decimals = Column(Integer, nullable=False, default=9)
    total_supply = Column(Numeric(precision=20, scale=9), nullable=True)
    creator = Column(String(44), nullable=True)  # Creator address
    is_active = Column(Boolean, default=True)
    currency = Column(String(10), nullable=True)  # Currency for price (e.g., USDC, SOL)
    
    # Enhanced metadata from DAS API
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    external_url = Column(String(500), nullable=True)
    collection_address = Column(String(44), nullable=True)
    token_standard = Column(String(50), nullable=True)
    is_mutable = Column(Boolean, nullable=True)
    is_burnt = Column(Boolean, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    transactions = relationship("TokenTransaction", back_populates="token")
    holders = relationship("TokenHolder", back_populates="token")
    metrics = relationship("TokenMetrics", back_populates="token")
    
    __table_args__ = (
        Index("idx_tokens_symbol", "symbol"),
        Index("idx_tokens_active", "is_active"),
    )


class TokenTransaction(Base):
    """Individual token transactions for velocity calculation."""
    
    __tablename__ = "token_transactions"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id = Column(PostgresUUID(as_uuid=True), ForeignKey("tokens.id"), nullable=False)
    signature = Column(String(88), nullable=False, unique=True, index=True)  # Transaction signature
    from_address = Column(String(44), nullable=True)
    to_address = Column(String(44), nullable=True)
    amount = Column(Numeric(precision=20, scale=9), nullable=False)
    transaction_type = Column(String(20), nullable=False)  # SWAP, TRANSFER, MINT, BURN
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    fee = Column(Numeric(precision=15, scale=0), nullable=True)  # Transaction fee in lamports (Solana native units)
    block_height = Column(Integer, nullable=True)
    raw_data = Column(JSON, nullable=True)  # Full transaction data from Helius
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    token = relationship("Token", back_populates="transactions")
    
    __table_args__ = (
        Index("idx_tx_token_timestamp", "token_id", "timestamp"),
        Index("idx_tx_type_timestamp", "transaction_type", "timestamp"),
        Index("idx_tx_from_to", "from_address", "to_address"),
    )


class TokenHolder(Base):
    """Token holder balances for concentration analysis."""
    
    __tablename__ = "token_holders"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id = Column(PostgresUUID(as_uuid=True), ForeignKey("tokens.id"), nullable=False)
    wallet_address = Column(String(44), nullable=False, index=True)
    balance = Column(Numeric(precision=20, scale=9), nullable=False)
    percentage_of_supply = Column(Float, nullable=True)
    rank = Column(Integer, nullable=True)  # Rank by balance size
    first_acquired = Column(DateTime(timezone=True), nullable=True)
    last_transaction = Column(DateTime(timezone=True), nullable=True)
    transaction_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    token = relationship("Token", back_populates="holders")
    
    __table_args__ = (
        Index("idx_holders_token_balance", "token_id", "balance"),
        Index("idx_holders_token_rank", "token_id", "rank"),
        Index("idx_holders_wallet", "wallet_address"),
    )


class TokenMetrics(Base):
    """Computed token metrics and analytics."""
    
    __tablename__ = "token_metrics"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id = Column(PostgresUUID(as_uuid=True), ForeignKey("tokens.id"), nullable=False)
    
    # Market data
    price_usd = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    volume_24h = Column(Float, nullable=True)
    price_change_24h = Column(Float, nullable=True)
    
    # Velocity metrics
    token_velocity = Column(Float, nullable=True)  # Volume / Market Cap
    turnover_rate = Column(Float, nullable=True)   # Daily volume / Total supply
    
    # Concentration metrics
    concentration_top_1 = Column(Float, nullable=True)   # % held by top 1
    concentration_top_5 = Column(Float, nullable=True)   # % held by top 5
    concentration_top_15 = Column(Float, nullable=True)  # % held by top 15
    holder_count = Column(Integer, nullable=True)
    
    # Trading behavior metrics
    paperhand_ratio = Column(Float, nullable=True)  # % of holders who sold within 24h
    diamond_hand_ratio = Column(Float, nullable=True)  # % of holders holding >30 days
    avg_holding_time = Column(Float, nullable=True)  # Average holding time in hours
    
    # Transaction metrics
    transaction_count_24h = Column(Integer, nullable=True)
    unique_traders_24h = Column(Integer, nullable=True)
    avg_transaction_size = Column(Float, nullable=True)
    
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    token = relationship("Token", back_populates="metrics")
    
    __table_args__ = (
        Index("idx_metrics_token_timestamp", "token_id", "timestamp"),
        Index("idx_metrics_timestamp", "timestamp"),
    )


class TrackingJob(Base):
    """Configuration for token tracking jobs."""
    
    __tablename__ = "tracking_jobs"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(String(100), nullable=False, unique=True, index=True)
    token_addresses = Column(JSON, nullable=False)  # Array of token addresses to track
    interval_seconds = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, running, paused, stopped, error
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    run_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100), nullable=True)
    
    __table_args__ = (
        Index("idx_tracking_job_status", "status"),
        Index("idx_tracking_job_next_run", "next_run_at"),
    )


class TokenMetricsCache(Base):
    """Cache table for frequently accessed token metrics."""
    
    __tablename__ = "token_metrics_cache"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cache_key = Column(String(200), nullable=False, unique=True, index=True)
    token_address = Column(String(44), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # price, velocity, concentration, etc.
    data = Column(JSON, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    accessed_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index("idx_cache_expires", "expires_at"),
        Index("idx_cache_token_type", "token_address", "metric_type"),
    )


class AnalyticsEvent(Base):
    """Raw analytics events for audit and debugging."""
    
    __tablename__ = "analytics_events"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False, index=True)  # price_update, holder_change, etc.
    token_address = Column(String(44), nullable=False, index=True)
    event_data = Column(JSON, nullable=False)
    source = Column(String(50), nullable=False)  # helius, manual, etc.
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index("idx_events_type_timestamp", "event_type", "timestamp"),
        Index("idx_events_token_timestamp", "token_address", "timestamp"),
    ) 
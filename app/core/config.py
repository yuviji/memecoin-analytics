"""
Core configuration settings for the Trojan Trading Analytics Service.
Uses Pydantic settings for environment variable management.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application
    app_name: str = "Trojan Trading Analytics"
    version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    
    # Database Configuration
    database_url: str = ("postgresql://postgres:password@postgres:5432/"
                         "market_data")
    database_pool_size: int = 20
    database_max_overflow: int = 0
    
    # Redis Configuration
    redis_url: str = "redis://redis:6379/0"
    redis_cache_ttl: int = 300  # 5 minutes
    
    # Kafka Configuration
    kafka_bootstrap_servers: str = "kafka:29092"
    kafka_token_events_topic: str = "token-events"
    kafka_consumer_group: str = "memecoin-analytics-consumers"
    kafka_auto_offset_reset: str = "latest"
    kafka_enable_auto_commit: bool = True
    kafka_max_poll_interval_ms: int = 300000  # 5 minutes
        
    # Helius RPC Configuration
    helius_api_key: Optional[str] = None
    helius_rpc_url: str = "https://mainnet.helius-rpc.com"
    helius_websocket_url: str = "wss://mainnet.helius-rpc.com"
    helius_enhanced_api_url: str = "https://api.helius.xyz/v0"
    
    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_per_minutes: int = 1
    
    # Analytics Configuration
    velocity_window_hours: int = 24
    concentration_top_holders: int = 15
    
    # Monitoring
    metrics_enabled: bool = True
    metrics_port: int = 8001
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Security
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    
    # Celery Configuration (for background tasks)
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        if v not in ["development", "staging", "production"]:
            raise ValueError("Environment must be one of: development, "
                           "staging, production")
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Create settings instance
settings = get_settings() 
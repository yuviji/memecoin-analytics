"""
Kafka configuration and connection settings.
Provides configuration for producers and consumers with error handling.
"""

from typing import Dict, Any
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class KafkaConfig:
    """Kafka configuration class."""
    
    @staticmethod
    def get_producer_config() -> Dict[str, Any]:
        """Get Kafka producer configuration."""
        return {
            'bootstrap.servers': settings.kafka_bootstrap_servers,
            'client.id': 'market-data-producer',
            'acks': 'all',  # Wait for all replicas to acknowledge
            'retries': 3,
            'retry.backoff.ms': 1000,
            'delivery.timeout.ms': 30000,
            'request.timeout.ms': 25000,
            'max.in.flight.requests.per.connection': 1,  # Ensure ordering
            'compression.type': 'gzip',
            'batch.size': 16384,
            'linger.ms': 10,  # Small delay to allow batching
            'queue.buffering.max.kbytes': 32768,  # 32MB in KB (equivalent to buffer.memory)
            'queue.buffering.max.messages': 100000,
            # Note: serializers are handled in the producer code, not in config
        }
    
    @staticmethod
    def get_consumer_config() -> Dict[str, Any]:
        """Get Kafka consumer configuration."""
        return {
            'bootstrap.servers': settings.kafka_bootstrap_servers,
            'group.id': settings.kafka_consumer_group,
            'client.id': 'market-data-consumer',
            'auto.offset.reset': settings.kafka_auto_offset_reset,
            'enable.auto.commit': settings.kafka_enable_auto_commit,
            'auto.commit.interval.ms': 5000,
            'max.poll.interval.ms': settings.kafka_max_poll_interval_ms,
            'session.timeout.ms': 30000,
            'heartbeat.interval.ms': 10000,
            'fetch.min.bytes': 1024,
            'fetch.wait.max.ms': 5000,  # Fixed: correct librdkafka property
            # Note: deserializers are handled in the consumer code, not in config
        }
    
    @staticmethod
    def get_topic_config() -> Dict[str, Any]:
        """Get topic configuration for creation."""
        return {
            'num_partitions': 3,
            'replication_factor': 1,  # For development
            'config': {
                'retention.ms': '604800000',  # 7 days
                'cleanup.policy': 'delete',
                'compression.type': 'gzip',
                'max.message.bytes': '1048576',  # 1MB
            }
        }
    
    @staticmethod
    def get_topics() -> Dict[str, str]:
        """Get topic names configuration."""
        return {
            'token_events': settings.kafka_token_events_topic,
            'analytics': 'token-analytics',
            'errors': 'token-analytics-errors',
            'dead_letter': 'token-analytics-dlq',
        } 
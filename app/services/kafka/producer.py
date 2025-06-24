"""
Kafka producer service for publishing market data events.
Handles publishing price events with error handling and retries.
"""

import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import uuid4

from confluent_kafka import Producer
from confluent_kafka.error import KafkaError, KafkaException

from app.core.logging import get_logger
from app.services.kafka.config import KafkaConfig
from typing import Dict, Any

logger = get_logger(__name__)


class KafkaProducerService:
    """Kafka producer service for market data events."""
    
    def __init__(self):
        self.producer: Optional[Producer] = None
        self.config = KafkaConfig.get_producer_config()
        self.topics = KafkaConfig.get_topics()
        self._running = False
        self._messages_sent = 0
        self._messages_failed = 0
        self._bytes_sent = 0
        self._start_time = datetime.now(timezone.utc)
    
    async def start(self):
        """Initialize the Kafka producer."""
        try:
            self.producer = Producer(self.config)
            self._running = True
            logger.info("Kafka producer started successfully")
            
        except Exception as e:
            logger.error("Failed to start Kafka producer", extra={"error": str(e)})
            raise
    
    async def stop(self):
        """Stop the Kafka producer and flush pending messages."""
        if self.producer:
            try:
                # Wait for any outstanding messages to be delivered
                self.producer.flush(timeout=10)
                self._running = False
                logger.info("Kafka producer stopped successfully")
                
            except Exception as e:
                logger.error("Error stopping Kafka producer", extra={"error": str(e)})
    
    def _delivery_callback(self, err, msg):
        """Callback for message delivery confirmation."""
        if err is not None:
            logger.error("Message delivery failed", extra={
                "error": str(err),
                "topic": msg.topic(),
                "partition": msg.partition(),
                "offset": msg.offset() if msg.offset() != -1 else "unknown"
            })
            self._messages_failed += 1
        else:
            logger.debug("Message delivered successfully", extra={
                "topic": msg.topic(),
                "partition": msg.partition(),
                "offset": msg.offset()
            })
            self._messages_sent += 1
            self._bytes_sent += len(msg.value())
    
    async def publish_token_event(
        self, 
        token_data: Dict[str, Any],
        raw_response_id: Optional[str] = None
    ) -> bool:
        """
        Publish a token event to the token-events topic.
        
        Args:
            token_data: Token analytics data
            raw_response_id: Optional ID of the raw response record
            
        Returns:
            True if published successfully, False otherwise
        """
        if not self._running or not self.producer:
            logger.error("Producer not running")
            return False
        
        try:
            # Create the event message according to the specified schema
            event = {
                "token_address": token_data.get("token_address"),
                "metrics": token_data.get("metrics", {}),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "token_analytics",
                "raw_response_id": raw_response_id or str(uuid4()),
                "event_id": str(uuid4()),
                "published_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Serialize the event
            message = json.dumps(event, default=str)
            
            # Use token address as the key for partitioning
            key = token_data.get("token_address", "unknown")
            
            # Publish the message
            self.producer.produce(
                topic=self.topics.get('token_events', 'token-events'),
                key=key,
                value=message,
                callback=self._delivery_callback
            )
            
            # Trigger delivery (non-blocking)
            self.producer.poll(0)
            
            logger.info("Token event published", extra={
                "token_address": token_data.get("token_address"),
                "event_type": "token_analytics"
            })
            
            return True
            
        except KafkaException as e:
            logger.error("Kafka error publishing token event", extra={
                "token_address": token_data.get("token_address"),
                "error": str(e)
            })
            return False
            
        except Exception as e:
            logger.error("Unexpected error publishing token event", extra={
                "token_address": token_data.get("token_address"),
                "error": str(e)
            })
            return False
    
    async def publish_error_event(
        self, 
        error_type: str, 
        error_message: str, 
        context: Dict[str, Any]
    ) -> bool:
        """
        Publish an error event to the errors topic.
        
        Args:
            error_type: Type of error
            error_message: Error message
            context: Additional context information
            
        Returns:
            True if published successfully, False otherwise
        """
        if not self._running or not self.producer:
            return False
        
        try:
            error_event = {
                "error_type": error_type,
                "error_message": error_message,
                "context": context,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error_id": str(uuid4())
            }
            
            message = json.dumps(error_event, default=str)
            
            self.producer.produce(
                topic=self.topics['errors'],
                value=message,
                callback=self._delivery_callback
            )
            
            self.producer.poll(0)
            
            logger.info("Error event published", extra={
                "error_type": error_type,
                "context": context
            })
            
            return True
            
        except Exception as e:
            logger.error("Failed to publish error event", extra={"error": str(e)})
            return False
    
    async def flush(self, timeout: float = 10.0) -> bool:
        """
        Flush any pending messages.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            True if all messages were flushed, False otherwise
        """
        if not self.producer:
            return False
        
        try:
            remaining = self.producer.flush(timeout=timeout)
            if remaining > 0:
                logger.warning("Some messages not flushed", extra={"remaining": remaining})
                return False
            
            logger.debug("All messages flushed successfully")
            return True
            
        except Exception as e:
            logger.error("Error flushing producer", extra={"error": str(e)})
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get producer metrics and statistics."""
        try:
            # Get real producer metrics from confluent_kafka
            if self.producer:
                # Get internal metrics from producer
                metrics = self.producer.list_metadata(timeout=1)
                
                return {
                    "messages_sent": self._messages_sent,
                    "messages_failed": self._messages_failed,
                    "bytes_sent": getattr(self, '_bytes_sent', 0),
                    "broker_count": len(metrics.brokers) if metrics.brokers else 0,
                    "topic_count": len(metrics.topics) if metrics.topics else 0,
                    "producer_queue_size": len(self.producer) if hasattr(self.producer, '__len__') else 0,
                    "is_connected": self.producer is not None,
                    "last_error": getattr(self, '_last_error', None),
                    "uptime_seconds": (datetime.now(timezone.utc) - self._start_time).total_seconds() if hasattr(self, '_start_time') else 0
                }
            else:
                return {
                    "messages_sent": 0,
                    "messages_failed": 0,
                    "bytes_sent": 0,
                    "broker_count": 0,
                    "topic_count": 0,
                    "producer_queue_size": 0,
                    "is_connected": False,
                    "last_error": "Producer not initialized",
                    "uptime_seconds": 0
                }
                
        except Exception as e:
            logger.error("Error getting producer metrics", extra={"error": str(e)})
            return {
                "error": str(e),
                "messages_sent": getattr(self, '_messages_sent', 0),
                "messages_failed": getattr(self, '_messages_failed', 0),
                "is_connected": False
            }


# Global producer instance
kafka_producer = KafkaProducerService() 
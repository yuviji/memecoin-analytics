"""
Kafka consumer service for processing token analytics events.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from statistics import mean

from confluent_kafka import Consumer, KafkaError
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.core.database import get_async_db
from app.core.logging import get_logger
from app.models.market_data import (
    Token, TokenTransaction, TokenHolder, TokenMetrics
)
from app.services.kafka.config import KafkaConfig
from app.services.cache import cache

logger = get_logger(__name__)


class KafkaConsumerService:
    """Kafka consumer service for processing token analytics events."""
    
    def __init__(self):
        self.consumer: Optional[Consumer] = None
        self.config = KafkaConfig.get_consumer_config()
        self.topics = KafkaConfig.get_topics()
        self._running = False
        self._processing_stats = {
            "messages_processed": 0,
            "messages_failed": 0,
            "events_processed": 0,
            "start_time": None
        }
    
    async def start(self):
        """Initialize the Kafka consumer."""
        try:
            self.consumer = Consumer(self.config)
            self.consumer.subscribe([self.topics['token_events']])
            self._running = True
            self._processing_stats["start_time"] = datetime.now(timezone.utc)
            
            logger.info("Kafka consumer started successfully", extra={
                "topics": [self.topics['token_events']],
                "group_id": self.config.get('group.id')
            })
            
        except Exception as e:
            logger.error("Failed to start Kafka consumer", extra={"error": str(e)})
            raise
    
    async def stop(self):
        """Stop the Kafka consumer."""
        if self.consumer:
            try:
                self.consumer.close()
                self._running = False
                logger.info("Kafka consumer stopped successfully")
                
            except Exception as e:
                logger.error("Error stopping Kafka consumer", extra={"error": str(e)})
    
    async def process_messages(self):
        """Main processing loop for consuming and processing messages."""
        if not self._running or not self.consumer:
            logger.error("Consumer not running")
            return
        
        logger.info("Starting message processing loop")
        
        while self._running:
            try:
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("Reached end of partition")
                        continue
                    else:
                        logger.error("Consumer error", extra={"error": str(msg.error())})
                        continue
                
                await self._process_token_event(msg)
                
            except Exception as e:
                logger.error("Unexpected error in message processing", extra={"error": str(e)})
                await asyncio.sleep(1)
    
    async def _process_token_event(self, msg):
        """Process a single token analytics event message."""
        try:
            event_data = json.loads(msg.value())
            
            event_type = event_data.get("event_type")
            token_address = event_data.get("token_address")
            timestamp_str = event_data.get("timestamp")
            source = event_data.get("source", "kafka")
            
            if not token_address or not event_type:
                logger.warning("Invalid token event data", extra={"event": event_data})
                self._processing_stats["messages_failed"] += 1
                return
            
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                timestamp = datetime.now(timezone.utc)
            
            async for db_session in get_async_db():
                try:
                    # Process different types of events
                    if event_type == "transaction":
                        await self._process_transaction_event(db_session, event_data, timestamp)
                    elif event_type == "holder_update":
                        await self._process_holder_event(db_session, event_data, timestamp)
                    elif event_type == "metrics_update":
                        await self._process_metrics_event(db_session, event_data, timestamp)
                    else:
                        logger.warning("Unknown event type", extra={
                            "event_type": event_type,
                            "token_address": token_address
                        })
                    
                    # Store raw analytics event for audit
                    await self._store_analytics_event(db_session, event_data, timestamp)
                    
                    await db_session.commit()
                    self._processing_stats["messages_processed"] += 1
                    self._processing_stats["events_processed"] += 1
                    
                    logger.info("Token event processed successfully", extra={
                        "event_type": event_type,
                        "token_address": token_address,
                        "source": source
                    })
                    
                    break
                    
                except Exception as e:
                    logger.error("Database error processing token event", extra={
                        "token_address": token_address,
                        "event_type": event_type,
                        "error": str(e)
                    })
                    await db_session.rollback()
                    self._processing_stats["messages_failed"] += 1
                    raise
                    
        except json.JSONDecodeError as e:
            logger.error("Failed to parse message JSON", extra={"error": str(e)})
            self._processing_stats["messages_failed"] += 1
            
        except Exception as e:
            logger.error("Unexpected error processing token event", extra={"error": str(e)})
            self._processing_stats["messages_failed"] += 1
    
    async def _process_transaction_event(self, db_session: AsyncSession, event_data: Dict, timestamp: datetime):
        """Process transaction events."""
        # Implementation for transaction processing
        pass
    
    async def _process_holder_event(self, db_session: AsyncSession, event_data: Dict, timestamp: datetime):
        """Process holder update events."""
        # Implementation for holder processing
        pass
    
    async def _process_metrics_event(self, db_session: AsyncSession, event_data: Dict, timestamp: datetime):
        """Process metrics update events."""
        # Implementation for metrics processing
        pass
    
    async def _store_analytics_event(self, db_session: AsyncSession, event_data: Dict, timestamp: datetime):
        """Store raw analytics event for audit purposes."""
        from app.models.market_data import AnalyticsEvent
        
        stmt = insert(AnalyticsEvent).values(
            event_type=event_data.get("event_type"),
            token_address=event_data.get("token_address"),
            event_data=event_data,
            source=event_data.get("source", "kafka"),
            timestamp=timestamp
        ).on_conflict_do_nothing()
        
        await db_session.execute(stmt)
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get consumer processing statistics."""
        stats = self._processing_stats.copy()
        if stats["start_time"]:
            runtime = datetime.now(timezone.utc) - stats["start_time"]
            stats["runtime_seconds"] = runtime.total_seconds()
            stats["messages_per_second"] = (
                stats["messages_processed"] / runtime.total_seconds()
                if runtime.total_seconds() > 0 else 0
            )
        return stats
    
    async def run(self):
        """Run the consumer (convenience method)."""
        await self.start()
        try:
            await self.process_messages()
        finally:
            await self.stop()


if __name__ == "__main__":
    """Standalone consumer runner."""
    import signal
    import sys
    
    consumer = KafkaConsumerService()
    
    async def main():
        """Main runner function."""
        logger.info("Starting Kafka consumer service")
        
        try:
            await consumer.run()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down")
        except Exception as e:
            logger.error("Consumer error", extra={"error": str(e)})
        finally:
            await consumer.stop()
            logger.info("Consumer service stopped")
    
    def signal_handler(sig, frame):
        """Handle shutdown signals."""
        logger.info("Received shutdown signal")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the consumer
    asyncio.run(main()) 
"""
Tracking tasks for fetching token analytics at scheduled intervals.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery import celery_app
from app.core.database import get_async_db
from app.core.logging import get_logger
from app.models.market_data import TrackingJob
from app.services.token_analytics_service import token_analytics_service

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.tracking_tasks.check_and_execute_tracking_jobs")
def check_and_execute_tracking_jobs() -> Dict[str, Any]:
    """
    Check for tracking jobs that are due to run and execute them.
    This task is scheduled to run periodically by Celery Beat.
    """
    import asyncio
    
    logger.info("Checking for tracking jobs to execute")
    
    # Run the async function in the synchronous Celery task
    return asyncio.run(_check_and_execute_tracking_jobs_async())


@celery_app.task(name="app.tasks.tracking_tasks.execute_tracking_job")
def execute_tracking_job(job_id: str) -> Dict[str, Any]:
    """
    Execute a specific tracking job by ID.
    """
    import asyncio
    
    logger.info(f"Executing tracking job {job_id}")
    
    # Run the async function in the synchronous Celery task
    return asyncio.run(_execute_tracking_job_async(job_id))


@celery_app.task(name="app.tasks.tracking_tasks.cleanup_expired_cache")
def cleanup_expired_cache() -> Dict[str, Any]:
    """
    Clean up expired cache entries and optimize cache performance.
    """
    import asyncio
    
    logger.info("Starting cache cleanup task")
    
    return asyncio.run(_cleanup_expired_cache_async())


async def _check_and_execute_tracking_jobs_async() -> Dict[str, Any]:
    """Check for pending tracking jobs and execute them."""
    try:
        logger.info("Checking for pending tracking jobs")
        
        executed_jobs = []
        failed_jobs = []
        
        async for db_session in get_async_db():
            # Get pending jobs that are ready to run
            current_time = datetime.now(timezone.utc)
            
            query = (
                select(TrackingJob)
                .where(
                    TrackingJob.status.in_(["pending", "active"]),
                    TrackingJob.next_run_at <= current_time
                )
                .order_by(TrackingJob.next_run_at)
                .limit(10)  # Process max 10 jobs at once
            )
            
            result = await db_session.execute(query)
            jobs = result.scalars().all()
            
            logger.info(f"Found {len(jobs)} jobs ready for execution")
            
            for job in jobs:
                try:
                    # Mark job as running
                    job.status = "running"
                    job.last_run_at = current_time
                    await db_session.commit()
                    
                    # Execute the job
                    await _execute_job(db_session, job)
                    
                    # Update job status and schedule next run
                    job.status = "active"
                    job.next_run_at = current_time + timedelta(seconds=job.interval_seconds)
                    job.run_count += 1
                    job.success_count += 1
                    job.error_message = None
                    
                    await db_session.commit()
                    
                    executed_jobs.append({
                        "job_id": job.job_id,
                        "token_addresses": job.token_addresses,
                        "next_run": job.next_run_at.isoformat()
                    })
                    
                    logger.info("Job executed successfully", extra={
                        "job_id": job.job_id,
                        "token_count": len(job.token_addresses)
                    })
                    
                except Exception as job_error:
                    # Handle job execution error
                    job.status = "error"
                    job.error_message = str(job_error)
                    job.error_count += 1
                    job.next_run_at = current_time + timedelta(seconds=job.interval_seconds * 2)  # Backoff
                    
                    await db_session.commit()
                    
                    failed_jobs.append({
                        "job_id": job.job_id,
                        "error": str(job_error)
                    })
                    
                    logger.error("Job execution failed", extra={
                        "job_id": job.job_id,
                        "error": str(job_error)
                    })
            
            break  # Exit the async for loop
        
        return {
            "executed_jobs": executed_jobs,
            "failed_jobs": failed_jobs,
            "total_executed": len(executed_jobs),
            "total_failed": len(failed_jobs),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error("Error checking tracking jobs", extra={"error": str(e)})
        raise


async def _execute_tracking_job_async(job_id: str) -> Dict[str, Any]:
    """Execute a specific tracking job by ID."""
    try:
        logger.info("Executing tracking job", extra={"job_id": job_id})
        
        async for db_session in get_async_db():
            # Get the job
            query = select(TrackingJob).where(TrackingJob.job_id == job_id)
            result = await db_session.execute(query)
            job = result.scalar_one_or_none()
            
            if not job:
                raise ValueError(f"Job not found: {job_id}")
            
            if job.status not in ["pending", "active"]:
                raise ValueError(f"Job cannot be executed (status: {job.status})")
            
            # Mark as running
            job.status = "running"
            job.last_run_at = datetime.now(timezone.utc)
            await db_session.commit()
            
            try:
                # Execute the job
                await _execute_job(db_session, job)
                
                # Update success status
                job.status = "active"
                job.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=job.interval_seconds)
                job.run_count += 1
                job.success_count += 1
                job.error_message = None
                
                await db_session.commit()
                
                logger.info("Tracking job executed successfully", extra={"job_id": job_id})
                
                return {
                    "job_id": job_id,
                    "status": "success",
                    "tokens_processed": len(job.token_addresses),
                    "next_run": job.next_run_at.isoformat(),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            except Exception as exec_error:
                # Handle execution error
                job.status = "error"
                job.error_message = str(exec_error)
                job.error_count += 1
                job.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=job.interval_seconds * 2)
                
                await db_session.commit()
                
                logger.error("Tracking job execution failed", extra={
                    "job_id": job_id,
                    "error": str(exec_error)
                })
                
                return {
                    "job_id": job_id,
                    "status": "error",
                    "error": str(exec_error),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            break  # Exit async for loop
            
    except Exception as e:
        logger.error("Error executing tracking job", extra={"job_id": job_id, "error": str(e)})
        raise


async def _execute_job(db_session: AsyncSession, job: TrackingJob) -> None:
    """Execute a single tracking job - sync data for all tokens."""
    from app.services.token_analytics_service import token_analytics_service
    
    try:
        logger.info("Executing job", extra={
            "job_id": job.job_id,
            "token_count": len(job.token_addresses)
        })
        
        # Process each token in the job
        for token_address in job.token_addresses:
            try:
                # Use the comprehensive metrics method from token analytics service
                sync_result = await token_analytics_service.get_comprehensive_metrics(token_address)
                
                logger.debug("Token processed in job", extra={
                    "job_id": job.job_id,
                    "token_address": token_address,
                    "sync_result": sync_result
                })
                
            except Exception as token_error:
                logger.error("Failed to process token in job", extra={
                    "job_id": job.job_id,
                    "token_address": token_address,
                    "error": str(token_error)
                })
                # Continue processing other tokens
                continue
        
        logger.info("Job execution completed", extra={"job_id": job.job_id})
        
    except Exception as e:
        logger.error("Job execution failed", extra={
            "job_id": job.job_id,
            "error": str(e)
        })
        raise


async def _cleanup_expired_cache_async() -> Dict[str, Any]:
    """Clean up expired cache entries."""
    try:
        from app.services.cache import cache
        
        # Ensure cache connection
        await cache._ensure_connection()
        
        # Get cache statistics before cleanup
        stats_before = await cache.get_cache_stats()
        
        # Clean up expired keys (Redis handles this automatically, but we can force it)
        info = await cache.redis.info('memory')
        memory_before = info.get('used_memory', 0)
        
        # Force garbage collection of expired keys
        await cache.redis.execute_command('MEMORY', 'PURGE')
        
        # Get statistics after cleanup
        stats_after = await cache.get_cache_stats()
        info_after = await cache.redis.info('memory')
        memory_after = info_after.get('used_memory', 0)
        
        memory_freed = memory_before - memory_after
        
        result = {
            "status": "success",
            "memory_freed_bytes": memory_freed,
            "memory_before": memory_before,
            "memory_after": memory_after,
            "hit_rate_before": stats_before.get("hit_rate", 0),
            "hit_rate_after": stats_after.get("hit_rate", 0),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info("Cache cleanup completed", extra=result)
        return result
        
    except Exception as e:
        logger.error("Cache cleanup failed", extra={"error": str(e)})
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        } 
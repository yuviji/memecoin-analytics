#!/usr/bin/env python3
"""
Database migration script for the Trojan Trading Analytics service.
Creates tables and initializes the database schema.
"""

import asyncio
import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import init_db
from app.core.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


async def main():
    """Run database migrations."""
    try:
        logger.info("Starting database migration...")
        
        # Initialize database tables
        await init_db()
        
        logger.info("Database migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Database migration failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

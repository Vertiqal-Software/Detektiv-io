# app/core/database.py
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError

from .config import settings

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def create_database_engine() -> Engine:
    """
    Create SQLAlchemy engine with connection pooling and optimization.
    
    Returns:
        Configured SQLAlchemy engine
    """
    database_url = settings.get_database_url()
    
    logger.info(
        "Creating database engine with URL: %s", 
        settings.get_database_url(mask_password=True)
    )
    
    engine = create_engine(
        database_url,
        future=True,  # Use SQLAlchemy 2.0 style
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,  # Validate connections before use
        poolclass=QueuePool,
        echo=settings.debug,  # Log SQL in debug mode
        echo_pool=settings.debug,  # Log pool events in debug mode
    )
    
    return engine


def get_engine() -> Engine:
    """
    Get or create the global database engine.
    
    Returns:
        SQLAlchemy engine instance
    """
    global _engine
    
    if _engine is None:
        _engine = create_database_engine()
        
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """
    Get or create the global session factory.
    
    Returns:
        SQLAlchemy session factory
    """
    global _session_factory
    
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(
            bind=engine,
            class_=Session,
            autoflush=False,  # Manual control over when to flush
            autocommit=False,
            expire_on_commit=False,  # Keep objects usable after commit
        )
        
    return _session_factory


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    Automatically handles commit/rollback and cleanup.
    
    Usage:
        with get_db_session() as session:
            # Use session here
            company = session.get(Company, 1)
            # Automatic commit on success, rollback on exception
    
    Yields:
        SQLAlchemy Session instance
    """
    session_factory = get_session_factory()
    session = session_factory()
    
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error("Database session error: %s", e)
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connection() -> tuple[bool, str]:
    """
    Test database connectivity.
    
    Returns:
        Tuple of (is_connected, message)
    """
    try:
        engine = get_engine()
        
        with engine.connect() as connection:
            # Simple connectivity test
            result = connection.execute(text("SELECT 1 AS test"))
            test_value = result.scalar()
            
            if test_value == 1:
                return True, "Database connection successful"
            else:
                return False, f"Unexpected test result: {test_value}"
                
    except SQLAlchemyError as e:
        logger.error("Database connection failed: %s", e)
        return False, f"Database connection failed: {str(e)}"
    except Exception as e:
        logger.error("Unexpected error testing database: %s", e)
        return False, f"Unexpected error: {str(e)}"


def get_database_info() -> dict[str, any]:
    """
    Get information about the database connection.
    
    Returns:
        Dictionary with database information
    """
    try:
        engine = get_engine()
        
        with engine.connect() as connection:
            # Get PostgreSQL version
            version_result = connection.execute(text("SELECT version()"))
            version = version_result.scalar()
            
            # Get current database name
            db_result = connection.execute(text("SELECT current_database()"))
            database_name = db_result.scalar()
            
            # Get connection count
            conn_result = connection.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            )
            active_connections = conn_result.scalar()
            
            return {
                "connected": True,
                "database_name": database_name,
                "postgresql_version": version,
                "active_connections": active_connections,
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "url": settings.get_database_url(mask_password=True)
            }
            
    except Exception as e:
        logger.error("Failed to get database info: %s", e)
        return {
            "connected": False,
            "error": str(e),
            "url": settings.get_database_url(mask_password=True)
        }


def close_database_connections() -> None:
    """
    Close all database connections and dispose of the engine.
    Useful for testing and shutdown.
    """
    global _engine, _session_factory
    
    if _engine:
        try:
            _engine.dispose()
            logger.info("Database engine disposed")
        except Exception as e:
            logger.error("Error disposing database engine: %s", e)
        finally:
            _engine = None
            _session_factory = None


# FastAPI dependency for dependency injection
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency to provide database sessions.
    
    Usage in FastAPI routes:
        @app.get("/companies/")
        def get_companies(db: Session = Depends(get_db)):
            return db.query(Company).all()
    """
    with get_db_session() as session:
        yield session


# Startup/shutdown handlers for FastAPI
async def startup_database() -> None:
    """Initialize database connections on startup."""
    logger.info("Initializing database connections...")
    
    # Test connection
    is_connected, message = check_database_connection()
    if not is_connected:
        raise RuntimeError(f"Failed to connect to database: {message}")
    
    logger.info("Database connection established successfully")


async def shutdown_database() -> None:
    """Clean up database connections on shutdown."""
    logger.info("Shutting down database connections...")
    close_database_connections()
    logger.info("Database connections closed")
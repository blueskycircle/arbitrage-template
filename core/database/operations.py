# This file contains the database access layer that handles connections to the database
# and provides reusable CRUD (Create, Read, Update, Delete) operations for our models

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from typing import List, Optional, Generator, Dict, Any
from datetime import datetime, timedelta
import sys
import os
import pymysql
import sqlalchemy.exc
# Add the project root to the path to allow importing from config
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.settings import get_settings
from .models import Base, Snapshot, Item, Opportunity

# Get application settings
settings = get_settings()

# Database Connection Setup
# This section establishes the connection to our MySQL database using SQLAlchemy
# The engine is the low-level interface to the database that handles the connection pool
engine = create_engine(settings.DATABASE_URL)

# Session Factory
# Creates a factory for database sessions which encapsulate database transactions
# Sessions are how we interact with the database - they manage the unit of work pattern
# allowing related changes to be committed or rolled back atomically
SessionLocal = sessionmaker(bind=engine)

def ensure_database_exists():
    """Ensure that the database exists before attempting operations."""
    try:
        # Test if we can connect to the database
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return  # Database exists and connection works
    except sqlalchemy.exc.OperationalError as e:
        # This is the specific exception for connection problems including "Unknown database"
        if "Unknown database" in str(e):
            # Database doesn't exist, so create it
            try:
                create_db_connection = pymysql.connect(
                    host=settings.DB_HOST,
                    user=settings.DB_USER,
                    password=settings.DB_PASS,
                    port=int(settings.DB_PORT)
                )
                try:
                    with create_db_connection.cursor() as cursor:
                        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {settings.DB_NAME}")
                    create_db_connection.close()
                    print(f"Created database '{settings.DB_NAME}'")
                except pymysql.Error as db_err:
                    print(f"Failed to create database: {db_err}")
                    raise
            except pymysql.Error as conn_err:
                print(f"Failed to connect to MySQL server: {conn_err}")
                raise
        else:
            # It's some other operational error
            print(f"Database connection error: {e}")
            raise
    except sqlalchemy.exc.SQLAlchemyError as e:
        # Handle other SQLAlchemy errors
        print(f"SQLAlchemy error: {e}")
        raise

def init_db():
    """Create database tables if they don't exist.
    
    This function creates all tables defined in the models module based on the
    metadata in the Base class. It's typically called once at application startup.
    
    In a production environment, you would typically use database migrations
    (Alembic) instead of creating tables directly, as it provides version control
    for schema changes.
    """
    ensure_database_exists()
    Base.metadata.create_all(bind=engine)

def get_db() -> Generator:
    """Create and yield a database session.
    
    This is a dependency injection pattern, commonly used with FastAPI.
    It creates a new session for each request, and ensures the session 
    is properly closed even if an exception occurs during the request.
    
    Yields:
        A SQLAlchemy session object for database operations
        
    Usage:
        @app.get("/items/")
        def read_items(db: Session = Depends(get_db)):
            items = db.query(Item).all()
            return items
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        # This ensures the session is closed even if an exception occurs
        db.close()

def create_snapshot(db, description=None) -> Snapshot:
    """Create a new snapshot in the database.
    
    Snapshots represent point-in-time collections of price data.
    This function creates an empty snapshot that items can then be added to.
    
    Args:
        db: Database session
        description: Optional human-readable description of this snapshot
        
    Returns:
        The newly created Snapshot object with its generated ID
        
    This is typically the first step in a data collection cycle - create
    a snapshot, then add multiple items to it.
    """
    snapshot = Snapshot(description=description)
    db.add(snapshot)  # Stage the new object for insertion
    db.commit()  # Commit the transaction to the database
    db.refresh(snapshot)  # Refresh to get the database-generated values
    return snapshot

def add_item(db, snapshot_id, source, name, price, url=None) -> Item:
    """Add a single item to a snapshot.
    
    This function creates a new item record linked to a specific snapshot.
    Items represent individual product prices from specific sources.
    
    Args:
        db: Database session
        snapshot_id: ID of the parent snapshot
        source: Name of the data source (e.g., "amazon")
        name: Product name or identifier
        price: Current price of the item
        url: Optional URL to the product page
        
    Returns:
        The newly created Item object with its generated ID
        
    This function is called for each product in a data collection cycle,
    building up the complete snapshot of prices across sources.
    """
    item = Item(
        snapshot_id=snapshot_id,
        source=source,
        name=name,
        price=price,
        url=url
    )
    db.add(item)  # Stage the new object for insertion
    db.commit()  # Commit the transaction to the database
    db.refresh(item)  # Refresh to get the database-generated values
    return item

def save_opportunities(db, snapshot_id: str, opportunities: List[Dict[str, Any]]) -> List[Opportunity]:
    """Save arbitrage opportunities to the database.
    
    Args:
        db: Database session
        snapshot_id: ID of the snapshot to associate with these opportunities
        opportunities: List of opportunity dictionaries
        
    Returns:
        List of created Opportunity objects
    """
    # Verify snapshot exists
    snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snapshot:
        raise ValueError(f"Snapshot with ID {snapshot_id} not found")
    
    created_opportunities = []
    
    for opp in opportunities:
        db_opp = Opportunity(
            snapshot_id=snapshot_id,
            item_name=opp["item_name"],
            buy_from=opp["buy_from"],
            buy_price=opp["buy_price"],
            sell_to=opp["sell_to"],
            sell_price=opp["sell_price"],
            profit_amount=opp["profit_amount"],
            profit_percent=opp["profit_percent"],
            buy_url=opp.get("buy_url"),
            sell_url=opp.get("sell_url")
        )
        db.add(db_opp)
        created_opportunities.append(db_opp)
    
    db.commit()
    return created_opportunities

def get_opportunities(db, 
                     snapshot_id: Optional[str] = None,
                     min_profit_percent: Optional[float] = None,
                     min_profit_amount: Optional[float] = None,
                     limit: int = 100) -> List[Opportunity]:
    """Get arbitrage opportunities from the database with optional filtering.
    
    Args:
        db: Database session
        snapshot_id: Optional snapshot ID to filter by
        min_profit_percent: Optional minimum profit percentage
        min_profit_amount: Optional minimum profit amount
        limit: Maximum number of results to return
        
    Returns:
        List of Opportunity objects
    """
    query = db.query(Opportunity)
    
    if snapshot_id:
        query = query.filter(Opportunity.snapshot_id == snapshot_id)
    
    if min_profit_percent is not None:
        query = query.filter(Opportunity.profit_percent >= min_profit_percent)
    
    if min_profit_amount is not None:
        query = query.filter(Opportunity.profit_amount >= min_profit_amount)
    
    # Order by profit percentage (highest first)
    query = query.order_by(Opportunity.profit_percent.desc())
    
    return query.limit(limit).all()

def get_recent_opportunities(db, days: int = 7, limit: int = 100) -> List[Opportunity]:
    """Get recent arbitrage opportunities from the database.
    
    Args:
        db: Database session
        days: Number of days to look back
        limit: Maximum number of results to return
        
    Returns:
        List of Opportunity objects
    """
    # Calculate the date threshold
    threshold = datetime.utcnow() - timedelta(days=days)
    
    return db.query(Opportunity)\
        .filter(Opportunity.timestamp >= threshold)\
        .order_by(Opportunity.timestamp.desc())\
        .limit(limit)\
        .all()
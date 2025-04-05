# This file defines the database schema for our application using SQLAlchemy's Object Relational Mapper (ORM)
# It creates the structure for storing snapshots of price data and detected opportunities

from sqlalchemy import Column, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

# Create a base class for all ORM models
# This base class will be used to create database tables and relationships
# It provides the metadata that SQLAlchemy needs to map Python classes to database tables
Base = declarative_base()

class Snapshot(Base):
    """Represents a point-in-time collection of price data from multiple sources.
    
    Snapshots are crucial for arbitrage detection as they capture the state of
    prices across different sources at the same moment, allowing for accurate
    comparison. They also enable historical analysis and auditing.
    """
    __tablename__ = "snapshots"  # The actual table name in the database
    
    # Primary key using UUID for distributed systems compatibility and to avoid sequence issues
    # String type used instead of UUID for broader database compatibility
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # When the snapshot was taken - critical for temporal analysis
    # Indexed to allow efficient querying by time range
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Optional human-readable description of why this snapshot was taken
    # Useful for manual scrapes or special events
    description = Column(String(255), nullable=True)
    
    # Relationship to items - defines the one-to-many relationship with Item model
    # This enables navigating from a snapshot to all its items using ORM queries
    # back_populates creates the bidirectional relationship with the Item.snapshot property
    items = relationship("Item", back_populates="snapshot")
    
    # Relationship to opportunities - defines the one-to-many relationship with Opportunity model
    # This enables navigating from a snapshot to all its opportunities using ORM queries
    opportunities = relationship("Opportunity", back_populates="snapshot", cascade="all, delete-orphan")


class Item(Base):
    """Represents a single product with its price from a specific source.
    
    Items are the core data entities that enable arbitrage detection.
    Each item belongs to a snapshot and contains price information from
    a specific source at that point in time.
    """
    __tablename__ = "items"
    
    # Primary key using UUID, similar to Snapshot
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign key to the parent snapshot
    # This links each item to its snapshot and is indexed for query performance
    snapshot_id = Column(String(36), ForeignKey("snapshots.id"), index=True)
    
    # The data source this item came from (e.g., "amazon", "ebay")
    # Indexed to allow querying items from specific sources
    source = Column(String(50), index=True)
    
    # The product name or identifier
    # Indexed because we frequently query by name to find the same product across sources
    name = Column(String(255), index=True)
    
    # The product price - the most critical data point for arbitrage detection
    # Indexed to enable finding lowest/highest priced items efficiently
    price = Column(Float, index=True)
    
    # URL to the product page - useful for verification and for acting on opportunities
    url = Column(String(512), nullable=True)
    
    # Relationship back to the parent snapshot
    # This completes the bidirectional relationship with Snapshot.items
    # Enables navigating from an item to its snapshot using ORM queries
    snapshot = relationship("Snapshot", back_populates="items")


class Opportunity(Base):
    """Database model for arbitrage opportunities."""
    
    __tablename__ = "opportunities"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    snapshot_id = Column(String(36), ForeignKey("snapshots.id"), nullable=False)
    item_name = Column(String(255), nullable=False)
    buy_from = Column(String(50), nullable=False)
    buy_price = Column(Float, nullable=False)
    sell_to = Column(String(50), nullable=False)
    sell_price = Column(Float, nullable=False)
    profit_amount = Column(Float, nullable=False)
    profit_percent = Column(Float, nullable=False)
    buy_url = Column(String(2048), nullable=True)
    sell_url = Column(String(2048), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to snapshot
    snapshot = relationship("Snapshot", back_populates="opportunities")
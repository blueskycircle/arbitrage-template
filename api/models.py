from typing import List, Optional
from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime


# Request Models
class ScrapeRequest(BaseModel):
    """Request model for scraping products."""

    amazon_urls: Optional[List[HttpUrl]] = Field(
        default=[], description="List of Amazon product URLs to scrape"
    )
    amazon_names: Optional[List[str]] = Field(
        default=[],
        description="Custom names for Amazon products (must match order of URLs)",
    )
    include_static: bool = Field(
        default=True, description="Whether to include static data"
    )
    snapshot_name: Optional[str] = Field(
        default="API scrape", description="Name for database snapshot"
    )


class OpportunityFilterRequest(BaseModel):
    """Filter criteria for retrieving arbitrage opportunities."""

    snapshot_id: Optional[str] = None
    use_latest: bool = True
    days: Optional[int] = None
    min_profit_percent: Optional[float] = None
    min_profit_amount: Optional[float] = None
    limit: int = 50


# Response Models
class Item(BaseModel):
    """API representation of a product item."""

    id: str
    source: str
    name: str
    price: float
    url: Optional[str] = None
    snapshot_id: str

    class Config:
        from_attributes = True


class Opportunity(BaseModel):
    """API representation of an arbitrage opportunity."""

    id: Optional[str] = None
    item_name: str
    buy_from: str
    buy_price: float
    buy_url: Optional[str] = None
    sell_to: str
    sell_price: float
    sell_url: Optional[str] = None
    profit_amount: float
    profit_percent: float
    timestamp: datetime
    snapshot_id: Optional[str] = None

    class Config:
        from_attributes = True


class SnapshotInfo(BaseModel):
    """API representation of a database snapshot."""

    id: str
    description: Optional[str] = None
    timestamp: datetime
    item_count: int

    class Config:
        from_attributes = True


class ScrapeResponse(BaseModel):
    """Response for a scrape operation."""

    success: bool
    snapshot_id: Optional[str] = None
    item_count: int
    items: List[Item]
    message: str


class OpportunityResponse(BaseModel):
    """Response containing arbitrage opportunities."""

    opportunities: List[Opportunity]
    count: int
    snapshot_id: Optional[str] = None
    min_profit_percent: Optional[float] = None
    min_profit_amount: Optional[float] = None


class ErrorResponse(BaseModel):
    """Error response model."""

    detail: str

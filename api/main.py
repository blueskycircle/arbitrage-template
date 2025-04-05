from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import sqlalchemy.exc
import requests

from core.database.operations import (
    get_db,
    create_snapshot,
    add_item,
    get_opportunities,
    get_recent_opportunities,
    save_opportunities,
)
from core.database.models import Snapshot, Item as DBItem
from core.scrapers.websites.amazon_scraper import AmazonScraper
from core.scrapers.websites.static_scraper import StaticScraper
from core.arbitrage.detector import ArbitrageDetector

from .models import (
    ScrapeRequest,
    OpportunityFilterRequest,
    Item,
    Opportunity,
    SnapshotInfo,
    ScrapeResponse,
    OpportunityResponse,
)

app = FastAPI(
    title="Arbitrage API",
    description="REST API for arbitrage detection platform",
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["General"])
async def root():
    """Root endpoint providing API information."""
    return {
        "name": "Arbitrage API",
        "version": "1.0.0",
        "description": "API for detecting arbitrage opportunities across different marketplaces",
        "endpoints": {
            "GET /": "This information",
            "POST /scrape": "Scrape product data from sources",
            "GET /opportunities": "Get arbitrage opportunities",
            "GET /items": "Get items from a snapshot",
            "GET /snapshots": "Get available snapshots",
            "GET /snapshots/{snapshot_id}": "Get specific snapshot details",
        },
    }


@app.post("/scrape", response_model=ScrapeResponse, tags=["Data Collection"])
async def scrape_products(request: ScrapeRequest, db: Session = Depends(get_db)):
    """Scrape product data from Amazon and/or static sources."""
    all_items = []

    try:
        # Scrape Amazon products if URLs provided
        if request.amazon_urls:
            # Check if names match URLs
            amazon_names = None
            if request.amazon_names:
                if len(request.amazon_urls) != len(request.amazon_names):
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={
                            "detail": "Number of Amazon names must match number of URLs"
                        },
                    )
                amazon_names = request.amazon_names

            # Create Amazon scraper
            amazon_scraper = AmazonScraper(
                product_urls=[str(url) for url in request.amazon_urls],
                product_names=amazon_names,
            )

            # Scrape products
            amazon_items = amazon_scraper.scrape()
            all_items.extend(amazon_items)

        # Include static data if requested
        if request.include_static:
            static_scraper = StaticScraper("static", "http://example.com")
            static_items = static_scraper.scrape()
            all_items.extend(static_items)

        # Save to database
        if not all_items:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"detail": "No products found to scrape"},
            )

        # Create snapshot and add items
        snapshot = create_snapshot(db, request.snapshot_name)

        for item in all_items:
            add_item(
                db,
                snapshot.id,
                item["source"],
                item["name"],
                item["price"],
                item.get("url", None),
            )

        # Get DB items for response
        db_items = db.query(DBItem).filter(DBItem.snapshot_id == snapshot.id).all()

        return ScrapeResponse(
            success=True,
            snapshot_id=snapshot.id,
            item_count=len(db_items),
            items=[Item.model_validate(item) for item in db_items],
            message=f"Successfully scraped {len(db_items)} products",
        )

    except sqlalchemy.exc.SQLAlchemyError as e:
        # Database errors
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"Database error: {str(e)}"},
        )
    except KeyError as e:
        # Missing keys in data structures
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"Data format error - missing key: {str(e)}"},
        )
    except ValueError as e:
        # Value conversion or validation errors
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"Invalid data value: {str(e)}"},
        )
    except requests.exceptions.RequestException as e:
        # Network request errors (for Amazon scraper)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": f"Error accessing external service: {str(e)}"},
        )
    except TypeError as e:
        # Type related errors
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"Data type error: {str(e)}"},
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        # We still need a general exception handler as final fallback
        # for unexpected errors, to prevent 500 errors without context
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"Error during scraping: {str(e)}"},
        )


@app.get("/opportunities", response_model=OpportunityResponse, tags=["Arbitrage"])
async def get_arbitrage_opportunities(
    snapshot_id: Optional[str] = None,
    latest: bool = True,
    days: Optional[int] = None,
    min_profit_percent: Optional[float] = Query(None, ge=0),
    min_profit_amount: Optional[float] = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Get arbitrage opportunities based on specified criteria."""
    try:
        opportunities = []
        active_snapshot_id = None

        if snapshot_id:
            # Verify snapshot exists
            snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
            if not snapshot:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Snapshot with ID {snapshot_id} not found",
                )

            opportunities = get_opportunities(
                db,
                snapshot_id=snapshot_id,
                min_profit_percent=min_profit_percent,
                min_profit_amount=min_profit_amount,
                limit=limit,
            )
            active_snapshot_id = snapshot_id

        elif latest:
            # Get the latest snapshot
            latest_snapshot = (
                db.query(Snapshot).order_by(Snapshot.timestamp.desc()).first()
            )
            if not latest_snapshot:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No snapshots found in database",
                )

            opportunities = get_opportunities(
                db,
                snapshot_id=latest_snapshot.id,
                min_profit_percent=min_profit_percent,
                min_profit_amount=min_profit_amount,
                limit=limit,
            )
            active_snapshot_id = latest_snapshot.id

        elif days:
            # Get recent opportunities
            opportunities = get_recent_opportunities(db, days=days, limit=limit)

            # Apply additional filtering if needed
            if min_profit_percent is not None or min_profit_amount is not None:
                opportunities = [
                    opp
                    for opp in opportunities
                    if (
                        min_profit_percent is None
                        or opp.profit_percent >= min_profit_percent
                    )
                    and (
                        min_profit_amount is None
                        or opp.profit_amount >= min_profit_amount
                    )
                ]

        return OpportunityResponse(
            opportunities=[Opportunity.model_validate(opp) for opp in opportunities],
            count=len(opportunities),
            snapshot_id=active_snapshot_id,
            min_profit_percent=min_profit_percent,
            min_profit_amount=min_profit_amount,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving opportunities: {str(e)}",
        ) from e


@app.get("/snapshots", response_model=List[SnapshotInfo], tags=["Snapshots"])
async def get_snapshots(
    limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)
):
    """Get list of available snapshots ordered by newest first."""
    try:
        snapshots = (
            db.query(Snapshot).order_by(Snapshot.timestamp.desc()).limit(limit).all()
        )

        # Count items for each snapshot
        result = []
        for snapshot in snapshots:
            item_count = (
                db.query(DBItem).filter(DBItem.snapshot_id == snapshot.id).count()
            )
            result.append(
                SnapshotInfo(
                    id=snapshot.id,
                    description=snapshot.description,
                    timestamp=snapshot.timestamp,
                    item_count=item_count,
                )
            )

        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving snapshots: {str(e)}",
        ) from e


@app.get("/snapshots/{snapshot_id}", response_model=SnapshotInfo, tags=["Snapshots"])
async def get_snapshot(snapshot_id: str, db: Session = Depends(get_db)):
    """Get detailed information about a specific snapshot."""
    try:
        snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
        if not snapshot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Snapshot with ID {snapshot_id} not found",
            )

        item_count = db.query(DBItem).filter(DBItem.snapshot_id == snapshot_id).count()

        return SnapshotInfo(
            id=snapshot.id,
            description=snapshot.description,
            timestamp=snapshot.timestamp,
            item_count=item_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving snapshot: {str(e)}",
        ) from e


@app.get("/items", response_model=List[Item], tags=["Items"])
async def get_items(
    snapshot_id: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Get items from a specific snapshot or the latest snapshot."""
    try:
        query = db.query(DBItem)

        # Determine which snapshot to use
        if snapshot_id:
            # Verify snapshot exists
            snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
            if not snapshot:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Snapshot with ID {snapshot_id} not found",
                )
            query = query.filter(DBItem.snapshot_id == snapshot_id)
        else:
            # Get latest snapshot
            latest_snapshot = (
                db.query(Snapshot).order_by(Snapshot.timestamp.desc()).first()
            )
            if not latest_snapshot:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No snapshots found in database",
                )
            query = query.filter(DBItem.snapshot_id == latest_snapshot.id)

        # Filter by source if specified
        if source:
            query = query.filter(DBItem.source == source)

        # Get items
        items = query.limit(limit).all()

        return [Item.model_validate(item) for item in items]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving items: {str(e)}",
        ) from e


@app.post("/detect", response_model=OpportunityResponse, tags=["Arbitrage"])
async def detect_opportunities(
    request: OpportunityFilterRequest, db: Session = Depends(get_db)
):
    """Detect arbitrage opportunities based on specified criteria."""
    try:
        all_items = []
        active_snapshot_id = None

        if request.snapshot_id or request.use_latest:
            # Determine which snapshot to use
            if request.use_latest:
                latest_snapshot = (
                    db.query(Snapshot).order_by(Snapshot.timestamp.desc()).first()
                )
                if not latest_snapshot:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="No snapshots found in database",
                    )
                active_snapshot_id = latest_snapshot.id
            else:
                # Verify snapshot exists
                snapshot = (
                    db.query(Snapshot)
                    .filter(Snapshot.id == request.snapshot_id)
                    .first()
                )
                if not snapshot:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Snapshot with ID {request.snapshot_id} not found",
                    )
                active_snapshot_id = request.snapshot_id

            # Get items from snapshot
            db_items = (
                db.query(DBItem).filter(DBItem.snapshot_id == active_snapshot_id).all()
            )

            # Convert DB items to the format expected by ArbitrageDetector
            for item in db_items:
                parsed_item = {
                    "source": item.source,
                    "name": item.name,
                    "price": item.price,
                    "url": item.url,
                }
                all_items.append(parsed_item)

        if not all_items:
            return OpportunityResponse(
                opportunities=[],
                count=0,
                snapshot_id=active_snapshot_id,
                min_profit_percent=request.min_profit_percent,
                min_profit_amount=request.min_profit_amount,
            )

        # Find opportunities
        detector = ArbitrageDetector(
            min_profit_percent=request.min_profit_percent or 5.0
        )
        opportunities = detector.find_opportunities(all_items)

        # Save opportunities if snapshot is available
        if active_snapshot_id and opportunities:
            db_opportunities = save_opportunities(db, active_snapshot_id, opportunities)
            return OpportunityResponse(
                opportunities=[
                    Opportunity.model_validate(opp) for opp in db_opportunities
                ],
                count=len(db_opportunities),
                snapshot_id=active_snapshot_id,
                min_profit_percent=request.min_profit_percent,
                min_profit_amount=request.min_profit_amount,
            )
        else:
            # Convert dictionary opportunities to response format
            opp_list = []
            for opp in opportunities:
                opp_obj = Opportunity(
                    item_name=opp["item_name"],
                    buy_from=opp["buy_from"],
                    buy_price=opp["buy_price"],
                    buy_url=opp.get("buy_url"),
                    sell_to=opp["sell_to"],
                    sell_price=opp["sell_price"],
                    sell_url=opp.get("sell_url"),
                    profit_amount=opp["profit_amount"],
                    profit_percent=opp["profit_percent"],
                    timestamp=datetime.now(),
                )
                opp_list.append(opp_obj)

            return OpportunityResponse(
                opportunities=opp_list,
                count=len(opp_list),
                snapshot_id=active_snapshot_id,
                min_profit_percent=request.min_profit_percent,
                min_profit_amount=request.min_profit_amount,
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error detecting opportunities: {str(e)}",
        ) from e


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def general_exception_handler(_request, exc):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Unexpected error: {str(exc)}"},
    )


# Run with: uvicorn api.main:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)

import click
import logging
import sqlalchemy.exc
from core.scrapers.websites.amazon_scraper import AmazonScraper
from core.scrapers.websites.static_scraper import StaticScraper
from core.arbitrage.detector import ArbitrageDetector
from core.database.operations import init_db, SessionLocal, create_snapshot, add_item
from tabulate import tabulate
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("arbitrage-cli")


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose):
    """Arbitrage detection tool."""
    # Store verbose flag in the Click context instead of a global variable
    ctx.ensure_object(dict)
    ctx.obj["VERBOSE"] = verbose

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")


@cli.command()
def init():
    """Initialize the database."""
    init_db()
    click.echo("Database initialized!")


@cli.command()
@click.option(
    "--amazon-url",
    "-a",
    multiple=True,
    help="Amazon product URL to scrape (can be specified multiple times)",
)
@click.option(
    "--amazon-name",
    "-n",
    multiple=True,
    help="Custom name for Amazon product (must match order of URLs)",
)
@click.option("--static", "-s", is_flag=True, help="Include static data")
@click.option("--save/--no-save", default=True, help="Save to database (default: True)")
@click.option(
    "--snapshot-name", default="CLI scrape", help="Name for database snapshot"
)
@click.pass_context
def scrape(ctx, amazon_url, amazon_name, static, save, snapshot_name):
    """Scrape products from Amazon and/or static data."""
    all_items = []

    # Scrape Amazon products if URLs provided
    if amazon_url:
        click.echo(f"Scraping {len(amazon_url)} Amazon products...")

        # Check if names match URLs
        if amazon_name and len(amazon_url) != len(amazon_name):
            click.echo("Warning: Number of custom names doesn't match number of URLs.")
            # Use only as many names as we have, or none if there's a mismatch
            amazon_name = (
                amazon_name[: len(amazon_url)]
                if len(amazon_name) < len(amazon_url)
                else None
            )

        # Create Amazon scraper
        amazon_scraper = AmazonScraper(
            product_urls=list(amazon_url),
            product_names=list(amazon_name) if amazon_name else None,
        )

        # Scrape products
        amazon_items = amazon_scraper.scrape()
        all_items.extend(amazon_items)

        click.echo(f"Found {len(amazon_items)} Amazon products.")

        # Display products
        if amazon_items:
            click.echo("\nAmazon Products:")
            for i, item in enumerate(amazon_items, 1):
                click.echo(f"{i}. {item['name']}")
                click.echo(f"   Price: £{item['price']:.2f}")
                click.echo(f"   URL: {item['url']}")

    # Include static data if requested
    if static:
        click.echo("Retrieving static products...")
        static_scraper = StaticScraper("static", "http://example.com")
        static_items = static_scraper.scrape()
        all_items.extend(static_items)

        click.echo(f"Found {len(static_items)} static products.")

        # Display products
        if static_items:
            click.echo("\nStatic Products:")
            for i, item in enumerate(static_items, 1):
                click.echo(f"{i}. {item['name']}")
                click.echo(f"   Price: £{item['price']:.2f}")
                if "url" in item:
                    click.echo(f"   URL: {item['url']}")

    # Summary
    click.echo(f"\nTotal: {len(all_items)} products scraped.")

    # Save to database if requested
    if save and all_items:
        db = SessionLocal()
        try:
            snapshot = create_snapshot(db, snapshot_name)
            click.echo(f"Created snapshot: {snapshot.id}")

            for item in all_items:
                add_item(
                    db,
                    snapshot.id,
                    item["source"],
                    item["name"],
                    item["price"],
                    item.get("url", None),
                )
            click.echo("Saved items to database.")
        except sqlalchemy.exc.SQLAlchemyError as e:
            # Database-specific errors
            db.rollback()
            click.echo(f"Database error: {str(e)}")
        except KeyError as e:
            # Missing required keys in item dictionaries
            click.echo(f"Item data error - missing key {str(e)}")
        except ValueError as e:
            # Value formatting issues
            click.echo(f"Value error: {str(e)}")
        except (IOError, OSError) as e:
            # File and OS errors
            click.echo(f"System error: {str(e)}")
        except (TypeError, AttributeError) as e:
            # Type-related errors
            click.echo(f"Type error: {str(e)}")
            click.echo(
                "This may be due to unexpected data formats in the scraped items."
            )
        except ImportError as e:
            # Missing module errors
            click.echo(f"Import error: {str(e)}")
            click.echo(
                "This may be due to missing dependencies. Try installing required packages."
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            error_str = str(e).lower()

            if (
                "network" in error_str
                or "connection" in error_str
                or "timeout" in error_str
            ):
                click.echo(f"Network error: {str(e)}")
                click.echo(
                    "This appears to be a network-related error. Check your internet connection."
                )
            elif "permission" in error_str:
                click.echo(f"Permission error: {str(e)}")
                click.echo(
                    "This appears to be a permission error. Check file/directory access rights."
                )
            elif "memory" in error_str:
                click.echo(f"Memory error: {str(e)}")
                click.echo(
                    "This appears to be a memory-related error. The operation may require more resources."
                )
            else:
                click.echo(f"Unexpected error: {str(e)}")

            # Always show traceback in verbose mode
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
        finally:
            db.close()


@cli.command()
@click.option(
    "--amazon-url", "-a", multiple=True, help="Amazon product URL to scrape (optional)"
)
@click.option(
    "--amazon-name", "-n", multiple=True, help="Custom name for Amazon product"
)
@click.option(
    "--static/--no-static", default=True, help="Include static data (default: True)"
)
@click.option(
    "--snapshot-id",
    "-s",
    type=str,
    help="Use products from a specific database snapshot ID",
)
@click.option(
    "--latest",
    "-l",
    is_flag=True,
    help="Use products from the latest database snapshot",
)
@click.option(
    "--min-profit", "-p", default=5.0, help="Minimum profit percentage (default: 5.0)"
)
@click.option(
    "--format-type",
    "-f",
    type=click.Choice(["text", "table", "csv"]),
    default="table",
    help="Output format (default: table)",
)
@click.option("--output", "-o", type=click.Path(), help="Save results to file")
@click.pass_context
def detect(
    ctx,
    amazon_url,
    amazon_name,
    static,
    snapshot_id,
    latest,
    min_profit,
    format_type,
    output,
):
    """Detect arbitrage opportunities between Amazon and static data.

    Can use live scraped data, database snapshots, or both.
    """
    all_items = []

    # Scrape live Amazon products if URLs provided
    if amazon_url:
        click.echo(f"Scraping {len(amazon_url)} Amazon products...")

        # Check if names match URLs
        if amazon_name and len(amazon_url) != len(amazon_name):
            click.echo("Warning: Number of custom names doesn't match number of URLs.")
            amazon_name = (
                amazon_name[: len(amazon_url)]
                if len(amazon_name) < len(amazon_url)
                else None
            )

        # Create Amazon scraper and get items
        amazon_scraper = AmazonScraper(
            product_urls=list(amazon_url),
            product_names=list(amazon_name) if amazon_name else None,
        )
        amazon_items = amazon_scraper.scrape()
        all_items.extend(amazon_items)
        click.echo(f"Found {len(amazon_items)} Amazon products from live scraping.")

    # Include live static data if requested and no snapshot specified
    if static and not (snapshot_id or latest):
        click.echo("Retrieving static products...")
        static_scraper = StaticScraper("static", "http://example.com")
        static_items = static_scraper.scrape()
        all_items.extend(static_items)
        click.echo(f"Found {len(static_items)} static products from live scraping.")

    # Get data from database if snapshot ID provided or latest flag set
    if snapshot_id or latest:
        db = SessionLocal()
        try:
            # Determine which snapshot to use
            if latest:
                from core.database.models import Snapshot

                latest_snapshot = (
                    db.query(Snapshot).order_by(Snapshot.timestamp.desc()).first()
                )
                if latest_snapshot:
                    snapshot_id = latest_snapshot.id
                    description = latest_snapshot.description or "No description"
                    click.echo(
                        f"Using latest snapshot (ID: {snapshot_id}, Description: '{description}', Created: {latest_snapshot.timestamp})"
                    )
                else:
                    click.echo("No snapshots found in database.")
                    return

            # Get items from the database
            if snapshot_id:
                from core.database.models import Item, Snapshot

                # Verify snapshot exists
                snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
                if not snapshot:
                    click.echo(f"Error: Snapshot with ID {snapshot_id} not found.")
                    return

                # Get items from snapshot
                db_items = db.query(Item).filter(Item.snapshot_id == snapshot_id).all()

                # Convert DB items to the format expected by ArbitrageDetector
                for item in db_items:
                    parsed_item = {
                        "source": item.source,
                        "name": item.name,
                        "price": item.price,
                        "url": item.url,
                    }
                    all_items.append(parsed_item)

                description = snapshot.description or "No description"
                click.echo(
                    f"Found {len(db_items)} products from database snapshot {snapshot_id} ('{description}')"
                )

        except sqlalchemy.exc.SQLAlchemyError as e:
            click.echo(f"Database error: {str(e)}")
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
            return
        except KeyError as e:
            click.echo(f"Data error - missing key: {str(e)}")
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
            return
        except ValueError as e:
            click.echo(f"Value error: {str(e)}")
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
            return
        except Exception as e:  # pylint: disable=broad-exception-caught
            if "HTTPError" in str(type(e)):
                click.echo(f"HTTP error when accessing external resources: {str(e)}")
            elif "JSONDecodeError" in str(type(e)):
                click.echo(f"Error parsing JSON data: {str(e)}")
            elif "ConnectionError" in str(type(e)):
                click.echo(
                    f"Connection error - could not reach external resource: {str(e)}"
                )
            elif "Timeout" in str(type(e)):
                click.echo(f"Request timed out: {str(e)}")
            elif "IO" in str(type(e)):
                click.echo(f"Input/output error: {str(e)}")
            elif "Parse" in str(type(e)) or "Syntax" in str(type(e)):
                click.echo(f"Error parsing data: {str(e)}")
            elif "Attribute" in str(type(e)):
                click.echo(
                    f"Object attribute error - likely a data structure mismatch: {str(e)}"
                )
            else:
                click.echo(f"Error retrieving data from database: {str(e)}")

            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
            return
        finally:
            db.close()

    # Find opportunities
    if not all_items:
        click.echo("No products found to analyze.")
        return

    click.echo(
        f"Analyzing {len(all_items)} total products for arbitrage opportunities (min profit: {min_profit}%)..."
    )
    detector = ArbitrageDetector(min_profit_percent=min_profit)
    opportunities = detector.find_opportunities(all_items)

    # Format and display results
    result_output = format_opportunities(opportunities, format_type)

    # Output to file or console
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(result_output)
        click.echo(f"Results written to {output}")
    else:
        click.echo("\n" + result_output)


@cli.command()
@click.option(
    "--amazon-url", "-a", multiple=True, help="Amazon product URL to scrape (optional)"
)
@click.option(
    "--amazon-name", "-n", multiple=True, help="Custom name for Amazon product"
)
@click.option(
    "--static/--no-static", default=True, help="Include static data (default: True)"
)
@click.option(
    "--snapshot-id",
    "-s",
    type=str,
    help="Use products from a specific database snapshot ID",
)
@click.option(
    "--latest",
    "-l",
    is_flag=True,
    help="Use products from the latest database snapshot",
)
@click.option(
    "--min-profit", "-p", default=5.0, help="Minimum profit percentage (default: 5.0)"
)
@click.option(
    "--save/--no-save",
    default=True,
    help="Save opportunities to database (default: True)",
)
@click.option(
    "--format-type",
    "-f",
    type=click.Choice(["text", "table", "csv"]),
    default="table",
    help="Output format (default: table)",
)
@click.option("--output", "-o", type=click.Path(), help="Save results to file")
@click.pass_context
def find(
    ctx,
    amazon_url,
    amazon_name,
    static,
    snapshot_id,
    latest,
    min_profit,
    save,
    format_type,
    output,
):
    """Find and optionally save arbitrage opportunities.

    Similar to 'detect' but also saves opportunities to the database for future reference.
    """
    all_items = []
    active_snapshot_id = None

    # Scrape live Amazon products if URLs provided
    if amazon_url:
        click.echo(f"Scraping {len(amazon_url)} Amazon products...")

        # Check if names match URLs
        if amazon_name and len(amazon_url) != len(amazon_name):
            click.echo("Warning: Number of custom names doesn't match number of URLs.")
            amazon_name = (
                amazon_name[: len(amazon_url)]
                if len(amazon_name) < len(amazon_url)
                else None
            )

        # Create Amazon scraper and get items
        amazon_scraper = AmazonScraper(
            product_urls=list(amazon_url),
            product_names=list(amazon_name) if amazon_name else None,
        )
        amazon_items = amazon_scraper.scrape()
        all_items.extend(amazon_items)
        click.echo(f"Found {len(amazon_items)} Amazon products from live scraping.")

    # Include live static data if requested and no snapshot specified
    if static and not (snapshot_id or latest):
        click.echo("Retrieving static products...")
        static_scraper = StaticScraper("static", "http://example.com")
        static_items = static_scraper.scrape()
        all_items.extend(static_items)
        click.echo(f"Found {len(static_items)} static products from live scraping.")

    # Get data from database if snapshot ID provided or latest flag set
    if snapshot_id or latest:
        db = SessionLocal()
        try:
            # Determine which snapshot to use
            if latest:
                from core.database.models import Snapshot

                latest_snapshot = (
                    db.query(Snapshot).order_by(Snapshot.timestamp.desc()).first()
                )
                if latest_snapshot:
                    snapshot_id = latest_snapshot.id
                    active_snapshot_id = snapshot_id  # Save for later use
                    description = latest_snapshot.description or "No description"
                    click.echo(
                        f"Using latest snapshot (ID: {snapshot_id}, Description: '{description}', Created: {latest_snapshot.timestamp})"
                    )
                else:
                    click.echo("No snapshots found in database.")
                    return

            # Get items from the database
            if snapshot_id:
                from core.database.models import Item, Snapshot

                active_snapshot_id = snapshot_id  # Save for later use

                # Verify snapshot exists
                snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
                if not snapshot:
                    click.echo(f"Error: Snapshot with ID {snapshot_id} not found.")
                    return

                # Get items from snapshot
                db_items = db.query(Item).filter(Item.snapshot_id == snapshot_id).all()

                # Convert DB items to the format expected by ArbitrageDetector
                for item in db_items:
                    parsed_item = {
                        "source": item.source,
                        "name": item.name,
                        "price": item.price,
                        "url": item.url,
                    }
                    all_items.append(parsed_item)

                description = snapshot.description or "No description"
                click.echo(
                    f"Found {len(db_items)} products from database snapshot {snapshot_id} ('{description}')"
                )

        except sqlalchemy.exc.SQLAlchemyError as e:
            click.echo(f"Database error: {str(e)}")
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
            return
        except KeyError as e:
            click.echo(f"Data error - missing key: {str(e)}")
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
            return
        except ValueError as e:
            click.echo(f"Value error: {str(e)}")
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
            return
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Import error analysis utilities
            from importlib.util import find_spec

            # Check if the error is related to missing modules
            if str(e).startswith("No module named"):
                module_name = (
                    str(e).split("'")[1] if "'" in str(e) else str(e).split("named ")[1]
                )
                if find_spec(module_name):
                    click.echo(
                        f"Module '{module_name}' is installed but could not be imported correctly."
                    )
                else:
                    click.echo(
                        f"Required module '{module_name}' is not installed. Try installing it with 'pip install {module_name}'."
                    )

            # Check for common database connection issues
            elif "connection" in str(e).lower() and "database" in str(e).lower():
                click.echo(
                    "Database connection error. Check your database server is running and credentials are correct."
                )

            # Check for common permission issues
            elif "permission" in str(e).lower():
                click.echo("Permission denied. Check file/database access rights.")

            # Default error message
            else:
                click.echo(f"Error retrieving data from database: {str(e)}")

            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
            return
        finally:
            db.close()

    # Find opportunities
    if not all_items:
        click.echo("No products found to analyze.")
        return

    click.echo(
        f"Analyzing {len(all_items)} total products for arbitrage opportunities (min profit: {min_profit}%)..."
    )
    detector = ArbitrageDetector(min_profit_percent=min_profit)
    opportunities = detector.find_opportunities(all_items)

    # Format and display results
    result_output = format_opportunities(opportunities, format_type)

    # Output to file or console
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(result_output)
        click.echo(f"Results written to {output}")
    else:
        click.echo("\n" + result_output)

    # Save opportunities to database if requested
    if save and opportunities:
        db = SessionLocal()
        try:
            # If we don't have an active snapshot yet, create one
            if not active_snapshot_id:
                snapshot = create_snapshot(db, "Opportunity detection")
                active_snapshot_id = snapshot.id
                click.echo(f"Created new snapshot: {active_snapshot_id}")

            # Add URLs to opportunities before saving
            for opp in opportunities:
                # Find the original items to get their URLs
                buy_item = next(
                    (
                        item
                        for item in all_items
                        if item["source"] == opp["buy_from"]
                        and item["name"] == opp["item_name"]
                    ),
                    None,
                )
                sell_item = next(
                    (
                        item
                        for item in all_items
                        if item["source"] == opp["sell_to"]
                        and item["name"] == opp["item_name"]
                    ),
                    None,
                )

                # Add URLs to the opportunity
                if buy_item and "url" in buy_item:
                    opp["buy_url"] = buy_item["url"]
                if sell_item and "url" in sell_item:
                    opp["sell_url"] = sell_item["url"]

            # Save opportunities
            from core.database.operations import save_opportunities

            saved = save_opportunities(db, active_snapshot_id, opportunities)
            click.echo(f"Saved {len(saved)} opportunities to database")

        except sqlalchemy.exc.SQLAlchemyError as e:
            click.echo(f"Database error: {str(e)}")
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
        except KeyError as e:
            click.echo(f"Data error - missing key: {str(e)}")
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
        except ValueError as e:
            click.echo(f"Value error: {str(e)}")
            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
        except Exception as e:  # pylint: disable=broad-exception-caught
            if (
                "json" in str(e).lower()
                or "serial" in str(e).lower()
                or "dump" in str(e).lower()
            ):
                click.echo(f"Data serialization error: {str(e)}")
                click.echo(
                    "The opportunity data might contain types that can't be saved directly."
                )
            # Memory issues
            elif "memory" in str(e).lower():
                click.echo(f"Memory error when saving data: {str(e)}")
                click.echo("You may need to process fewer items at a time.")
            # Handle potential schema issues
            elif "schema" in str(e).lower() or "column" in str(e).lower():
                click.echo(f"Database schema error: {str(e)}")
                click.echo(
                    "The database structure might not match the required schema. Try running 'init' command."
                )
            # Other errors
            else:
                click.echo(f"Error saving opportunities to database: {str(e)}")

            if ctx.obj["VERBOSE"]:
                click.echo(traceback.format_exc())
        finally:
            db.close()


@cli.command()
@click.option(
    "--snapshot-id", "-s", type=str, help="Show opportunities from a specific snapshot"
)
@click.option(
    "--latest", "-l", is_flag=True, help="Show opportunities from the latest snapshot"
)
@click.option(
    "--days",
    "-d",
    type=int,
    default=7,
    help="Show opportunities from the last N days (default: 7)",
)
@click.option(
    "--min-profit-percent", "-p", type=float, help="Minimum profit percentage"
)
@click.option("--min-profit-amount", "-a", type=float, help="Minimum profit amount")
@click.option(
    "--limit", type=int, default=50, help="Maximum number of results (default: 50)"
)
@click.option(
    "--format-type",
    "-f",
    type=click.Choice(["text", "table", "csv"]),
    default="table",
    help="Output format (default: table)",
)
@click.option("--output", "-o", type=click.Path(), help="Save results to file")
@click.pass_context
def history(
    ctx,
    snapshot_id,
    latest,
    days,
    min_profit_percent,
    min_profit_amount,
    limit,
    format_type,
    output,
):
    """View historical arbitrage opportunities from the database."""
    from core.database.operations import get_opportunities, get_recent_opportunities
    from core.database.models import Snapshot

    db = SessionLocal()
    try:
        opportunities = []

        if snapshot_id:
            # Verify snapshot exists
            snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
            if not snapshot:
                click.echo(f"Error: Snapshot with ID {snapshot_id} not found.")
                return

            description = snapshot.description or "No description"
            click.echo(
                f"Getting opportunities from snapshot: {snapshot_id} ('{description}', {snapshot.timestamp})"
            )
            opportunities = get_opportunities(
                db,
                snapshot_id=snapshot_id,
                min_profit_percent=min_profit_percent,
                min_profit_amount=min_profit_amount,
                limit=limit,
            )

        elif latest:
            # Get the latest snapshot
            latest_snapshot = (
                db.query(Snapshot).order_by(Snapshot.timestamp.desc()).first()
            )
            if not latest_snapshot:
                click.echo("No snapshots found in database.")
                return

            snapshot_id = latest_snapshot.id
            description = latest_snapshot.description or "No description"
            click.echo(
                f"Getting opportunities from latest snapshot: {snapshot_id} ('{description}', {latest_snapshot.timestamp})"
            )

            opportunities = get_opportunities(
                db,
                snapshot_id=snapshot_id,
                min_profit_percent=min_profit_percent,
                min_profit_amount=min_profit_amount,
                limit=limit,
            )

        else:
            # Get recent opportunities
            click.echo(f"Getting opportunities from the last {days} days")
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

        # Format and display results
        if not opportunities:
            click.echo("No opportunities found with the specified criteria.")
            return

        click.echo(f"Found {len(opportunities)} opportunities")

        # Convert to dictionaries for formatting
        opp_dicts = [
            {
                "item_name": opp.item_name,
                "buy_from": opp.buy_from,
                "buy_price": opp.buy_price,
                "sell_to": opp.sell_to,
                "sell_price": opp.sell_price,
                "profit_amount": opp.profit_amount,
                "profit_percent": opp.profit_percent,
                "timestamp": (
                    opp.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    if format_type == "csv" or format_type == "text"
                    else opp.timestamp
                ),
            }
            for opp in opportunities
        ]

        # Add timestamp to the result
        result_output = format_opportunities(
            opp_dicts, format_type, include_timestamp=True
        )

        # Output to file or console
        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(result_output)
            click.echo(f"Results written to {output}")
        else:
            click.echo("\n" + result_output)

    except sqlalchemy.exc.SQLAlchemyError as e:
        click.echo(f"Database error: {str(e)}")
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    except KeyError as e:
        click.echo(f"Data error - missing key: {str(e)}")
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    except UnicodeError as e:  # Move UnicodeError before ValueError
        click.echo(f"Text encoding error: {str(e)}")
        click.echo("This may be due to issues with character encoding or decoding.")
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    except ValueError as e:
        click.echo(f"Value error: {str(e)}")
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    except (IOError, OSError) as e:
        click.echo(f"File or system error: {str(e)}")
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    except TypeError as e:
        click.echo(f"Type error: {str(e)}")
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    except AttributeError as e:
        click.echo(f"Attribute error: {str(e)}")
        click.echo(
            "This may be due to accessing a property that doesn't exist on an object."
        )
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    except ImportError as e:
        click.echo(f"Import error: {str(e)}")
        click.echo(
            "This may be due to missing dependencies. Try installing required packages."
        )
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    except LookupError as e:
        click.echo(f"Lookup error: {str(e)}")
        click.echo("This may be due to invalid indices or keys in data structures.")
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    except RuntimeError as e:
        click.echo(f"Runtime error: {str(e)}")
        click.echo("This is a runtime error that occurred during execution.")
        if ctx.obj["VERBOSE"]:
            click.echo(traceback.format_exc())
    finally:
        db.close()


def format_opportunities(opportunities, format_type, include_timestamp=False):
    """Format arbitrage opportunities based on specified format type."""
    if not opportunities:
        return "No arbitrage opportunities found."

    if format_type == "text":
        lines = [f"Found {len(opportunities)} opportunities:"]
        for i, opp in enumerate(opportunities, 1):
            lines.append(f"\n{i}. {opp['item_name']}")
            lines.append(f"   Buy from {opp['buy_from']} for £{opp['buy_price']:.2f}")
            lines.append(f"   Sell to {opp['sell_to']} for £{opp['sell_price']:.2f}")
            lines.append(
                f"   Profit: £{opp['profit_amount']:.2f} ({opp['profit_percent']:.1f}%)"
            )
            if include_timestamp and "timestamp" in opp:
                lines.append(f"   Date: {opp['timestamp']}")

        return "\n".join(lines)

    elif format_type == "csv":
        import csv
        from io import StringIO

        output = StringIO()

        # Determine headers based on whether timestamp is included
        headers = [
            "Product",
            "Buy From",
            "Buy Price",
            "Sell To",
            "Sell Price",
            "Profit",
            "Profit %",
        ]
        if include_timestamp:
            headers.append("Timestamp")

        writer = csv.writer(output)
        writer.writerow(headers)

        # Write data
        for opp in opportunities:
            row = [
                opp["item_name"],
                opp["buy_from"],
                f"{opp['buy_price']:.2f}",
                opp["sell_to"],
                f"{opp['sell_price']:.2f}",
                f"{opp['profit_amount']:.2f}",
                f"{opp['profit_percent']:.1f}%",
            ]

            if include_timestamp and "timestamp" in opp:
                row.append(opp["timestamp"])

            writer.writerow(row)

        return output.getvalue()

    else:  # table format
        table_data = []
        for opp in opportunities:
            # Truncate item name if too long
            item_name = opp["item_name"]
            if len(item_name) > 40:
                item_name = item_name[:37] + "..."

            row = [
                item_name,
                opp["buy_from"],
                f"£{opp['buy_price']:.2f}",
                opp["sell_to"],
                f"£{opp['sell_price']:.2f}",
                f"£{opp['profit_amount']:.2f}",
                f"{opp['profit_percent']:.1f}%",
            ]

            # Add timestamp if included
            if include_timestamp and "timestamp" in opp:
                # Format datetime for display
                if isinstance(opp["timestamp"], str):
                    timestamp = opp["timestamp"]
                else:
                    timestamp = opp["timestamp"].strftime("%Y-%m-%d %H:%M")
                row.append(timestamp)

            table_data.append(row)

        # Headers
        headers = [
            "Product",
            "Buy From",
            "Buy Price",
            "Sell To",
            "Sell Price",
            "Profit",
            "Profit %",
        ]

        if include_timestamp:
            headers.append("Date")

        return tabulate(table_data, headers=headers, tablefmt="grid")


if __name__ == "__main__":
    # This runs the Click application
    cli.main(obj={})

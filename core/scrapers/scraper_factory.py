from typing import Dict, Type
from core.scrapers.base import BaseScraper
from core.scrapers.websites.static_scraper import StaticScraper
from core.scrapers.websites.amazon_scraper import AmazonScraper

class ScraperFactory:
    """Factory for creating appropriate scraper instances based on source name.
    
    This factory pattern allows the application to create the right type of scraper
    without needing to know the specific implementation details of each website.
    It centralizes scraper creation logic and makes adding new scrapers easier.
    """
    
    # Map of source names to scraper classes
    SCRAPERS: Dict[str, Type[BaseScraper]] = {
        "static": StaticScraper,
        "amazon": AmazonScraper,
    }
    
    @classmethod
    def create_scraper(cls, source: str, **kwargs) -> BaseScraper:
        """Create and return a scraper for the specified source.
        
        Args:
            source: Name of the data source (must be in SCRAPERS dictionary)
            **kwargs: Additional keyword arguments for the scraper
                
        For product-specific scrapers:
            - 'product_url' for a single product URL
            - 'product_urls' for multiple product URLs
        """
        # Check if the source is supported
        if source not in cls.SCRAPERS:
            # Fall back to static scraper with a warning
            print(f"Warning: Unknown source '{source}', using static scraper instead")
            return StaticScraper(source, f"http://example.com/{source}")
        
        # Get the scraper class
        scraper_class = cls.SCRAPERS[source]
        
        # Handle product URL-based scrapers
        if source == "amazon":
            return scraper_class(
                product_url=kwargs.get("product_url"),
                product_urls=kwargs.get("product_urls")
            )
        
        # Static scraper case
        elif source == "static":
            return scraper_class(source, f"http://example.com/{source}")
        
        # Generic case
        return scraper_class(**kwargs)
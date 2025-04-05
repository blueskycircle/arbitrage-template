from core.scrapers.base import BaseScraper

class StaticScraper(BaseScraper):
    """A scraper that returns static data (for testing)."""
    
    def scrape(self):
        """Return static test data."""
        return [
            {
                "source": self.name,
                "name": "USB Cable",
                "price": 9.99,
                "url": "http://example.com/product1"
            },
            {
                "source": self.name,
                "name": "HDMI Cable",
                "price": 14.99,
                "url": "http://example.com/product2"
            },
            {
                "source": self.name,
                "name": "Wireless Mouse",
                "price": 24.99,
                "url": "http://example.com/product3"
            },
            {
                "source": self.name,
                "name": "iPhone 16 128GB",
                "price": 830,
                "url": "http://example.com/product4"
            },
            {
                "source": self.name,
                "name": "iPhone 16 256GB",
                "price": 900,
                "url": "http://example.com/product5"
            }
        ]
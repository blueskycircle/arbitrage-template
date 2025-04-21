import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional
import time
import random
import logging
from core.scrapers.base import BaseScraper

class WebScraperBase(BaseScraper):
    """Base class for web scrapers that fetch actual data from websites.
    
    This class extends the BaseScraper with common functionality needed for
    HTTP requests, HTML parsing, and responsible scraping practices like
    rate limiting and error handling.
    """
    
    def __init__(self, name: str, url: str, user_agent: Optional[str] = None):
        """Initialize the web scraper.
        
        Args:
            name: Unique identifier for this data source
            url: Base URL of the website to scrape
            user_agent: Optional custom user agent string
        """
        super().__init__(name, url)
        self.user_agent = user_agent or "ArbitragePlatform/0.1.0 (Research Project)"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.logger = logging.getLogger(f"scraper.{name}")
    
    def get_page(self, url: str = None, params: Dict = None) -> BeautifulSoup:
        """Fetch a page and parse it with BeautifulSoup.
        
        Args:
            url: URL to fetch, defaults to the scraper's base URL
            params: Optional query parameters
            
        Returns:
            BeautifulSoup object for HTML parsing
            
        Raises:
            Exception: If the request fails
        """
        target_url = url or self.url
        self.logger.info("Fetching %s", target_url)
        
        # Add a small delay to be respectful to the server
        time.sleep(random.uniform(1, 3))
        
        try:
            response = self.session.get(target_url, params=params, timeout=30)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            
            # Parse the HTML
            return BeautifulSoup(response.text, "lxml")
        except Exception as e:
            self.logger.error("Error fetching %s: %s", target_url, str(e))
            raise
    
    def extract_price(self, price_text: str) -> float:
        """Extract a numerical price from text.
        
        Args:
            price_text: String containing a price (e.g., "$19.99")
            
        Returns:
            Float value of the price
        """
        # Remove currency symbols, commas, and whitespace
        clean_price = price_text.replace('$', '').replace('£', '').replace('€', '')
        clean_price = clean_price.replace(',', '').strip()
        
        # Try to convert to float
        try:
            return float(clean_price)
        except ValueError:
            self.logger.warning("Could not parse price: %s", price_text)
            return 0.0
    
    def scrape(self) -> List[Dict[str, Any]]:
        """
        This should be implemented by subclasses to scrape specific websites.
        """
        raise NotImplementedError("WebScraperBase.scrape() must be implemented by subclasses")
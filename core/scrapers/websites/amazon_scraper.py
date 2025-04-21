from core.scrapers.web_scraper_base import WebScraperBase
from typing import Dict, List, Any, Optional, Union
import logging
import re
import os

class AmazonScraper(WebScraperBase):
    """Scraper for Amazon product pages.
    
    This scraper fetches data for specific Amazon product URLs directly,
    without needing to search. This is useful for tracking specific products
    you're already interested in for arbitrage opportunities.
    """
    
    def __init__(self, 
                 product_url: Optional[str] = None, 
                 product_urls: Optional[List[str]] = None,
                 product_names: Optional[Union[str, List[str], Dict[str, str]]] = None):
        """Initialize the Amazon product scraper.
        
        Args:
            product_url: Single Amazon product URL to scrape
            product_urls: List of Amazon product URLs to scrape
            product_names: Custom product names to use instead of scraped titles.
                           Can be provided as:
                           - A single string (for single product_url)
                           - A list of strings (matching order of product_urls)
                           - A dict mapping product IDs or URLs to custom names
            
        Either product_url or product_urls should be provided.
        """
        super().__init__("amazon", "https://www.amazon.com")
        
        # Setup product URLs - either single or multiple
        self.product_urls = []
        if product_url:
            self.product_urls.append(product_url)
        if product_urls:
            self.product_urls.extend(product_urls)
            
        if not self.product_urls:
            # Default example URL if none provided
            self.product_urls = ["https://www.amazon.com/dp/B07ZPML7NP"]
        
        # Process custom product names
        self.product_names = {}
        if product_names is not None:
            if isinstance(product_names, str) and product_url:
                # Single product name for single URL
                product_id = self._extract_product_id(product_url)
                self.product_names[product_id] = product_names
            elif isinstance(product_names, list) and len(product_names) > 0:
                # List of product names matching product_urls order
                for i, url in enumerate(self.product_urls):
                    if i < len(product_names):
                        product_id = self._extract_product_id(url)
                        self.product_names[product_id] = product_names[i]
            elif isinstance(product_names, dict):
                # Dictionary mapping either product IDs or full URLs to names
                for key, name in product_names.items():
                    if '/' in key:  # Looks like a URL
                        product_id = self._extract_product_id(key)
                        self.product_names[product_id] = name
                    else:  # Assume it's already a product ID
                        self.product_names[key] = name
        
        # Enhanced logging setup
        self.logger = logging.getLogger("scraper.amazon")
        self.logger.setLevel(logging.DEBUG)
    
    def scrape(self) -> List[Dict[str, Any]]:
        """Scrape specific Amazon product pages.
        
        Returns:
            List of dictionaries containing product data
        """
        self.logger.info(f"Starting Amazon product scrape for {len(self.product_urls)} URLs")
        results = []
        
        for url in self.product_urls:
            self.logger.debug(f"Processing product URL: {url}")
            try:
                # Get the product page
                soup = self.get_page(url=url)
                
                # Save HTML to file for debugging if needed
                debug_dir = "debug_output"
                os.makedirs(debug_dir, exist_ok=True)
                product_id = self._extract_product_id(url)
                debug_filename = f"{debug_dir}/amazon_product_{product_id}.html"
                with open(debug_filename, "w", encoding="utf-8") as f:
                    f.write(str(soup))
                self.logger.debug(f"Saved HTML to {debug_filename}")
                
                # Check for CAPTCHA or robot detection
                if "robot" in soup.text.lower() or "captcha" in soup.text.lower():
                    self.logger.warning("Detected CAPTCHA or robot check page!")
                    with open(f"{debug_dir}/amazon_captcha.html", "w", encoding="utf-8") as f:
                        f.write(str(soup))
                    self.logger.warning(f"Saved CAPTCHA page to {debug_dir}/amazon_captcha.html")
                    continue
                
                # Extract product information using various selectors
                
                # Title - try multiple selectors
                title_element = (
                    soup.select_one("#productTitle") or
                    soup.select_one("#title") or
                    soup.select_one(".product-title-word-break")
                )
                
                # Price - try multiple selectors
                price_element = (
                    soup.select_one(".a-price .a-offscreen") or
                    soup.select_one("#priceblock_ourprice") or
                    soup.select_one("#priceblock_dealprice") or
                    soup.select_one(".a-price")
                )
                
                # Check if we found the critical elements
                if not title_element:
                    self.logger.warning(f"Could not find title for {url}")
                    continue
                    
                if not price_element:
                    self.logger.warning(f"Could not find price for {url}")
                    continue
                
                # Extract data
                # Use custom product name if available, otherwise use scraped title
                title = title_element.text.strip()
                if product_id in self.product_names:
                    custom_title = self.product_names[product_id]
                    self.logger.debug(f"Using custom name: {custom_title} instead of: {title[:30]}...")
                    title = custom_title
                
                price_text = price_element.text.strip()
                
                # Log extracted data
                self.logger.debug(f"Title: {title[:50]}...")
                self.logger.debug(f"Raw price: {price_text}")
                
                # Clean and convert price
                price = self.extract_price(price_text)
                self.logger.debug(f"Extracted price: {price}")
                
                # Get availability
                availability = "In Stock"  # Default
                availability_element = soup.select_one("#availability")
                if availability_element:
                    availability = availability_element.text.strip()
                    self.logger.debug(f"Availability: {availability}")
                
                # Create item dict
                item = {
                    "source": self.name,
                    "name": title,
                    "price": price,
                    "url": url,
                    "availability": availability,
                    "product_id": product_id
                }
                
                results.append(item)
                self.logger.debug(f"Added product: {title[:30]}... at £{price:.2f}")
                
            except Exception as e:
                self.logger.error(f"Error processing {url}: {str(e)}")
                import traceback
                self.logger.error(f"Stack trace: {traceback.format_exc()}")
        
        self.logger.info(f"Scraped {len(results)} products from Amazon")
        return results
    
    def _extract_product_id(self, url: str) -> str:
        """Extract the Amazon product ID (ASIN) from the URL.
        
        Args:
            url: Amazon product URL
            
        Returns:
            Product ID string
        """
        # Try to extract using regex patterns
        patterns = [
            r"/dp/([A-Z0-9]{10})",
            r"/gp/product/([A-Z0-9]{10})",
            r"/ASIN/([A-Z0-9]{10})"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # If no pattern matches, use a portion of the URL as ID
        url_parts = url.split("/")
        return url_parts[-1] if url_parts[-1] else "unknown"
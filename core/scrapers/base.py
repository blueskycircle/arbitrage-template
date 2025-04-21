# This file defines the abstract base class for all scrapers in the system
# It establishes a common interface that all concrete scraper implementations must follow

import abc  # The Abstract Base Classes module enables the creation of abstract classes
from typing import Dict, List, Any  # Type hints for better code documentation and IDE support

class BaseScraper(abc.ABC):
    """Base class for website scrapers.
    
    This abstract base class defines the contract that all scrapers must implement.
    Using an abstract base class provides several benefits:
    1. Enforces a consistent interface across all scrapers
    2. Allows treating different scrapers polymorphically (interchangeably)
    3. Makes the code more maintainable by centralizing common functionality
    4. Enables dependency injection patterns when using scrapers
    
    Any new data source can be integrated by simply implementing this interface,
    without having to modify the core arbitrage detection logic.
    """
    
    def __init__(self, name: str, url: str):
        """Initialize the scraper with a name and URL.
        
        Args:
            name: Unique identifier for this data source (e.g., "amazon", "ebay")
                 This name is used to identify which source a price comes from
                 when detecting arbitrage opportunities.
            url: Base URL of the website or API to scrape
                 This could be a product listing page, API endpoint, or search URL.
                 
        The constructor captures the essential information needed to identify
        and access a data source, while keeping implementation details in
        the concrete scraper classes.
        """
        self.name = name  # Store source identifier
        self.url = url    # Store the target URL
    
    @abc.abstractmethod
    def scrape(self) -> List[Dict[str, Any]]:
        """Scrape website and return list of items.
        
        This abstract method must be implemented by all concrete scraper classes.
        It defines the core functionality: extract product data from a source.
        
        Returns:
            A list of dictionaries, where each dictionary represents a product
            with standardized keys:
            - name: Product name or title (required)
            - price: Numerical price (required)
            - url: Direct link to the product (optional)
            - description: Product description (optional)
            - availability: Whether the item is in stock (optional)
            - metadata: Any additional source-specific data (optional)
            
        Raises:
            Various exceptions may be raised by concrete implementations
            depending on the source (connection errors, parsing errors, etc.)
            
        This consistent return format allows the arbitrage system to compare
        prices across different sources regardless of how the data was obtained
        or how it was structured in the original source.
        """
        # Abstract method doesn't need implementation
        raise NotImplementedError("Concrete scraper classes must implement scrape() method")
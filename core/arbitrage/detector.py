class ArbitrageDetector:
    """Detects arbitrage opportunities between different sources."""
    
    def __init__(self, min_profit_percent=5.0):
        self.min_profit_percent = min_profit_percent
    
    def find_opportunities(self, items):
        """Find arbitrage opportunities in a list of items."""
        # Group items by name
        grouped_items = {}
        for item in items:
            name = item["name"]
            if name not in grouped_items:
                grouped_items[name] = []
            grouped_items[name].append(item)
        
        # Find opportunities
        opportunities = []
        for name, items in grouped_items.items():
            if len(items) < 2:
                continue
                
            # Find cheapest and most expensive
            cheapest = min(items, key=lambda x: x["price"])
            most_expensive = max(items, key=lambda x: x["price"])
            
            # Calculate profit percentage
            price_diff = most_expensive["price"] - cheapest["price"]
            profit_percent = (price_diff / cheapest["price"]) * 100
            
            if profit_percent >= self.min_profit_percent:
                opportunities.append({
                    "item_name": name,
                    "buy_from": cheapest["source"],
                    "buy_price": cheapest["price"],
                    "sell_to": most_expensive["source"],
                    "sell_price": most_expensive["price"],
                    "profit_amount": price_diff,
                    "profit_percent": profit_percent
                })
        
        return sorted(opportunities, key=lambda x: x["profit_percent"], reverse=True)
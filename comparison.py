def compare_prices(supplier_a_data: dict, supplier_b_data: dict, query: str) -> list:
    """
    Compares product prices across Supplier A and Supplier B for a given search query.
    """
    query = query.lower().strip()
    
    matches_a = {k: v for k, v in supplier_a_data.items() if query in k}
    matches_b = {k: v for k, v in supplier_b_data.items() if query in k}
    
    comparison_results = []
    all_keys = set(matches_a.keys()).union(set(matches_b.keys()))
    
    for key in all_keys:
        price_a = matches_a.get(key)
        price_b = matches_b.get(key)
        
        diff = None
        cheaper = None
        if price_a is not None and price_b is not None:
            diff = abs(price_a - price_b)
            if price_a < price_b:
                cheaper = "Supplier A"
            elif price_b < price_a:
                cheaper = "Supplier B"
            else:
                cheaper = "Same Price"
        
        comparison_results.append({
            "product": key,
            "supplier_a_price": price_a,
            "supplier_b_price": price_b,
            "difference": diff,
            "cheaper": cheaper
        })
        
    return comparison_results
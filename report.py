import os

def generate_text_report(results: list, output_path: str = "files/output/comparison_report.txt") -> str:
    """
    Generates a downloadable text comparison report.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    report_lines = ["=== SUPPLIER PRICE COMPARISON REPORT ===", ""]
    
    if not results:
        report_lines.append("No matching products found in both supplier lists.")
    else:
        for res in results:
            report_lines.append(f"Product: {res['product'].title()}")
            report_lines.append(f"  - Supplier A Price: ₹{res['supplier_a_price'] if res['supplier_a_price'] is not None else 'N/A'}")
            report_lines.append(f"  - Supplier B Price: ₹{res['supplier_b_price'] if res['supplier_b_price'] is not None else 'N/A'}")
            if res['difference'] is not None:
                report_lines.append(f"  - Difference: ₹{res['difference']:.2f} ({res['cheaper']} is cheaper)")
            report_lines.append("-" * 40)
            
    report_content = "\n".join(report_lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    return output_path
# import os
# from pydantic import BaseModel
# from google import genai
# from google.genai import types
# import pdfplumber
# from dotenv import load_dotenv

# # 1. Load variables from .env so GEMINI_API_KEY is detected
# load_dotenv()

# # 2. Initialize the Gemini client (automatically reads os.environ["GEMINI_API_KEY"])
# client = genai.Client()

# class ProductItem(BaseModel):
#     product_name: str
#     price: float

# class SupplierCatalog(BaseModel):
#     company_name: str
#     items: list[ProductItem]

# def extract_price_list_with_ai(pdf_path: str) -> dict:
#     """
#     Extracts company name and product prices from a supplier PDF using Gemini.
#     Returns a dictionary: {product_name_lower: price_float}
#     """
#     full_text = ""
#     with pdfplumber.open(pdf_path) as pdf:
#         for page in pdf.pages:
#             text = page.extract_text()
#             if text:
#                 full_text += text + "\n"

#     if not full_text.strip():
#         return {}

#     prompt = f"""
#     Analyze this supplier price list / quotation text and extract the company name 
#     and all products with their respective prices. 
    
#     Text content:
#     {full_text}
#     """

#     response = client.models.generate_content(
#         model="gemini-3.8-flash",
#         contents=prompt,
#         config=types.GenerateContentConfig(
#             response_mime_type="application/json",
#             response_schema=SupplierCatalog,
#             temperature=0.0,
#         ),
#     )

#     try:
#         catalog = SupplierCatalog.model_validate_json(response.text)
#         products_dict = {item.product_name.lower().strip(): item.price for item in catalog.items}
#         return products_dict
#     except Exception as e:
#         print(f"Error parsing AI response: {e}")
#         return {}


#-------------------------------------------------------------------------------------------------------------------
# import os
# from dotenv import load_dotenv
# from pydantic import BaseModel
# from google import genai
# from google.genai import types
# import pdfplumber

# load_dotenv()
# client = genai.Client()

# class ProductItem(BaseModel):
#     product_name: str
#     price: float

# class SupplierCatalog(BaseModel):
#     company_name: str
#     items: list[ProductItem]

# def extract_price_list_with_ai(pdf_path: str) -> dict:
#     print(f"\n--- DEBUG: Starting extraction for {os.path.basename(pdf_path)} ---")
    
#     if not os.path.exists(pdf_path):
#         print(f"❌ DEBUG: File not found at path: {pdf_path}")
#         return {}

#     full_text = ""
#     try:
#         print(f"DEBUG: Opening PDF with pdfplumber...")
#         with pdfplumber.open(pdf_path) as pdf:
#             total_pages = len(pdf.pages)
#             print(f"DEBUG: PDF opened successfully. Total pages: {total_pages}")
            
#             pages_to_read = pdf.pages[:5]
#             print(f"DEBUG: Extracting text from first {len(pages_to_read)} pages...")
            
#             for i, page in enumerate(pages_to_read):
#                 print(f"DEBUG: Reading page {i+1}...")
#                 text = page.extract_text()
#                 if text:
#                     full_text += text + "\n"
                    
#         print(f"DEBUG: Text extraction complete. Total characters extracted: {len(full_text)}")
#     except Exception as e:
#         print(f"❌ DEBUG: Error during pdfplumber extraction: {e}")
#         return {}

#     if not full_text.strip():
#         print(f"⚠️ DEBUG: Warning - No text found in {pdf_path} (it might be a scanned image-only PDF).")
#         return {}

#     print(f"DEBUG: Preparing prompt for Gemini...")
#     prompt = f"""
#     Analyze this supplier price list / quotation text and extract the company name 
#     and all products with their respective prices. 
    
#     Text content:
#     {full_text}
#     """

#     print(f"DEBUG: Sending request to Gemini (gemini-3.8-flash)...")
#     try:
#         response = client.models.generate_content(
#             model="gemini-3.8-flash",
#             contents=prompt,
#             config=types.GenerateContentConfig(
#                 response_mime_type="application/json",
#                 response_schema=SupplierCatalog,
#                 temperature=0.0,
#             ),
#         )
#         print(f"DEBUG: Received response from Gemini successfully!")
#     except Exception as e:
#         print(f"❌ DEBUG: Network or API error during Gemini call: {e}")
#         return {}

#     print(f"DEBUG: Parsing JSON response...")
#     try:
#         catalog = SupplierCatalog.model_validate_json(response.text)
#         products_dict = {item.product_name.lower().strip(): item.price for item in catalog.items}
#         print(f"✅ DEBUG: Successfully parsed {len(products_dict)} products.")
#         return products_dict
#     except Exception as e:
#         print(f"❌ DEBUG: Error validating Pydantic schema: {e}")
#         return {}



import os
from dotenv import load_dotenv
from pydantic import BaseModel
from google import genai
from google.genai import types
import pdfplumber

# Load environment variables
load_dotenv()

# Initialize the Gemini client
client = genai.Client()

# Define the structured data schemas
class ProductItem(BaseModel):
    product_name: str
    price: float

class SupplierCatalog(BaseModel):
    company_name: str
    items: list[ProductItem]

def extract_price_list_with_ai(pdf_path: str) -> dict:
    """
    Extracts company name and product prices from a supplier PDF using Gemini.
    Returns a dictionary: {product_name_lower: price_float}
    """
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        return {}

    # 1. Extract text (sliced to first 5 pages to maintain speed and avoid payload limits)
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[:5]):
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not full_text.strip():
        print(f"⚠️ Warning: No text found in {pdf_path}")
        return {}

    # 2. Ask Gemini to extract structured JSON matching our Pydantic schema
    prompt = f"""
    Analyze this supplier price list / quotation text and extract the company name 
    and all products with their respective prices. 
    
    Text content:
    {full_text}
    """

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SupplierCatalog,
                temperature=0.0,
                http_options={'timeout': 15000} # Prevents silent hanging
            ),
        )
    except Exception as e:
        print(f"❌ Network or API error during Gemini call: {e}")
        return {}

    # 3. Parse the structured JSON response into a clean dictionary
    try:
        catalog = SupplierCatalog.model_validate_json(response.text)
        products_dict = {item.product_name.lower().strip(): item.price for item in catalog.items}
        print(f"✅ Successfully extracted {len(products_dict)} products from {catalog.company_name or 'Supplier'}.")
        return products_dict
    except Exception as e:
        print(f"❌ Error parsing AI response into Pydantic schema: {e}")
        return {}
# import os
# import time
# from pydantic import BaseModel
# from google import genai
# from google.genai import types
# import pdfplumber
# from dotenv import load_dotenv

# load_dotenv()
# client = genai.Client()

# class ProductItem(BaseModel):
#     product_name: str
#     price: float

# class SupplierCatalog(BaseModel):
#     company_name: str
#     items: list[ProductItem]

# def extract_price_list_with_ai(pdf_path: str) -> dict:
#     print(f"📄 Opening and reading text from {os.path.basename(pdf_path)}...")
#     full_text = ""
#     with pdfplumber.open(pdf_path) as pdf:
#         for i, page in enumerate(pdf.pages):
#             text = page.extract_text()
#             if text:
#                 full_text += text + "\n"

#     if not full_text.strip():
#         print("⚠️ Warning: No text found in PDF.")
#         return {}

#     print(f"🤖 Sending extracted text to Gemini AI (takes ~3-5 seconds)...")
#     start_time = time.time()

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

#     elapsed = time.time() - start_time
#     print(f"✨ Gemini responded in {elapsed:.1f} seconds! Parsing data...")

#     try:
#         catalog = SupplierCatalog.model_validate_json(response.text)
#         products_dict = {item.product_name.lower().strip(): item.price for item in catalog.items}
#         print(f"✅ Successfully extracted {len(products_dict)} products from {catalog.company_name or 'Supplier'}.")
#         return products_dict
#     except Exception as e:
#         print(f"❌ Error parsing AI response: {e}")
#         return {}

# import os
# from pydantic import BaseModel
# from google import genai
# from google.genai import types
# import pdfplumber

# # Initialize the Gemini client (picks up GEMINI_API_KEY from environment)
# client = genai.Client()

# # Define the structure you want to extract from each price list
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
#     # 1. Extract text from the PDF using pdfplumber as a reliable text layer
#     full_text = ""
#     with pdfplumber.open(pdf_path) as pdf:
#         for page in pdf.pages:
#             text = page.extract_text()
#             if text:
#                 full_text += text + "\n"

#     if not full_text.strip():
#         return {}

#     # 2. Ask Gemini to extract structured data matching our Pydantic schema
#     prompt = f"""
#     Analyze this supplier price list / quotation text and extract the company name 
#     and all products with their respective prices. 
    
#     Text content:
#     {full_text}
#     """

#     response = client.models.generate_content(
#         model="gemini-2.8-flash",  # Fast, lightweight model ideal for structured extraction
#         contents=prompt,
#         config=types.GenerateContentConfig(
#             response_mime_type="application/json",
#             response_schema=SupplierCatalog,
#             temperature=0.0,
#         ),
#     )

#     # 3. Parse the structured JSON response into a clean dictionary
#     try:
#         catalog = SupplierCatalog.model_validate_json(response.text)
#         # Convert list of items into a lookup dictionary
#         products_dict = {item.product_name.lower().strip(): item.price for item in catalog.items}
#         return products_dict
#     except Exception as e:
#         print(f"Error parsing AI response: {e}")
#         return {}


import os
from dotenv import load_dotenv
from pydantic import BaseModel
from google import genai
from google.genai import types
import pdfplumber

# 1. Load environment variables from .env first so client can find the API key
load_dotenv()

# Initialize the Gemini client
client = genai.Client()

# Define the structure you want to extract from each price list
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
    # 1. Extract text from the PDF (sliced to the first 5 pages to prevent timeouts)
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        print(f"📄 Reading first {min(5, len(pdf.pages))} pages of {os.path.basename(pdf_path)}...")
        for i, page in enumerate(pdf.pages[:5]):
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not full_text.strip():
        print(f"⚠️ Warning: No text found in {pdf_path}")
        return {}

    # 2. Ask Gemini to extract structured data matching our Pydantic schema
    prompt = f"""
    Analyze this supplier price list / quotation text and extract the company name 
    and all products with their respective prices. 
    
    Text content:
    {full_text}
    """

    print(f"🤖 Sending payload to Gemini AI (gemini-3.8-flash)...")
    response = client.models.generate_content(
        model="gemini-3.8-flash",  # Correct active model ID
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SupplierCatalog,
            temperature=0.0,
        ),
    )

    # 3. Parse the structured JSON response into a clean dictionary
    try:
        catalog = SupplierCatalog.model_validate_json(response.text)
        products_dict = {item.product_name.lower().strip(): item.price for item in catalog.items}
        print(f"✅ Extracted {len(products_dict)} items from {catalog.company_name or 'Supplier'}.")
        return products_dict
    except Exception as e:
        print(f"❌ Error parsing AI response: {e}")
        return {}
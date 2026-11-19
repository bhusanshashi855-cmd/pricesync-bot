print("Testing imports one by one...")

try:
    import os
    print("✅ os loaded successfully")
except Exception as e:
    print(f"❌ os failed: {e}")

try:
    import dotenv
    print("✅ dotenv loaded successfully")
except Exception as e:
    print(f"❌ dotenv failed: {e}")

try:
    import pydantic
    print("✅ pydantic loaded successfully")
except Exception as e:
    print(f"❌ pydantic failed: {e}")

try:
    from google import genai
    print("✅ google-genai loaded successfully")
except Exception as e:
    print(f"❌ google-genai failed: {e}")

try:
    import pdfplumber
    print("✅ pdfplumber loaded successfully (This one often checks font/C-extensions)")
except Exception as e:
    print(f"❌ pdfplumber failed: {e}")

print("Import test complete!")
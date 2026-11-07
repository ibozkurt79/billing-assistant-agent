import sys
from dotenv import load_dotenv
load_dotenv("billing_assistant/.env")       # project + enterprise switch

from google import genai

location = sys.argv[1] if len(sys.argv) > 1 else "us-central1"
client = genai.Client(location=location)    # overrides the .env location

print(f"Gemini base models in {location}:")
for m in client.models.list(config={"query_base": True}):
    if "gemini" in m.name.lower():
        print(" ", m.name)
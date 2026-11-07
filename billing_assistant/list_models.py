# list_models.py
# Lists Gemini models that support embeddings.
# The API key is read from the environment (GOOGLE_API_KEY), never hardcoded.
#   export GOOGLE_API_KEY="your-key"     or add it to billing_assistant/.env
import os

from dotenv import load_dotenv
from google import genai

load_dotenv("billing_assistant/.env")

api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    raise SystemExit("GOOGLE_API_KEY is not set. Export it or add it to billing_assistant/.env")

client = genai.Client(api_key=api_key)

# for m in client.models.list():
#     if "generateContent" in (m.supported_actions or []):
#         print(m.name)

for m in client.models.list():
    if "embedContent" in (m.supported_actions or []):
        print(m.name)

import os

from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from google import genai
from google.genai import errors, types
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()  # reads GEMINI_API_KEY and ALLOWED_ORIGIN from .env (locally) or Render's environment

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)  # Render sits behind a proxy; use the real client IP
CORS(app, origins=os.getenv("ALLOWED_ORIGIN", "*"))
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")

client = genai.Client()  # reads GEMINI_API_KEY from the environment
# Tried in order; the next one is used if a model is overloaded, over quota, or unavailable to this key.
# Override on Render with GEMINI_MODELS (comma-separated) without changing code.
MODELS = os.getenv("GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.8-flash,gemini-3.1-flash-lite,gemini-flash-lite-latest").split(",")
RETRYABLE = {404, 429, 503}

SYSTEM_PROMPT = """You are a customer support agent for Zomato, a food-delivery app.
Write a short, empathetic apology email to a customer who left the negative review below.

- Address the specific problems the customer mentions.
- Keep it under 150 words, warm and professional.
- Ask them to reply with their order ID so the team can look into it.
- Do not promise refunds, credits, compensation or timelines, and do not invent facts.
- Start with a subject line in the form "Subject: ...", greet with "Hi there," and sign off as "Zomato Customer Support".
"""


def generate_apology_email(review_text):
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=review_text,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            return response.text
        except errors.APIError as e:
            if e.code not in RETRYABLE or model == MODELS[-1]:
                raise
            app.logger.warning("%s returned %s, trying the next model", model, e.code)


@app.get("/")
def health():
    return {"status": "ok"}


@app.errorhandler(errors.APIError)
def gemini_error(e):
    app.logger.error("Gemini error %s: %s", e.code, e.message)
    return {"error": "Gemini is busy right now. Try again in a minute."}, 503


@app.post("/generate")
@limiter.limit("10 per minute;100 per day")
def generate():
    data = request.get_json()
    review = str(data.get("review", "")).strip()
    rating = int(data.get("rating", 0))

    if not review or len(review) > 2000:
        return {"error": "Enter a review between 1 and 2,000 characters."}, 400
    if rating not in (1, 2):
        return {"error": "Replies are only drafted for 1- and 2-star reviews."}, 400

    return {"email": generate_apology_email(review)}

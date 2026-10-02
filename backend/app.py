import os
import re

import requests
from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from google import genai
from google.genai import errors, types
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()  # GEMINI_API_KEY, BREVO_API_KEY, SENDER_EMAIL, ALLOWED_ORIGIN come from .env or Render's environment

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)  # Render sits behind a proxy; use the real client IP
CORS(app, origins=os.getenv("ALLOWED_ORIGIN", "*"))
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")

client = genai.Client()  # reads GEMINI_API_KEY from the environment

# Tried in order; the next one is used if a model is overloaded, over quota, or unavailable to this key.
# Override on Render with GEMINI_MODELS (comma-separated) without changing code.
MODELS = os.getenv("GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.8-flash,gemini-3.1-flash-lite,gemini-flash-lite-latest").split(",")
RETRYABLE = {404, 429, 503}

# 1-2 stars: the notebook's prompt, with the brand changed to the fictional Foodblix.
APOLOGY_PROMPT = """You are a customer support agent for Foodblix, a food-delivery app.
Write a short, empathetic apology email to a customer who left the negative review below.

- Address the specific problems the customer mentions.
- Keep it under 150 words, warm and professional.
- Ask them to reply with their order ID so the team can look into it.
- Do not promise refunds, credits, compensation or timelines, and do not invent facts.
- Start with a subject line in the form "Subject: ...", greet with "Hi there," and sign off as "Foodblix Customer Support".
"""

# 3-5 stars: same rules, thank-you tone.
THANK_YOU_PROMPT = """You are a customer support agent for Foodblix, a food-delivery app.
Write a short, warm reply email to a customer who left the review below with a rating of 3 stars or more.

- Thank them and mention the specific things they liked.
- If they mention any problems, acknowledge them briefly and apologise for those.
- Keep it under 150 words, warm and professional.
- Do not promise refunds, credits, compensation or timelines, and do not invent facts.
- Start with a subject line in the form "Subject: ...", greet with "Hi there," and sign off as "Foodblix Customer Support".
"""

EMAIL_FOOTER = "\n\n--\nSent by a student demo project. Foodblix is a fictional brand."
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def generate_reply(review_text, rating):
    prompt = APOLOGY_PROMPT if rating <= 2 else THANK_YOU_PROMPT
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=review_text,
                config=types.GenerateContentConfig(system_instruction=prompt),
            )
            return response.text
        except errors.APIError as e:
            if e.code not in RETRYABLE or model == MODELS[-1]:
                raise
            app.logger.warning("%s returned %s, trying the next model", model, e.code)


def split_subject(reply):
    lines = reply.strip().splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        return lines[0].split(":", 1)[1].strip(), "\n".join(lines[1:]).strip()
    return "Thank you for your feedback", reply.strip()


def send_email(to_address, subject, body):
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": os.environ["BREVO_API_KEY"]},
        json={
            "sender": {"name": os.getenv("SENDER_NAME", "Foodblix Support (Demo)"), "email": os.environ["SENDER_EMAIL"]},
            "to": [{"email": to_address}],
            "subject": subject,
            "textContent": body + EMAIL_FOOTER,
        },
        timeout=15,
    )
    if not response.ok:
        app.logger.error("Brevo error %s: %s", response.status_code, response.text)
    return response.ok


@app.errorhandler(errors.APIError)
def gemini_error(e):
    app.logger.error("Gemini error %s: %s", e.code, e.message)
    return {"error": "Gemini is busy right now. Try again in a minute."}, 503


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/generate")
@limiter.limit("5 per minute;30 per day")
def generate():
    data = request.get_json()
    review = str(data.get("review", "")).strip()
    rating = int(data.get("rating", 0))
    email = str(data.get("email", "")).strip()

    if not review or len(review) > 2000:
        return {"error": "Enter a review between 1 and 2,000 characters."}, 400
    if rating not in range(1, 6):
        return {"error": "Choose a rating from 1 to 5 stars."}, 400
    if not EMAIL_PATTERN.match(email):
        return {"error": "Enter a valid email address."}, 400

    reply = generate_reply(review, rating)
    subject, body = split_subject(reply)
    sent = send_email(email, subject, body)
    return {"reply": reply, "subject": subject, "sent": sent}
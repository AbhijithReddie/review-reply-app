# Review Reply Generator

A small web app that turns a critical customer review into a personalised apology email, using Google Gemini with the same prompt as the `customer_feedback_analysis.ipynb` notebook.

- **Frontend** (`docs/index.html`): one static page, hosted on GitHub Pages.
- **Backend** (`backend/app.py`): a Flask API, hosted on Render. The Gemini API key lives only here, as a Render environment variable, so it is never exposed in the browser or in the repo.

```
Browser (GitHub Pages) ──POST /generate──▶ Flask API (Render) ──▶ Gemini
```

## Project structure

```
├── backend/
│   ├── app.py             # API: same prompt as the notebook, sent to Gemini
│   ├── requirements.txt
│   └── .env.example       # template for local runs
├── docs/
│   └── index.html         # the web page (GitHub Pages serves this folder)
├── render.yaml            # Render deployment settings
└── .gitignore
```

## Rules

- Only 1- and 2-star reviews get a reply, matching the notebook's critical-review rule.
- Reviews are capped at 2,000 characters.
- Each visitor is limited to 10 requests per minute and 100 per day, so a public page can't use up your Gemini quota or bill.
- The API only accepts requests from your GitHub Pages address (`ALLOWED_ORIGIN`).

## Deploy

### 1. Push to GitHub
Create a new repository and push this folder to the `main` branch.

### 2. Deploy the backend on Render
1. On [render.com](https://render.com), choose **New → Blueprint** and select your repository. Render reads `render.yaml`.
2. When asked, set the environment variables:
   - `GEMINI_API_KEY`: your Gemini API key from Google AI Studio
   - `ALLOWED_ORIGIN`: your GitHub Pages address, e.g. `https://your-username.github.io` (no trailing slash, no repo name)
3. Deploy. Visiting your Render URL (e.g. `https://review-reply-api.onrender.com`) should show `{"status": "ok"}`.

### 3. Point the frontend at the backend
In `docs/index.html`, set `API_URL` to your Render URL:

```js
const API_URL = "https://review-reply-api.onrender.com";
```

Commit and push.

### 4. Turn on GitHub Pages
In the repository, open **Settings → Pages**. Under **Build and deployment**, choose **Deploy from a branch**, branch `main`, folder `/docs`, then save. After a minute the site is live at `https://your-username.github.io/your-repo/`.

## Run locally

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then add your real key; set ALLOWED_ORIGIN=* for local testing
flask run
```

Set `API_URL` in `docs/index.html` to `http://127.0.0.1:5000` and open the file in a browser.

## Notes

- Render's free plan sleeps after about 15 minutes of inactivity, so the first request after a quiet period can take up to a minute. The page tells the user this while it waits.
- If billing is enabled on your Google AI Studio project, set a budget alert in Google Cloud as an extra safeguard.

# PocketSmart AI

Budget-aware recommendations for home interiors, parties and jewelry. FastAPI + Gemini + Jinja2.

## Run it
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # add GEMINI_API_KEY and JWT_SECRET
python test_gemini.py                                  # Milestone 1: check the API key works
python main.py                                         # open http://127.0.0.1:8000
```
Without a key the app still runs and shows default (fallback) suggestions.

## Layout
| File | Role |
|---|---|
| `main.py` | Routes: pages, auth, `/generate-home|party|jewelry`, `/history`, `/recommendations-details/{id}`, `/session-info`, `/session-data`, `/token` |
| `gemini_utils.py` | Prompts, Gemini calls (text + image), platform links, validation, fallbacks |
| `auth.py`, `db.py` | JWT cookie auth, SQLite users and history |
| `templates/`, `static/` | Jinja2 pages and CSS |

## Notes
- The document names Gemini 1.5 Flash, which Google has retired. Set `GEMINI_MODEL` in `.env` to any current Flash model.
- Item links are live search URLs on each platform, not scraped product pages, so they never go stale.
- Sample testimonials on the home page are placeholders.

"""Prompt orchestration, Gemini calls, platform links and fallbacks for all three planners."""
import json, os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_client = None

# Search-URL templates: we link to live search results on each platform instead of inventing product URLs.
PLATFORMS = {
    "amazon": "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "ikea": "https://www.ikea.com/in/en/search/?q={q}",
    "swiggy": "https://www.swiggy.com/search?query={q}",
    "zomato": "https://www.zomato.com/search?q={q}",
    "oyo": "https://www.oyorooms.com/search?q={q}",
}

SCHEMA = """Return ONLY JSON (no markdown) in this shape:
{"summary": "2 sentence overview",
 "items": [{"category": "string", "name": "specific searchable product/service name",
            "platform": "one of: %s", "estimated_price": integer INR total for the quantity,
            "reason": "one short sentence"}],
 "tips": ["short money-saving tip", "..."]}
Rules: all prices in INR; the sum of estimated_price MUST NOT exceed the budget; keep names generic enough
to be found by a platform search; 6 to 12 items.""" % ", ".join(PLATFORMS)


def _client_():
    global _client
    if _client is None:
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=key)
    return _client


def ask_gemini(prompt: str, image: bytes | None = None, mime: str | None = None) -> dict:
    from google.genai import types
    parts = [prompt]
    if image:
        parts.append(types.Part.from_bytes(data=image, mime_type=mime or "image/jpeg"))
    resp = _client_().models.generate_content(
        model=MODEL, contents=parts,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4))
    return json.loads(resp.text)


def platform_link(platform: str, name: str) -> str:
    key = (platform or "").strip().lower()
    tpl = PLATFORMS.get(key, PLATFORMS["amazon"])
    return tpl.format(q=quote_plus(name))


# ---------- prompts ----------
def home_prompt(f: dict) -> str:
    return f"""You are a home interior budget planner for Indian shoppers.
Total budget: INR {f['budget']}. Style: {f['style']}. Rooms: {', '.join(f['rooms']) or 'unspecified'}.
Quantities needed: lights={f['lights']}, ceiling fans={f['fans']}, dining tables={f['tables']}, beds={f['beds']}, sofas={f['sofas']}.
Recommend cost-effective options per room from IKEA, Amazon and Flipkart, balancing function, style and price.
{SCHEMA}"""


def party_prompt(f: dict) -> str:
    return f"""You are a party budget planner in India.
Event: {f['event_type']}. Guests: {f['guests']}. Total budget: INR {f['budget']}. City/venue details: {f['venue']}.
Split the budget across catering, decoration, entertainment (and venue/stay if needed) in sensible proportions for this event type.
Use Swiggy/Zomato for food, OYO for stay/venue, Amazon/Flipkart for decor and supplies.
{SCHEMA}
Also add "allocation": {{"catering": percent, "decoration": percent, "entertainment": percent, "venue": percent}} to the JSON."""


def jewelry_prompt(f: dict, has_image: bool) -> str:
    img = "An outfit photo is attached: match jewelry to its colours, neckline and formality." if has_image else "No outfit photo was provided."
    return f"""You are a jewelry stylist working to a budget.
Budget: INR {f['budget']}. Occasion: {f['occasion']}. Style preference: {f['style']}. {img}
Recommend matching pieces (necklace, earrings, bangles, rings...) from Amazon and Flipkart.
{SCHEMA}"""


# ---------- fallbacks ----------
FALLBACKS = {
    "home": [("Lighting", "LED ceiling light", "amazon", .15), ("Lighting", "table lamp", "ikea", .07),
             ("Cooling", "BLDC ceiling fan", "flipkart", .18), ("Dining", "4 seater dining table set", "ikea", .30),
             ("Decor", "wall art frames set", "amazon", .10), ("Decor", "cushion covers and rug", "flipkart", .12),
             ("Storage", "shoe rack and shelf", "ikea", .08)],
    "party": [("Catering", "party catering per plate", "zomato", .45), ("Catering", "snack platters", "swiggy", .10),
              ("Decoration", "balloon and backdrop decoration kit", "amazon", .15),
              ("Decoration", "fairy lights and banners", "flipkart", .07),
              ("Entertainment", "party speaker and games", "amazon", .13), ("Venue", "banquet hall or room", "oyo", .10)],
    "jewelry": [("Necklace", "statement necklace set", "amazon", .35), ("Earrings", "earrings to match outfit", "flipkart", .20),
                ("Bangles", "bangles set", "amazon", .20), ("Ring", "cocktail ring", "flipkart", .10),
                ("Accessories", "maang tikka or brooch", "amazon", .10)],
}


def fallback(category: str, budget: int) -> dict:
    items = [{"category": c, "name": n, "platform": p, "estimated_price": int(budget * s),
              "reason": "Default pick while AI suggestions are unavailable."} for c, n, p, s in FALLBACKS[category]]
    return {"summary": "Showing default suggestions scaled to your budget.", "items": items,
            "tips": ["Compare prices across platforms before buying."], "fallback": True}


# ---------- pipeline ----------
def finalize(result: dict, budget: int, category: str) -> dict:
    """Clean AI output: valid items only, links attached, totals and budget flag computed."""
    items = []
    for it in result.get("items", []):
        try:
            price = int(float(it.get("estimated_price", 0)))
        except (TypeError, ValueError):
            continue
        if not it.get("name") or price <= 0:
            continue
        plat = str(it.get("platform", "amazon")).lower()
        plat = plat if plat in PLATFORMS else "amazon"
        items.append({"category": it.get("category", "General"), "name": it["name"], "platform": plat,
                      "estimated_price": price, "reason": it.get("reason", ""),
                      "link": platform_link(plat, it["name"])})
    if not items:
        return finalize(fallback(category, budget), budget, category)
    total = sum(i["estimated_price"] for i in items)
    groups: dict = {}
    for i in items:
        groups[i["category"]] = groups.get(i["category"], 0) + i["estimated_price"]
    return {"summary": result.get("summary", ""), "items": items, "tips": result.get("tips", []),
            "total": total, "budget": budget, "over_budget": total > budget,
            "remaining": budget - total, "groups": groups, "fallback": bool(result.get("fallback"))}


def recommend(category: str, form: dict, image: bytes | None = None, mime: str | None = None) -> dict:
    budget = int(form["budget"])
    try:
        prompt = {"home": lambda: home_prompt(form), "party": lambda: party_prompt(form),
                  "jewelry": lambda: jewelry_prompt(form, bool(image))}[category]()
        raw = ask_gemini(prompt, image, mime)
    except Exception as exc:  # missing key, network, bad JSON...
        print(f"[gemini] falling back: {exc}")
        raw = fallback(category, budget)
    return finalize(raw, budget, category)

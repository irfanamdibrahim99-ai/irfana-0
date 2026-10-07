"""PocketSmart AI - FastAPI backend."""
from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth, db
from gemini_utils import recommend

app = FastAPI(title="PocketSmart AI")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

MAX_IMAGE_BYTES = 5 * 1024 * 1024


@app.on_event("startup")
def startup():
    db.init_db()


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    wants_html = "text/html" in request.headers.get("accept", "")
    if exc.status_code == 401 and wants_html:
        return RedirectResponse("/login", status_code=303)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


def page(request, name, user=None, **ctx):
    return templates.TemplateResponse(request, name, {"user": user, **ctx})


# ---------- public pages ----------
@app.get("/")
async def index(request: Request):
    return page(request, "index.html", auth.optional_user(request))


# ---------- auth ----------
@app.get("/register")
async def register_page(request: Request):
    return page(request, "register.html")


@app.post("/register")
async def register(request: Request, username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    username = username.strip()
    if len(username) < 3 or len(password) < 6 or "@" not in email:
        return page(request, "register.html", error="Use a username of 3+ characters, a valid email and a password of 6+ characters.")
    if not db.create_user(username, email.strip(), password):
        return page(request, "register.html", error="That username is taken. Try another.")
    return RedirectResponse("/login?registered=1", status_code=303)


@app.get("/login")
async def login_page(request: Request, registered: int = 0):
    return page(request, "login.html", registered=bool(registered))


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not db.verify_user(username.strip(), password):
        return page(request, "login.html", error="Wrong username or password.")
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie("access_token", auth.create_token(username.strip()), httponly=True,
                    samesite="lax", max_age=auth.EXPIRE_MINUTES * 60)
    return resp


@app.post("/token")
async def token(username: str = Form(...), password: str = Form(...)):
    """Issue a JWT for API clients (Authorization: Bearer <token>)."""
    if not db.verify_user(username, password):
        raise HTTPException(401, "Incorrect username or password")
    return {"access_token": auth.create_token(username), "token_type": "bearer"}


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("access_token")
    return resp


@app.get("/session-info")
async def session_info(request: Request):
    user = auth.optional_user(request)
    return {"logged_in": bool(user), "user_id": user["id"] if user else None,
            "username": user["username"] if user else None}


@app.get("/session-data")
async def session_data(user: dict = Depends(auth.current_user)):
    hist = db.list_history(user["id"])
    counts = {}
    for h in hist:
        counts[h["category"]] = counts.get(h["category"], 0) + 1
    return {"user": user, "total_queries": len(hist), "by_category": counts,
            "last_category": hist[0]["category"] if hist else None}


# ---------- dashboard / history ----------
@app.get("/dashboard")
async def dashboard(request: Request, user: dict = Depends(auth.current_user)):
    return page(request, "dashboard.html", user, history=db.list_history(user["id"], 5))


@app.get("/history")
async def history(request: Request, user: dict = Depends(auth.current_user)):
    return page(request, "history.html", user, history=db.list_history(user["id"]))


@app.get("/recommendations-details/{item_id}")
async def recommendation_details(request: Request, item_id: int, format: str = "html",
                                 user: dict = Depends(auth.current_user)):
    item = db.get_history_item(user["id"], item_id)
    if not item:
        raise HTTPException(404, "Recommendation not found")
    if format == "json":
        return item
    return page(request, "results.html", user, category=item["category"], result=item["result"], inputs=item["inputs"])


# ---------- planners ----------
@app.get("/home-planner")
async def home_planner(request: Request, user: dict = Depends(auth.current_user)):
    return page(request, "home_planner.html", user)


@app.get("/party-planner")
async def party_planner(request: Request, user: dict = Depends(auth.current_user)):
    return page(request, "party_planner.html", user)


@app.get("/jewelry-planner")
async def jewelry_planner(request: Request, user: dict = Depends(auth.current_user)):
    return page(request, "jewelry_planner.html", user)


def _budget_error(request, template, user, budget, minimum):
    if budget < minimum:
        return page(request, template, user, error=f"Enter a budget of at least Rs {minimum:,}.")


@app.post("/generate-home")
async def generate_home(request: Request, user: dict = Depends(auth.current_user),
                        budget: int = Form(...), style: str = Form("Modern"),
                        rooms: list[str] = Form(default=[]), lights: int = Form(0), fans: int = Form(0),
                        tables: int = Form(0), beds: int = Form(0), sofas: int = Form(0)):
    if err := _budget_error(request, "home_planner.html", user, budget, 5000):
        return err
    if not rooms:
        return page(request, "home_planner.html", user, error="Pick at least one room.")
    form = dict(budget=budget, style=style, rooms=rooms, lights=max(lights, 0), fans=max(fans, 0),
                tables=max(tables, 0), beds=max(beds, 0), sofas=max(sofas, 0))
    result = recommend("home", form)
    db.save_history(user["id"], "home", form, result)
    return page(request, "results.html", user, category="home", result=result, inputs=form)


@app.post("/generate-party")
async def generate_party(request: Request, user: dict = Depends(auth.current_user),
                         budget: int = Form(...), guests: int = Form(...), event_type: str = Form(...),
                         venue: str = Form("")):
    if err := _budget_error(request, "party_planner.html", user, budget, 5000):
        return err
    if not 1 <= guests <= 2000:
        return page(request, "party_planner.html", user, error="Guest count must be between 1 and 2000.")
    form = dict(budget=budget, guests=guests, event_type=event_type, venue=venue.strip() or "Not specified")
    result = recommend("party", form)
    db.save_history(user["id"], "party", form, result)
    return page(request, "results.html", user, category="party", result=result, inputs=form)


@app.post("/generate-jewelry")
async def generate_jewelry(request: Request, user: dict = Depends(auth.current_user),
                           budget: int = Form(...), occasion: str = Form(...), style: str = Form("Elegant"),
                           outfit: UploadFile | None = File(None)):
    if err := _budget_error(request, "jewelry_planner.html", user, budget, 500):
        return err
    image = mime = None
    if outfit and outfit.filename:
        if outfit.content_type not in ("image/jpeg", "image/png", "image/webp"):
            return page(request, "jewelry_planner.html", user, error="Upload a JPG, PNG or WebP image.")
        image = await outfit.read()
        if len(image) > MAX_IMAGE_BYTES:
            return page(request, "jewelry_planner.html", user, error="Image is larger than 5 MB.")
        mime = outfit.content_type
    form = dict(budget=budget, occasion=occasion, style=style, image_used=bool(image))
    result = recommend("jewelry", form, image, mime)
    db.save_history(user["id"], "jewelry", form, result)
    return page(request, "results.html", user, category="jewelry", result=result, inputs=form)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

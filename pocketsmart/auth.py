"""JWT auth helpers. The token lives in an httponly cookie so HTML pages and API calls share one session."""
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request

import db

SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGO = "HS256"
EXPIRE_MINUTES = 60 * 8


def create_token(username: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "exp": exp}, SECRET, algorithm=ALGO)


def current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() or None
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        username = jwt.decode(token, SECRET, algorithms=[ALGO])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired")
    user = db.get_user(username)
    if not user:
        raise HTTPException(401, "Unknown user")
    return user


def optional_user(request: Request):
    try:
        return current_user(request)
    except HTTPException:
        return None

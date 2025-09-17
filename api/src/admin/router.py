import os
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.hash import bcrypt
from starlette.templating import Jinja2Templates


router = APIRouter(prefix="/admin", tags=["admin"])


templates = Jinja2Templates(directory=os.getenv("ADMIN_TEMPLATES_DIR", "/app/src/admin/templates"))


def _is_logged_in(request: Request) -> bool:
    return bool(request.session.get("admin_auth"))


def require_admin(request: Request) -> None:
    if not _is_logged_in(request):
        raise RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if _is_logged_in(request):
        return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)) -> Response:
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    if username != expected_user or not expected_hash or not bcrypt.verify(password, expected_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"}, status_code=status.HTTP_401_UNAUTHORIZED)
    request.session["admin_auth"] = True
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)


@router.post("/logout")
async def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)


@router.get("", response_class=HTMLResponse)
async def admin_home(request: Request) -> HTMLResponse:
    require_admin(request)
    # Minimal placeholder dashboard
    ctx = {"request": request}
    return templates.TemplateResponse("dashboard.html", ctx)



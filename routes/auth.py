from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import User
from services.auth import verify_password, create_access_token
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.cookies.get("session_token"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login")
def login(request: Request, response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password."})
    
    token = create_access_token(data={"sub": str(user.id)})
    
    # Redirect response
    redirect = RedirectResponse(url="/dashboard", status_code=303)
    redirect.set_cookie(
        key="session_token", 
        value=token, 
        httponly=True, 
        max_age=7*24*3600, 
        samesite="lax",
        secure=request.url.scheme == "https"
    )
    return redirect

@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response

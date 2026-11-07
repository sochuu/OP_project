from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import (
    SESSION_COOKIE,
    SECRET,
    check_lock,
    client_ip,
    register_fail,
    register_ok,
    valid_code_hash,
)
from app.database import Base, engine, get_db, migrate_schema
from app.ml.forecast import forecast_year
from app.models import Earning, Settings
from app.tax import NPD_BONUS_MAX, bonus_spent, calc_tax, remaining_npd_bonus

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Прогноз налогов для фрилансера (РФ)")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))
signer = URLSafeSerializer(SECRET, salt="login")

migrate_schema()
Base.metadata.create_all(bind=engine)

PUBLIC_PATHS = {"/login", "/logout"}


def owner_from_request(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = signer.loads(token)
    except BadSignature:
        return None
    uid = data.get("uid")
    if isinstance(uid, str) and len(uid) == 64:
        return uid
    return None


class AuthGate(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/static") or path in PUBLIC_PATHS:
            return await call_next(request)
        if not owner_from_request(request):
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)


app.add_middleware(AuthGate)


def current_owner(request: Request) -> str:
    uid = owner_from_request(request)
    if not uid:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return uid


def get_settings(db: Session, owner: str) -> Settings:
    s = db.query(Settings).filter(Settings.owner_hash == owner).one_or_none()
    if s is None:
        s = Settings(owner_hash=owner)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@app.get("/login")
def login_form(request: Request, error: str | None = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
def login(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    ip = client_ip(request)
    locked = check_lock(db, ip)
    if locked:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": f"Слишком много попыток. Повторите после {locked.strftime('%H:%M')} UTC.",
            },
            status_code=429,
        )
    digest = valid_code_hash(code)
    if not digest:
        until = register_fail(db, ip)
        msg = "Неверный код."
        if until:
            msg = f"Неверный код. IP заблокирован до {until.strftime('%H:%M')} UTC."
        return templates.TemplateResponse("login.html", {"request": request, "error": msg}, status_code=401)
    register_ok(db, ip)
    get_settings(db, digest)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE,
        signer.dumps({"ok": True, "uid": digest}),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 14,
    )
    return resp


@app.get("/logout")
@app.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db),
    owner: str = Depends(current_owner),
    sort: str = "date_desc",
    q: str = "",
):
    s = get_settings(db, owner)
    all_earnings = (
        db.query(Earning)
        .filter(Earning.owner_hash == owner)
        .order_by(Earning.earned_on.asc(), Earning.id.asc())
        .all()
    )
    query = (q or "").strip()
    listed = list(all_earnings)
    if query:
        needle = query.casefold()
        listed = [e for e in listed if needle in (e.note or "").casefold()]
    keys = {
        "date_asc": lambda e: (e.earned_on, e.id),
        "date_desc": lambda e: (e.earned_on, e.id),
        "amount_asc": lambda e: (e.amount, e.earned_on, e.id),
        "amount_desc": lambda e: (e.amount, e.earned_on, e.id),
        "payer_fl": lambda e: (0 if e.payer_type == "fl" else 1, e.earned_on, e.id),
        "payer_org": lambda e: (0 if e.payer_type == "org" else 1, e.earned_on, e.id),
    }
    if sort not in keys:
        sort = "date_desc"
    reverse = sort in {"date_desc", "amount_desc"}
    earnings = sorted(listed, key=keys[sort], reverse=reverse)
    fc = forecast_year(all_earnings, s.financial_year)
    tax = calc_tax(s.tax_regime, fc["total_fl"], fc["total_org"], s)
    bonus_now = remaining_npd_bonus(s.npd_bonus_left, all_earnings)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "settings": s,
            "earnings": earnings,
            "forecast": fc,
            "tax": tax,
            "today": date.today().isoformat(),
            "bonus_max": NPD_BONUS_MAX,
            "bonus_start": s.npd_bonus_left,
            "bonus_now": bonus_now,
            "bonus_used": bonus_spent(s.npd_bonus_left, all_earnings),
            "sort": sort,
            "q": query,
        },
    )


@app.post("/earnings")
def add_earning(
    earned_on: date = Form(...),
    amount: float = Form(...),
    payer_type: str = Form("fl"),
    note: str = Form(""),
    db: Session = Depends(get_db),
    owner: str = Depends(current_owner),
):
    db.add(
        Earning(
            owner_hash=owner,
            earned_on=earned_on,
            amount=amount,
            payer_type=payer_type,
            note=note,
        )
    )
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/earnings/{eid}/delete")
def delete_earning(
    eid: int,
    db: Session = Depends(get_db),
    owner: str = Depends(current_owner),
):
    row = db.get(Earning, eid)
    if row and row.owner_hash == owner:
        db.delete(row)
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/settings")
def save_settings(
    tax_regime: str = Form(...),
    usn_rate: float = Form(6.0),
    ndfl_rate: float = Form(13.0),
    npd_bonus_left: float = Form(10000.0),
    financial_year: int = Form(datetime.utcnow().year),
    db: Session = Depends(get_db),
    owner: str = Depends(current_owner),
):
    s = get_settings(db, owner)
    s.tax_regime = tax_regime
    s.usn_rate = usn_rate
    s.ndfl_rate = ndfl_rate
    s.npd_bonus_left = max(0.0, min(float(npd_bonus_left), NPD_BONUS_MAX))
    s.financial_year = financial_year
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/bonus")
def save_bonus(
    npd_bonus_left: float = Form(0.0),
    db: Session = Depends(get_db),
    owner: str = Depends(current_owner),
):
    s = get_settings(db, owner)
    s.npd_bonus_left = max(0.0, min(float(npd_bonus_left), NPD_BONUS_MAX))
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/api/forecast")
def api_forecast(db: Session = Depends(get_db), owner: str = Depends(current_owner)):
    s = get_settings(db, owner)
    rows = db.query(Earning).filter(Earning.owner_hash == owner).all()
    fc = forecast_year(rows, s.financial_year)
    tax = calc_tax(s.tax_regime, fc["total_fl"], fc["total_org"], s)
    return {"forecast": fc, "tax": tax.__dict__}

from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
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
    code_is_valid,
    register_fail,
    register_ok,
)
from app.database import Base, engine, get_db
from app.ml.forecast import forecast_year
from app.models import Earning, Settings
from app.tax import NPD_BONUS_MAX, bonus_spent, calc_tax, remaining_npd_bonus

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Прогноз налогов для фрилансера (РФ)")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))
signer = URLSafeSerializer(SECRET, salt="login")

Base.metadata.create_all(bind=engine)

PUBLIC_PATHS = {"/login", "/logout"}


class AuthGate(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/static") or path in PUBLIC_PATHS:
            return await call_next(request)
        token = request.cookies.get(SESSION_COOKIE)
        ok = False
        if token:
            try:
                data = signer.loads(token)
                ok = bool(data.get("ok"))
            except BadSignature:
                ok = False
        if not ok:
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)


app.add_middleware(AuthGate)


def get_settings(db: Session) -> Settings:
    s = db.get(Settings, 1)
    if s is None:
        s = Settings(id=1)
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
    if not code_is_valid(code):
        until = register_fail(db, ip)
        msg = "Неверный код."
        if until:
            msg = f"Неверный код. IP заблокирован до {until.strftime('%H:%M')} UTC."
        return templates.TemplateResponse("login.html", {"request": request, "error": msg}, status_code=401)
    register_ok(db, ip)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE,
        signer.dumps({"ok": True}),
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
def index(request: Request, db: Session = Depends(get_db)):
    s = get_settings(db)
    all_earnings = db.query(Earning).order_by(Earning.earned_on.asc(), Earning.id.asc()).all()
    earnings = list(reversed(all_earnings))
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
        },
    )


@app.post("/earnings")
def add_earning(
    earned_on: date = Form(...),
    amount: float = Form(...),
    payer_type: str = Form("fl"),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(Earning(earned_on=earned_on, amount=amount, payer_type=payer_type, note=note))
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/earnings/{eid}/delete")
def delete_earning(eid: int, db: Session = Depends(get_db)):
    row = db.get(Earning, eid)
    if row:
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
):
    s = get_settings(db)
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
):
    s = get_settings(db)
    s.npd_bonus_left = max(0.0, min(float(npd_bonus_left), NPD_BONUS_MAX))
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/api/forecast")
def api_forecast(db: Session = Depends(get_db)):
    s = get_settings(db)
    fc = forecast_year(db.query(Earning).all(), s.financial_year)
    tax = calc_tax(s.tax_regime, fc["total_fl"], fc["total_org"], s)
    return {"forecast": fc, "tax": tax.__dict__}

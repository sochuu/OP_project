from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.ml.forecast import forecast_year
from app.models import Earning, Settings
from app.tax import calc_tax

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Прогноз налогов для фрилансера (РФ)")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))

Base.metadata.create_all(bind=engine)


def get_settings(db: Session) -> Settings:
    s = db.get(Settings, 1)
    if s is None:
        s = Settings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    s = get_settings(db)
    earnings = db.query(Earning).order_by(Earning.earned_on.desc()).all()
    fc = forecast_year(db.query(Earning).all(), s.financial_year)
    tax = calc_tax(s.tax_regime, fc["total_fl"], fc["total_org"], s)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "settings": s,
            "earnings": earnings,
            "forecast": fc,
            "tax": tax,
            "today": date.today().isoformat(),
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
    s.npd_bonus_left = npd_bonus_left
    s.financial_year = financial_year
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/api/forecast")
def api_forecast(db: Session = Depends(get_db)):
    s = get_settings(db)
    fc = forecast_year(db.query(Earning).all(), s.financial_year)
    tax = calc_tax(s.tax_regime, fc["total_fl"], fc["total_org"], s)
    return {"forecast": fc, "tax": tax.__dict__}

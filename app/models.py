from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Earning(Base):
    __tablename__ = "earnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    earned_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    # fl — физлицо; org — ИП/юрлицо
    payer_type: Mapped[str] = mapped_column(String(8), nullable=False, default="fl")
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tax_regime: Mapped[str] = mapped_column(String(16), default="npd")
    usn_rate: Mapped[float] = mapped_column(Float, default=6.0)
    ndfl_rate: Mapped[float] = mapped_column(Float, default=13.0)
    npd_bonus_left: Mapped[float] = mapped_column(Float, default=10000.0)
    financial_year: Mapped[int] = mapped_column(Integer, default=datetime.utcnow().year)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    ip: Mapped[str] = mapped_column(String(64), primary_key=True)
    fails: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_fail: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

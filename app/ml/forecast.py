"""Прогноз месячного дохода.

"""

from __future__ import annotations

import os
from calendar import monthrange
from collections import defaultdict
from datetime import date

import numpy as np

BACKEND = os.environ.get("FORECAST_BACKEND", "numpy").lower()


def _features(month_start: date) -> np.ndarray:
    t = month_start.year * 12 + month_start.month
    m = month_start.month
    return np.array(
        [
            1.0,
            float(t),
            np.sin(2 * np.pi * m / 12.0),
            np.cos(2 * np.pi * m / 12.0),
            1.0 if m in (11, 12, 1) else 0.0,
            1.0 if m in (6, 7, 8) else 0.0,
        ],
        dtype=float,
    )


def fit_predict_numpy(X: np.ndarray, y: np.ndarray, X_new: np.ndarray) -> np.ndarray:
    if len(y) < 2:
        return np.full(len(X_new), float(y[0]) if len(y) else 0.0)
    xtx = X.T @ X
    try:
        w = np.linalg.pinv(xtx) @ X.T @ y
    except np.linalg.LinAlgError:
        return np.full(len(X_new), float(np.mean(y)))
    return np.maximum(X_new @ w, 0.0)


def fit_predict_sklearn(X: np.ndarray, y: np.ndarray, X_new: np.ndarray) -> np.ndarray:
    from sklearn.ensemble import RandomForestRegressor

    model = RandomForestRegressor(n_estimators=80, max_depth=4, random_state=42)
    model.fit(X, y)
    return np.maximum(model.predict(X_new), 0.0)


def _monthly_buckets(earnings: list) -> dict:
    buckets: dict[date, dict] = defaultdict(lambda: {"amount": 0.0, "fl": 0.0, "org": 0.0})
    for e in earnings:
        key = date(e.earned_on.year, e.earned_on.month, 1)
        buckets[key]["amount"] += e.amount
        if e.payer_type == "fl":
            buckets[key]["fl"] += e.amount
        else:
            buckets[key]["org"] += e.amount
    return dict(buckets)


def forecast_year(earnings: list, year: int, today: date | None = None) -> dict:
    today = today or date.today()
    hist = _monthly_buckets(earnings)
    months = [date(year, m, 1) for m in range(1, 13)]

    train_months = sorted(hist.keys())
    train_X = np.array([_features(m) for m in train_months], dtype=float) if train_months else np.zeros((0, 6))
    train_y = np.array([hist[m]["amount"] for m in train_months], dtype=float)

    mean_all = float(np.mean(train_y)) if len(train_y) else 0.0
    by_month: dict[int, list] = defaultdict(list)
    for m, val in zip(train_months, train_y):
        by_month[m.month].append(float(val))
    seasonal = {k: float(np.mean(v)) for k, v in by_month.items()}

    total_amt = float(sum(v["amount"] for v in hist.values())) or 1.0
    fl_share = float(sum(v["fl"] for v in hist.values()) / total_amt) if hist else 0.5

    future = [
        ms
        for ms in months
        if date(ms.year, ms.month, monthrange(ms.year, ms.month)[1]) >= date(today.year, today.month, 1)
        and ms not in hist
    ]
    X_new = np.array([_features(m) for m in future], dtype=float) if future else np.zeros((0, 6))

    preds = None
    method = "seasonal_mean"
    if len(train_y) >= 4 and len(X_new):
        if BACKEND == "sklearn":
            try:
                preds = fit_predict_sklearn(train_X, train_y, X_new)
                method = "sklearn_rf"
            except ImportError:
                preds = fit_predict_numpy(train_X, train_y, X_new)
                method = "numpy_ols_fallback"
        else:
            preds = fit_predict_numpy(train_X, train_y, X_new)
            method = "numpy_ols"
    pred_map = {m: float(p) for m, p in zip(future, preds)} if preds is not None else {}

    monthly = []
    actual_total = actual_fl = actual_org = 0.0
    for ms in months:
        last_day = monthrange(ms.year, ms.month)[1]
        month_end = date(ms.year, ms.month, last_day)
        if ms in hist:
            amt, fl, org = hist[ms]["amount"], hist[ms]["fl"], hist[ms]["org"]
            kind = "fact"
        elif month_end < date(today.year, today.month, 1):
            amt = fl = org = 0.0
            kind = "empty"
        else:
            amt = pred_map.get(ms, seasonal.get(ms.month, mean_all))
            fl, org = amt * fl_share, amt * (1 - fl_share)
            kind = "forecast"
        actual_total += amt
        actual_fl += fl
        actual_org += org
        monthly.append(
            {
                "month": ms.isoformat(),
                "label": ms.strftime("%Y-%m"),
                "amount": round(amt, 2),
                "fl": round(fl, 2),
                "org": round(org, 2),
                "kind": kind,
            }
        )

    return {
        "year": year,
        "method": method,
        "backend": BACKEND,
        "monthly": monthly,
        "total": round(actual_total, 2),
        "total_fl": round(actual_fl, 2),
        "total_org": round(actual_org, 2),
        "points_used": int(len(train_y)),
    }

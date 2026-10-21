"""
Pure forecasting maths (NumPy + scikit-learn). No Django imports, so it can be
unit-tested on its own. The database layer lives in forecasting_utils.py.
"""
import numpy as np
from sklearn.linear_model import LinearRegression

MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

MIN_DATA_POINTS = 3          # months of sales needed before we trust a model
TREND_SLOPE_THRESHOLD = 0.75  # units / month


def shift_month(year, month, offset):
    """Return (year, month) moved by `offset` months."""
    index = year * 12 + (month - 1) + offset
    return index // 12, index % 12 + 1


def month_label(year, month):
    return f"{MONTH_NAMES[month - 1]} {year}"


def trim_leading_zeros(values):
    """Drop months before the first sale so a product's launch date doesn't distort the trend."""
    for i, v in enumerate(values):
        if v > 0:
            return list(values[i:])
    return []


def fit_linear_regression(values):
    """OLS fit of y = slope * x + intercept with x = 0..n-1. Returns slope, intercept, r2."""
    n = len(values)
    X = np.arange(n).reshape(-1, 1)
    y = np.array(values, dtype=float)
    model = LinearRegression().fit(X, y)
    # R-squared is undefined for a perfectly flat series; treat it as a perfect fit.
    r2 = 1.0 if np.ptp(y) == 0 else float(model.score(X, y))
    return float(model.coef_[0]), float(model.intercept_), max(0.0, min(1.0, r2))


def moving_average_forecast(values, horizon=3, window=3):
    """Recursive rolling mean: each prediction is fed back into the window."""
    series = [float(v) for v in values]
    out = []
    for _ in range(horizon):
        chunk = series[-window:]
        pred = max(0, int(round(sum(chunk) / len(chunk))))
        out.append(pred)
        series.append(pred)
    return out


def classify_trend(slope):
    if slope >= TREND_SLOPE_THRESHOLD:
        return 'UPWARD'
    if slope <= -TREND_SLOPE_THRESHOLD:
        return 'DOWNWARD'
    return 'STABLE'


def classify_priority(blended_demand, trend):
    if blended_demand >= 15 or (trend == 'UPWARD' and blended_demand >= 8):
        return 'HIGH_DEMAND'
    if blended_demand >= 5:
        return 'MODERATE_DEMAND'
    return 'LOW_DEMAND'


def forecast_series(history, horizon=3, window=3):
    """
    Forecast the next `horizon` months from a list of monthly unit sales.

    Returns a dict. When there are fewer than MIN_DATA_POINTS months of sales
    the status is 'INSUFFICIENT_DATA' and no forecast numbers are produced.
    """
    series = trim_leading_zeros(history)
    result = {
        'data_points': len(series),
        'status': 'OK',
        'lr_forecast': [],
        'ma_forecast': [],
        'slope': 0.0,
        'intercept': 0.0,
        'r_squared': 0.0,
        'trend': 'STABLE',
        'next_month_lr': 0,
        'next_month_ma': 0,
        'blended_next_month': 0,
        'priority': 'LOW_DEMAND',
    }
    if len(series) < MIN_DATA_POINTS:
        result['status'] = 'INSUFFICIENT_DATA'
        return result

    slope, intercept, r2 = fit_linear_regression(series)
    n = len(series)
    lr = [max(0, int(round(slope * (n + i) + intercept))) for i in range(horizon)]
    ma = moving_average_forecast(series, horizon=horizon, window=window)
    blended = int(round((lr[0] + ma[0]) / 2))
    trend = classify_trend(slope)

    result.update({
        'lr_forecast': lr,
        'ma_forecast': ma,
        'slope': round(slope, 2),
        'intercept': round(intercept, 2),
        'r_squared': round(r2, 3),
        'trend': trend,
        'next_month_lr': lr[0],
        'next_month_ma': ma[0],
        'blended_next_month': blended,
        'priority': classify_priority(blended, trend),
    })
    return result


def recommended_restock(blended_next_month, current_stock, on_order, safety_buffer):
    """Units to order so next month's demand plus a safety buffer is covered."""
    return max(0, blended_next_month + safety_buffer - (current_stock + on_order))

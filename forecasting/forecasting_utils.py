import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np
from inventory.models import StockMovement


def get_daily_stock_out(product_id, days=30):
    """
    Pulls StockMovement records for a product and aggregates
    OUT quantities by day, returning a pandas DataFrame.
    """
    movements = StockMovement.objects.filter(
        product_id=product_id,
        movement_type='OUT'
    ).order_by('timestamp')

    if not movements.exists():
        return pd.DataFrame(columns=['date', 'quantity'])

    data = [{'date': m.timestamp.date(), 'quantity': m.quantity} for m in movements]
    df = pd.DataFrame(data)
    daily = df.groupby('date')['quantity'].sum().reset_index()
    return daily


def moving_average_forecast(product_id, window=7, forecast_days=7):
    """
    Simple moving average forecast based on recent stock-out history.
    """
    df = get_daily_stock_out(product_id)
    if len(df) < window:
        return {'error': 'Not enough data for a moving average forecast'}

    avg = df['quantity'].tail(window).mean()
    forecast = [round(avg, 2)] * forecast_days
    return {'method': 'Moving Average', 'forecast': forecast, 'daily_avg': round(avg, 2)}


def linear_regression_forecast(product_id, forecast_days=7):
    df = get_daily_stock_out(product_id)
    if len(df) < 3:
        return {'error': 'Not enough data for a linear regression forecast'}

    df['day_number'] = (df['date'] - df['date'].min()).apply(lambda x: x.days)
    X = df[['day_number']]
    y = df['quantity']

    model = LinearRegression()
    model.fit(X, y)

    last_day = df['day_number'].max()
    future_days = np.array([[last_day + i] for i in range(1, forecast_days + 1)])
    predictions = model.predict(future_days)
    predictions = [float(max(0, round(p, 2))) for p in predictions]  # cast to plain float

    return {
        'method': 'Linear Regression',
        'forecast': predictions,
        'slope': float(round(model.coef_[0], 4)),
        'intercept': float(round(model.intercept_, 4)),
    }

def moving_average_forecast(product_id, window=7, forecast_days=7):
    df = get_daily_stock_out(product_id)
    if len(df) < window:
        return {'error': 'Not enough data for a moving average forecast'}

    avg = float(round(df['quantity'].tail(window).mean(), 2))  # cast to plain float
    forecast = [avg] * forecast_days
    return {'method': 'Moving Average', 'forecast': forecast, 'daily_avg': avg}
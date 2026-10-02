from flask import Flask, render_template_string
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.express as px

app = Flask(__name__)

# 網頁的前端 HTML 模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>Modern Portfolio Theory</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; color: #333; }
        h1, h2 { color: #2c3e50; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 30px; font-size: 14px; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: right; }
        th { background-color: #f8f9fa; color: #333; }
        .container { background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
    <div class="container">
        <h1>Modern Portfolio Theory - 資產分析與相關性</h1>
        <p>分析資產：VOO, BRK-B, JPM, NVDA, GLD (資料期間: 2018-01-01 至 2024-01-01)</p>
        
        <h2>1. 報酬與風險分析 (Return and Risk)</h2>
        {{ stats_table | safe }}
        
        <h2>2. 相關係數熱力圖 (Correlation Heatmap)</h2>
        <div>{{ heatmap_div | safe }}</div>
        
        <h2>3. 相關係數矩陣 (Correlation Matrix)</h2>
        {{ corr_table | safe }}
        
        <h2>4. 共變異數矩陣 (Covariance Matrix)</h2>
        {{ cov_table | safe }}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    # 1. 抓取資料
    tickers = ['VOO', 'BRK-B', 'JPM', 'NVDA', 'GLD']
    data = yf.download(tickers, start="2018-01-01", end="2024-01-01")['Adj Close']
    data = data.ffill().dropna()

    # 2. 計算每日報酬率
    daily_returns = data.pct_change().dropna()
    trading_days = 252

    # 3. 計算各項 MPT 指標
    avg_daily_return = daily_returns.mean()
    annualized_return = (1 + avg_daily_return) ** trading_days - 1
    std_dev = daily_returns.std()
    annualized_volatility = std_dev * np.sqrt(trading_days)

    stats_df = pd.DataFrame({
        'Average Daily Return': avg_daily_return,
        'Annualized Return': annualized_return,
        'Daily Standard Deviation': std_dev,
        'Annualized Volatility': annualized_volatility
    }).round(4)

    corr_matrix = daily_returns.corr().round(4)
    cov_matrix = daily_returns.cov().round(6)

    # 4. 使用 Plotly 繪製相關係數熱力圖，並轉成 HTML
    fig = px.imshow(
        corr_matrix, 
        text_auto=True, 
        aspect="auto", 
        color_continuous_scale='RdBu_r', 
        zmin=-1, zmax=1
    )
    fig.update_layout(margin=dict(l=20, r=20, t=20, b=20))
    heatmap_div = fig.to_html(full_html=False, include_plotlyjs='cdn')

    # 5. 將 Pandas DataFrame 轉換為 HTML 表格
    stats_table = stats_df.to_html(classes='table')
    corr_table = corr_matrix.to_html(classes='table')
    cov_table = cov_matrix.to_html(classes='table')

    # 6. 渲染網頁
    return render_template_string(
        HTML_TEMPLATE,
        stats_table=stats_table,
        corr_table=corr_table,
        cov_table=cov_table,
        heatmap_div=heatmap_div
    )

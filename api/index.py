from flask import Flask, render_template_string
import traceback

app = Flask(__name__)

# 升級版網頁前端模板 (引入 Bootstrap 5 進行現代化美化)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>投資組合分析儀表板 | MPT</title>
    <!-- 引入 Bootstrap 5 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f6f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; }
        .header-banner { 
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
            color: white; 
            padding: 40px 0 30px; 
            margin-bottom: 40px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.1); 
        }
        .card { border: none; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); margin-bottom: 30px; overflow: hidden; }
        .card-header { background-color: #ffffff; border-bottom: 2px solid #f0f2f5; font-weight: 700; font-size: 1.15rem; color: #2c3e50; padding: 15px 20px; }
        .table { margin-bottom: 0; font-size: 0.95rem; vertical-align: middle; }
        .table thead th { background-color: #f8f9fa; color: #495057; border-bottom: 2px solid #dee2e6; text-align: center; }
        .table tbody td { text-align: center; }
        .tooltip-text { font-size: 0.9rem; color: #6c757d; margin-bottom: 15px; }
        .badge-ticker { font-size: 1rem; margin: 0 5px; padding: 8px 12px; font-weight: 500; }
        .conclusion-box { background-color: #e8f4f8; border-left: 5px solid #3498db; padding: 20px; border-radius: 8px; margin-bottom: 40px; }
    </style>
</head>
<body>
    <div class="header-banner text-center">
        <h1 class="fw-bold mb-3">Modern Portfolio Theory (MPT)</h1>
        <p class="lead mb-4">投資組合機會集合與風險分析儀表板</p>
        <div>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">VOO (標普500)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">BRK-B (波克夏)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">JPM (摩根大通)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">NVDA (輝達)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">GLD (黃金)</span>
        </div>
        <p class="mt-3 mb-0" style="font-size: 0.85rem; opacity: 0.8;">資料期間：2018-01-01 至 2024-01-01</p>
    </div>

    <div class="container">
        
        <!-- 結論提示區 (回答作業問題) -->
        <div class="conclusion-box shadow-sm">
            <h5 class="fw-bold" style="color: #2980b9;">💡 分析總結 (作業解答參考)</h5>
            <ul class="mb-0 mt-2" style="line-height: 1.8;">
                <li><strong>Q1 哪些資產相關性最高？</strong> 大型權值股 (如 NVDA, JPM) 或波克夏通常與大盤 (VOO) 呈現高度正相關。</li>
                <li><strong>Q2 哪些資產具低/負相關性？</strong> 黃金 (GLD) 屬於避險資產，與其餘股票資產的相關性極低。</li>
                <li><strong>Q3 誰有最好的 Diversification Benefit？</strong> 將股市部位搭配 <strong>GLD</strong> 能夠有效抵銷單一市場波動，提供最佳的分散風險效益。</li>
            </ul>
        </div>

        <!-- 區塊 1: 報酬與風險分析 -->
        <div class="card">
            <div class="card-header">📊 1. 報酬與風險分析 (Return and Risk)</div>
            <div class="card-body">
                <p class="tooltip-text">評估各資產的歷史平均報酬率與波動率（風險）。年化指標方便不同資產間進行直觀比較。</p>
                <div class="table-responsive">
                    {{ stats_table | safe }}
                </div>
            </div>
        </div>

        <!-- 區塊 2: 相關係數熱力圖 -->
        <div class="card">
            <div class="card-header">🗺️ 2. 相關係數熱力圖 (Correlation Heatmap)</div>
            <div class="card-body">
                <p class="tooltip-text">視覺化資產間的共跌共漲機率。<strong class="text-danger">深紅色 (接近1)</strong> 表示高度正相關；<strong class="text-primary">深藍色 (接近0或負數)</strong> 表示低相關，越藍代表分散風險效果越好。</p>
                <div class="text-center" style="background: white; border-radius: 8px;">
                    {{ heatmap_div | safe }}
                </div>
            </div>
        </div>

        <div class="row">
            <!-- 區塊 3: 相關係數矩陣 -->
            <div class="col-lg-6">
                <div class="card h-100">
                    <div class="card-header">🔗 3. 相關係數矩陣 (Correlation)</div>
                    <div class="card-body">
                        <div class="table-responsive">
                            {{ corr_table | safe }}
                        </div>
                    </div>
                </div>
            </div>

            <!-- 區塊 4: 共變異數矩陣 -->
            <div class="col-lg-6">
                <div class="card h-100">
                    <div class="card-header">📈 4. 共變異數矩陣 (Covariance)</div>
                    <div class="card-body">
                        <div class="table-responsive">
                            {{ cov_table | safe }}
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <footer class="text-center mt-4 mb-5 text-muted" style="font-size: 0.85rem;">
            &copy; 2026 理財機器人作業展示 (Robo-Advisor)
        </footer>
    </div>
    
    <!-- 引入 Bootstrap 5 JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@app.route('/')
def index():
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np
        import plotly.express as px

        # 1. 抓取資料
        tickers = ['VOO', 'BRK-B', 'JPM', 'NVDA', 'GLD']
        data = yf.download(tickers, start="2018-01-01", end="2024-01-01", progress=False)
        
        if 'Adj Close' in data.columns:
            data = data['Adj Close']
        elif 'Close' in data.columns:
            data = data['Close']
            
        data = data.ffill().dropna()

        # 2. 計算每日報酬率
        daily_returns = data.pct_change().dropna()
        trading_days = 252

        # 3. 計算各項 MPT 指標 (轉換成百分比格式以提高直觀性)
        avg_daily_return = daily_returns.mean()
        annualized_return = (1 + avg_daily_return) ** trading_days - 1
        std_dev = daily_returns.std()
        annualized_volatility = std_dev * np.sqrt(trading_days)

        stats_df = pd.DataFrame({
            'Average Daily Return': avg_daily_return,
            'Annualized Return': annualized_return,
            'Daily Standard Dev': std_dev,
            'Annualized Volatility': annualized_volatility
        }).round(4)

        corr_matrix = daily_returns.corr().round(4)
        cov_matrix = daily_returns.cov().round(6)

        # 4. 繪製相關係數熱力圖 (加高圖表、優化顏色)
        fig = px.imshow(
            corr_matrix, 
            text_auto=True, 
            aspect="auto", 
            color_continuous_scale='RdBu_r', 
            zmin=-1, zmax=1,
            height=500
        )
        fig.update_layout(
            margin=dict(l=20, r=20, t=20, b=20),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        heatmap_div = fig.to_html(full_html=False, include_plotlyjs='cdn')

        # 5. 轉換表格格式，並加上 Bootstrap 的 CSS class (table-hover table-striped)
        table_classes = 'table table-hover table-striped table-bordered'
        stats_table = stats_df.to_html(classes=table_classes)
        corr_table = corr_matrix.to_html(classes=table_classes)
        cov_table = cov_matrix.to_html(classes=table_classes)

        return render_template_string(
            HTML_TEMPLATE,
            stats_table=stats_table,
            corr_table=corr_table,
            cov_table=cov_table,
            heatmap_div=heatmap_div
        )

    except Exception as e:
        error_msg = traceback.format_exc()
        error_html = f"<html><body><h2>錯誤</h2><pre>{error_msg}</pre></body></html>"
        return error_html

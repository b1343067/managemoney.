from flask import Flask, render_template_string
import traceback

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>MPT 資產配置最佳化分析 | Robo-Advisor</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f6f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; }
        .header-banner { 
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
            color: white; 
            padding: 40px 0 30px; 
            margin-bottom: 30px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.1); 
        }
        .card { border: none; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); margin-bottom: 30px; overflow: hidden; }
        .card-header { background-color: #ffffff; border-bottom: 2px solid #f0f2f5; font-weight: 700; font-size: 1.15rem; color: #2c3e50; padding: 15px 20px; }
        .table { margin-bottom: 0; font-size: 0.95rem; vertical-align: middle; }
        .table thead th { background-color: #f8f9fa; color: #495057; border-bottom: 2px solid #dee2e6; text-align: center; }
        .table tbody td { text-align: center; }
        .badge-ticker { font-size: 1rem; margin: 4px; padding: 8px 12px; font-weight: 500; display: inline-block; }
        .insight-box { background-color: #f8f9fa; border-left: 5px solid #2c3e50; padding: 20px; border-radius: 8px; margin-bottom: 30px; }
        /* 強制表格不換行並可滾動，避免 10 檔資產擠破版面 */
        .table-responsive { overflow-x: auto; }
        .text-nowrap td, .text-nowrap th { white-space: nowrap; }
    </style>
</head>
<body>
    <div class="header-banner text-center">
        <h1 class="fw-bold mb-3">Modern Portfolio Theory (MPT)</h1>
        <p class="lead mb-4">跨資產配置最佳化與投資組合機會集合分析 (Robo-Advisor)</p>
        <div class="container px-5">
            <span class="badge bg-light text-dark badge-ticker shadow-sm">VOO (美股大盤)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">QQQ (科技大盤)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">BRK-B (價值投資)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">JPM (金融業)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">NVDA (AI成長)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">PG (核心消費)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">VNQ (房地產)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">TLT (長天期美債)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">VWO (新興市場)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">GLD (黃金避險)</span>
        </div>
        <p class="mt-4 mb-0" style="font-size: 0.85rem; opacity: 0.8;">Data Period: 2018-01-01 to 2024-01-01 (Daily Adjusted Close Price)</p>
    </div>

    <div class="container-fluid px-4 px-lg-5">
        
        <!-- 商業洞察區塊 (整合 MPT 分析邏輯) -->
        <div class="insight-box shadow-sm">
            <h5 class="fw-bold" style="color: #2c3e50;">資產關聯性與分散風險洞察</h5>
            <ul class="mb-0 mt-3" style="line-height: 1.8;">
                <li><strong>高連動性與攻擊部位：</strong>VOO、QQQ 與美國大型權值股 (NVDA, JPM) 具備高度正相關，作為推升預期報酬的主力。</li>
                <li><strong>低連動與防禦部位：</strong>公債 (TLT) 與黃金 (GLD) 與一般股市的連動性極低，在市場波動時能提供強大的下檔保護。</li>
                <li><strong>跨界分散效益 (Diversification)：</strong>納入房地產 (VNQ)、新興市場 (VWO) 以及防禦性消費股 (PG)，進一步將風險分散至不同資產類別與地理區域，完美實踐 MPT 理論中追求最大化 Diversification Benefit 的核心精神。</li>
            </ul>
        </div>

        <!-- Part I. 價格資料與 Return Matrix 展示區塊 -->
        <div class="card border-info" style="border: 1px solid #17a2b8;">
            <div class="card-header bg-light text-info border-info">
                 Part I. 資料蒐集與處理 (Price & Return Matrix)
            </div>
            <div class="card-body">
                <p class="text-muted small mb-3">已透過 Python 讀取 5 年以上歷史資料 (Adjusted Close Price)，並使用 <code>ffill().dropna()</code> 完成 Missing Values 處理。以下展示整理後的「歷史價格表」與由價格計算而來的「每日報酬率矩陣 (Return Matrix)」前 5 筆資料。</p>
                
                <h6 class="fw-bold text-secondary mt-4 mb-2">Step 1~3: 歷史價格表 (Adjusted Close Price)</h6>
                <div class="table-responsive mb-4">
                    {{ price_head_table | safe }}
                </div>

                <h6 class="fw-bold text-secondary mt-4 mb-2">Step 4~5: 每日報酬率矩陣 (Return Matrix)</h6>
                <div class="table-responsive mb-2">
                    {{ return_matrix_head_table | safe }}
                </div>
            </div>
        </div>

        <!-- MPT 核心：機會集合與 MVP -->
        <div class="card border-primary" style="border: 1px solid #b8daff;">
            <div class="card-header bg-light text-primary border-primary">
                 Part II. 投資組合機會集合 (Opportunity Set) & 最小變異投資組合 (MVP)
            </div>
            <div class="card-body">
                <p class="text-muted small mb-4">透過蒙地卡羅模擬隨機生成 3,000 組投資權重，構建 10 檔資產的投資組合機會集合，並精確定位出年化波動率最低的最優資產配置比例 (MVP)。</p>
                
                <div class="row align-items-center">
                    <div class="col-xl-8 mb-4 mb-xl-0">
                        <div style="background: white; border-radius: 8px; overflow: hidden;">
                            {{ mpt_chart_div | safe }}
                        </div>
                    </div>
                    <div class="col-xl-4">
                        <div class="p-4 rounded h-100" style="background-color: #fcfdfd; border: 1px solid #e9ecef;">
                            <h5 class="fw-bold mb-3 text-center"> MVP 最佳權重配置</h5>
                            <div class="row">
                                <div class="col-6">
                                    <ul class="list-group list-group-flush mb-0" style="font-size: 0.9rem;">
                                        {{ mvp_weights_html_1 | safe }}
                                    </ul>
                                </div>
                                <div class="col-6">
                                    <ul class="list-group list-group-flush mb-4" style="font-size: 0.9rem;">
                                        {{ mvp_weights_html_2 | safe }}
                                    </ul>
                                </div>
                            </div>
                            <div class="text-center mt-3 pt-3 border-top">
                                <p class="mb-1 text-muted">預期年化報酬率</p>
                                <h4 class="text-success fw-bold">{{ mvp_return }}</h4>
                                <p class="mb-1 mt-3 text-muted">年化波動率 (風險)</p>
                                <h4 class="text-danger fw-bold">{{ mvp_volatility }}</h4>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 基礎數據與矩陣區塊 -->
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header"> Part II. 單一資產報酬與風險指標</div>
                    <div class="card-body p-0">
                        <div class="table-responsive">
                            {{ stats_table | safe }}
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="col-12">
                <div class="card">
                    <div class="card-header"> Part II. 相關係數矩陣 (Correlation Matrix)</div>
                    <div class="card-body p-0">
                        <div class="table-responsive">
                            {{ corr_table | safe }}
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-12">
                <div class="card">
                    <div class="card-header">📉 Part II. 共變異數矩陣 (Covariance Matrix)</div>
                    <div class="card-body p-0">
                        <div class="table-responsive">
                            {{ cov_table | safe }}
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <footer class="text-center mt-4 mb-5 text-muted" style="font-size: 0.85rem;">
            &copy; 2026 MPT Robo-Advisor System
        </footer>
    </div>
    
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
        import plotly.graph_objects as go

        # 1. 抓取 10 檔資產資料
        tickers = ['VOO', 'QQQ', 'BRK-B', 'JPM', 'NVDA', 'PG', 'VNQ', 'TLT', 'VWO', 'GLD']
        df_list = []
        
        for t in tickers:
            stock = yf.Ticker(t)
            hist_data = stock.history(start="2018-01-01", end="2024-01-01")
            if not hist_data.empty and 'Close' in hist_data.columns:
                price_series = hist_data['Close'].rename(t)
                price_series.index = price_series.index.tz_localize(None)
                df_list.append(price_series)

        # 處理 Missing Values (向前填補並刪除) -> 取得乾淨的歷史價格表
        clean_price_data = pd.concat(df_list, axis=1).ffill().dropna()

        # 2. 計算 Return Matrix
        daily_returns = clean_price_data.pct_change().dropna()
        trading_days = 252

        avg_daily_return = daily_returns.mean()
        annualized_return = (1 + avg_daily_return) ** trading_days - 1
        std_dev = daily_returns.std()
        annualized_volatility = std_dev * np.sqrt(trading_days)
        
        # 共變異數矩陣
        cov_matrix = daily_returns.cov()
        annualized_cov_matrix = cov_matrix * trading_days 

        stats_df = pd.DataFrame({
            'Average Daily Return': avg_daily_return,
            'Annualized Return': annualized_return,
            'Daily Standard Dev': std_dev,
            'Annualized Volatility': annualized_volatility
        }).round(4)

        # 3. 蒙地卡羅模擬 (3000組)
        num_portfolios = 3000
        results = np.zeros((3, num_portfolios))
        weights_record = []

        for i in range(num_portfolios):
            weights = np.random.random(len(tickers))
            weights /= np.sum(weights)
            weights_record.append(weights)
            
            portfolio_return = np.sum(weights * annualized_return)
            portfolio_std_dev = np.sqrt(np.dot(weights.T, np.dot(annualized_cov_matrix, weights)))
            
            results[0,i] = portfolio_std_dev
            results[1,i] = portfolio_return
            results[2,i] = portfolio_return / portfolio_std_dev

        min_vol_idx = np.argmin(results[0])
        mvp_volatility = results[0, min_vol_idx]
        mvp_return = results[1, min_vol_idx]
        mvp_weights = weights_record[min_vol_idx]

        # 將 10 檔資產分兩欄顯示
        mvp_weights_html_1 = ""
        mvp_weights_html_2 = ""
        for i, ticker in enumerate(tickers):
            weight_pct = mvp_weights[i] * 100
            item_html = f'<li class="list-group-item d-flex justify-content-between align-items-center px-1 border-0">{ticker} <span class="badge bg-primary rounded-pill">{weight_pct:.1f}%</span></li>'
            if i < 5:
                mvp_weights_html_1 += item_html
            else:
                mvp_weights_html_2 += item_html

        # 4. Plotly 散佈圖
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=results[0,:],
            y=results[1,:],
            mode='markers',
            marker=dict(
                size=4,
                color=results[2,:], 
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title="Sharpe Ratio")
            ),
            name='Opportunity Set',
            text=[f"Risk: {r[0]:.3f}<br>Return: {r[1]:.3f}" for r in results.T],
            hoverinfo='text'
        ))
        
        fig.add_trace(go.Scatter(
            x=[mvp_volatility],
            y=[mvp_return],
            mode='markers+text',
            marker=dict(color='red', size=14, symbol='star'),
            name='MVP',
            text=['MVP'],
            textposition='top center',
            textfont=dict(size=14, color='red', weight='bold')
        ))

        fig.update_layout(
            title='Portfolio Opportunity Set (Efficient Frontier Simulation)',
            xaxis_title='Annualized Volatility (Risk)',
            yaxis_title='Annualized Return',
            margin=dict(l=40, r=40, t=40, b=40),
            height=450,
            showlegend=False
        )
        
        mpt_chart_div = fig.to_html(full_html=False, include_plotlyjs='cdn')

        # 5. 表格渲染 (加入 text-nowrap 避免 10 檔資產表格跑版)
        table_classes = 'table table-hover table-striped table-bordered text-nowrap m-0'
        
        # 轉換所有需要的表格，新增 price_head_table
        price_head_table = clean_price_data.head().round(2).to_html(classes=table_classes)
        return_matrix_head_table = daily_returns.head().round(4).to_html(classes=table_classes)
        
        stats_table = stats_df.T.to_html(classes=table_classes)
        corr_table = daily_returns.corr().round(4).to_html(classes=table_classes)
        cov_table = cov_matrix.round(6).to_html(classes=table_classes)

        return render_template_string(
            HTML_TEMPLATE,
            mpt_chart_div=mpt_chart_div,
            mvp_weights_html_1=mvp_weights_html_1,
            mvp_weights_html_2=mvp_weights_html_2,
            mvp_return=f"{mvp_return * 100:.2f}%",
            mvp_volatility=f"{mvp_volatility * 100:.2f}%",
            price_head_table=price_head_table,
            return_matrix_head_table=return_matrix_head_table,
            stats_table=stats_table,
            corr_table=corr_table,
            cov_table=cov_table
        )

    except Exception as e:
        error_msg = traceback.format_exc()
        error_html = f"<html><body><h2>程式執行發生錯誤</h2><pre style='background:#fee; padding:15px;'>{error_msg}</pre></body></html>"
        return error_html

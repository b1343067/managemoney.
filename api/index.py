from flask import Flask, render_template_string
import traceback

app = Flask(__name__)

# 升級版網頁前端模板 (引入 Bootstrap 5)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>投資組合分析儀表板 | MPT</title>
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
        .badge-ticker { font-size: 1rem; margin: 0 5px; padding: 8px 12px; font-weight: 500; }
        .conclusion-box { background-color: #e8f4f8; border-left: 5px solid #3498db; padding: 20px; border-radius: 8px; margin-bottom: 40px; }
    </style>
</head>
<body>
    <div class="header-banner text-center">
        <h1 class="fw-bold mb-3">Modern Portfolio Theory (MPT)</h1>
        <p class="lead mb-4">作業展示：投資組合機會集合與風險分析</p>
        <div>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">VOO (大盤)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">BRK-B (價值股)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">JPM (金融股)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">NVDA (成長股)</span>
            <span class="badge bg-light text-dark badge-ticker shadow-sm">GLD (黃金避險)</span>
        </div>
        <p class="mt-3 mb-0" style="font-size: 0.85rem; opacity: 0.8;">資料期間：2018-01-01 至 2024-01-01 (Daily Data)</p>
    </div>

    <div class="container">
        
        <!-- Part II 回答問題區塊 -->
        <div class="conclusion-box shadow-sm">
            <h5 class="fw-bold" style="color: #2980b9;">📝 Part II. Return and Risk Analysis - 作業問題回答</h5>
            <ul class="mb-0 mt-3" style="line-height: 1.8;">
                <li><strong>Q1. 哪些資產彼此相關性最高？</strong><br>
                從 Correlation Matrix 中可看出，大型權值股 (如 NVDA、JPM) 或大型控股 (BRK-B) 通常與標普500大盤 (VOO) 呈現最高的正相關（數值接近 1）。</li>
                <li class="mt-2"><strong>Q2. 哪些資產具有較低或負相關性？</strong><br>
                黃金 (GLD) 作為商品與避險資產，與 VOO、NVDA、JPM 等股市資產的相關係數極低（顏色偏向藍色，數值接近 0 甚至為負）。</li>
                <li class="mt-2"><strong>Q3. 從 Correlation Matrix 判斷，哪些資產可能具有較好的 diversification benefit？</strong><br>
                相關係數越低，分散投資效益 (Diversification benefit) 越好。因此，在純股票部位中加入與股市具備極低相關性的 <strong>GLD (黃金)</strong>，能有效抵銷市場下跌時的波動，達到最佳的分散風險效果。</li>
            </ul>
        </div>

        <!-- Part I 區塊 -->
        <div class="card border-primary" style="border: 1px solid #b8daff;">
            <div class="card-header bg-light">📂 Part I. 資產選擇與資料處理 (Return Matrix)</div>
            <div class="card-body">
                <div class="row">
                    <div class="col-lg-6">
                        <h6 class="fw-bold text-secondary mb-2">Step 1~3: 價格資料 (Adj Close) 處理遺失值後</h6>
                        <div class="table-responsive mb-3">
                            {{ price_head_table | safe }}
                        </div>
                    </div>
                    <div class="col-lg-6">
                        <h6 class="fw-bold text-secondary mb-2">Step 4~5: Return Matrix (每日報酬率)</h6>
                        <div class="table-responsive mb-3">
                            {{ return_matrix_head_table | safe }}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Part II 區塊: 報酬與風險 -->
        <div class="card">
            <div class="card-header">📊 Part II. 報酬與風險指標 (Return and Risk)</div>
            <div class="card-body">
                <div class="table-responsive">
                    {{ stats_table | safe }}
                </div>
            </div>
        </div>

        <!-- Part II 區塊: 熱力圖 -->
        <div class="card">
            <div class="card-header">🗺️ Part II. 相關係數熱力圖 (Correlation Heatmap)</div>
            <div class="card-body">
                <div class="text-center" style="background: white; border-radius: 8px;">
                    {{ heatmap_div | safe }}
                </div>
            </div>
        </div>

        <!-- Part II 區塊: 矩陣 -->
        <div class="row">
            <div class="col-lg-6">
                <div class="card h-100">
                    <div class="card-header">🔗 Part II. 相關係數矩陣 (Correlation Matrix)</div>
                    <div class="card-body">
                        <div class="table-responsive">
                            {{ corr_table | safe }}
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-lg-6">
                <div class="card h-100">
                    <div class="card-header">📈 Part II. 共變異數矩陣 (Covariance Matrix)</div>
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

        # ==========================================
        # Part I. 資產選擇與資料蒐集
        # ==========================================
        tickers = ['VOO', 'BRK-B', 'JPM', 'NVDA', 'GLD']
        df_list = []
        
        # 【終極修正】捨棄 download()，改用 Ticker().history() 避開所有索引錯誤
        for t in tickers:
            stock = yf.Ticker(t)
            # history() 拿到的 Close 預設就是經過除權息調整的 Adj Close
            hist_data = stock.history(start="2018-01-01", end="2024-01-01")
            
            if not hist_data.empty and 'Close' in hist_data.columns:
                # 只取出 Close 欄位，並將欄位名稱改成股票代號
                price_series = hist_data['Close'].rename(t)
                # 移除時區資訊，避免合併時出錯
                price_series.index = price_series.index.tz_localize(None)
                df_list.append(price_series)

        # 合併所有單一股票資料並處理遺失值
        clean_price_data = pd.concat(df_list, axis=1).ffill().dropna()

        # 4 & 5. 計算各資產 Return 並建立 Return Matrix
        daily_returns = clean_price_data.pct_change()
        return_matrix = daily_returns.dropna()

        # [前端展示用] 取前 5 筆資料
        table_classes = 'table table-hover table-striped table-bordered'
        price_head_table = clean_price_data.head().round(2).to_html(classes=table_classes)
        return_matrix_head_table = return_matrix.head().round(4).to_html(classes=table_classes)

        # ==========================================
        # Part II. Return and Risk Analysis
        # ==========================================
        trading_days = 252 # 一年交易日設定

        # 1. 計算 Average Return (平均日報酬)
        avg_daily_return = return_matrix.mean()
        
        # 2. 計算 Annualized Return (年化報酬率)
        annualized_return = (1 + avg_daily_return) ** trading_days - 1
        
        # 3. 計算 Standard Deviation (日標準差)
        std_dev = return_matrix.std()
        
        # 4. 計算 Annualized Volatility (年化波動率)
        annualized_volatility = std_dev * np.sqrt(trading_days)

        # 統整為 DataFrame 以利展示
        stats_df = pd.DataFrame({
            'Average Return': avg_daily_return,
            'Annualized Return': annualized_return,
            'Standard Deviation': std_dev,
            'Annualized Volatility': annualized_volatility
        }).round(4)

        # 5. 建立 Correlation Matrix (相關係數矩陣)
        corr_matrix = return_matrix.corr().round(4)
        
        # 6. 建立 Covariance Matrix (共變異數矩陣)
        cov_matrix = return_matrix.cov().round(6)

        # 繪製 Plotly 相關係數熱力圖
        fig = px.imshow(
            corr_matrix, 
            text_auto=True, 
            aspect="auto", 
            color_continuous_scale='RdBu_r', 
            zmin=-1, zmax=1,
            height=450
        )
        fig.update_layout(
            margin=dict(l=20, r=20, t=20, b=20),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        heatmap_div = fig.to_html(full_html=False, include_plotlyjs='cdn')

        # 將 Pandas 表格轉為 HTML 供前端渲染
        stats_table = stats_df.to_html(classes=table_classes)
        corr_table = corr_matrix.to_html(classes=table_classes)
        cov_table = cov_matrix.to_html(classes=table_classes)

        # 渲染最終網頁
        return render_template_string(
            HTML_TEMPLATE,
            price_head_table=price_head_table,
            return_matrix_head_table=return_matrix_head_table,
            stats_table=stats_table,
            corr_table=corr_table,
            cov_table=cov_table,
            heatmap_div=heatmap_div
        )

    except Exception as e:
        error_msg = traceback.format_exc()
        error_html = f"<html><body><h2>程式執行發生錯誤</h2><pre style='background:#fee; padding:15px;'>{error_msg}</pre></body></html>"
        return error_html

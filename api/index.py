from flask import Flask, request, render_template_string, Response
import traceback
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf

app = Flask(__name__)

# ==========================================
# 1. NLP 分析引擎與計分邏輯 (來自你的設計)
# ==========================================
def analyze_nlp(t1, t2, t3):
    text = (t1 + t2 + t3).lower()
    if not text.strip():
        return "無數據", "請輸入對話以啟動分析", "無"
    if any(w in text for w in ["怕", "賣", "擔心", "焦慮", "虧", "恐慌", "睡不著"]):
        return "高度焦慮 / 損失規避", "留意恐慌性拋售風險，建議提高防禦資產。", "焦慮"
    elif any(w in text for w in ["加碼", "買", "抄底", "機會", "歐印", "滿倉"]):
        return "過度自信", "留意過度集中與槓桿風險，嚴守停損紀律。", "自信"
    elif any(w in text for w in ["朋友", "別人", "跟", "羨慕", "不是滋味", "換"]):
        return "從眾傾向 / FOMO", "易受外界雜訊影響，留意追高殺低風險。", "從眾"
    else:
        return "情緒平穩", "無極端偏誤，維持長期投資紀律。", "平穩"

# ==========================================
# 2. 前端 HTML 模板 (Jinja2 條件渲染)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Robo-Advisor | MPT & KYC</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f6f9; font-family: 'Segoe UI', sans-serif; color: #333; }
        .header-banner { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 40px 0 20px; margin-bottom: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .card { border: none; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); margin-bottom: 30px; }
        .card-header { background-color: #ffffff; border-bottom: 2px solid #f0f2f5; font-weight: 700; font-size: 1.15rem; color: #2c3e50; }
        .btn-primary { background-color: #2979FF; border: none; padding: 12px; font-size: 1.1rem; font-weight: bold; border-radius: 8px; }
        .btn-primary:hover { background-color: #1e3c72; }
    </style>
</head>
<body>
    <div class="header-banner text-center">
        <h1 class="fw-bold mb-2">Automated Robo-Advisor</h1>
        <p class="lead mb-4">動態風險評估與 MPT 資產配置最佳化</p>
        {% if show_results %}
        <a href="/download_csv" class="btn btn-outline-light btn-sm mb-3">⬇️ 下載歷史價格 CSV (繳交作業用)</a>
        {% endif %}
    </div>

    <div class="container px-4" style="max-width: 1200px;">
        
        {% if not show_results %}
        <!-- ================= KYC 問卷表單區 ================= -->
        <div class="row justify-content-center">
            <div class="col-lg-8">
                <div class="card p-4">
                    <h4 class="fw-bold text-center mb-4" style="color: #2c3e50;">📊 投資人風險屬性評估 (KYC)</h4>
                    <form method="POST" action="/">
                        <div class="mb-3">
                            <label class="form-label fw-bold">💰 收入與現金流</label>
                            <select class="form-select" name="inc"><option>穩定正向</option><option>收支打平</option><option>入不敷出</option></select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold">💼 可投資資產</label>
                            <select class="form-select" name="ast"><option>50萬以下</option><option>50-300萬</option><option>300萬以上</option></select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold">🏠 流動性需求</label>
                            <select class="form-select" name="liq"><option>高 (隨時需要變現)</option><option>中 (偶有資金需求)</option><option>低 (閒置資金)</option></select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold">📅 投資期限</label>
                            <select class="form-select" name="hor"><option>1年內</option><option>1-3年</option><option>3-10年</option><option>10年以上</option></select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold">🧾 負債狀況</label>
                            <select class="form-select" name="lia"><option>無負債</option><option>可控負債 (如房貸)</option><option>高負債壓力</option></select>
                        </div>
                        <hr class="my-4">
                        <h5 class="fw-bold mb-3 text-primary">🧠 情境與行為測試 (NLP 分析)</h5>
                        <div class="mb-3">
                            <label class="form-label">如果您的投資組合一個月下跌 20%，您會怎麼做？為什麼？</label>
                            <textarea class="form-control" name="q1" rows="2" required></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">最近市場波動很大，您目前對自己的投資有什麼感受？</label>
                            <textarea class="form-control" name="q2" rows="2" required></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">如果您的朋友靠 AI 股票賺了 30%，而您的投資只有 5%，您會怎麼做？</label>
                            <textarea class="form-control" name="q3" rows="2" required></textarea>
                        </div>
                        <button type="submit" class="btn btn-primary w-100 mt-3">Generate Dynamic Profile & Portfolio</button>
                    </form>
                </div>
            </div>
        </div>
        
        {% else %}
        <!-- ================= 分析結果儀表板區 ================= -->
        <div class="row mb-4">
            <!-- 動態畫像 SVG 與判定結果 -->
            <div class="col-lg-4">
                <div class="card h-100 p-4 text-center" style="background-color: #1a1a2e; color: white;">
                    <h3 class="fw-bold text-white mb-0">Dynamic Investor</h3>
                    <p class="text-muted mb-3">動態風險畫像判定</p>
                    <svg width="200" height="120" viewBox="0 0 240 140" class="mx-auto">
                        <defs>
                            <linearGradient id="grad1" x1="0%" y1="100%" x2="100%" y2="0%">
                                <stop offset="0%" stop-color="#00E5FF" />
                                <stop offset="100%" stop-color="#2979FF" />
                            </linearGradient>
                            <linearGradient id="grad2" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#2979FF" />
                                <stop offset="100%" stop-color="#AA00FF" />
                            </linearGradient>
                        </defs>
                        <path d="M 40 120 A 80 80 0 0 1 120 40" fill="none" stroke="url(#grad1)" stroke-width="24" stroke-linecap="round" />
                        <path d="M 120 40 A 80 80 0 0 1 200 120" fill="none" stroke="url(#grad2)" stroke-width="24" stroke-linecap="round" />
                        <circle cx="120" cy="85" r="20" fill="#3949AB" />
                        <path d="M 85 140 C 85 110, 155 110, 155 140" fill="#3949AB" />
                    </svg>
                    <div class="text-start mt-4">
                        <h6 class="text-info">📊 Baseline Risk</h6>
                        <p class="fw-bold fs-5">{{ baseline }}</p>
                        <h6 class="text-info mt-3">❤️ Emotional State</h6>
                        <p class="fw-bold">{{ state }}</p>
                        <h6 class="text-info mt-3">⚙️ Behavioral Alert</h6>
                        <p class="fw-bold">{{ alert }}</p>
                        <h6 class="text-warning mt-3">✅ 系統最終適配組合</h6>
                        <p class="fw-bold text-warning fs-5">{{ final_profile }}</p>
                    </div>
                    <a href="/" class="btn btn-outline-light mt-4">🔄 重新測驗</a>
                </div>
            </div>

            <!-- 作業規定 Figure 1 & Figure 2 -->
            <div class="col-lg-8">
                <div class="card mb-4">
                    <div class="card-header">📈 Figure 1. 效率前緣與專屬投資組合 (Efficient Frontier)</div>
                    <div class="card-body p-0">
                        {{ fig1_html | safe }}
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">📊 Figure 2. 資產配置最佳化比例 (Optimal Asset Allocation)</div>
                    <div class="card-body p-0">
                        {{ fig2_html | safe }}
                    </div>
                </div>
            </div>
        </div>
        {% endif %}
        
        <footer class="text-center mt-4 mb-5 text-muted" style="font-size: 0.85rem;">
            &copy; 2026 MPT Robo-Advisor System (Assignment 3)
        </footer>
    </div>
</body>
</html>
"""

# ==========================================
# 3. 抓取資料與 MPT 運算 (快取於全域變數避免超時)
# ==========================================
global_mpt_data = None

def get_mpt_data():
    global global_mpt_data
    if global_mpt_data is not None:
        return global_mpt_data
    
    tickers = ['VOO', 'QQQ', 'BRK-B', 'JPM', 'NVDA', 'PG', 'VNQ', 'TLT', 'VWO', 'GLD']
    df_list = []
    for t in tickers:
        hist_data = yf.Ticker(t).history(start="2018-01-01", end="2024-01-01")
        if not hist_data.empty and 'Close' in hist_data.columns:
            s = hist_data['Close'].rename(t)
            s.index = s.index.tz_localize(None)
            df_list.append(s)
            
    clean_price = pd.concat(df_list, axis=1).ffill().dropna()
    daily_returns = clean_price.pct_change().dropna()
    ann_ret = daily_returns.mean() * 252
    ann_cov = daily_returns.cov() * 252
    
    num_portfolios = 1500
    results = np.zeros((3, num_portfolios))
    weights_record = []
    
    for i in range(num_portfolios):
        w = np.random.random(len(tickers))
        w /= np.sum(w)
        weights_record.append(w)
        p_ret = np.sum(w * ann_ret)
        p_std = np.sqrt(np.dot(w.T, np.dot(ann_cov, w)))
        results[0,i] = p_std
        results[1,i] = p_ret
        results[2,i] = p_ret / p_std
        
    idx_cons = np.argmin(results[0])
    idx_mod = np.argmax(results[2])
    high_risk_threshold = np.percentile(results[0], 90)
    high_risk_indices = np.where(results[0] >= high_risk_threshold)[0]
    idx_agg = high_risk_indices[np.argmax(results[1, high_risk_indices])]
    
    global_mpt_data = {
        'csv': clean_price.to_csv(),
        'tickers': tickers,
        'results': results,
        'ports': {
            'Conservative': {'risk': results[0, idx_cons], 'ret': results[1, idx_cons], 'w': weights_record[idx_cons]},
            'Moderate': {'risk': results[0, idx_mod], 'ret': results[1, idx_mod], 'w': weights_record[idx_mod]},
            'Aggressive': {'risk': results[0, idx_agg], 'ret': results[1, idx_agg], 'w': weights_record[idx_agg]}
        }
    }
    return global_mpt_data

# ==========================================
# 4. 路由設定
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template_string(HTML_TEMPLATE, show_results=False)
    
    try:
        # 1. 處理表單與計分
        d = request.form
        score = 0
        if d.get("inc") == "穩定正向": score += 1
        if d.get("ast") in ["50-300萬", "300萬以上"]: score += 1
        if d.get("liq") == "低 (閒置資金)": score += 1
        if d.get("hor") in ["3-10年", "10年以上"]: score += 1
        if d.get("lia") == "無負債": score += 1
        
        if score <= 2: baseline = "Conservative"
        elif score <= 4: baseline = "Moderate"
        else: baseline = "Aggressive"
        
        state, alert, logic_flag = analyze_nlp(d.get("q1",""), d.get("q2",""), d.get("q3",""))
        
        # 動態修正最終屬性
        final_profile = baseline
        if logic_flag == "焦慮": final_profile = "Conservative"
        elif logic_flag in ["自信", "從眾"] and baseline == "Conservative": pass
        
        # 2. 獲取 MPT 數據並繪圖
        mpt = get_mpt_data()
        res = mpt['results']
        ports = mpt['ports']
        
        # Figure 1: 效率前緣
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=res[0,:], y=res[1,:], mode='markers', marker=dict(color=res[2,:], colorscale='Viridis', size=4, showscale=True), name='Opportunity Set'))
        colors = {'Conservative': 'blue', 'Moderate': 'orange', 'Aggressive': 'red'}
        
        for name, data in ports.items():
            # 針對測驗出的屬性放大標示
            size = 18 if name == final_profile else 10
            sym = 'star' if name == final_profile else 'circle'
            fig1.add_trace(go.Scatter(x=[data['risk']], y=[data['ret']], mode='markers+text', marker=dict(color=colors[name], size=size, symbol=sym, line=dict(color='black', width=1)), text=[name], textposition='top center', textfont=dict(color=colors[name], size=14, weight='bold'), name=name))
        fig1.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=400, showlegend=False, xaxis_title="Risk (Volatility)", yaxis_title="Expected Return")
        fig1_html = fig1.to_html(full_html=False, include_plotlyjs='cdn')
        
        # Figure 2: 堆疊長條圖 (資產配置)
        fig2 = go.Figure()
        labels = ['Conservative', 'Moderate', 'Aggressive']
        for i, ticker in enumerate(mpt['tickers']):
            y_vals = [ports[label]['w'][i] * 100 for label in labels]
            text_vals = [f"{ticker} {v:.1f}%" if v > 4 else "" for v in y_vals]
            fig2.add_trace(go.Bar(name=ticker, x=labels, y=y_vals, text=text_vals, textposition='inside'))
        fig2.update_layout(barmode='stack', margin=dict(l=20, r=20, t=20, b=20), height=350, legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
        fig2_html = fig2.to_html(full_html=False, include_plotlyjs='cdn')
        
        return render_template_string(HTML_TEMPLATE, show_results=True, baseline=baseline, state=state, alert=alert, final_profile=final_profile, fig1_html=fig1_html, fig2_html=fig2_html)

    except Exception as e:
        return f"<h2>系統運算錯誤</h2><pre>{traceback.format_exc()}</pre>"

@app.route('/download_csv')
def download_csv():
    # 自動化產出作業要求的 CSV 檔案
    mpt = get_mpt_data()
    return Response(
        mpt['csv'],
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=stock_data.csv"}
    )

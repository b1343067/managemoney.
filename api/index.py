。from flask import Flask, request, render_template_string, Response
import traceback
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf

app = Flask(__name__)

# ==========================================
# 1. NLP 分析引擎與計分邏輯
# ==========================================
def analyze_nlp(t1, t2, t3):
    text = (t1 + t2 + t3).lower()
    if not text.strip():
        return "尚未填寫", "請完成問卷以獲取個人化行為建議。", "無"
    
    if any(w in text for w in ["怕", "賣", "擔心", "焦慮", "虧", "恐慌", "睡不著"]):
        return "謹慎保守 (風險趨避)", "您對市場波動較為敏感。建議配置較高比例的防禦性資產（如債券），以降低資產波動帶來的心理壓力。", "保守"
    elif any(w in text for w in ["加碼", "買", "抄底", "機會", "歐印", "滿倉"]):
        return "積極進取 (追求成長)", "您對市場抱持樂觀態度。在追求高報酬的同時，建議仍需注意資產過度集中的風險，維持適度的資產配置紀律。", "激進"
    elif any(w in text for w in ["朋友", "別人", "跟", "羨慕", "不是滋味", "換"]):
        return "市場跟隨 (易受情緒影響)", "您較容易關注市場熱點與他人績效。建議制定屬於自己的長期投資計畫，避免因市場雜訊而頻繁交易。", "從眾"
    else:
        return "理性平穩 (紀律投資)", "您目前的投資心態相當穩定。建議繼續保持理性，不受短期波動影響，堅定執行長期資產配置。", "平穩"

# ==========================================
# 2. 前端 HTML 模板
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
        <h1 class="fw-bold mb-2">智能理財機器人 (Robo-Advisor)</h1>
        <p class="lead mb-4">動態風險評估與 MPT 資產配置最佳化</p>
        {% if show_results %}
        <a href="/download_csv" class="btn btn-outline-light btn-sm mb-3">⬇️ 下載歷史價格 CSV (作業繳交用)</a>
        {% endif %}
    </div>

    <div class="container px-4" style="max-width: 1200px;">
        
        {% if not show_results %}
        <!-- ================= KYC 問卷表單區 ================= -->
        <div class="row justify-content-center">
            <div class="col-lg-8">
                <div class="card p-4">
                    <h4 class="fw-bold text-center mb-4" style="color: #2c3e50;">投資人風險屬性評估</h4>
                    <form method="POST" action="/">
                        <div class="mb-3">
                            <label class="form-label fw-bold">收入</label>
                            <select class="form-select" name="inc"><option>穩定正向</option><option>收支打平</option><option>入不敷出</option></select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold">可投資資產</label>
                            <select class="form-select" name="ast"><option>50萬以下</option><option>50-300萬</option><option>300萬以上</option></select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold">流動性需求</label>
                            <select class="form-select" name="liq"><option>高 (隨時需要變現)</option><option>中 (偶有資金需求)</option><option>低 (閒置資金)</option></select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold">投資期限</label>
                            <select class="form-select" name="hor"><option>1年內</option><option>1-3年</option><option>3-10年</option><option>10年以上</option></select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold">負債狀況</label>
                            <select class="form-select" name="lia"><option>無負債</option><option>可控負債 (如房貸)</option><option>高負債壓力</option></select>
                        </div>
                        <hr class="my-4">
                        <h5 class="fw-bold mb-3 text-primary"</h5>
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
                        <button type="submit" class="btn btn-primary w-100 mt-3">生成專屬風險畫像與投資組合</button>
                    </form>
                </div>
            </div>
        </div>
        
        {% else %}
        <!-- ================= 分析結果儀表板區 ================= -->
        <div class="row mb-4">
            <!-- 動態畫像判定結果 -->
            <div class="col-lg-4">
                <div class="card h-100 p-4 text-center" style="background-color: #1a1a2e; color: white;">
                    <h3 class="fw-bold text-white mb-2">個人化投資畫像</h3>
                    <p class="text-muted mb-4">風險承擔能力評估</p>
                    
                    <!-- 專業級環形進度條與標準人像 -->
                    <div style="position: relative; width: 160px; height: 160px; margin: 0 auto;">
                        <!-- 背景外圈 -->
                        <svg viewBox="0 0 36 36" style="width: 160px; height: 160px; transform: rotate(-90deg);">
                            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                fill="none" stroke="#2c3e50" stroke-width="2.5" />
                            <!-- 動態風險進度條 -->
                            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                fill="none" stroke="{{ icon_color }}" stroke-width="3" stroke-linecap="round"
                                stroke-dasharray="{{ stroke_dash }}, 100" style="transition: stroke-dasharray 1s ease-out;" />
                        </svg>
                        <!-- 中間專業人像 -->
                        <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);">
                            <svg width="65" height="65" viewBox="0 0 24 24" fill="{{ icon_color }}">
                                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                            </svg>
                        </div>
                    </div>
                    <!-- 屬性大標題 -->
                    <h3 class="fw-bold mt-4 mb-4" style="color: {{ icon_color }}; letter-spacing: 2px;">{{ final_profile }}</h3>
                    
                    <hr class="border-secondary mb-4">
                    <div class="text-start">
                        <h6 class="text-info">客觀財務風險評分</h6>
                        <p class="fw-bold fs-5">{{ baseline }}</p>
                        <h6 class="text-info mt-4">當前投資心態</h6>
                        <p class="fw-bold">{{ state }}</p>
                        <h6 class="text-info mt-4">專業投資行為建議</h6>
                        <p class="fw-bold" style="font-size: 0.95rem; color: #dcdde1;">{{ alert }}</p>
                    </div>
                    <div class="text-center mt-auto pt-4">
                        <a href="/" class="btn btn-outline-light w-100">重新測驗</a>
                    </div>
                </div>
            </div>

            <!-- 作業規定 Figure 1 & Figure 2 -->
            <div class="col-lg-8">
                <div class="card mb-4">
                    <div class="card-header">Figure 1. 效率前緣與專屬投資組合 (Efficient Frontier)</div>
                    <div class="card-body p-0">
                        {{ fig1_html | safe }}
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">Figure 2. 資產配置最佳化比例 (Optimal Asset Allocation)</div>
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
# 3. 抓取資料與 MPT 運算
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
            '保守型': {'risk': results[0, idx_cons], 'ret': results[1, idx_cons], 'w': weights_record[idx_cons]},
            '穩健型': {'risk': results[0, idx_mod], 'ret': results[1, idx_mod], 'w': weights_record[idx_mod]},
            '激進型': {'risk': results[0, idx_agg], 'ret': results[1, idx_agg], 'w': weights_record[idx_agg]}
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
        
        if score <= 2: baseline = "保守型"
        elif score <= 4: baseline = "穩健型"
        else: baseline = "激進型"
        
        state, alert, logic_flag = analyze_nlp(d.get("q1",""), d.get("q2",""), d.get("q3",""))
        
        # 動態修正最終屬性
        final_profile = baseline
        if logic_flag == "保守": final_profile = "保守型"
        elif logic_flag in ["激進", "從眾"] and baseline == "保守型": pass 
        
        # 設定新版儀表板的顏色與進度條長度
        if final_profile == "保守型":
            icon_color, stroke_dash = "#00BFFF", "33" # 藍色，進度 1/3
        elif final_profile == "穩健型":
            icon_color, stroke_dash = "#FFB300", "66" # 橘黃，進度 2/3
        else:
            icon_color, stroke_dash = "#FF5252", "100" # 紅色，進度全滿

        # 2. 獲取 MPT 數據並繪圖
        mpt = get_mpt_data()
        res = mpt['results']
        ports = mpt['ports']
        
        # Figure 1: 效率前緣
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=res[0,:], y=res[1,:], mode='markers', marker=dict(color=res[2,:], colorscale='Viridis', size=4, showscale=True), name='投資機會集合'))
        colors = {'保守型': 'blue', '穩健型': 'orange', '激進型': 'red'}
        
        for name, data in ports.items():
            size = 20 if name == final_profile else 10
            sym = 'star' if name == final_profile else 'circle'
            fig1.add_trace(go.Scatter(
                x=[data['risk']], y=[data['ret']], mode='markers+text', 
                marker=dict(color=colors[name], size=size, symbol=sym, line=dict(color='black', width=1)), 
                text=[name], textposition='top center', 
                textfont=dict(color=colors[name], size=14, weight='bold'), name=name
            ))
            
        fig1.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=400, showlegend=False, xaxis_title="風險 (年化波動率)", yaxis_title="預期報酬率")
        fig1_html = fig1.to_html(full_html=False, include_plotlyjs='cdn')
        
        # Figure 2: 堆疊長條圖
        fig2 = go.Figure()
        labels = ['保守型', '穩健型', '激進型']
        for i, ticker in enumerate(mpt['tickers']):
            y_vals = [ports[label]['w'][i] * 100 for label in labels]
            text_vals = [f"{ticker} {v:.1f}%" if v > 4 else "" for v in y_vals]
            fig2.add_trace(go.Bar(name=ticker, x=labels, y=y_vals, text=text_vals, textposition='inside'))
            
        fig2.update_layout(barmode='stack', margin=dict(l=20, r=20, t=20, b=20), height=350, legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
        fig2_html = fig2.to_html(full_html=False, include_plotlyjs='cdn')
        
        return render_template_string(HTML_TEMPLATE, show_results=True, baseline=baseline, state=state, alert=alert, final_profile=final_profile, fig1_html=fig1_html, fig2_html=fig2_html, icon_color=icon_color, stroke_dash=stroke_dash)

    except Exception as e:
        return f"<h2>系統運算錯誤</h2><pre>{traceback.format_exc()}</pre>"

@app.route('/download_csv')
def download_csv():
    mpt = get_mpt_data()
    return Response(
        mpt['csv'],
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=stock_data.csv"}
    )

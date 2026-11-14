from flask import Flask, request, render_template_string, Response
import traceback
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf

app = Flask(__name__)

# ==========================================
# 0. 全域參數設定
# ==========================================
TICKERS = ['VOO', 'QQQ', 'BRK-B', 'JPM', 'NVDA', 'PG', 'VNQ', 'TLT', 'VWO', 'GLD']

# 資料期間：估計期 (In-sample) 用來估計模型；測試期 (Out-of-sample) 用來做績效回測
DATA_START = "2018-01-01"
TRAIN_END = "2024-01-01"      # 估計期 2018/01 ~ 2023/12 (與前次作業相同)
DATA_END = "2025-01-01"       # 測試期 2024/01 ~ 2024/12

RF = 0.02         # 無風險利率 (年化)
TAU = 0.05        # BL 模型 τ：先驗均衡報酬的不確定性縮放係數 (文獻常用 0.025~0.05)
DELTA_MKT = 2.5   # 市場風險趨避係數 δ (He & Litterman 1999 常用值)

# 市場均衡權重 (Market-cap weights)：以 2023 年底「市值 / ETF 資產規模」約略值計算 (單位：十億美元)
# 個股使用公司市值、ETF 使用基金規模 (AUM)，作為市場對各資產的「共識配置」代理變數。
MARKET_CAP = {
    'VOO': 370, 'QQQ': 250, 'BRK-B': 780, 'JPM': 490, 'NVDA': 1220,
    'PG': 345, 'VNQ': 33, 'TLT': 50, 'VWO': 80, 'GLD': 57,
}

# 依投資人屬性設定個人風險趨避係數 λ (越大越保守)
PROFILE_LAMBDA = {'保守型': 10.0, '穩健型': 5.0, '激進型': 2.0}

# 預設投資人觀點 (表單預設值，使用者可修改)
DEFAULT_VIEWS = [
    {'on': True, 'type': 'rel', 'a': 'QQQ', 'b': 'TLT', 'q': 6.0, 'c': 60},
    {'on': True, 'type': 'abs', 'a': 'NVDA', 'b': 'VOO', 'q': 20.0, 'c': 40},
    {'on': True, 'type': 'rel', 'a': 'GLD', 'b': 'VWO', 'q': 3.0, 'c': 50},
]


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
    <title>Robo-Advisor | MPT & Black-Litterman</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f6f9; font-family: 'Segoe UI', sans-serif; color: #333; }
        .header-banner { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 40px 0 20px; margin-bottom: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .card { border: none; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); margin-bottom: 30px; }
        .card-header { background-color: #ffffff; border-bottom: 2px solid #f0f2f5; font-weight: 700; font-size: 1.15rem; color: #2c3e50; }
        .btn-primary { background-color: #2979FF; border: none; padding: 12px; font-size: 1.1rem; font-weight: bold; border-radius: 8px; }
        .btn-primary:hover { background-color: #1e3c72; }
        .section-title { border-left: 6px solid #2979FF; padding-left: 12px; margin: 10px 0 25px; font-weight: 800; color: #1e3c72; }
        .formula { background: #f8f9fb; border-radius: 8px; padding: 12px 16px; font-family: 'Cambria Math', 'Times New Roman', serif; font-size: 1.02rem; }
        .view-row { background: #f8f9fb; border-radius: 10px; padding: 12px; margin-bottom: 10px; }
        table.table-sm td, table.table-sm th { font-size: 0.9rem; vertical-align: middle; }
        .best { font-weight: 700; color: #0a7d32; }
    </style>
</head>
<body>
    <div class="header-banner text-center">
        <h1 class="fw-bold mb-2">智能理財機器人 (Robo-Advisor)</h1>
        <p class="lead mb-4">動態風險評估 × MPT 均值-變異數最佳化 × Black–Litterman 模型</p>
        {% if show_results %}
        <a href="/download_csv" class="btn btn-outline-light btn-sm mb-3 me-2">⬇️ 下載歷史價格 CSV</a>
        <a href="/download_bl_csv" class="btn btn-outline-light btn-sm mb-3">⬇️ 下載 BL 模型結果 CSV</a>
        {% endif %}
    </div>

    <div class="container px-4" style="max-width: 1200px;">

        {% if not show_results %}
        <!-- ================= KYC 問卷表單區 ================= -->
        <div class="row justify-content-center">
            <div class="col-lg-9">
                <div class="card p-4">
                    <h4 class="fw-bold text-center mb-4" style="color: #2c3e50;">投資人風險屬性評估</h4>
                    <form method="POST" action="/">
                        <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label fw-bold">收入</label>
                            <select class="form-select" name="inc"><option>穩定正向</option><option>收支打平</option><option>入不敷出</option></select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label fw-bold">可投資資產</label>
                            <select class="form-select" name="ast"><option>50萬以下</option><option>50-300萬</option><option>300萬以上</option></select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label fw-bold">流動性需求</label>
                            <select class="form-select" name="liq"><option>高 (隨時需要變現)</option><option>中 (偶有資金需求)</option><option>低 (閒置資金)</option></select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label fw-bold">投資期限</label>
                            <select class="form-select" name="hor"><option>1年內</option><option>1-3年</option><option>3-10年</option><option>10年以上</option></select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label fw-bold">負債狀況</label>
                            <select class="form-select" name="lia"><option>無負債</option><option>可控負債 (如房貸)</option><option>高負債壓力</option></select>
                        </div>
                        </div>
                        <hr class="my-4">
                        <h5 class="fw-bold mb-3 text-primary">行為財務問卷</h5>
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

                        <hr class="my-4">
                        <h5 class="fw-bold mb-2 text-primary">投資人觀點 (Investor Views) — Black–Litterman 輸入</h5>
                        <p class="text-muted small mb-3">
                            絕對觀點：「A 的年化報酬率為 Q%」；相對觀點：「A 的年化報酬率將比 B 高 Q%」。
                            信心水準 (0–100%) 越高，後驗報酬越貼近您的觀點；越低則越貼近市場均衡報酬。
                        </p>
                        {% for v in views %}
                        {% set i = loop.index %}
                        <div class="view-row">
                            <div class="row g-2 align-items-end">
                                <div class="col-md-1 col-2 text-center">
                                    <label class="form-label small">啟用</label><br>
                                    <input class="form-check-input" type="checkbox" name="v{{i}}_on" value="1" {% if v.on %}checked{% endif %}>
                                </div>
                                <div class="col-md-2 col-10">
                                    <label class="form-label small">觀點類型</label>
                                    <select class="form-select form-select-sm" name="v{{i}}_type">
                                        <option value="abs" {% if v.type=='abs' %}selected{% endif %}>絕對觀點</option>
                                        <option value="rel" {% if v.type=='rel' %}selected{% endif %}>相對觀點</option>
                                    </select>
                                </div>
                                <div class="col-md-2 col-6">
                                    <label class="form-label small">資產 A</label>
                                    <select class="form-select form-select-sm" name="v{{i}}_a">
                                        {% for t in tickers %}<option {% if t==v.a %}selected{% endif %}>{{t}}</option>{% endfor %}
                                    </select>
                                </div>
                                <div class="col-md-2 col-6">
                                    <label class="form-label small">資產 B (相對觀點用)</label>
                                    <select class="form-select form-select-sm" name="v{{i}}_b">
                                        {% for t in tickers %}<option {% if t==v.b %}selected{% endif %}>{{t}}</option>{% endfor %}
                                    </select>
                                </div>
                                <div class="col-md-2 col-6">
                                    <label class="form-label small">預期報酬 / 差距 Q (%)</label>
                                    <input type="number" step="0.1" class="form-control form-control-sm" name="v{{i}}_q" value="{{v.q}}">
                                </div>
                                <div class="col-md-3 col-6">
                                    <label class="form-label small">信心水準 (%)</label>
                                    <input type="number" min="1" max="100" step="1" class="form-control form-control-sm" name="v{{i}}_c" value="{{v.c}}">
                                </div>
                            </div>
                        </div>
                        {% endfor %}

                        <button type="submit" class="btn btn-primary w-100 mt-3">生成專屬風險畫像與投資組合</button>
                    </form>
                </div>
            </div>
        </div>

        {% else %}
        <!-- ================= 分析結果儀表板區 ================= -->
        <h3 class="section-title">Part 1. 投資人畫像與 MPT 資產配置</h3>
        <div class="row mb-4">
            <div class="col-lg-4">
                <div class="card h-100 p-4 text-center" style="background-color: #1a1a2e; color: white;">
                    <h3 class="fw-bold text-white mb-2">個人化投資畫像</h3>
                    <p class="text-muted mb-4">風險承擔能力評估</p>
                    <div style="position: relative; width: 160px; height: 160px; margin: 0 auto;">
                        <svg viewBox="0 0 36 36" style="width: 160px; height: 160px; transform: rotate(-90deg);">
                            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                fill="none" stroke="#2c3e50" stroke-width="2.5" />
                            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                fill="none" stroke="{{ icon_color }}" stroke-width="3" stroke-linecap="round"
                                stroke-dasharray="{{ stroke_dash }}, 100" style="transition: stroke-dasharray 1s ease-out;" />
                        </svg>
                        <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);">
                            <svg width="65" height="65" viewBox="0 0 24 24" fill="{{ icon_color }}">
                                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                            </svg>
                        </div>
                    </div>
                    <h3 class="fw-bold mt-4 mb-4" style="color: {{ icon_color }}; letter-spacing: 2px;">{{ final_profile }}</h3>
                    <hr class="border-secondary mb-4">
                    <div class="text-start">
                        <h6 class="text-info">客觀財務風險評分</h6>
                        <p class="fw-bold fs-5">{{ baseline }}</p>
                        <h6 class="text-info mt-4">當前投資心態</h6>
                        <p class="fw-bold">{{ state }}</p>
                        <h6 class="text-info mt-4">專業投資行為建議</h6>
                        <p class="fw-bold" style="font-size: 0.95rem; color: #dcdde1;">{{ alert }}</p>
                        <h6 class="text-info mt-4">個人風險趨避係數 λ</h6>
                        <p class="fw-bold">{{ user_lambda }}</p>
                    </div>
                    <div class="text-center mt-auto pt-4">
                        <a href="/" class="btn btn-outline-light w-100">重新測驗</a>
                    </div>
                </div>
            </div>
            <div class="col-lg-8">
                <div class="card mb-4">
                    <div class="card-header">Figure 1. 效率前緣與專屬投資組合 (Efficient Frontier, 歷史資料 MPT)</div>
                    <div class="card-body p-0">{{ fig1_html | safe }}</div>
                </div>
                <div class="card">
                    <div class="card-header">Figure 2. 資產配置最佳化比例 (Optimal Asset Allocation, MPT)</div>
                    <div class="card-body p-0">{{ fig2_html | safe }}</div>
                </div>
            </div>
        </div>

        <h3 class="section-title">Part 2. Black–Litterman 模型</h3>

        <div class="row">
            <div class="col-lg-6">
                <div class="card">
                    <div class="card-header">Step 1. 市場均衡先驗報酬 (Market Equilibrium Prior)</div>
                    <div class="card-body">
                        <div class="formula mb-3">Π = δ · Σ · w<sub>mkt</sub></div>
                        <p class="small text-muted mb-2">
                            估計期間：{{ train_period }}　|　δ = {{ delta }}　|　τ = {{ tau }}　|　r<sub>f</sub> = {{ rf_pct }}
                        </p>
                        <p class="small mb-0">
                            以市值權重 w<sub>mkt</sub> 代表「市場共識」的最適配置，透過反向最佳化 (Reverse Optimization)
                            推回市場隱含的均衡超額報酬 Π，作為貝氏估計的先驗分配 (Prior)：μ ~ N(Π, τΣ)。
                        </p>
                    </div>
                </div>
            </div>
            <div class="col-lg-6">
                <div class="card">
                    <div class="card-header">Step 2–3. 投資人觀點與信心水準 (Views & Confidence)</div>
                    <div class="card-body">
                        <div class="formula mb-3">P·μ = Q + ε,　ε ~ N(0, Ω)，　Ω<sub>kk</sub> = (1−c<sub>k</sub>)/c<sub>k</sub> · τ · P<sub>k</sub>ΣP<sub>k</sub>ᵀ</div>
                        <div class="table-responsive">
                        <table class="table table-sm mb-0">
                            <thead><tr><th>#</th><th>觀點</th><th>Q</th><th>信心 c</th><th>Ω<sub>kk</sub></th></tr></thead>
                            <tbody>
                            {% for v in view_table %}
                            <tr><td>{{loop.index}}</td><td>{{v.desc}}</td><td>{{v.q}}</td><td>{{v.c}}</td><td>{{v.omega}}</td></tr>
                            {% else %}
                            <tr><td colspan="5" class="text-muted">未啟用任何觀點 → 後驗報酬 = 市場均衡報酬</td></tr>
                            {% endfor %}
                            </tbody>
                        </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Step 4. 貝氏估計後驗預期報酬 (Posterior Expected Returns)</div>
            <div class="card-body">
                <div class="formula mb-3">
                    μ<sub>BL</sub> = [ (τΣ)<sup>−1</sup> + PᵀΩ<sup>−1</sup>P ]<sup>−1</sup> [ (τΣ)<sup>−1</sup>Π + PᵀΩ<sup>−1</sup>Q ]，
                    Σ<sub>BL</sub> = Σ + [ (τΣ)<sup>−1</sup> + PᵀΩ<sup>−1</sup>P ]<sup>−1</sup>
                </div>
                {{ fig3_html | safe }}
                <div class="table-responsive mt-2">
                <table class="table table-sm table-striped text-center">
                    <thead><tr><th>資產</th><th>市值權重 w<sub>mkt</sub></th><th>歷史平均報酬 (MVO 輸入)</th><th>均衡先驗 Π + r<sub>f</sub></th><th>BL 後驗 μ<sub>BL</sub> + r<sub>f</sub></th><th>後驗 − 先驗</th></tr></thead>
                    <tbody>
                    {% for r in ret_table %}
                    <tr><td>{{r.t}}</td><td>{{r.w}}</td><td>{{r.hist}}</td><td>{{r.prior}}</td><td>{{r.post}}</td><td>{{r.diff}}</td></tr>
                    {% endfor %}
                    </tbody>
                </table>
                </div>
            </div>
        </div>

        <h3 class="section-title">Part 3. MVO vs. Black–Litterman 比較</h3>
        <div class="row">
            <div class="col-lg-6">
                <div class="card">
                    <div class="card-header">Figure 4. 最適權重比較（{{ final_profile }}, λ = {{ user_lambda }}）</div>
                    <div class="card-body p-0">{{ fig4_html | safe }}</div>
                </div>
            </div>
            <div class="col-lg-6">
                <div class="card">
                    <div class="card-header">Figure 5. 效率前緣比較 (MVO vs BL)</div>
                    <div class="card-body p-0">{{ fig5_html | safe }}</div>
                </div>
            </div>
        </div>
        <div class="card">
            <div class="card-header">配置差異摘要</div>
            <div class="card-body">
                <div class="table-responsive">
                <table class="table table-sm text-center">
                    <thead><tr><th>投資組合</th><th>預期報酬 (模型)</th><th>預期波動</th><th>最大單一權重</th><th>持有資產數 (&gt;1%)</th><th>有效資產數 1/HHI</th><th>與市值權重偏離 (TE 代理)</th></tr></thead>
                    <tbody>
                    {% for r in alloc_table %}
                    <tr><td class="fw-bold">{{r.name}}</td><td>{{r.ret}}</td><td>{{r.vol}}</td><td>{{r.maxw}}</td><td>{{r.n}}</td><td>{{r.eff}}</td><td>{{r.dev}}</td></tr>
                    {% endfor %}
                    </tbody>
                </table>
                </div>
                <ul class="mb-0">
                    {% for s in insights %}<li>{{ s }}</li>{% endfor %}
                </ul>
            </div>
        </div>

        <h3 class="section-title">Part 4. 績效分析（樣本外回測 {{ test_period }}）</h3>
        <div class="card">
            <div class="card-header">Figure 6. 樣本外累積報酬 (Out-of-Sample Cumulative Return)</div>
            <div class="card-body p-0">{{ fig6_html | safe }}</div>
        </div>
        <div class="card">
            <div class="card-header">績效指標 (Performance Metrics)</div>
            <div class="card-body">
                <div class="table-responsive">
                <table class="table table-sm table-striped text-center">
                    <thead><tr><th>投資組合</th><th>累積報酬</th><th>年化報酬</th><th>年化波動</th><th>Sharpe Ratio</th><th>Sortino Ratio</th><th>最大回撤 MDD</th></tr></thead>
                    <tbody>
                    {% for r in perf_table %}
                    <tr><td class="fw-bold">{{r.name}}</td><td>{{r.cum}}</td><td>{{r.ann}}</td><td>{{r.vol}}</td><td>{{r.sharpe}}</td><td>{{r.sortino}}</td><td>{{r.mdd}}</td></tr>
                    {% endfor %}
                    </tbody>
                </table>
                </div>
                <p class="small text-muted mb-0">
                    說明：所有模型參數僅使用估計期資料計算，再以買入持有 (Buy-and-Hold) 方式套用至測試期，避免前視偏差 (Look-ahead Bias)。
                    Sharpe = (年化報酬 − r<sub>f</sub>) / 年化波動。
                </p>
            </div>
        </div>
        {% endif %}

        <footer class="text-center mt-4 mb-5 text-muted" style="font-size: 0.85rem;">
            &copy; 2026 MPT &amp; Black–Litterman Robo-Advisor System
        </footer>
    </div>
</body>
</html>
"""


# ==========================================
# 3. 資料抓取與 MPT 運算 (前次作業)
# ==========================================
global_mpt_data = None


def get_mpt_data():
    global global_mpt_data
    if global_mpt_data is not None:
        return global_mpt_data

    df_list = []
    for t in TICKERS:
        hist_data = yf.Ticker(t).history(start=DATA_START, end=DATA_END)
        if not hist_data.empty and 'Close' in hist_data.columns:
            s = hist_data['Close'].rename(t)
            s.index = s.index.tz_localize(None)
            df_list.append(s)

    all_price = pd.concat(df_list, axis=1).ffill().dropna()
    tickers = list(all_price.columns)

    train_price = all_price[all_price.index < TRAIN_END]
    test_price = all_price[all_price.index >= TRAIN_END]

    daily_returns = train_price.pct_change().dropna()
    ann_ret = daily_returns.mean() * 252
    ann_cov = daily_returns.cov() * 252

    np.random.seed(42)
    num_portfolios = 1500
    results = np.zeros((3, num_portfolios))
    weights_record = []
    for i in range(num_portfolios):
        w = np.random.random(len(tickers))
        w /= np.sum(w)
        weights_record.append(w)
        p_ret = np.sum(w * ann_ret)
        p_std = np.sqrt(np.dot(w.T, np.dot(ann_cov, w)))
        results[0, i] = p_std
        results[1, i] = p_ret
        results[2, i] = p_ret / p_std

    idx_cons = np.argmin(results[0])
    idx_mod = np.argmax(results[2])
    high_risk_threshold = np.percentile(results[0], 90)
    high_risk_indices = np.where(results[0] >= high_risk_threshold)[0]
    idx_agg = high_risk_indices[np.argmax(results[1, high_risk_indices])]

    global_mpt_data = {
        'csv': all_price.to_csv(),
        'tickers': tickers,
        'ann_ret': ann_ret.values,
        'ann_cov': ann_cov.values,
        'test_price': test_price,
        'train_period': f"{train_price.index[0]:%Y/%m/%d} ~ {train_price.index[-1]:%Y/%m/%d}",
        'test_period': f"{test_price.index[0]:%Y/%m/%d} ~ {test_price.index[-1]:%Y/%m/%d}" if len(test_price) else "無資料",
        'results': results,
        'ports': {
            '保守型': {'risk': results[0, idx_cons], 'ret': results[1, idx_cons], 'w': weights_record[idx_cons]},
            '穩健型': {'risk': results[0, idx_mod], 'ret': results[1, idx_mod], 'w': weights_record[idx_mod]},
            '激進型': {'risk': results[0, idx_agg], 'ret': results[1, idx_agg], 'w': weights_record[idx_agg]},
        },
    }
    return global_mpt_data


# ==========================================
# 4. Black–Litterman 模型核心
# ==========================================
def project_simplex(v):
    """把向量投影到 {w >= 0, sum(w) = 1}（只做多、權重和為 1）"""
    n = len(v)
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, n + 1) > (css - 1))[0][-1]
    theta = (css[rho] - 1) / (rho + 1.0)
    return np.maximum(v - theta, 0)


def mean_variance_opt(mu, cov, lam, iters=4000):
    """
    均值-變異數最適化（只做多、全額投資）：
        max_w  wᵀμ − (λ/2) wᵀΣw   s.t. Σw = 1, w ≥ 0
    使用投影梯度法 (Projected Gradient Ascent) 求解，不需 scipy。
    """
    n = len(mu)
    w = np.ones(n) / n
    L = lam * np.max(np.linalg.eigvalsh(cov)) + 1e-12
    step = 1.0 / L
    for _ in range(iters):
        grad = mu - lam * cov @ w
        w_new = project_simplex(w + step * grad)
        if np.max(np.abs(w_new - w)) < 1e-10:
            w = w_new
            break
        w = w_new
    w[w < 1e-6] = 0
    return w / w.sum()


def parse_views(form, tickers):
    """讀取表單中的投資人觀點；GET 時回傳預設觀點"""
    views = []
    for i, dv in enumerate(DEFAULT_VIEWS, start=1):
        if form is None:
            views.append(dict(dv))
            continue
        try:
            q = float(form.get(f"v{i}_q", dv['q']))
        except ValueError:
            q = dv['q']
        try:
            c = float(form.get(f"v{i}_c", dv['c']))
        except ValueError:
            c = dv['c']
        a = form.get(f"v{i}_a", dv['a'])
        b = form.get(f"v{i}_b", dv['b'])
        views.append({
            'on': form.get(f"v{i}_on") == "1",
            'type': form.get(f"v{i}_type", dv['type']),
            'a': a if a in tickers else dv['a'],
            'b': b if b in tickers else dv['b'],
            'q': q,
            'c': min(max(c, 1), 100),
        })
    return views


def black_litterman(cov, w_mkt, views, tickers, delta=DELTA_MKT, tau=TAU, rf=RF):
    """
    回傳：
        pi      : 市場均衡超額報酬 (先驗)
        mu_bl   : BL 後驗超額報酬
        cov_bl  : BL 後驗共變異數矩陣
        P, Q, Omega, view_table
    """
    n = len(tickers)
    idx = {t: i for i, t in enumerate(tickers)}

    # Step 1. 反向最佳化求均衡先驗報酬
    pi = delta * cov @ w_mkt

    # Step 2. 建立觀點矩陣 P 與觀點向量 Q（皆以超額報酬表示）
    P_rows, Q_list, conf, view_table = [], [], [], []
    for v in views:
        if not v['on']:
            continue
        row = np.zeros(n)
        if v['type'] == 'abs':
            row[idx[v['a']]] = 1.0
            q = v['q'] / 100 - rf
            desc = f"{v['a']} 年化報酬 = {v['q']:.1f}%"
        else:
            if v['a'] == v['b']:
                continue
            row[idx[v['a']]] = 1.0
            row[idx[v['b']]] = -1.0
            q = v['q'] / 100
            desc = f"{v['a']} 報酬比 {v['b']} 高 {v['q']:.1f}%"
        P_rows.append(row)
        Q_list.append(q)
        conf.append(v['c'] / 100)
        view_table.append({'desc': desc, 'q': f"{v['q']:.1f}%", 'c': f"{v['c']:.0f}%"})

    tau_cov = tau * cov
    if not P_rows:
        return pi, pi.copy(), cov + tau_cov, None, None, None, view_table

    P = np.array(P_rows)
    Q = np.array(Q_list)

    # Step 3. 由信心水準建立觀點不確定性 Ω (Walters / Idzorek 近似)
    #   c → 100%：Ω → 0，完全相信觀點；c → 0%：Ω → ∞，忽略觀點
    c = np.clip(np.array(conf), 0.01, 0.999)
    omega_diag = (1 - c) / c * np.diag(P @ tau_cov @ P.T)
    omega_diag = np.maximum(omega_diag, 1e-10)
    Omega = np.diag(omega_diag)
    for k, vt in enumerate(view_table):
        vt['omega'] = f"{omega_diag[k]:.6f}"

    # Step 4. 貝氏更新求後驗分配
    inv_tau_cov = np.linalg.inv(tau_cov)
    inv_omega = np.diag(1 / omega_diag)
    M = np.linalg.inv(inv_tau_cov + P.T @ inv_omega @ P)
    mu_bl = M @ (inv_tau_cov @ pi + P.T @ inv_omega @ Q)
    cov_bl = cov + M
    return pi, mu_bl, cov_bl, P, Q, Omega, view_table


def efficient_frontier(mu, cov, n_points=35):
    pts = []
    for lam in np.logspace(-0.7, 2.3, n_points):
        w = mean_variance_opt(mu, cov, lam, iters=2500)
        pts.append((np.sqrt(w @ cov @ w), w @ mu))
    pts.sort()
    return np.array(pts)


def perf_metrics(daily_ret, rf=RF):
    nav = (1 + daily_ret).cumprod()
    n = len(daily_ret)
    cum = nav.iloc[-1] - 1
    ann = (1 + cum) ** (252 / n) - 1
    vol = daily_ret.std() * np.sqrt(252)
    downside = daily_ret[daily_ret < 0].std() * np.sqrt(252)
    mdd = (nav / nav.cummax() - 1).min()
    return {
        'cum': cum, 'ann': ann, 'vol': vol,
        'sharpe': (ann - rf) / vol if vol > 0 else np.nan,
        'sortino': (ann - rf) / downside if downside > 0 else np.nan,
        'mdd': mdd, 'nav': nav,
    }


def pct(x, d=2):
    return f"{x * 100:.{d}f}%"


# ==========================================
# 5. 路由設定
# ==========================================
last_bl_result = {}


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template_string(HTML_TEMPLATE, show_results=False,
                                      views=parse_views(None, TICKERS), tickers=TICKERS)

    try:
        # ---------- 1. KYC 計分 ----------
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

        state, alert, logic_flag = analyze_nlp(d.get("q1", ""), d.get("q2", ""), d.get("q3", ""))
        final_profile = baseline
        if logic_flag == "保守":
            final_profile = "保守型"

        if final_profile == "保守型":
            icon_color, stroke_dash = "#00BFFF", "33"
        elif final_profile == "穩健型":
            icon_color, stroke_dash = "#FFB300", "66"
        else:
            icon_color, stroke_dash = "#FF5252", "100"
        user_lambda = PROFILE_LAMBDA[final_profile]

        # ---------- 2. MPT (前次作業) ----------
        mpt = get_mpt_data()
        tickers = mpt['tickers']
        res = mpt['results']
        ports = mpt['ports']

        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=res[0, :], y=res[1, :], mode='markers',
                                  marker=dict(color=res[2, :], colorscale='Viridis', size=4, showscale=True),
                                  name='投資機會集合'))
        colors = {'保守型': 'blue', '穩健型': 'orange', '激進型': 'red'}
        for name, data in ports.items():
            size = 20 if name == final_profile else 10
            sym = 'star' if name == final_profile else 'circle'
            fig1.add_trace(go.Scatter(
                x=[data['risk']], y=[data['ret']], mode='markers+text',
                marker=dict(color=colors[name], size=size, symbol=sym, line=dict(color='black', width=1)),
                text=[name], textposition='top center',
                textfont=dict(color=colors[name], size=14), name=name))
        fig1.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=400, showlegend=False,
                           xaxis_title="風險 (年化波動率)", yaxis_title="預期報酬率")
        fig1_html = fig1.to_html(full_html=False, include_plotlyjs='cdn')

        fig2 = go.Figure()
        labels = ['保守型', '穩健型', '激進型']
        for i, ticker in enumerate(tickers):
            y_vals = [ports[label]['w'][i] * 100 for label in labels]
            text_vals = [f"{ticker} {v:.1f}%" if v > 4 else "" for v in y_vals]
            fig2.add_trace(go.Bar(name=ticker, x=labels, y=y_vals, text=text_vals, textposition='inside'))
        fig2.update_layout(barmode='stack', margin=dict(l=20, r=20, t=20, b=20), height=350,
                           legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
        fig2_html = fig2.to_html(full_html=False, include_plotlyjs=False)

        # ---------- 3. Black–Litterman ----------
        cov = mpt['ann_cov']
        mu_hist = mpt['ann_ret']                       # 歷史平均報酬 (總報酬)
        cap = np.array([MARKET_CAP.get(t, 1) for t in tickers], dtype=float)
        w_mkt = cap / cap.sum()

        views = parse_views(d, tickers)
        pi, mu_bl, cov_bl, P, Q, Omega, view_table = black_litterman(cov, w_mkt, views, tickers)

        # 最適權重：MVO 用歷史報酬 + 樣本共變異；BL 用後驗報酬 + 後驗共變異
        w_mvo = mean_variance_opt(mu_hist - RF, cov, user_lambda)
        w_bl = mean_variance_opt(mu_bl, cov_bl, user_lambda)

        ret_table = [{
            't': t, 'w': pct(w_mkt[i], 1), 'hist': pct(mu_hist[i]),
            'prior': pct(pi[i] + RF), 'post': pct(mu_bl[i] + RF),
            'diff': f"{(mu_bl[i] - pi[i]) * 100:+.2f}%",
        } for i, t in enumerate(tickers)]

        # Figure 3. 報酬估計比較
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(name='歷史平均報酬 (MVO)', x=tickers, y=mu_hist * 100, marker_color='#B0BEC5'))
        fig3.add_trace(go.Bar(name='均衡先驗 Π', x=tickers, y=(pi + RF) * 100, marker_color='#64B5F6'))
        fig3.add_trace(go.Bar(name='BL 後驗 μ_BL', x=tickers, y=(mu_bl + RF) * 100, marker_color='#1E3C72'))
        fig3.update_layout(barmode='group', height=380, margin=dict(l=20, r=20, t=30, b=20),
                           title=dict(text="Figure 3. 預期報酬率估計比較 (%)", font=dict(size=14)),
                           yaxis_title="年化預期報酬 (%)",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig3_html = fig3.to_html(full_html=False, include_plotlyjs=False)

        # Figure 4. 權重比較
        fig4 = go.Figure()
        for name, w, col in [('市值權重', w_mkt, '#90A4AE'), ('MVO', w_mvo, '#FF7043'), ('Black–Litterman', w_bl, '#1E3C72')]:
            fig4.add_trace(go.Bar(name=name, x=tickers, y=w * 100, marker_color=col,
                                  text=[f"{v * 100:.0f}" if v > 0.03 else "" for v in w], textposition='outside'))
        fig4.update_layout(barmode='group', height=380, margin=dict(l=20, r=20, t=20, b=20),
                           yaxis_title="權重 (%)",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig4_html = fig4.to_html(full_html=False, include_plotlyjs=False)

        # Figure 5. 效率前緣比較
        ef_mvo = efficient_frontier(mu_hist - RF, cov)
        ef_bl = efficient_frontier(mu_bl, cov_bl)
        fig5 = go.Figure()
        fig5.add_trace(go.Scatter(x=ef_mvo[:, 0] * 100, y=(ef_mvo[:, 1] + RF) * 100, mode='lines',
                                  name='MVO 效率前緣 (歷史報酬)', line=dict(color='#FF7043', width=3)))
        fig5.add_trace(go.Scatter(x=ef_bl[:, 0] * 100, y=(ef_bl[:, 1] + RF) * 100, mode='lines',
                                  name='BL 效率前緣 (後驗報酬)', line=dict(color='#1E3C72', width=3)))
        for name, w, mu_, cv, col in [('MVO 最適', w_mvo, mu_hist - RF, cov, '#FF7043'),
                                      ('BL 最適', w_bl, mu_bl, cov_bl, '#1E3C72')]:
            fig5.add_trace(go.Scatter(x=[np.sqrt(w @ cv @ w) * 100], y=[(w @ mu_ + RF) * 100],
                                      mode='markers+text', text=[name], textposition='top left',
                                      marker=dict(size=16, symbol='star', color=col, line=dict(color='black', width=1)),
                                      showlegend=False))
        w_m_vol = np.sqrt(w_mkt @ cov_bl @ w_mkt)
        fig5.add_trace(go.Scatter(x=[w_m_vol * 100], y=[(w_mkt @ mu_bl + RF) * 100], mode='markers+text',
                                  text=['市值組合'], textposition='bottom right',
                                  marker=dict(size=12, color='#90A4AE', line=dict(color='black', width=1)),
                                  showlegend=False))
        fig5.update_layout(height=380, margin=dict(l=20, r=20, t=20, b=20),
                           xaxis_title="年化波動率 (%)", yaxis_title="年化預期報酬 (%)",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig5_html = fig5.to_html(full_html=False, include_plotlyjs=False)

        # 配置差異摘要
        def alloc_row(name, w, mu_, cv):
            return {
                'name': name, 'ret': pct(w @ mu_ + RF), 'vol': pct(np.sqrt(w @ cv @ w)),
                'maxw': f"{tickers[int(np.argmax(w))]} {pct(w.max(), 1)}",
                'n': int((w > 0.01).sum()), 'eff': f"{1 / np.sum(w ** 2):.2f}",
                'dev': pct(np.sum(np.abs(w - w_mkt)) / 2, 1),
            }
        alloc_table = [
            alloc_row('市值權重 (均衡)', w_mkt, pi, cov),
            alloc_row('MVO', w_mvo, mu_hist - RF, cov),
            alloc_row('Black–Litterman', w_bl, mu_bl, cov_bl),
        ]

        insights = []
        insights.append(
            f"MVO 直接使用歷史平均報酬，最大權重集中在 {tickers[int(np.argmax(w_mvo))]}（{pct(w_mvo.max(), 1)}），"
            f"有效資產數僅 {1 / np.sum(w_mvo ** 2):.1f} 檔，反映出 MVO 對預期報酬估計誤差高度敏感、容易產生極端配置的問題。")
        insights.append(
            f"Black–Litterman 以市場均衡為錨點，只在有觀點的資產上做偏離，有效資產數為 {1 / np.sum(w_bl ** 2):.1f} 檔，"
            f"與市值權重的偏離度為 {pct(np.sum(np.abs(w_bl - w_mkt)) / 2, 1)}（MVO 為 {pct(np.sum(np.abs(w_mvo - w_mkt)) / 2, 1)}），配置較分散且直覺。")
        if view_table:
            moved = sorted(range(len(tickers)), key=lambda i: -abs(mu_bl[i] - pi[i]))[:3]
            insights.append("觀點對後驗報酬影響最大的資產：" + "、".join(
                f"{tickers[i]}（{(mu_bl[i] - pi[i]) * 100:+.2f}%）" for i in moved) +
                "。信心水準越高，Ω 越小，後驗報酬越往觀點 Q 移動。")
        else:
            insights.append("未啟用任何觀點，BL 後驗報酬等於均衡先驗報酬，最適配置會接近市值權重（再依個人 λ 調整風險）。")

        # ---------- 4. 樣本外績效回測 ----------
        test_price = mpt['test_price']
        perf_table, fig6_html = [], "<p class='p-3 text-muted'>測試期無資料</p>"
        if len(test_price) > 5:
            test_ret = test_price[tickers].pct_change().dropna()
            n = len(tickers)
            strategies = {
                'Black–Litterman': (w_bl, '#1E3C72'),
                'MVO': (w_mvo, '#FF7043'),
                f'MPT 隨機模擬 ({final_profile})': (np.array(ports[final_profile]['w']), '#AB47BC'),
                '市值權重': (w_mkt, '#90A4AE'),
                '等權重 1/N': (np.ones(n) / n, '#66BB6A'),
            }
            fig6 = go.Figure()
            for name, (w, col) in strategies.items():
                # 買入持有：期初依權重配置，之後不再平衡
                nav = (test_price[tickers] / test_price[tickers].iloc[0]) @ w
                daily = nav.pct_change().dropna()
                m = perf_metrics(daily)
                perf_table.append({
                    'name': name, 'cum': pct(m['cum']), 'ann': pct(m['ann']), 'vol': pct(m['vol']),
                    'sharpe': f"{m['sharpe']:.2f}", 'sortino': f"{m['sortino']:.2f}", 'mdd': pct(m['mdd']),
                })
                fig6.add_trace(go.Scatter(x=nav.index, y=(nav - 1) * 100, mode='lines', name=name,
                                          line=dict(color=col, width=3 if name in ('Black–Litterman', 'MVO') else 1.8)))
            fig6.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20),
                               yaxis_title="累積報酬 (%)",
                               legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            fig6_html = fig6.to_html(full_html=False, include_plotlyjs=False)

        # 儲存結果供 CSV 下載
        last_bl_result['df'] = pd.DataFrame({
            'ticker': tickers,
            'market_weight': w_mkt,
            'hist_mean_return': mu_hist,
            'prior_return_pi_plus_rf': pi + RF,
            'posterior_return_bl_plus_rf': mu_bl + RF,
            'weight_mvo': w_mvo,
            'weight_bl': w_bl,
        })

        return render_template_string(
            HTML_TEMPLATE, show_results=True, baseline=baseline, state=state, alert=alert,
            final_profile=final_profile, icon_color=icon_color, stroke_dash=stroke_dash,
            user_lambda=user_lambda,
            fig1_html=fig1_html, fig2_html=fig2_html, fig3_html=fig3_html,
            fig4_html=fig4_html, fig5_html=fig5_html, fig6_html=fig6_html,
            train_period=mpt['train_period'], test_period=mpt['test_period'],
            delta=DELTA_MKT, tau=TAU, rf_pct=pct(RF, 1),
            view_table=view_table, ret_table=ret_table, alloc_table=alloc_table,
            insights=insights, perf_table=perf_table,
        )

    except Exception:
        return f"<h2>系統運算錯誤</h2><pre>{traceback.format_exc()}</pre>"


@app.route('/download_csv')
def download_csv():
    mpt = get_mpt_data()
    return Response(mpt['csv'], mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=stock_data.csv"})


@app.route('/download_bl_csv')
def download_bl_csv():
    if 'df' not in last_bl_result:
        return "請先在首頁完成問卷並產生 Black–Litterman 結果。", 400
    return Response(last_bl_result['df'].to_csv(index=False), mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=black_litterman_result.csv"})


if __name__ == '__main__':
    app.run(debug=True)

from flask import Flask, request, render_template_string, Response
from collections import deque
import io
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
BENCHMARK = 'VOO'

DATA_START = "2015-01-01"     # 回測起點 (約 10 年歷史)
TRAIN_START = "2018-01-01"    # 模型估計期起點 (與前次作業相同)
TRAIN_END = "2024-01-01"      # 估計期 2018/01 ~ 2023/12；之後為樣本外測試期
DATA_END = None               # None = 抓到最新資料

RF = 0.02         # 無風險利率 (年化)
TAU = 0.05        # BL 模型 τ
DELTA_MKT = 2.5   # 市場風險趨避係數 δ
FX_FALLBACK = 31.5  # 抓不到匯率時使用的 USD/TWD

# 市場均衡權重：2023 年底「市值 / ETF 資產規模」約略值 (十億美元)
MARKET_CAP = {
    'VOO': 370, 'QQQ': 250, 'BRK-B': 780, 'JPM': 490, 'NVDA': 1220,
    'PG': 345, 'VNQ': 33, 'TLT': 50, 'VWO': 80, 'GLD': 57,
}

PROFILE_LAMBDA = {'保守型': 10.0, '穩健型': 5.0, '激進型': 2.0}

DEFAULT_VIEWS = [
    {'on': True, 'type': 'rel', 'a': 'QQQ', 'b': 'TLT', 'q': 6.0, 'c': 60},
    {'on': True, 'type': 'abs', 'a': 'NVDA', 'b': 'VOO', 'q': 20.0, 'c': 40},
    {'on': True, 'type': 'rel', 'a': 'GLD', 'b': 'VWO', 'q': 3.0, 'c': 50},
]

# 目標試算與台灣投資人成本預設值
DEFAULT_PLAN = {
    'init_twd': 300000, 'monthly_twd': 10000, 'target_twd': 3000000, 'years': 5,
    'tax': 30.0, 'fee': 3.0, 'fxc': 0.1,
}

DISCLAIMER = ("本網站為課程作業與學習用途，所有模型結果、回測與試算皆基於歷史資料與假設參數，"
              "不代表未來績效，亦不構成任何投資建議或要約。投資有風險，請依自身狀況審慎評估。")


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
HEAD = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Robo-Advisor | MPT & Black-Litterman</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
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
        .kpi { background: #f8f9fb; border-radius: 10px; padding: 16px; text-align: center; height: 100%; }
        .kpi .v { font-size: 1.6rem; font-weight: 800; color: #1e3c72; }
        .kpi .l { font-size: 0.85rem; color: #6c757d; }
        .disclaimer { background: #fff8e1; border-left: 5px solid #ffb300; border-radius: 8px; padding: 12px 16px; font-size: 0.9rem; }
        details summary { cursor: pointer; font-weight: 700; color: #2979FF; }
    </style>
</head>
<body>
"""

FOOTER = """
        <div class="disclaimer mt-4">⚠️ <b>免責聲明：</b>{{ disclaimer }}</div>
        <footer class="text-center mt-4 mb-5 text-muted" style="font-size: 0.85rem;">
            &copy; 2026 MPT &amp; Black–Litterman Robo-Advisor System
        </footer>
    </div>
</body>
</html>
"""

HTML_TEMPLATE = HEAD + """
    <div class="header-banner text-center">
        <h1 class="fw-bold mb-2">智能理財機器人 (Robo-Advisor)</h1>
        <p class="lead mb-4">動態風險評估 × MPT × Black–Litterman × 回測與目標試算</p>
        {% if show_results %}
        <a href="/download_csv" class="btn btn-outline-light btn-sm mb-3 me-2">⬇️ 下載歷史價格 CSV</a>
        <a href="/download_bl_csv" class="btn btn-outline-light btn-sm mb-3 me-2">⬇️ 下載 BL 模型結果 CSV</a>
        {% endif %}
        <a href="/journal" class="btn btn-outline-light btn-sm mb-3">📒 交易日誌分析</a>
    </div>

    <div class="container px-4" style="max-width: 1200px;">

        {% if not show_results %}
        <!-- ================= 問卷表單區 ================= -->
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
                            絕對觀點：「A 的年化報酬率為 Q%」（資產 B 不使用）；相對觀點：「A 的年化報酬率將比 B 高 Q%」。
                            信心水準越高，後驗報酬越貼近您的觀點；越低則越貼近市場均衡報酬。
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

                        <hr class="my-4">
                        <h5 class="fw-bold mb-2 text-primary">理財目標與台灣投資人真實成本</h5>
                        <p class="text-muted small mb-3">用於歷史回測、蒙地卡羅目標試算與稅費計算。手續費依各券商複委託方案而異，請改成您自己的券商費率。</p>
                        <div class="row g-3">
                            <div class="col-md-3 col-6"><label class="form-label small fw-bold">初始投入 (TWD)</label>
                                <input type="number" min="0" step="1000" class="form-control" name="init_twd" value="{{plan.init_twd}}"></div>
                            <div class="col-md-3 col-6"><label class="form-label small fw-bold">每月定期定額 (TWD)</label>
                                <input type="number" min="0" step="1000" class="form-control" name="monthly_twd" value="{{plan.monthly_twd}}"></div>
                            <div class="col-md-3 col-6"><label class="form-label small fw-bold">目標金額 (TWD)</label>
                                <input type="number" min="0" step="10000" class="form-control" name="target_twd" value="{{plan.target_twd}}"></div>
                            <div class="col-md-3 col-6"><label class="form-label small fw-bold">目標年限 (年)</label>
                                <input type="number" min="1" max="40" step="1" class="form-control" name="years" value="{{plan.years}}"></div>
                            <div class="col-md-4 col-6"><label class="form-label small fw-bold">美股股利預扣稅率 (%)</label>
                                <input type="number" min="0" max="50" step="0.5" class="form-control" name="tax" value="{{plan.tax}}"></div>
                            <div class="col-md-4 col-6"><label class="form-label small fw-bold">複委託每筆手續費 (USD)</label>
                                <input type="number" min="0" step="0.5" class="form-control" name="fee" value="{{plan.fee}}"></div>
                            <div class="col-md-4 col-12"><label class="form-label small fw-bold">換匯成本 / 匯差 (%)</label>
                                <input type="number" min="0" step="0.05" class="form-control" name="fxc" value="{{plan.fxc}}"></div>
                        </div>

                        <details class="mt-4">
                            <summary>目前持股（選填，填寫後產生再平衡與本月定投建議）</summary>
                            <p class="text-muted small mt-2">請填入各資產目前的市值（美元），沒有持有的留空即可。</p>
                            <div class="row g-2">
                                {% for t in tickers %}
                                <div class="col-md-2 col-4"><label class="form-label small">{{t}} (USD)</label>
                                    <input type="number" min="0" step="1" class="form-control form-control-sm" name="h_{{t}}"></div>
                                {% endfor %}
                            </div>
                        </details>

                        <button type="submit" class="btn btn-primary w-100 mt-4">生成專屬風險畫像與投資組合</button>
                    </form>
                </div>
            </div>
        </div>

        {% else %}
        <div class="disclaimer mb-4">⚠️ <b>免責聲明：</b>{{ disclaimer }}</div>

        <!-- ================= Part 1 ================= -->
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

        <!-- ================= Part 2 ================= -->
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

        <!-- ================= Part 3 ================= -->
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
                    <thead><tr><th>投資組合</th><th>預期報酬 (模型)</th><th>預期波動</th><th>最大單一權重</th><th>持有資產數 (&gt;1%)</th><th>有效資產數 1/HHI</th><th>與市值權重偏離</th></tr></thead>
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

        <!-- ================= Part 4 ================= -->
        <h3 class="section-title">Part 4. 績效分析（樣本外回測 {{ test_period }}）</h3>
        <div class="card">
            <div class="card-header">Figure 6. 樣本外累積報酬 (Out-of-Sample Cumulative Return, USD)</div>
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
                    模型參數僅使用估計期資料計算，再以買入持有方式套用至測試期，避免前視偏差 (Look-ahead Bias)。Sharpe = (年化報酬 − r<sub>f</sub>) / 年化波動。
                </p>
            </div>
        </div>

        <!-- ================= Part 5 ================= -->
        <h3 class="section-title">Part 5. 長期歷史回測 vs. VOO（含台灣投資人真實成本）</h3>
        <div class="card">
            <div class="card-header">Figure 7. 單筆投入 {{ init_twd_fmt }} 的累積報酬（{{ bt_period }}，新台幣計價、每年再平衡）</div>
            <div class="card-body p-0">{{ fig7_html | safe }}</div>
        </div>
        <div class="card">
            <div class="card-header">回測績效：這個配置過去表現如何、最慘會跌多少？</div>
            <div class="card-body">
                <div class="table-responsive">
                <table class="table table-sm table-striped text-center">
                    <thead><tr><th>投資組合</th><th>累積報酬</th><th>年化報酬 CAGR</th><th>年化波動</th><th>Sharpe</th><th>最大回撤 MDD</th><th>最差年度</th><th>最慘時帳面虧損</th></tr></thead>
                    <tbody>
                    {% for r in bt_table %}
                    <tr><td class="fw-bold">{{r.name}}</td><td>{{r.cum}}</td><td>{{r.ann}}</td><td>{{r.vol}}</td><td>{{r.sharpe}}</td><td>{{r.mdd}}</td><td>{{r.worst}}</td><td>{{r.loss}}</td></tr>
                    {% endfor %}
                    </tbody>
                </table>
                </div>
                <ul class="mb-0 small">
                    {% for s in bt_notes %}<li>{{ s }}</li>{% endfor %}
                </ul>
            </div>
        </div>
        <div class="row">
            <div class="col-lg-7">
                <div class="card">
                    <div class="card-header">Figure 8. 定期定額回測：初始 {{ init_twd_fmt }} + 每月 {{ monthly_twd_fmt }}</div>
                    <div class="card-body p-0">{{ fig8_html | safe }}</div>
                </div>
            </div>
            <div class="col-lg-5">
                <div class="card">
                    <div class="card-header">台灣投資人真實成本拆解（推薦組合）</div>
                    <div class="card-body">
                        <table class="table table-sm mb-3">
                            <tbody>
                            {% for r in cost_table %}
                            <tr><td>{{r.k}}</td><td class="text-end fw-bold">{{r.v}}</td></tr>
                            {% endfor %}
                            </tbody>
                        </table>
                        <ul class="small mb-0">
                            {% for s in cost_tips %}<li>{{ s }}</li>{% endfor %}
                        </ul>
                    </div>
                </div>
            </div>
        </div>

        <!-- ================= Part 6 ================= -->
        <h3 class="section-title">Part 6. 目標試算（蒙地卡羅模擬 {{ mc_n }} 種市場情境）</h3>
        <div class="row g-3 mb-4">
            <div class="col-md-3 col-6"><div class="kpi"><div class="v">{{ mc.prob }}</div><div class="l">{{ mc.years }} 年後達成 {{ target_twd_fmt }} 的機率<br>（推薦組合）</div></div></div>
            <div class="col-md-3 col-6"><div class="kpi"><div class="v">{{ mc.median }}</div><div class="l">終值中位數</div></div></div>
            <div class="col-md-3 col-6"><div class="kpi"><div class="v">{{ mc.p10 }}</div><div class="l">悲觀情境（第 10 百分位）</div></div></div>
            <div class="col-md-3 col-6"><div class="kpi"><div class="v">{{ mc.prob_voo }}</div><div class="l">對照：全部買 VOO 的達成機率</div></div></div>
        </div>
        <div class="card">
            <div class="card-header">Figure 9. 資產成長模擬區間（第 10 / 50 / 90 百分位）</div>
            <div class="card-body p-0">{{ fig9_html | safe }}</div>
        </div>
        <div class="card">
            <div class="card-header">每個月要投入多少才夠？</div>
            <div class="card-body">
                <div class="table-responsive">
                <table class="table table-sm text-center">
                    <thead><tr><th>想要的達成機率</th><th>每月需投入 (TWD)</th><th>與目前設定 {{ monthly_twd_fmt }} 相比</th></tr></thead>
                    <tbody>
                    {% for r in mc.req %}
                    <tr><td class="fw-bold">{{r.p}}</td><td>{{r.c}}</td><td>{{r.diff}}</td></tr>
                    {% endfor %}
                    </tbody>
                </table>
                </div>
                <p class="small text-muted mb-0">
                    假設：推薦組合年化預期報酬 {{ mc.mu }}（BL 後驗報酬扣除股利預扣稅）、年化波動 {{ mc.sigma }}，月報酬服從對數常態分配；
                    已扣除每次投入的換匯成本與複委託手續費，未考慮匯率波動與再平衡費用。
                </p>
            </div>
        </div>

        <!-- ================= Part 7 ================= -->
        <h3 class="section-title">Part 7. 再平衡與本月定投建議</h3>
        <div class="card">
            <div class="card-body">
                {% if rebal %}
                <p class="mb-2">目前總市值 <b>{{ rebal.total }}</b>，本月可投入約 <b>{{ rebal.contrib }}</b>（{{ monthly_twd_fmt }} 扣除匯差後）。只買不賣的再平衡建議：</p>
                <div class="table-responsive">
                <table class="table table-sm table-striped text-center">
                    <thead><tr><th>資產</th><th>目前市值</th><th>目前比例</th><th>目標比例</th><th>差距</th><th>方案 A：依缺口比例買入</th><th>方案 B：集中補足（省手續費）</th><th>買入後比例 (B)</th></tr></thead>
                    <tbody>
                    {% for r in rebal.rows %}
                    <tr><td class="fw-bold">{{r.t}}</td><td>{{r.cur}}</td><td>{{r.cur_w}}</td><td>{{r.tgt_w}}</td><td>{{r.gap}}</td><td>{{r.buy_a}}</td><td>{{r.buy_b}}</td><td>{{r.after}}</td></tr>
                    {% endfor %}
                    </tbody>
                </table>
                </div>
                <ul class="small mb-0">
                    {% for s in rebal.notes %}<li>{{ s }}</li>{% endfor %}
                </ul>
                {% else %}
                <p class="text-muted mb-0">尚未填寫目前持股。回到首頁展開「目前持股」並填入各資產市值，即可得到與目標配置的差距，以及本月定期定額該買哪一檔。</p>
                {% endif %}
            </div>
        </div>
        {% endif %}
""" + FOOTER


JOURNAL_TEMPLATE = HEAD + """
    <div class="header-banner text-center">
        <h1 class="fw-bold mb-2">交易日誌分析</h1>
        <p class="lead mb-4">上傳交易紀錄 → 勝率、平均賺賠、持有天數，並與同期 VOO 比較</p>
        <a href="/" class="btn btn-outline-light btn-sm mb-3">← 回到理財機器人</a>
    </div>
    <div class="container px-4" style="max-width: 1100px;">
        <div class="card p-4">
            <form method="POST" action="/journal" enctype="multipart/form-data">
                <label class="form-label fw-bold">上傳交易紀錄 CSV</label>
                <input class="form-control mb-2" type="file" name="file" accept=".csv" required>
                <p class="small text-muted mb-3">
                    欄位：<code>date, ticker, action, shares, price, fee</code>（action 填 BUY / SELL，fee 可省略，金額單位一致即可）。
                    賣出以先進先出 (FIFO) 配對買進。<a href="/journal/sample">下載範例 CSV</a>
                </p>
                <button class="btn btn-primary w-100">開始分析</button>
            </form>
        </div>

        {% if error %}
        <div class="alert alert-danger">{{ error }}</div>
        {% endif %}

        {% if stats %}
        <div class="row g-3 mb-4">
            {% for k in stats %}
            <div class="col-md-3 col-6"><div class="kpi"><div class="v">{{k.v}}</div><div class="l">{{k.l}}</div></div></div>
            {% endfor %}
        </div>
        <div class="card">
            <div class="card-header">每筆已實現交易報酬 vs. 同期持有 VOO</div>
            <div class="card-body p-0">{{ fig_a | safe }}</div>
        </div>
        <div class="card">
            <div class="card-header">累積已實現損益</div>
            <div class="card-body p-0">{{ fig_b | safe }}</div>
        </div>
        <div class="card">
            <div class="card-header">已實現交易明細</div>
            <div class="card-body">
                <div class="table-responsive">
                <table class="table table-sm table-striped text-center">
                    <thead><tr><th>標的</th><th>買進日</th><th>賣出日</th><th>股數</th><th>成本價</th><th>賣出價</th><th>損益</th><th>報酬率</th><th>同期 VOO</th><th>持有天數</th></tr></thead>
                    <tbody>
                    {% for r in trades %}
                    <tr><td>{{r.ticker}}</td><td>{{r.buy}}</td><td>{{r.sell}}</td><td>{{r.shares}}</td><td>{{r.cost}}</td><td>{{r.px}}</td><td>{{r.pnl}}</td><td>{{r.ret}}</td><td>{{r.voo}}</td><td>{{r.days}}</td></tr>
                    {% endfor %}
                    </tbody>
                </table>
                </div>
                {% for w in warnings %}<p class="small text-danger mb-1">⚠️ {{ w }}</p>{% endfor %}
                {% if open_pos %}<p class="small text-muted mb-0">尚未平倉部位：{{ open_pos }}</p>{% endif %}
            </div>
        </div>
        {% endif %}
""" + FOOTER


# ==========================================
# 3. 資料抓取與 MPT 運算
# ==========================================
global_mpt_data = None


def get_mpt_data():
    global global_mpt_data
    if global_mpt_data is not None:
        return global_mpt_data

    adj_list, close_list, div_list = [], [], []
    for t in TICKERS:
        h = yf.Ticker(t).history(start=DATA_START, end=DATA_END, auto_adjust=False)
        if h.empty:
            continue
        h.index = h.index.tz_localize(None)
        adj_col = 'Adj Close' if 'Adj Close' in h.columns else 'Close'
        adj_list.append(h[adj_col].rename(t))
        close_list.append(h['Close'].rename(t))
        div_list.append((h['Dividends'] if 'Dividends' in h.columns else h['Close'] * 0).rename(t))

    all_price = pd.concat(adj_list, axis=1).ffill().dropna()          # 還原權值價格 (含息總報酬)
    raw_close = pd.concat(close_list, axis=1).reindex(all_price.index).ffill()
    divs = pd.concat(div_list, axis=1).reindex(all_price.index).fillna(0)
    div_yield = (divs / raw_close.shift(1)).fillna(0)               # 每日現金股利殖利率 (除息日)
    tickers = list(all_price.columns)

    # 匯率 USD/TWD
    try:
        fx_h = yf.Ticker("TWD=X").history(start=DATA_START, end=DATA_END)
        fx_h.index = fx_h.index.tz_localize(None)
        fx = fx_h['Close'].reindex(all_price.index, method='ffill').bfill()
        if fx.isna().any() or fx.empty:
            raise ValueError
    except Exception:
        fx = pd.Series(FX_FALLBACK, index=all_price.index)

    train_mask = (all_price.index >= TRAIN_START) & (all_price.index < TRAIN_END)
    train_price = all_price[train_mask]
    test_price = all_price[all_price.index >= TRAIN_END]

    daily_returns = train_price.pct_change().dropna()
    ann_ret = daily_returns.mean() * 252
    ann_cov = daily_returns.cov() * 252
    train_years = len(train_price) / 252
    ann_div_yield = div_yield[train_mask].sum() / train_years       # 年化現金殖利率

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
        'all_price': all_price,
        'div_yield': div_yield,
        'ann_div_yield': ann_div_yield.values,
        'fx': fx,
        'ann_ret': ann_ret.values,
        'ann_cov': ann_cov.values,
        'test_price': test_price,
        'train_period': f"{train_price.index[0]:%Y/%m/%d} ~ {train_price.index[-1]:%Y/%m/%d}",
        'test_period': f"{test_price.index[0]:%Y/%m/%d} ~ {test_price.index[-1]:%Y/%m/%d}" if len(test_price) else "無資料",
        'bt_period': f"{all_price.index[0]:%Y/%m} ~ {all_price.index[-1]:%Y/%m}",
        'results': results,
        'ports': {
            '保守型': {'risk': results[0, idx_cons], 'ret': results[1, idx_cons], 'w': weights_record[idx_cons]},
            '穩健型': {'risk': results[0, idx_mod], 'ret': results[1, idx_mod], 'w': weights_record[idx_mod]},
            '激進型': {'risk': results[0, idx_agg], 'ret': results[1, idx_agg], 'w': weights_record[idx_agg]},
        },
    }
    return global_mpt_data


# ==========================================
# 4. Black–Litterman 模型與最佳化
# ==========================================
def project_simplex(v):
    """投影到 {w >= 0, sum(w) = 1}"""
    n = len(v)
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, n + 1) > (css - 1))[0][-1]
    theta = (css[rho] - 1) / (rho + 1.0)
    return np.maximum(v - theta, 0)


def mean_variance_opt(mu, cov, lam, iters=4000, w0=None):
    """max wᵀμ − (λ/2) wᵀΣw, s.t. Σw=1, w≥0；投影梯度法"""
    n = len(mu)
    w = np.ones(n) / n if w0 is None else w0.copy()
    step = 1.0 / (lam * np.max(np.linalg.eigvalsh(cov)) + 1e-12)
    for _ in range(iters):
        w_new = project_simplex(w + step * (mu - lam * cov @ w))
        if np.max(np.abs(w_new - w)) < 1e-9:
            w = w_new
            break
        w = w_new
    w = np.where(w < 1e-6, 0, w)
    return w / w.sum()


def parse_views(form, tickers):
    views = []
    for i, dv in enumerate(DEFAULT_VIEWS, start=1):
        if form is None:
            views.append(dict(dv))
            continue
        q = fnum(form, f"v{i}_q", dv['q'])
        c = fnum(form, f"v{i}_c", dv['c'])
        a = form.get(f"v{i}_a", dv['a'])
        b = form.get(f"v{i}_b", dv['b'])
        views.append({
            'on': form.get(f"v{i}_on") == "1",
            'type': form.get(f"v{i}_type", dv['type']),
            'a': a if a in tickers else dv['a'],
            'b': b if b in tickers else dv['b'],
            'q': q, 'c': min(max(c, 1), 100),
        })
    return views


def black_litterman(cov, w_mkt, views, tickers, delta=DELTA_MKT, tau=TAU, rf=RF):
    n = len(tickers)
    idx = {t: i for i, t in enumerate(tickers)}
    pi = delta * cov @ w_mkt

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
        return pi, pi.copy(), cov + tau_cov, view_table

    P = np.array(P_rows)
    Q = np.array(Q_list)
    c = np.clip(np.array(conf), 0.01, 0.999)
    omega_diag = np.maximum((1 - c) / c * np.diag(P @ tau_cov @ P.T), 1e-10)
    for k, vt in enumerate(view_table):
        vt['omega'] = f"{omega_diag[k]:.6f}"

    inv_tau_cov = np.linalg.inv(tau_cov)
    inv_omega = np.diag(1 / omega_diag)
    M = np.linalg.inv(inv_tau_cov + P.T @ inv_omega @ P)
    mu_bl = M @ (inv_tau_cov @ pi + P.T @ inv_omega @ Q)
    return pi, mu_bl, cov + M, view_table


def efficient_frontier(mu, cov, n_points=25):
    pts, w = [], None
    for lam in np.logspace(2.3, -0.7, n_points):   # 由保守到積極，暖啟動加速
        w = mean_variance_opt(mu, cov, lam, iters=2000, w0=w)
        pts.append((np.sqrt(w @ cov @ w), w @ mu))
    pts.sort()
    return np.array(pts)


# ==========================================
# 5. 績效、回測、蒙地卡羅、再平衡
# ==========================================
def perf_metrics(daily_ret, rf=RF):
    nav = (1 + daily_ret).cumprod()
    n = len(daily_ret)
    cum = nav.iloc[-1] - 1
    ann = (1 + cum) ** (252 / n) - 1
    vol = daily_ret.std() * np.sqrt(252)
    downside = daily_ret[daily_ret < 0].std() * np.sqrt(252)
    mdd = (nav / nav.cummax() - 1).min()
    yearly = nav.groupby(nav.index.year).last()
    yearly_ret = yearly.pct_change()
    yearly_ret.iloc[0] = yearly.iloc[0] - 1
    return {
        'cum': cum, 'ann': ann, 'vol': vol,
        'sharpe': (ann - rf) / vol if vol > 0 else np.nan,
        'sortino': (ann - rf) / downside if downside > 0 else np.nan,
        'mdd': mdd, 'nav': nav,
        'worst_year': yearly_ret.min(), 'worst_year_label': int(yearly_ret.idxmin()),
    }


def simulate_portfolio(prices, div_yield, fx, w, initial_twd, monthly_twd,
                       tax=0.30, fee_usd=3.0, fx_cost=0.001, costs=True, rebalance=True):
    """
    以新台幣投入、美元持有的每日模擬：
      - 期初投入 initial_twd，每月第一個交易日投入 monthly_twd
      - 換匯：扣匯差 fx_cost；每筆買賣扣固定手續費 fee_usd（每檔資產算一筆）
      - 股利：除息日扣 tax 比例的預扣稅（還原價格已含息，故從總報酬中扣除）
      - 每年第一個交易日再平衡回目標權重
    """
    w = np.where(w < 1e-4, 0, w)
    w = w / w.sum()
    held = w > 0
    rets = prices.pct_change().fillna(0).values
    dy = div_yield.values
    fxv = fx.values
    dates = prices.index

    values = np.zeros(len(w))
    principal = 0.0
    fee_twd = fx_twd = tax_twd = 0.0
    nav, prin = np.zeros(len(dates)), np.zeros(len(dates))

    for t in range(len(dates)):
        if t > 0:
            if costs:
                tax_amt = values * tax * dy[t]
                tax_twd += tax_amt.sum() * fxv[t]
                values = values * (1 + rets[t]) - tax_amt
            else:
                values = values * (1 + rets[t])
        new_month = t == 0 or dates[t].month != dates[t - 1].month
        cash = initial_twd if t == 0 else (monthly_twd if new_month else 0)
        if cash > 0:
            principal += cash
            fxc = cash * fx_cost if costs else 0
            fee = fee_usd * held.sum() if costs else 0
            usd = max((cash - fxc) / fxv[t] - fee, 0)
            values += usd * w
            fx_twd += fxc
            fee_twd += fee * fxv[t]
        if rebalance and t > 0 and dates[t].year != dates[t - 1].year:
            total = values.sum()
            n_trades = int((np.abs(total * w - values) > 1).sum())
            fee = fee_usd * n_trades if costs else 0
            values = max(total - fee, 0) * w
            fee_twd += fee * fxv[t]
        nav[t] = values.sum() * fxv[t]
        prin[t] = principal

    return {
        'nav': pd.Series(nav, index=dates), 'principal': pd.Series(prin, index=dates),
        'fee_twd': fee_twd, 'fx_twd': fx_twd, 'tax_twd': tax_twd,
    }


def monte_carlo_goal(mu, sigma, initial_twd, monthly_twd, target_twd, years,
                     fee_twd_per_month, fx_cost, n_sims=5000, seed=7):
    """
    月對數報酬 ~ N((μ − σ²/2)/12, σ²/12)。
    終值 FV = A'·G_M + c'·Σ_k (G_M / G_k)，對每月投入 c 為線性 → 可直接反推所需月投入。
    """
    M = int(years * 12)
    rng = np.random.default_rng(seed)
    r = rng.normal((np.log1p(mu) - 0.5 * sigma ** 2) / 12, sigma / np.sqrt(12), size=(n_sims, M))
    G = np.exp(np.cumsum(r, axis=1))                       # G_1..G_M
    G_prev = np.hstack([np.ones((n_sims, 1)), G[:, :-1]])   # G_0..G_{M-1}
    G_M = G[:, -1]
    g1 = (G_M[:, None] / G_prev).sum(axis=1)

    A = max(initial_twd * (1 - fx_cost) - fee_twd_per_month, 0) if initial_twd > 0 else 0
    c_net = max(monthly_twd * (1 - fx_cost) - fee_twd_per_month, 0) if monthly_twd > 0 else 0
    fv = A * G_M + c_net * g1

    # 每月資產路徑 (第 10/50/90 百分位)
    V = np.full(n_sims, A, dtype=float)
    path = np.zeros((n_sims, M + 1))
    path[:, 0] = V
    for k in range(M):
        V = (V + c_net) * np.exp(r[:, k])
        path[:, k + 1] = V
    pct_paths = np.percentile(path, [10, 50, 90], axis=0)

    # 反推所需月投入：c' = (T − A·G_M)/g1，c = (c' + fee)/(1 − fx)
    c_req = ((target_twd - A * G_M) / g1 + fee_twd_per_month) / (1 - fx_cost)
    req = {p: max(np.percentile(c_req, p), 0) for p in (50, 75, 90)}
    return {
        'prob': float(np.mean(fv >= target_twd)), 'fv': fv,
        'pct_paths': pct_paths, 'req': req, 'months': M,
        'principal': initial_twd + monthly_twd * np.arange(M + 1),
    }


def rebalance_plan(holdings, w, tickers, contrib_usd, fee_usd):
    cur = np.array([holdings.get(t, 0.0) for t in tickers])
    total = cur.sum()
    new_total = total + contrib_usd
    target = new_total * w
    deficit = np.maximum(target - cur, 0)

    # 方案 A：依缺口比例分配本月資金
    if deficit.sum() > 0:
        buy_a = contrib_usd * deficit / deficit.sum() if deficit.sum() >= contrib_usd else deficit + (contrib_usd - deficit.sum()) * w
    else:
        buy_a = contrib_usd * w

    # 方案 B：由缺口最大者開始集中補足，減少交易筆數
    buy_b = np.zeros(len(w))
    remain = contrib_usd
    for i in np.argsort(-deficit):
        if remain <= 0 or deficit[i] <= 0:
            break
        amt = min(deficit[i], remain)
        buy_b[i] = amt
        remain -= amt
    if remain > 0:
        buy_b += remain * w

    after = (cur + buy_b) / new_total if new_total > 0 else w
    n_a, n_b = int((buy_a > 0.5).sum()), int((buy_b > 0.5).sum())
    notes = [
        f"方案 A 需交易 {n_a} 筆，手續費約 {usd(n_a * fee_usd)}（占本月投入 {pct(n_a * fee_usd / contrib_usd if contrib_usd else 0, 1)}）；"
        f"方案 B 只需 {n_b} 筆，手續費約 {usd(n_b * fee_usd)}（{pct(n_b * fee_usd / contrib_usd if contrib_usd else 0, 1)}）。",
        "採「只買不賣」的方式再平衡：用新資金補足比例偏低的資產，不需賣出獲利部位，可避免額外手續費與實現損益。",
    ]
    small = [tickers[i] for i in range(len(w)) if 0.5 < buy_a[i] < fee_usd * 20]
    if small:
        notes.append(f"方案 A 中 {', '.join(small)} 的買入金額過小（手續費占比 > 5%），建議累積到下個月再一起買。")
    drift = np.abs(cur / total - w).max() if total > 0 else 0
    if drift > 0.05:
        notes.append(f"目前最大偏離達 {pct(drift, 1)}，超過 5% 門檻，建議本月就執行再平衡。")

    rows = [{
        't': t, 'cur': usd(cur[i]), 'cur_w': pct(cur[i] / total if total else 0, 1), 'tgt_w': pct(w[i], 1),
        'gap': f"{(target[i] - cur[i]):+,.0f}", 'buy_a': usd(buy_a[i]) if buy_a[i] > 0.5 else "—",
        'buy_b': usd(buy_b[i]) if buy_b[i] > 0.5 else "—", 'after': pct(after[i], 1),
    } for i, t in enumerate(tickers)]
    return {'total': usd(total), 'contrib': usd(contrib_usd), 'rows': rows, 'notes': notes}


# ==========================================
# 6. 小工具
# ==========================================
def fnum(form, key, default):
    try:
        v = form.get(key, "")
        return float(v) if str(v).strip() != "" else float(default)
    except (ValueError, TypeError):
        return float(default)


def pct(x, d=2):
    return f"{x * 100:.{d}f}%"


def twd(x):
    return f"NT$ {x:,.0f}"


def usd(x):
    return f"US$ {x:,.0f}"


# ==========================================
# 7. 路由設定
# ==========================================
last_bl_result = {}


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template_string(HTML_TEMPLATE, show_results=False, views=parse_views(None, TICKERS),
                                      tickers=TICKERS, plan=DEFAULT_PLAN, disclaimer=DISCLAIMER)

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
        final_profile = "保守型" if logic_flag == "保守" else baseline

        if final_profile == "保守型":
            icon_color, stroke_dash = "#00BFFF", "33"
        elif final_profile == "穩健型":
            icon_color, stroke_dash = "#FFB300", "66"
        else:
            icon_color, stroke_dash = "#FF5252", "100"
        user_lambda = PROFILE_LAMBDA[final_profile]

        plan = {k: fnum(d, k, v) for k, v in DEFAULT_PLAN.items()}
        plan['years'] = int(min(max(plan['years'], 1), 40))
        tax, fee_usd, fx_cost = plan['tax'] / 100, plan['fee'], plan['fxc'] / 100

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
                text=[name], textposition='top center', textfont=dict(color=colors[name], size=14), name=name))
        fig1.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=400, showlegend=False,
                           xaxis_title="風險 (年化波動率)", yaxis_title="預期報酬率")

        fig2 = go.Figure()
        labels = ['保守型', '穩健型', '激進型']
        for i, ticker in enumerate(tickers):
            y_vals = [ports[label]['w'][i] * 100 for label in labels]
            fig2.add_trace(go.Bar(name=ticker, x=labels, y=y_vals,
                                  text=[f"{ticker} {v:.1f}%" if v > 4 else "" for v in y_vals], textposition='inside'))
        fig2.update_layout(barmode='stack', margin=dict(l=20, r=20, t=20, b=20), height=350,
                           legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))

        # ---------- 3. Black–Litterman ----------
        cov = mpt['ann_cov']
        mu_hist = mpt['ann_ret']
        cap = np.array([MARKET_CAP.get(t, 1) for t in tickers], dtype=float)
        w_mkt = cap / cap.sum()

        views = parse_views(d, tickers)
        pi, mu_bl, cov_bl, view_table = black_litterman(cov, w_mkt, views, tickers)

        w_mvo = mean_variance_opt(mu_hist - RF, cov, user_lambda)
        w_bl = mean_variance_opt(mu_bl, cov_bl, user_lambda)

        ret_table = [{
            't': t, 'w': pct(w_mkt[i], 1), 'hist': pct(mu_hist[i]),
            'prior': pct(pi[i] + RF), 'post': pct(mu_bl[i] + RF),
            'diff': f"{(mu_bl[i] - pi[i]) * 100:+.2f}%",
        } for i, t in enumerate(tickers)]

        fig3 = go.Figure()
        fig3.add_trace(go.Bar(name='歷史平均報酬 (MVO)', x=tickers, y=mu_hist * 100, marker_color='#B0BEC5'))
        fig3.add_trace(go.Bar(name='均衡先驗 Π', x=tickers, y=(pi + RF) * 100, marker_color='#64B5F6'))
        fig3.add_trace(go.Bar(name='BL 後驗 μ_BL', x=tickers, y=(mu_bl + RF) * 100, marker_color='#1E3C72'))
        fig3.update_layout(barmode='group', height=380, margin=dict(l=20, r=20, t=30, b=20),
                           title=dict(text="Figure 3. 預期報酬率估計比較 (%)", font=dict(size=14)),
                           yaxis_title="年化預期報酬 (%)",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

        fig4 = go.Figure()
        for name, w, col in [('市值權重', w_mkt, '#90A4AE'), ('MVO', w_mvo, '#FF7043'), ('Black–Litterman', w_bl, '#1E3C72')]:
            fig4.add_trace(go.Bar(name=name, x=tickers, y=w * 100, marker_color=col,
                                  text=[f"{v * 100:.0f}" if v > 0.03 else "" for v in w], textposition='outside'))
        fig4.update_layout(barmode='group', height=380, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="權重 (%)",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

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
        fig5.add_trace(go.Scatter(x=[np.sqrt(w_mkt @ cov_bl @ w_mkt) * 100], y=[(w_mkt @ mu_bl + RF) * 100],
                                  mode='markers+text', text=['市值組合'], textposition='bottom right',
                                  marker=dict(size=12, color='#90A4AE', line=dict(color='black', width=1)),
                                  showlegend=False))
        fig5.update_layout(height=380, margin=dict(l=20, r=20, t=20, b=20),
                           xaxis_title="年化波動率 (%)", yaxis_title="年化預期報酬 (%)",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

        def alloc_row(name, w, mu_, cv):
            return {
                'name': name, 'ret': pct(w @ mu_ + RF), 'vol': pct(np.sqrt(w @ cv @ w)),
                'maxw': f"{tickers[int(np.argmax(w))]} {pct(w.max(), 1)}",
                'n': int((w > 0.01).sum()), 'eff': f"{1 / np.sum(w ** 2):.2f}",
                'dev': pct(np.sum(np.abs(w - w_mkt)) / 2, 1),
            }
        alloc_table = [alloc_row('市值權重 (均衡)', w_mkt, pi, cov),
                       alloc_row('MVO', w_mvo, mu_hist - RF, cov),
                       alloc_row('Black–Litterman', w_bl, mu_bl, cov_bl)]

        insights = [
            f"MVO 直接使用歷史平均報酬，最大權重集中在 {tickers[int(np.argmax(w_mvo))]}（{pct(w_mvo.max(), 1)}），"
            f"有效資產數僅 {1 / np.sum(w_mvo ** 2):.1f} 檔，反映出 MVO 對預期報酬估計誤差高度敏感、容易產生極端配置的問題。",
            f"Black–Litterman 以市場均衡為錨點，只在有觀點的資產上做偏離，有效資產數為 {1 / np.sum(w_bl ** 2):.1f} 檔，"
            f"與市值權重的偏離度為 {pct(np.sum(np.abs(w_bl - w_mkt)) / 2, 1)}（MVO 為 {pct(np.sum(np.abs(w_mvo - w_mkt)) / 2, 1)}），配置較分散且直覺。",
        ]
        if view_table:
            moved = sorted(range(len(tickers)), key=lambda i: -abs(mu_bl[i] - pi[i]))[:3]
            insights.append("觀點對後驗報酬影響最大的資產：" + "、".join(
                f"{tickers[i]}（{(mu_bl[i] - pi[i]) * 100:+.2f}%）" for i in moved) +
                "。信心水準越高，Ω 越小，後驗報酬越往觀點 Q 移動。")
        else:
            insights.append("未啟用任何觀點，BL 後驗報酬等於均衡先驗報酬，最適配置會接近市值權重（再依個人 λ 調整風險）。")

        # ---------- 4. 樣本外績效 (Part 4) ----------
        test_price = mpt['test_price']
        perf_table, fig6 = [], None
        if len(test_price) > 5:
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
                nav = (test_price[tickers] / test_price[tickers].iloc[0]) @ w
                m = perf_metrics(nav.pct_change().dropna())
                perf_table.append({'name': name, 'cum': pct(m['cum']), 'ann': pct(m['ann']), 'vol': pct(m['vol']),
                                   'sharpe': f"{m['sharpe']:.2f}", 'sortino': f"{m['sortino']:.2f}", 'mdd': pct(m['mdd'])})
                fig6.add_trace(go.Scatter(x=nav.index, y=(nav - 1) * 100, mode='lines', name=name,
                                          line=dict(color=col, width=3 if name in ('Black–Litterman', 'MVO') else 1.8)))
            fig6.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="累積報酬 (%)",
                               legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

        # ---------- 5. 長期回測 vs VOO + 真實成本 (Part 5) ----------
        prices, dyield, fx = mpt['all_price'][tickers], mpt['div_yield'][tickers], mpt['fx']
        w_voo = np.array([1.0 if t == BENCHMARK else 0.0 for t in tickers])
        init_twd, monthly_twd = plan['init_twd'], plan['monthly_twd']
        lump = init_twd if init_twd > 0 else 1_000_000
        sim_kw = dict(tax=tax, fee_usd=fee_usd, fx_cost=fx_cost)

        bt_runs = [
            ('推薦組合 BL（稅費後）', w_bl, True, '#1E3C72', 'solid'),
            ('推薦組合 BL（稅費前）', w_bl, False, '#1E3C72', 'dot'),
            ('MVO（稅費後）', w_mvo, True, '#FF7043', 'solid'),
            ('VOO 單押（稅費後）', w_voo, True, '#2E7D32', 'solid'),
        ]
        fig7 = go.Figure()
        bt_table, bt_m = [], {}
        for name, w, costs, col, dash in bt_runs:
            sim = simulate_portfolio(prices, dyield, fx, w, lump, 0, costs=costs, **sim_kw)
            nav = sim['nav'] / sim['nav'].iloc[0]
            m = perf_metrics(nav.pct_change().dropna())
            bt_m[name] = m
            bt_table.append({
                'name': name, 'cum': pct(m['cum']), 'ann': pct(m['ann']), 'vol': pct(m['vol']),
                'sharpe': f"{m['sharpe']:.2f}", 'mdd': pct(m['mdd']),
                'worst': f"{pct(m['worst_year'], 1)} ({m['worst_year_label']})",
                'loss': twd(lump * m['mdd']),
            })
            fig7.add_trace(go.Scatter(x=nav.index, y=(nav - 1) * 100, mode='lines', name=name,
                                      line=dict(color=col, width=2.5, dash=dash)))
        fig7.add_vrect(x0=TRAIN_START, x1=TRAIN_END, fillcolor="#90A4AE", opacity=0.12, line_width=0,
                       annotation_text="模型估計期", annotation_position="top left")
        fig7.update_layout(height=420, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="累積報酬 (%，新台幣)",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

        m_net, m_gross, m_voo = bt_m['推薦組合 BL（稅費後）'], bt_m['推薦組合 BL（稅費前）'], bt_m['VOO 單押（稅費後）']
        bt_notes = [
            f"回測期間 {mpt['bt_period']}：推薦組合稅費後年化報酬 {pct(m_net['ann'])}，VOO 為 {pct(m_voo['ann'])}；"
            f"最大回撤分別為 {pct(m_net['mdd'])} 與 {pct(m_voo['mdd'])}。"
            + ("推薦組合的波動與回撤較小，風險調整後報酬 (Sharpe) " + ("較佳。" if m_net['sharpe'] > m_voo['sharpe'] else "仍不及 VOO。")
               if m_net['mdd'] > m_voo['mdd'] else "推薦組合的回撤比 VOO 更深，需確認自己承受得住。"),
            f"稅費拖累：同一組合稅費前年化 {pct(m_gross['ann'])}、稅費後 {pct(m_net['ann'])}，每年少了約 {pct(m_gross['ann'] - m_net['ann'])}。",
            "注意：權重是用 2018–2023 資料估計的，回測期間包含估計期（灰色區塊），屬樣本內結果，可能高估實際表現；"
            "2024 年之後才是真正的樣本外。所有報酬以新台幣計價，已反映匯率變動。",
        ]

        # 定期定額
        fig8 = go.Figure()
        dca = {}
        for name, w, col in [('推薦組合 BL', w_bl, '#1E3C72'), ('VOO 單押', w_voo, '#2E7D32')]:
            sim = simulate_portfolio(prices, dyield, fx, w, init_twd, monthly_twd, costs=True, **sim_kw)
            dca[name] = sim
            fig8.add_trace(go.Scatter(x=sim['nav'].index, y=sim['nav'], mode='lines', name=f"{name} 市值",
                                      line=dict(color=col, width=2.5)))
        fig8.add_trace(go.Scatter(x=dca['推薦組合 BL']['principal'].index, y=dca['推薦組合 BL']['principal'],
                                  mode='lines', name='累積投入本金', line=dict(color='#9E9E9E', dash='dash')))
        fig8.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="新台幣",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

        s = dca['推薦組合 BL']
        final_v, princ = s['nav'].iloc[-1], s['principal'].iloc[-1]
        n_hold = int((w_bl > 1e-4).sum())
        fx_last = float(fx.iloc[-1])
        div_drag = tax * float(w_bl @ mpt['ann_div_yield'])
        fee_ratio = (n_hold * fee_usd * fx_last) / monthly_twd if monthly_twd > 0 else 0
        total_cost = s['fee_twd'] + s['fx_twd'] + s['tax_twd']
        cost_table = [
            {'k': '累積投入本金', 'v': twd(princ)},
            {'k': '期末市值（稅費後）', 'v': twd(final_v)},
            {'k': 'VOO 單押期末市值（稅費後）', 'v': twd(dca['VOO 單押']['nav'].iloc[-1])},
            {'k': '複委託手續費合計', 'v': twd(s['fee_twd'])},
            {'k': '換匯成本合計', 'v': twd(s['fx_twd'])},
            {'k': '股利預扣稅合計', 'v': twd(s['tax_twd'])},
            {'k': '總成本占本金比例', 'v': pct(total_cost / princ if princ else 0)},
            {'k': '每年股利稅拖累（估計）', 'v': pct(div_drag)},
            {'k': f'每月手續費占投入比例（{n_hold} 檔 × US${fee_usd:g}）', 'v': pct(fee_ratio)},
        ]
        cost_tips = [f"美股現金股利預扣 {plan['tax']:g}% 稅，高股息與債券 ETF（如 TLT、VNQ、PG）受影響最大。"]
        if fee_ratio > 0.01:
            cost_tips.append(f"每月定投 {n_hold} 檔資產，固定手續費就吃掉投入金額的 {pct(fee_ratio, 1)}。"
                             "建議改成每 2–3 個月買一次、每次只買 1–2 檔比例最低的資產（見 Part 7 方案 B），或選擇有定期定額優惠的券商。")
        else:
            cost_tips.append("目前手續費占投入比例在 1% 以內，成本控制良好。")
        cost_tips.append("美國註冊 ETF 的股利預扣稅為 30%；部分愛爾蘭註冊的 UCITS ETF 在基金層級適用 15%，長期持有可評估。")

        # ---------- 6. 蒙地卡羅目標試算 (Part 6) ----------
        fee_twd_month = n_hold * fee_usd * fx_last
        mu_port = float(w_bl @ (mu_bl + RF)) - div_drag
        sig_port = float(np.sqrt(w_bl @ cov_bl @ w_bl))
        mc_res = monte_carlo_goal(mu_port, sig_port, init_twd, monthly_twd, plan['target_twd'], plan['years'],
                                  fee_twd_month, fx_cost)
        i_voo = tickers.index(BENCHMARK)
        mu_voo = float(mu_bl[i_voo] + RF) - tax * float(mpt['ann_div_yield'][i_voo])
        mc_voo = monte_carlo_goal(mu_voo, float(np.sqrt(cov_bl[i_voo, i_voo])), init_twd, monthly_twd,
                                  plan['target_twd'], plan['years'], fee_usd * fx_last, fx_cost)

        mc = {
            'prob': pct(mc_res['prob'], 1), 'prob_voo': pct(mc_voo['prob'], 1), 'years': plan['years'],
            'median': twd(np.median(mc_res['fv'])), 'p10': twd(np.percentile(mc_res['fv'], 10)),
            'mu': pct(mu_port), 'sigma': pct(sig_port),
            'req': [{'p': f"{p}%", 'c': twd(v), 'diff': (f"+{twd(v - monthly_twd)}" if v > monthly_twd else "目前設定已足夠")}
                    for p, v in mc_res['req'].items()],
        }
        months = np.arange(mc_res['months'] + 1)
        x_dates = pd.Timestamp.today().normalize() + pd.to_timedelta(months * 30.44, unit='D')
        p10, p50, p90 = mc_res['pct_paths']
        fig9 = go.Figure()
        fig9.add_trace(go.Scatter(x=x_dates, y=p90, mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig9.add_trace(go.Scatter(x=x_dates, y=p10, mode='lines', line=dict(width=0), fill='tonexty',
                                  fillcolor='rgba(41,121,255,0.18)', name='10%–90% 區間'))
        fig9.add_trace(go.Scatter(x=x_dates, y=p50, mode='lines', name='中位數', line=dict(color='#1E3C72', width=3)))
        fig9.add_trace(go.Scatter(x=x_dates, y=mc_res['principal'], mode='lines', name='投入本金',
                                  line=dict(color='#9E9E9E', dash='dash')))
        fig9.add_hline(y=plan['target_twd'], line=dict(color='#E53935', dash='dot'),
                       annotation_text=f"目標 {twd(plan['target_twd'])}", annotation_position="top left")
        fig9.update_layout(height=420, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="新台幣",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

        # ---------- 7. 再平衡 (Part 7) ----------
        holdings = {t: fnum(d, f"h_{t}", 0) for t in tickers}
        rebal = None
        if sum(holdings.values()) > 0:
            contrib_usd = monthly_twd * (1 - fx_cost) / fx_last
            rebal = rebalance_plan(holdings, w_bl, tickers, contrib_usd, fee_usd)

        last_bl_result['df'] = pd.DataFrame({
            'ticker': tickers, 'market_weight': w_mkt, 'hist_mean_return': mu_hist,
            'prior_return_pi_plus_rf': pi + RF, 'posterior_return_bl_plus_rf': mu_bl + RF,
            'weight_mvo': w_mvo, 'weight_bl': w_bl, 'annual_dividend_yield': mpt['ann_div_yield'],
        })

        def html(fig, first=False):
            return fig.to_html(full_html=False, include_plotlyjs=False) if fig is not None else \
                "<p class='p-3 text-muted'>無資料</p>"

        return render_template_string(
            HTML_TEMPLATE, show_results=True, disclaimer=DISCLAIMER,
            baseline=baseline, state=state, alert=alert, final_profile=final_profile,
            icon_color=icon_color, stroke_dash=stroke_dash, user_lambda=user_lambda,
            fig1_html=html(fig1), fig2_html=html(fig2), fig3_html=html(fig3), fig4_html=html(fig4),
            fig5_html=html(fig5), fig6_html=html(fig6), fig7_html=html(fig7), fig8_html=html(fig8),
            fig9_html=html(fig9),
            train_period=mpt['train_period'], test_period=mpt['test_period'], bt_period=mpt['bt_period'],
            delta=DELTA_MKT, tau=TAU, rf_pct=pct(RF, 1),
            view_table=view_table, ret_table=ret_table, alloc_table=alloc_table, insights=insights,
            perf_table=perf_table, bt_table=bt_table, bt_notes=bt_notes,
            cost_table=cost_table, cost_tips=cost_tips, mc=mc, mc_n="5,000", rebal=rebal,
            init_twd_fmt=twd(lump), monthly_twd_fmt=twd(monthly_twd), target_twd_fmt=twd(plan['target_twd']),
        )

    except Exception:
        return f"<h2>系統運算錯誤</h2><pre>{traceback.format_exc()}</pre>"


# ==========================================
# 8. 交易日誌分析
# ==========================================
SAMPLE_JOURNAL = """date,ticker,action,shares,price,fee
2023-01-05,AAPL,BUY,10,126.00,3
2023-03-10,MSFT,BUY,5,250.00,3
2023-06-20,AAPL,SELL,10,184.00,3
2023-08-01,TSLA,BUY,8,260.00,3
2023-10-25,TSLA,SELL,8,212.00,3
2024-01-15,MSFT,SELL,5,390.00,3
2024-02-01,VOO,BUY,3,440.00,3
"""


def analyze_journal(df):
    df.columns = [c.strip().lower() for c in df.columns]
    need = {'date', 'ticker', 'action', 'shares', 'price'}
    if not need.issubset(df.columns):
        raise ValueError(f"CSV 缺少欄位：{', '.join(sorted(need - set(df.columns)))}")
    if 'fee' not in df.columns:
        df['fee'] = 0
    df['date'] = pd.to_datetime(df['date'])
    df['ticker'] = df['ticker'].astype(str).str.upper().str.strip()
    df['action'] = df['action'].astype(str).str.upper().str.strip().replace({'買': 'BUY', '賣': 'SELL', '買進': 'BUY', '賣出': 'SELL'})
    df[['shares', 'price', 'fee']] = df[['shares', 'price', 'fee']].apply(pd.to_numeric, errors='coerce').fillna(0)
    df = df.sort_values('date', kind='stable')

    lots, trades, warnings = {}, [], []
    for _, r in df.iterrows():
        if r['shares'] <= 0:
            continue
        if r['action'] == 'BUY':
            lots.setdefault(r['ticker'], deque()).append([r['shares'], r['price'] + r['fee'] / r['shares'], r['date']])
        elif r['action'] == 'SELL':
            sell_px = r['price'] - r['fee'] / r['shares']
            remain = r['shares']
            q_lots = lots.get(r['ticker'], deque())
            while remain > 1e-9 and q_lots:
                lot = q_lots[0]
                q = min(lot[0], remain)
                trades.append({'ticker': r['ticker'], 'buy': lot[2], 'sell': r['date'], 'shares': q,
                               'cost': lot[1], 'px': sell_px, 'pnl': q * (sell_px - lot[1]),
                               'ret': sell_px / lot[1] - 1, 'days': (r['date'] - lot[2]).days})
                lot[0] -= q
                remain -= q
                if lot[0] <= 1e-9:
                    q_lots.popleft()
            if remain > 1e-9:
                warnings.append(f"{r['date']:%Y-%m-%d} 賣出 {r['ticker']} 超過持有股數 {remain:g} 股，已忽略超出部分。")
        else:
            warnings.append(f"無法辨識的交易方向：{r['action']}")
    open_pos = {t: sum(l[0] for l in q) for t, q in lots.items() if sum(l[0] for l in q) > 1e-9}
    return pd.DataFrame(trades), open_pos, warnings


@app.route('/journal', methods=['GET', 'POST'])
def journal():
    ctx = dict(disclaimer=DISCLAIMER, stats=None, error=None, warnings=[], open_pos=None, trades=[])
    if request.method == 'GET':
        return render_template_string(JOURNAL_TEMPLATE, **ctx)
    try:
        f = request.files.get('file')
        raw = f.read().decode('utf-8-sig')
        tr, open_pos, warnings = analyze_journal(pd.read_csv(io.StringIO(raw)))
        if tr.empty:
            raise ValueError("沒有任何已平倉（買進後賣出）的交易可以分析。")

        # 同期 VOO 報酬
        start = (tr['buy'].min() - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
        end = (tr['sell'].max() + pd.Timedelta(days=5)).strftime('%Y-%m-%d')
        try:
            voo = yf.Ticker(BENCHMARK).history(start=start, end=end)['Close']
            voo.index = voo.index.tz_localize(None)
            tr['voo'] = [voo.asof(s) / voo.asof(b) - 1 for b, s in zip(tr['buy'], tr['sell'])]
        except Exception:
            tr['voo'] = np.nan
            warnings.append("無法取得 VOO 歷史價格，略過同期比較。")

        wins, losses = tr[tr['pnl'] > 0], tr[tr['pnl'] <= 0]
        beat = (tr['ret'] > tr['voo']).mean() if tr['voo'].notna().any() else np.nan
        pf = wins['pnl'].sum() / abs(losses['pnl'].sum()) if len(losses) and losses['pnl'].sum() != 0 else np.inf
        stats = [
            {'v': f"{len(tr)}", 'l': '已實現交易筆數'},
            {'v': pct(len(wins) / len(tr), 1), 'l': '勝率'},
            {'v': pct(wins['ret'].mean(), 1) if len(wins) else "—", 'l': '平均獲利（賺錢的交易）'},
            {'v': pct(losses['ret'].mean(), 1) if len(losses) else "—", 'l': '平均虧損（賠錢的交易）'},
            {'v': f"{pf:.2f}" if np.isfinite(pf) else "∞", 'l': '獲利因子（總獲利 / 總虧損）'},
            {'v': f"{tr['days'].mean():.0f} 天", 'l': '平均持有天數'},
            {'v': f"{tr['pnl'].sum():,.0f}", 'l': '已實現損益合計'},
            {'v': pct(beat, 1) if pd.notna(beat) else "—", 'l': '跑贏同期 VOO 的比例'},
        ]

        labels = [f"{t} ({s:%Y/%m/%d})" for t, s in zip(tr['ticker'], tr['sell'])]
        fig_a = go.Figure()
        fig_a.add_trace(go.Bar(name='我的交易報酬', x=labels, y=tr['ret'] * 100,
                               marker_color=['#2E7D32' if v > 0 else '#E53935' for v in tr['ret']]))
        fig_a.add_trace(go.Bar(name='同期持有 VOO', x=labels, y=tr['voo'] * 100, marker_color='#90A4AE'))
        fig_a.update_layout(barmode='group', height=380, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="報酬率 (%)",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        cum = tr.sort_values('sell').assign(cum=lambda x: x['pnl'].cumsum())
        fig_b = go.Figure(go.Scatter(x=cum['sell'], y=cum['cum'], mode='lines+markers', line=dict(color='#1E3C72', width=3)))
        fig_b.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="累積已實現損益")

        rows = [{
            'ticker': r.ticker, 'buy': f"{r.buy:%Y-%m-%d}", 'sell': f"{r.sell:%Y-%m-%d}", 'shares': f"{r.shares:g}",
            'cost': f"{r.cost:,.2f}", 'px': f"{r.px:,.2f}", 'pnl': f"{r.pnl:+,.0f}", 'ret': pct(r.ret, 1),
            'voo': pct(r.voo, 1) if pd.notna(r.voo) else "—", 'days': r.days,
        } for r in tr.itertuples()]
        ctx.update(stats=stats, trades=rows, warnings=warnings,
                   open_pos="、".join(f"{t} {s:g} 股" for t, s in open_pos.items()) or None,
                   fig_a=fig_a.to_html(full_html=False, include_plotlyjs=False),
                   fig_b=fig_b.to_html(full_html=False, include_plotlyjs=False))
    except Exception as e:
        ctx['error'] = f"分析失敗：{e}"
    return render_template_string(JOURNAL_TEMPLATE, **ctx)


@app.route('/journal/sample')
def journal_sample():
    return Response(SAMPLE_JOURNAL, mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=trade_journal_sample.csv"})


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

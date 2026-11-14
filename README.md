智能理財機器人 (Robo-Advisor)：MPT × Black–Litterman

Flask 網頁應用，部署於 Vercel（程式放在 api/index.py）。

流程
KYC 問卷 + NLP 行為分析 → 判定保守／穩健／激進型，並對應個人風險趨避係數 λ（10／5／2）。
MPT（前次作業） → 蒙地卡羅模擬 1,500 組投資組合，繪製效率前緣（Figure 1–2）。
Black–Litterman 模型
市場均衡先驗：Π = δΣw_mkt（δ = 2.5，w_mkt 為 2023 年底市值／ETF 規模約略值）
投資人觀點：P、Q（可在網頁上輸入最多 3 個絕對／相對觀點）
信心水準 → 觀點不確定性：Ω_kk = (1−c)/c · τ · P_kΣP_kᵀ（τ = 0.05）
貝氏後驗：μ_BL = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹[(τΣ)⁻¹Π + PᵀΩ⁻¹Q]，Σ_BL = Σ + M
最佳化：只做多、全額投資的均值-變異數最佳化（投影梯度法，不需 scipy）， MVO 使用歷史平均報酬，BL 使用後驗報酬。
績效分析：估計期 2018–2023，樣本外測試期 2024（買入持有）， 比較 BL、MVO、MPT 隨機模擬、市值權重、等權重的累積報酬、年化報酬、波動、Sharpe、Sortino、最大回撤。
輸出
Figure 1–2：MPT 效率前緣與配置
Figure 3：歷史報酬 vs 均衡先驗 vs BL 後驗
Figure 4：市值 / MVO / BL 權重比較
Figure 5：MVO 與 BL 效率前緣比較
Figure 6：樣本外累積報酬
/download_csv：歷史價格；/download_bl_csv：BL 模型結果

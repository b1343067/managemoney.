import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

# 設定網頁標題與版面
st.set_page_config(page_title="Portfolio Analysis", layout="wide")
st.title("Modern Portfolio Theory - 資產分析與相關性")

# 1. 定義資產 (波克夏 B 股在 yfinance 的代號為 BRK-B)
tickers = ['VOO', 'BRK-B', 'JPM', 'NVDA', 'GLD']

# 使用快取避免每次重整網頁都重新抓取資料
@st.cache_data
def load_data():
    # 讀取 5 年以上歷史資料
    data = yf.download(tickers, start="2018-01-01", end="2024-01-01")['Adj Close']
    # 處理 Missing Values (向前填補空值並刪除無法填補的列)
    data = data.ffill().dropna()
    return data

data = load_data()

st.subheader("1. 資產價格走勢 (Adjusted Close Price)")
st.line_chart(data)

# 計算每日報酬率 (Daily Return)
daily_returns = data.pct_change().dropna()

st.subheader("2. 報酬與風險分析 (Return and Risk Analysis)")
# 假設一年有 252 個交易日
trading_days = 252

# 計算各項指標
avg_daily_return = daily_returns.mean()
annualized_return = (1 + avg_daily_return) ** trading_days - 1
std_dev = daily_returns.std()
annualized_volatility = std_dev * np.sqrt(trading_days)

# 建立統整表格並顯示
metrics_df = pd.DataFrame({
    'Average Daily Return': avg_daily_return,
    'Annualized Return': annualized_return,
    'Daily Standard Deviation': std_dev,
    'Annualized Volatility': annualized_volatility
})
# 將數值格式化為小數點後四位
st.dataframe(metrics_df.style.format("{:.4f}"))

st.subheader("3. 相關係數矩陣 (Correlation Matrix)")
correlation_matrix = daily_returns.corr()

# 建立熱力圖 (Heatmap) 視覺化相關性
fig, ax = plt.subplots(figsize=(8, 6))
sns.heatmap(correlation_matrix, annot=True, cmap='coolwarm', vmin=-1, vmax=1, ax=ax, fmt=".2f", linewidths=.5)
st.pyplot(fig)

st.subheader("4. 共變異數矩陣 (Covariance Matrix)")
covariance_matrix = daily_returns.cov()
st.dataframe(covariance_matrix.style.format("{:.6f}"))

st.markdown("""
---
### 💡 作業分析提示 (供參考)
*   **Q1 (高相關性)**：觀察熱力圖中顏色偏深紅、數值接近 1 的區塊（例如大型股與大盤之間）。
*   **Q2 (低/負相關性)**：觀察顏色偏藍、數值接近 0 或為負的區塊（通常 GLD 會與其他股票資產呈現較低的相關性）。
*   **Q3 (分散投資效益)**：相關係數越低的資產組合，越能抵銷彼此的波動，提供更好的 Diversification benefit。
""")

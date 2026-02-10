%%writefile app.py
import streamlit as st
import pandas as pd
import pandas_datareader.data as web
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="STIR Master Desk", layout="wide", initial_sidebar_state="expanded")
st.title("🏦 STIR Master Desk: Rates & Liquidity Correlation")

# --- 1. DATA ENGINE (Optimized) ---
@st.cache_data
def load_data():
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=365*4)

    series = {
        'DFEDTARU': 'Target Upper', 'DFEDTARL': 'Target Lower',
        'IORB': 'IORB', 'IOER': 'IOER', 'EFFR': 'EFFR', 'SOFR': 'SOFR',
        'RRPONTSYAWARD': 'RRP Rate', 'RRPONTSYD': 'RRP Vol',
        'WALCL': 'Fed Assets', 'WTREGEN': 'TGA'
    }

    # Fetch Data
    with st.spinner('Pinging Fed Servers...'):
        try:
            df = web.DataReader(list(series.keys()), 'fred', start_date, end_date)
        except:
            st.error("Data Feed Disconnected. Refresh to retry.")
            st.stop()
    
    df = df.rename(columns=series)
    
    # Clean & Calc
    df['IORB'] = df['IORB'].combine_first(df['IOER']) # Merge historical series
    df = df.ffill().dropna(subset=['IORB']) # Fill weekends
    
    # Liquidity Math (Trillions)
    df['Liq_Assets'] = df['Fed Assets'] / 1e6
    df['Liq_TGA'] = df['TGA'] / 1e6
    df['Liq_RRP'] = df['RRP Vol'].fillna(0) / 1000
    df['Net Liquidity'] = df['Liq_Assets'] - df['Liq_TGA'] - df['Liq_RRP']
    df['Net Liquidity (SMA5)'] = df['Net Liquidity'].rolling(5).mean() # Smooth noise
    
    return df

df = load_data()

# --- 2. TRADER CONTROLS ---
with st.sidebar:
    st.header("⚡ Desk Controls")
    
    # Date Filter
    st.subheader("Timeframe")
    max_d = df.index[-1].date()
    # Default to last 18 months for clearer view
    dates = st.date_input("Window", [max_d - datetime.timedelta(days=540), max_d])
    
    st.divider()
    
    # Arb Selector
    st.subheader("Arb Monitor")
    rates_list = ['IORB', 'EFFR', 'SOFR', 'Target Upper', 'RRP Rate']
    long_leg = st.selectbox("Long (Earn)", rates_list, index=0)
    short_leg = st.selectbox("Short (Pay)", rates_list, index=1)

# Filter Data
mask = (df.index.date >= dates[0]) & (df.index.date <= dates[1])
data = df.loc[mask]

# Calc Spread
spread_vals = (data[long_leg] - data[short_leg]) * 100 # In bps
# --- DASHBOARD HEADER ---
st.divider()
k1, k2, k3, k4 = st.columns(4)

# Get latest values and the specific DATE of the data
latest_date = data.index[-1].strftime('%Y-%m-%d')  # <--- NEW: Gets the date
latest_spread = spread_vals.iloc[-1]
latest_liq = data['Net Liquidity'].iloc[-1]
latest_rrp = data['Liq_RRP'].iloc[-1]
latest_tga = data['Liq_TGA'].iloc[-1]

# Render the big numbers with the Date Timestamp
k1.metric(
    label=f"Spread ({latest_date})",  # <--- NEW: Shows the date in the label
    value=f"{latest_spread:.2f} bps", 
    delta_color="normal" if latest_spread > 0 else "inverse"
)
k2.metric("Net Liquidity", f"${latest_liq:.2f} T")
k3.metric("RRP (Cash Floor)", f"${latest_rrp:.3f} T")
k4.metric("TGA (Gov Account)", f"${latest_tga:.3f} T")

st.divider()
# --- 3. THE "GOD VIEW" CHART ---
# We use a 3-Row Subplot to synchronize the timeline
fig = make_subplots(
    rows=3, cols=1, 
    shared_xaxes=True, # CRITICAL: This links the zoom
    vertical_spacing=0.03,
    row_heights=[0.25, 0.25, 0.50], # 25% Rates, 25% Spread, 50% Liquidity
    specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": False}]]
)

# --- ROW 1: RATES (Context) ---
fig.add_trace(go.Scatter(x=data.index, y=data[long_leg], name=long_leg, line=dict(color='#00CC96', width=2)), row=1, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data[short_leg], name=short_leg, line=dict(color='#EF553B', width=2, dash='dot')), row=1, col=1)

# --- ROW 2: SPREAD (Signal) ---
# Profit Zone (Green)
fig.add_trace(go.Scatter(x=data.index, y=spread_vals.clip(lower=0), name="Profit (Arb)", 
                         fill='tozeroy', line=dict(color='green', width=0), opacity=0.5, showlegend=False), row=2, col=1)
# Loss Zone (Red)
fig.add_trace(go.Scatter(x=data.index, y=spread_vals.clip(upper=0), name="Negative Spread", 
                         fill='tozeroy', line=dict(color='red', width=0), opacity=0.5, showlegend=False), row=2, col=1)
# The Line Itself
fig.add_trace(go.Scatter(x=data.index, y=spread_vals, name="Spread (bps)", 
                         line=dict(color='black', width=1)), row=2, col=1)

# --- ROW 3: LIQUIDITY (Drivers) ---
# Stacked Drains (TGA & RRP) - "The Floor"
fig.add_trace(go.Scatter(x=data.index, y=data['Liq_RRP'], name="RRP Drain", stackgroup='one', 
                         line=dict(width=0, color='cornflowerblue')), row=3, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data['Liq_TGA'], name="TGA Drain", stackgroup='one', 
                         line=dict(width=0, color='salmon')), row=3, col=1)

# Net Liquidity - "The Ceiling"
fig.add_trace(go.Scatter(x=data.index, y=data['Net Liquidity (SMA5)'], name="Net Liquidity", 
                         line=dict(color='#FFD700', width=2)), row=3, col=1)

# --- LAYOUT POLISH ---
last_spread = spread_vals.iloc[-1]
last_liq = data['Net Liquidity'].iloc[-1]

fig.update_layout(
    height=800, # Tall chart
    title_text=f"Market Dashboard | Spread: {last_spread:.2f} bps | Liquidity: ${last_liq:.2f}T",
    hovermode="x unified", # Shows all data points on one hover line
    margin=dict(l=20, r=20, t=60, b=20),
    legend=dict(orientation="h", y=1.02, xanchor="right", x=1)
)

# Axis Titles
fig.update_yaxes(title_text="Rate (%)", row=1, col=1)
fig.update_yaxes(title_text="Spread (bps)", row=2, col=1)
fig.update_yaxes(title_text="Trillions ($)", row=3, col=1)

# Render
st.plotly_chart(fig, use_container_width=True)

# Data Grid below for detailed checks
with st.expander("📋 View Raw Data Feed"):
    st.dataframe(data.sort_index(ascending=False).style.format("{:.4f}"))

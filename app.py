import streamlit as st
import pandas as pd
import pandas_datareader.data as web
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="STIR Master Desk", layout="wide", initial_sidebar_state="expanded")
st.title("🏦 STIR Master Desk: Rates & Liquidity Correlation")

# --- 1. DATA ENGINE (The "Invincible" Version) ---
@st.cache_data
def load_data():
    # 1. Define Timeframe (10 Years)
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=365*10)

    # 2. Define Series (Target Lower MUST be here)
    series = {
        'DFEDTARU': 'Target Upper', 
        'DFEDTARL': 'Target Lower',
        'IORB': 'IORB', 
        'IOER': 'IOER', 
        'EFFR': 'EFFR', 
        'SOFR': 'SOFR',
        'RRPONTSYAWARD': 'RRP Rate', 
        'RRPONTSYD': 'RRP Vol',
        'WALCL': 'Fed Assets', 
        'WTREGEN': 'TGA'
    }

    # 3. Fetch Data
    with st.spinner('Pinging Fed Servers...'):
        try:
            df = web.DataReader(list(series.keys()), 'fred', start_date, end_date)
        except Exception as e:
            st.error(f"Data Feed Error: {e}")
            st.stop()
    
    df = df.rename(columns=series)
    
    # 4. Clean & Calc
    if 'IOER' in df.columns and 'IORB' in df.columns:
        df['IORB'] = df['IORB'].combine_first(df['IOER'])
    
    # FORCE FILL: Ensure Target Lower never vanishes
    df = df.ffill()
    df = df.dropna(subset=['IORB']) 
    
    # Liquidity Math
    df['Liq_Assets'] = df['Fed Assets'] / 1e6
    df['Liq_TGA'] = df['TGA'] / 1e6
    df['Liq_RRP'] = df['RRP Vol'].fillna(0) / 1000
    df['Net Liquidity'] = df['Liq_Assets'] - df['Liq_TGA'] - df['Liq_RRP']
    df['Net Liquidity (SMA5)'] = df['Net Liquidity'].rolling(5).mean()
    
    return df

# Load Data
df = load_data()

# --- 2. TRADER CONTROLS ---
with st.sidebar:
    st.header("⚡ Desk Controls")
    st.caption("✅ v2.0 - Live Update") # <--- LOOK FOR THIS TAG
    
    # Date Filter
    st.subheader("Timeframe")
    max_d = df.index[-1].date()
    dates = st.date_input("Window", [max_d - datetime.timedelta(days=540), max_d])
    
    st.divider()
    
    # Arb Selector
    st.subheader("Arb Monitor")
    # UPDATED LIST: Target Lower IS here
    rates_list = ['IORB', 'EFFR', 'SOFR', 'Target Upper', 'Target Lower', 'RRP Rate']
    
    long_leg = st.selectbox("Long (Earn)", rates_list, index=0)
    short_leg = st.selectbox("Short (Pay)", rates_list, index=1)

# Filter Data
if len(dates) != 2: st.stop()
mask = (df.index.date >= dates[0]) & (df.index.date <= dates[1])
data = df.loc[mask]

# Calc Spread
spread_vals = (data[long_leg] - data[short_leg]) * 100 # In bps

# --- DASHBOARD HEADER ---
st.divider()
k1, k2, k3, k4 = st.columns(4)

latest_date = data.index[-1].strftime('%Y-%m-%d')
latest_spread = spread_vals.iloc[-1]
latest_liq = data['Net Liquidity'].iloc[-1]
latest_rrp = data['Liq_RRP'].iloc[-1]
latest_tga = data['Liq_TGA'].iloc[-1]

k1.metric(label=f"Spread ({latest_date})", value=f"{latest_spread:.2f} bps", delta_color="normal" if latest_spread > 0 else "inverse")
k2.metric("Net Liquidity", f"${latest_liq:.2f} T")
k3.metric("RRP (Cash Floor)", f"${latest_rrp:.3f} T")
k4.metric("TGA (Gov Account)", f"${latest_tga:.3f} T")

st.divider()

# --- 3. THE "GOD VIEW" CHART ---
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                    row_heights=[0.35, 0.25, 0.40],
                    specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": False}]])

# ROW 1: RATES
# Background Corridor
if 'IORB' in data.columns:
    fig.add_trace(go.Scatter(x=data.index, y=data['IORB'], name='Ceiling (IORB)',
                  line=dict(color='rgba(150, 150, 150, 0.5)', width=1, dash='dashdot'), hoverinfo='skip'), row=1, col=1)
if 'RRP Rate' in data.columns:
    fig.add_trace(go.Scatter(x=data.index, y=data['RRP Rate'], name='Floor (RRP)',
                  line=dict(color='rgba(150, 150, 150, 0.5)', width=1, dash='dashdot'), hoverinfo='skip'), row=1, col=1)

# Selected Pair
fig.add_trace(go.Scatter(x=data.index, y=data[long_leg], name=f"Long: {long_leg}", line=dict(color='#00CC96', width=2)), row=1, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data[short_leg], name=f"Short: {short_leg}", line=dict(color='#EF553B', width=2, dash='dot')), row=1, col=1)

# ROW 2: SPREAD
fig.add_trace(go.Scatter(x=data.index, y=spread_vals.clip(lower=0), name="Profit", fill='tozeroy', line=dict(color='green', width=0), opacity=0.5, showlegend=False), row=2, col=1)
fig.add_trace(go.Scatter(x=data.index, y=spread_vals.clip(upper=0), name="Loss", fill='tozeroy', line=dict(color='red', width=0), opacity=0.5, showlegend=False), row=2, col=1)
fig.add_trace(go.Scatter(x=data.index, y=spread_vals, name="Spread", line=dict(color='black', width=1)), row=2, col=1)

# ROW 3: LIQUIDITY
fig.add_trace(go.Scatter(x=data.index, y=data['Liq_RRP'], name="RRP Drain", stackgroup='one', line=dict(width=0, color='cornflowerblue')), row=3, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data['Liq_TGA'], name="TGA Drain", stackgroup='one', line=dict(width=0, color='salmon')), row=3, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data['Net Liquidity (SMA5)'], name="Net Liquidity", line=dict(color='#FFD700', width=2)), row=3, col=1)

fig.update_layout(height=900, title_text="Institutional Market Dashboard", hovermode="x unified", margin=dict(l=20, r=20, t=60, b=20), legend=dict(orientation="h", y=1.01, xanchor="right", x=1))

st.plotly_chart(fig, use_container_width=True)

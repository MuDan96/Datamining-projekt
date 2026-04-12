import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================
# 1. KONFIGURÁCIA A ŠTÝL (CSS Mágia)
# ============================================
st.set_page_config(page_title="Praha Air Quality Live", layout="wide", page_icon="🌤️")

st.markdown("""
    <style>
    /* Desaturácia mapy ako v HTML verzii */
    .mapboxgl-canvas-container { filter: contrast(0.9) saturate(60%) brightness(1.05) !important; opacity: 0.9; }
    
    /* Štýlovanie kariet hypotéz */
    .hypo-card {
        background: #fff; border-left: 5px solid #e74c3c; border-radius: 8px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.08); padding: 20px; margin-bottom: 25px;
    }
    .hypo-title { color: #c0392b; font-size: 20px; font-weight: bold; margin-bottom: 10px; }
    .zaver-box { background: #e8f6f3; padding: 15px; border-radius: 5px; border-left: 4px solid #1abc9c; color: #16a085; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# ============================================
# 2. API A DÁTA (S pamäťou / Cachingom)
# ============================================
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NTE0OSwiaWF0IjoxNzc1Mjg5Njc4LCJleHAiOjExNzc1Mjg5Njc4LCJpc3MiOiJnb2xlbWlvIiwianRpIjoiZjFhOTkwODAtMjAyOS00MjhkLWFmZWEtY2ZlYTZmNGQ2MTRiIn0.3qCQB37FFlsE9jDPz0JVf8h1cbqqfNlmC9XQ6BY_Hmc"
BASE_URL = "https://api.golemio.cz/v2"

INFO_ZLOZKY = {
    "PM10": {"nazov": "Prachové častice (PM10)", "analyza": "Tieto ťažšie častice prachu sa držia najmä v nízkych polohách a pri dopravných uzloch. Všimnite si, že stanice v blízkosti zelených zón vykazujú menšie body."},
    "PM2_5": {"nazov": "Jemné prachové častice (PM2.5)", "analyza": "Micro prach zo spaľovacích motorov. Rozptyľuje sa ľahšie, no koncentrácia je najvyššia na rušných križovatkách."},
    "NO2": {"nazov": "Oxid dusičitý (NO2)", "analyza": "Ultimátny dôkaz dopravnej záťaže. Tmavé body presne lícujú s Magistrálou. Zelené plochy tvoria čisté ostrovy."},
    "O3": {"nazov": "Prízemný ozón (O3)", "analyza": "Ozónový paradox. Hodnoty bývajú vyššie v parkoch, lebo emisie v centre (NO) ozón chemicky rozkladajú."}
}

LIMITS_WHO = {"NO2": 25, "PM10": 50, "PM2_5": 15, "O3": 100}

@st.cache_data(ttl=3600)
def load_stations():
    try:
        resp = requests.get(f"{BASE_URL}/airqualitystations", headers={"X-Access-Token": API_KEY}, params={"limit": 1000})
        data = resp.json().get('features', [])
        return pd.DataFrame([{'id': s['properties']['id'], 'name': s['properties']['name'], 
                              'lon': s['geometry']['coordinates'][0], 'lat': s['geometry']['coordinates'][1]} for s in data])
    except: return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner="Sťahujem históriu z Golemia...")
def load_air_history(start, end):
    session = requests.Session()
    session.headers.update({"X-Access-Token": API_KEY})
    enriched = []
    curr = datetime.combine(start, datetime.min.time())
    last = datetime.combine(end, datetime.max.time())
    while curr < last:
        to_dt = min(curr + timedelta(days=1), last)
        try:
            resp = session.get(f"{BASE_URL}/airqualitystations/history", params={"from": curr.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "to": to_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "limit": 10000})
            records = resp.json().get('data', [])
            for r in records:
                s_id, meas = r.get('id'), r.get('measurement', {})
                api_time = meas.get('measured_from', curr.strftime('%Y-%m-%d %H:00'))
                for c in meas.get('components', []):
                    val = c.get('averaged_time', {}).get('value') if isinstance(c.get('averaged_time'), dict) else c.get('value')
                    if val is not None: enriched.append({'station_id': s_id, 'datetime': api_time, 'type': c.get('type'), 'value': val})
        except: pass
        curr = to_dt
    df = pd.DataFrame(enriched)
    if not df.empty:
        df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
    return df

@st.cache_data(ttl=86400)
def load_weather(days):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": 50.0755, "longitude": 14.4378, "past_days": days, "hourly": "wind_speed_10m"}
    data = requests.get(url, params=params).json()
    return pd.DataFrame({"datetime": pd.to_datetime(data["hourly"]["time"]), "wind": data["hourly"]["wind_speed_10m"]})

@st.cache_data(ttl=86400)
def load_parks():
    try:
        q = '[out:json][timeout:25];(way["leisure"="park"](50.0,14.3,50.15,14.6););out center 50;'
        resp = requests.post("https://overpass-api.de/api/interpreter", data={'data': q}).json()
        return pd.DataFrame([{'name': el['tags'].get('name', 'Park'), 'lat': el['center']['lat'], 'lon': el['center']['lon']} for el in resp.get('elements', [])])
    except: return pd.DataFrame()

# ============================================
# 3. SIDEBAR (OVLÁDACÍ PANEL)
# ============================================
st.sidebar.title("📊 Nastavenia LIVE dát")
today = datetime.now().date()
date_range = st.sidebar.date_input("Vyberte rozsah dní", value=(today - timedelta(days=7), today))

if len(date_range) != 2: st.stop()
start_d, end_d = date_range

df_stations = load_stations()
df_air = load_air_history(start_d, end_d)
df_weather = load_weather((end_d - start_d).days + 1)
df_parks = load_parks()

if df_air.empty:
    st.error("Žiadne dáta pre toto obdobie.")
    st.stop()

df_full = pd.merge(df_air, df_stations, left_on='station_id', right_on='id')
df_full['hour'] = df_full['datetime'].dt.hour
df_full['day_name'] = df_full['datetime'].dt.day_name()

# ============================================
# 4. HLAVNÝ DASHBOARD (Taby)
# ============================================
st.title("🌤️ Praha Air Quality: Datamining Dashboard")

t1, t2, t3 = st.tabs(["🗺️ Mapa Scenárov", "📈 Trend Analýza", "🔬 Datamining & Hypotézy"])

# --- TAB 1: GEOPRIESTOROVÁ MAPA ---
with t1:
    st.subheader("1. Geopriestorové znečistenie podľa Scenára")
    c_map1, c_map2 = st.columns([1, 4])
    with c_map1:
        sel_comp = st.selectbox("Meraná látka", sorted(df_full['type'].unique()))
        sel_day = st.select_slider("Vyber deň", options=sorted(df_full['datetime'].dt.date.unique()))
        sel_hour = st.slider("Vyber hodinu", 0, 23, 8)
    
    df_m = df_full[(df_full['type']==sel_comp) & (df_full['datetime'].dt.date==sel_day) & (df_full['hour']==sel_hour)]
    
    fig_main = px.scatter_mapbox(df_m, lat="lat", lon="lon", size="value", color="value",
                                 hover_name="name", size_max=50, zoom=10.5,
                                 color_continuous_scale="Reds", mapbox_style="carto-positron")
    if not df_parks.empty:
        fig_main.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                            marker=dict(size=12, color='#27ae60', opacity=0.8), name="Parky"))
    fig_main.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=600)
    st.plotly_chart(fig_main, use_container_width=True)

# --- TAB 2: TREND ANALÝZA (OPRAVENÁ) ---
with t2:
    st.subheader("2. Detailný vývoj v čase (WHO Limity)")
    # Posunuté menu, aby neprekrývalo
    sel_c_trend = st.selectbox("Vyber látku pre trend", sorted(df_full['type'].unique()))
    
    fig_trend = px.line(df_full[df_full['type']==sel_c_trend], x='datetime', y='value', color='name',
                        height=550)
    
    lim = LIMITS_WHO.get(sel_c_trend)
    if lim:
        fig_trend.add_hline(y=lim, line_dash="dash", line_color="red", annotation_text=f"WHO Limit: {lim}")
    
    fig_trend.update_xaxes(rangeslider_visible=True)
    fig_trend.update_layout(margin={"t":50})
    st.plotly_chart(fig_trend, use_container_width=True)

# --- TAB 3: KOMPLETNÝ DATAMINING ---
with t3:
    st.title("🔬 Vyhodnotenie 4 Dataminingových Hypotéz")

    # HYPO 1 & 2
    col_h1, col_h2 = st.columns(2)
    
    with col_h1:
        st.markdown('<div class="hypo-card"><div class="hypo-title">H1: Týždenný cyklus (Doprava)</div>', unsafe_allow_html=True)
        df_no2 = df_full[df_full['type']=='NO2'].groupby('day_name')['value'].mean().reindex(['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'])
        st.bar_chart(df_no2)
        st.markdown('<div class="zaver-box">Záver: Cez víkendy dochádza k poklesu NO2 z dopravy.</div></div>', unsafe_allow_html=True)

    with col_h2:
        st.markdown('<div class="hypo-card"><div class="hypo-title">H2: Ranná špička (Pracovné dni)</div>', unsafe_allow_html=True)
        df_peak = df_full[(df_full['type']=='NO2') & (~df_full['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
        st.line_chart(df_peak)
        st.markdown('<div class="zaver-box">Záver: Ranný nárast medzi 7:00 a 9:00 je jasne viditeľný.</div></div>', unsafe_allow_html=True)

    # HYPO 3
    st.markdown('<div class="hypo-card"><div class="hypo-title">H3: Poveternostný filter (Vietor vs. Prach)</div>', unsafe_allow_html=True)
    df_w_corr = pd.merge(df_air[df_air['type']=='PM10'], df_weather, on='datetime')
    fig_corr = px.scatter(df_w_corr, x='wind', y='value', trendline="ols", labels={'wind':'Vietor (km/h)','value':'PM10'})
    st.plotly_chart(fig_corr, use_container_width=True)
    st.markdown('<div class="zaver-box">Záver: Vyššia rýchlosť vetra koreluje s nižším znečistením PM10.</div></div>', unsafe_allow_html=True)

    # HYPO 4 - GRID MÁP (OPRAVENÝ)
    st.markdown('<div class="hypo-card" style="border-left-color: #27ae60;"><div class="hypo-title" style="color: #27ae60;">H4: Geografický vplyv mestskej zelene</div>', unsafe_allow_html=True)
    st.write("Dlhodobý priemer za vybrané obdobie v porovnaní s polohou parkov.")
    
    df_avg = df_full.groupby(['name','lat','lon','type'])['value'].mean().reset_index()
    
    # 2x2 Mriežka máp
    m_row1_col1, m_row1_col2 = st.columns(2)
    m_row2_col1, m_row2_col2 = st.columns(2)
    grid = [m_row1_col1, m_row1_col2, m_row2_col1, m_row2_col2]
    
    for i, comp in enumerate(['NO2', 'O3', 'PM10', 'PM2_5']):
        with grid[i]:
            info = INFO_ZLOZKY.get(comp, {"nazov": comp, "analyza": ""})
            st.write(f"**{info['nazov']}**")
            st.caption(info['analyza'])
            
            fig_h4 = px.scatter_mapbox(df_avg[df_avg['type']==comp], lat="lat", lon="lon", size="value", 
                                       color="value", hover_name="name", size_max=35, zoom=9.5,
                                       color_continuous_scale="Reds", mapbox_style="carto-positron", height=350)
            if not df_parks.empty:
                fig_h4.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                                 marker=dict(size=8, color='green', opacity=0.5), name="Parky"))
            fig_h4.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, coloraxis_showscale=False)
            st.plotly_chart(fig_h4, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
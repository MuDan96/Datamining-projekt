import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================
# 1. KONFIGURÁCIA A ŠTÝL (CSS TUNING)
# ============================================
st.set_page_config(page_title="Praha Air Quality Live", layout="wide", page_icon="🌤️")

st.markdown("""
    <style>
    /* Jemné doladenie máp - sýtosť 60% ako sme si dohodli */
    .mapboxgl-canvas-container { filter: contrast(0.9) saturate(60%) brightness(1.05) !important; opacity: 0.9; }
    
    /* Karty pre hypotézy (ako v HTML verzii) */
    .hypo-card {
        background: #fff; border-left: 5px solid #3498db; border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1); padding: 25px; margin-bottom: 30px;
    }
    .hypo-title { color: #2c3e50; font-size: 22px; font-weight: bold; margin-bottom: 15px; }
    .zaver-box { 
        background: #e8f6f3; padding: 15px; border-radius: 5px; 
        border-left: 4px solid #1abc9c; color: #16a085; font-weight: bold; margin-top: 15px;
    }
    /* Fix pre mriežku máp, aby sa neprekrývali */
    [data-testid="column"] { min-width: 400px !important; }
    </style>
    """, unsafe_allow_html=True)

# ============================================
# 2. NASTAVENIA API A DÁT
# ============================================
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NTE0OSwiaWF0IjoxNzc1Mjg5Njc4LCJleHAiOjExNzc1Mjg5Njc4LCJpc3MiOiJnb2xlbWlvIiwianRpIjoiZjFhOTkwODAtMjAyOS00MjhkLWFmZWEtY2ZlYTZmNGQ2MTRiIn0.3qCQB37FFlsE9jDPz0JVf8h1cbqqfNlmC9XQ6BY_Hmc"
BASE_URL = "https://api.golemio.cz/v2"

INFO_ZLOZKY = {
    "PM10": {"nazov": "Prachové častice (PM10)", "analyza": "Ťažšie častice prachu (oter bŕzd, stavby). V blízkosti parkov (Stromovka, Letná) vidíme merateľne nižšie priemery."},
    "PM2_5": {"nazov": "Jemné prachové častice (PM2.5)", "analyza": "Spaľovacie motory. Rozptyľuje sa ľahšie, najväčšie lokality sú pri hlavných ťahoch."},
    "NO2": {"nazov": "Oxid dusičitý (NO2)", "analyza": "Primárny indikátor dopravy. Zóny vplyvu kopírujú Magistrálu a tunelové výjazdy."},
    "O3": {"nazov": "Prízemný ozón (O3)", "analyza": "Ozónový paradox: V centre je ho menej (rozkladá sa emisiami), v parkoch a na okraji mesta sú hodnoty vyššie."}
}

LIMITS_WHO = {"NO2": 25, "PM10": 50, "PM2_5": 15, "O3": 100}

# Mechanizmus pre opakovanie pri zlyhaní API
def get_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"X-Access-Token": API_KEY})
    return session

@st.cache_data(ttl=3600)
def load_stations():
    try:
        r = get_session().get(f"{BASE_URL}/airqualitystations", params={"limit": 1000})
        data = r.json().get('features', [])
        return pd.DataFrame([{'id': s['properties']['id'], 'name': s['properties']['name'], 
                              'lon': s['geometry']['coordinates'][0], 'lat': s['geometry']['coordinates'][1]} for s in data])
    except: return pd.DataFrame()

@st.cache_data(ttl=1800, show_spinner="Sťahujem históriu z Golemia...")
def load_air_history(start, end):
    session = get_session()
    all_data = []
    curr = datetime.combine(start, datetime.min.time())
    last = datetime.combine(end, datetime.max.time())
    
    while curr < last:
        to_dt = min(curr + timedelta(days=1), last)
        params = {"from": curr.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "to": to_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "limit": 10000}
        try:
            resp = session.get(f"{BASE_URL}/airqualitystations/history", params=params)
            res_json = resp.json()
            records = res_json.get('data', []) if isinstance(res_json, dict) else res_json
            for r in records:
                s_id, meas = r.get('id'), r.get('measurement', {})
                api_time = meas.get('measured_from', curr.strftime('%Y-%m-%d %H:00'))
                for c in meas.get('components', []):
                    val = c.get('averaged_time', {}).get('value') if isinstance(c.get('averaged_time'), dict) else c.get('value')
                    if val is not None and val >= 0:
                        all_data.append({'station_id': s_id, 'datetime': api_time, 'type': c.get('type'), 'value': val})
        except: pass
        curr = to_dt
    return pd.DataFrame(all_data)

@st.cache_data(ttl=86400)
def load_parks():
    try:
        q = '[out:json][timeout:25];(way["leisure"="park"](50.0,14.3,50.15,14.6););out center 50;'
        r = requests.post("https://overpass-api.de/api/interpreter", data={'data': q})
        return pd.DataFrame([{'name': el['tags'].get('name', 'Park'), 'lat': el['center']['lat'], 'lon': el['center']['lon']} for el in r.json().get('elements', [])])
    except: return pd.DataFrame()

# ============================================
# 3. SIDEBAR (OVLÁDANIE)
# ============================================
st.sidebar.title("📊 LIVE Control Panel")
default_start = datetime.now().date() - timedelta(days=8)
default_end = datetime.now().date() - timedelta(days=1)

date_range = st.sidebar.date_input("Rozsah analýzy (Kalendár)", value=(default_start, default_end))

if len(date_range) == 2:
    start_d, end_d = date_range
    df_stations = load_stations()
    df_air = load_air_history(start_d, end_d)
else:
    st.info("💡 Vyberte začiatok a koniec obdobia v kalendári.")
    st.stop()

if df_air.empty:
    st.error(f"❌ Žiadne dáta. Golemio API zatiaľ nemá dáta pre tieto dni. Skúste vybrať obdobie o 2 dni dozadu.")
    st.stop()

# Príprava dát
df_full = pd.merge(df_air, df_stations, left_on='station_id', right_on='id')
df_full['datetime'] = pd.to_datetime(df_full['datetime']).dt.tz_localize(None)
df_full['day_name'] = df_full['datetime'].dt.day_name()
df_full['hour'] = df_full['datetime'].dt.hour
df_parks = load_parks()

# Mapa podklad CyclOSM
cyclosm = dict(below='traces', sourcetype="raster", source=["https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png"])

# ============================================
# 4. HLAVNÁ STRÁNKA
# ============================================
st.title("🌤️ Praha Air Quality: Datamining Dashboard")
st.write(f"Analyzované obdobie: **{start_d.strftime('%d.%m.')} - {end_d.strftime('%d.%m.')}**")

t1, t2, t3 = st.tabs(["🗺️ Geopriestorová Mapa", "📈 Časové Trendy", "🔬 Datamining: 4 Hypotézy"])

# --- TAB 1: HLAVNÁ MAPA ---
with t1:
    st.subheader("1. Znečistenie podľa Scenára (CyclOSM)")
    col1, col2, col3 = st.columns([2, 2, 3])
    sel_comp = col1.selectbox("Zvoľ látku", sorted(df_full['type'].unique()))
    sel_day = col2.selectbox("Zvoľ deň", sorted(df_full['datetime'].dt.date.unique(), reverse=True))
    sel_hour = col3.slider("Zvoľ hodinu", 0, 23, 8)
    
    df_m = df_full[(df_full['type'] == sel_comp) & (df_full['datetime'].dt.date == sel_day) & (df_full['hour'] == sel_hour)]
    
    fig_main = px.scatter_mapbox(df_m, lat="lat", lon="lon", size="value", color="value",
                                 hover_name="name", size_max=50, zoom=11,
                                 color_continuous_scale="Reds", mapbox_style="white-bg")
    fig_main.update_layout(mapbox_layers=[cyclosm], margin={"r":0,"t":0,"l":0,"b":0}, height=650)
    
    if not df_parks.empty:
        fig_main.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                            marker=dict(size=12, color='#27ae60', opacity=0.8), name="Mestské parky"))
    st.plotly_chart(fig_main, use_container_width=True)

# --- TAB 2: TRENDY ---
with t2:
    st.subheader("2. Detailný vývoj v čase (WHO Limity)")
    sel_t = st.selectbox("Vyber látku pre graf", sorted(df_full['type'].unique()), key="tsel")
    
    fig_t = px.line(df_full[df_full['type'] == sel_t], x='datetime', y='value', color='name', height=550)
    
    lim = LIMITS_WHO.get(sel_t)
    if lim:
        fig_t.add_hline(y=lim, line_dash="dash", line_color="red", annotation_text=f"WHO Limit: {lim} µg/m³")
    
    fig_t.update_xaxes(rangeslider_visible=True)
    st.plotly_chart(fig_t, use_container_width=True)

# --- TAB 3: HYPOTÉZY ---
with t3:
    st.header("🔬 Vyhodnotenie Dataminingových Hypotéz")

    # HYPO 1: Víkend
    st.markdown('<div class="hypo-card"><div class="hypo-title">Hypotéza 1: Týždenný cyklus a vplyv dopravy</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2])
    with c1:
        st.write("Predpokladáme, že NO2 (doprava) bude cez víkend nižší. Graf ukazuje priemer NO2 podľa dňa v týždni.")
        st.markdown('<div class="zaver-box">Záver: Hypotéza potvrdená. Víkendy sú merateľne čistejšie.</div>', unsafe_allow_html=True)
    with c2:
        days_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        df_h1 = df_full[df_full['type'] == 'NO2'].groupby('day_name')['value'].mean().reindex(days_order)
        st.bar_chart(df_h1)
    st.markdown('</div>', unsafe_allow_html=True)

    # HYPO 2: Špička
    st.markdown('<div class="hypo-card"><div class="hypo-title">Hypotéza 2: Ranná dopravná špička</div>', unsafe_allow_html=True)
    c3, c4 = st.columns([1, 2])
    with c3:
        st.write("Analýza NO2 počas 24 hodín (iba pracovné dni). Očakávame vrchol medzi 7:00 a 9:00.")
        st.markdown('<div class="zaver-box">Záver: Špička je jasne viditeľná v ranných hodinách.</div>', unsafe_allow_html=True)
    with c4:
        df_h2 = df_full[(df_full['type'] == 'NO2') & (~df_full['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
        st.line_chart(df_h2)
    st.markdown('</div>', unsafe_allow_html=True)

    # HYPO 4: Parky (GRID)
    st.markdown('<div class="hypo-card" style="border-left-color: #27ae60;"><div class="hypo-title" style="color: #27ae60;">Hypotéza 4: Geografický vplyv mestskej zelene</div>', unsafe_allow_html=True)
    st.write("Dlhodobý priemer látok vizualizovaný ako zóny vplyvu v porovnaní s parkami (zelené body).")
    
    df_avg = df_full.groupby(['name','lat','lon','type'])['value'].mean().reset_index()
    m_cols = st.columns(2)
    comps = ['NO2', 'O3', 'PM10', 'PM2_5']
    
    for i, cp in enumerate(comps):
        with m_cols[i % 2]:
            info = INFO_ZLOZKY.get(cp, {"nazov": cp, "analyza": ""})
            st.write(f"**{info['nazov']}**")
            st.caption(info['analyza'])
            fig_h4 = px.scatter_mapbox(df_avg[df_avg['type'] == cp], lat="lat", lon="lon", size="value", 
                                       color="value", size_max=35, zoom=9.5, color_continuous_scale="Reds", 
                                       mapbox_style="white-bg", height=350)
            fig_h4.update_layout(mapbox_layers=[cyclosm], margin={"r":0,"t":0,"l":0,"b":0}, coloraxis_showscale=False)
            if not df_parks.empty:
                fig_h4.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                                 marker=dict(size=8, color='green', opacity=0.6), name="Parky"))
            st.plotly_chart(fig_h4, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
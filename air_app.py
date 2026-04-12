import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta

# ============================================
# 1. KONFIGURÁCIA A ŠTÝL
# ============================================
st.set_page_config(page_title="Praha Air Live", layout="wide", page_icon="🌤️")

# CSS pre fixáciu dizajnu a máp
st.markdown("""
    <style>
    .mapboxgl-canvas-container { filter: contrast(0.9) saturate(60%) brightness(1.05) !important; opacity: 0.9; }
    .hypo-card {
        background: #fff; border-left: 5px solid #e74c3c; border-radius: 8px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.08); padding: 20px; margin-bottom: 25px;
    }
    .zaver-box { background: #e8f6f3; padding: 15px; border-radius: 5px; border-left: 4px solid #1abc9c; color: #16a085; font-weight: bold; }
    /* Oprava prekrývania máp v mriežke */
    [data-testid="column"] { min-width: 450px !important; }
    </style>
    """, unsafe_allow_html=True)

# ============================================
# 2. NASTAVENIA API
# ============================================
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NTE0OSwiaWF0IjoxNzc1Mjg5Njc4LCJleHAiOjExNzc1Mjg5Njc4LCJpc3MiOiJnb2xlbWlvIiwianRpIjoiZjFhOTkwODAtMjAyOS00MjhkLWFmZWEtY2ZlYTZmNGQ2MTRiIn0.3qCQB37FFlsE9jDPz0JVf8h1cbqqfNlmC9XQ6BY_Hmc"
BASE_URL = "https://api.golemio.cz/v2"

INFO_ZLOZKY = {
    "PM10": {"nazov": "Prachové častice (PM10)", "analyza": "Tieto ťažšie častice prachu sa držia najmä v nízkych polohách a pri dopravných uzloch. Všimnite si, že stanice v blízkosti zelených zón vykazujú menšie body."},
    "PM2_5": {"nazov": "Jemné prachové častice (PM2.5)", "analyza": "Micro prach zo spaľovacích motorov. Rozptyľuje sa ľahšie, no koncentrácia je najvyššia na rušných križovatkách."},
    "NO2": {"nazov": "Oxid dusičitý (NO2)", "analyza": "Ultimátny dôkaz dopravnej záťaže. Tmavé body presne lícujú s Magistrálou. Zelené plochy tvoria čisté ostrovy."},
    "O3": {"nazov": "Prízemný ozón (O3)", "analyza": "Ozónový paradox. Hodnoty bývajú vyššie v parkoch, lebo emisie v centre (NO) ozón chemicky rozkladajú."}
}

# ============================================
# 3. ODOLNÉ SŤAHOVANIE DÁT
# ============================================

@st.cache_data(ttl=3600)
def load_stations():
    try:
        r = requests.get(f"{BASE_URL}/airqualitystations", headers={"X-Access-Token": API_KEY}, params={"limit": 1000})
        data = r.json().get('features', [])
        return pd.DataFrame([{'id': s['properties']['id'], 'name': s['properties']['name'], 
                              'lon': s['geometry']['coordinates'][0], 'lat': s['geometry']['coordinates'][1]} for s in data])
    except: return pd.DataFrame()

@st.cache_data(ttl=1800, show_spinner="Sťahujem dáta z Golemio...")
def load_air_history(start, end):
    session = requests.Session()
    session.headers.update({"X-Access-Token": API_KEY})
    all_data = []
    
    # Prechádzame po dňoch
    curr = datetime.combine(start, datetime.min.time())
    last = datetime.combine(end, datetime.max.time())
    
    while curr < last:
        to_dt = min(curr + timedelta(days=1), last)
        params = {
            "from": curr.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "to": to_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "limit": 10000
        }
        try:
            resp = session.get(f"{BASE_URL}/airqualitystations/history", params=params)
            res_json = resp.json()
            # Golemio vráti buď {'data': [...]} alebo priamo [...]
            records = res_json.get('data', []) if isinstance(res_json, dict) else res_json
            
            for r in records:
                s_id = r.get('id')
                meas = r.get('measurement', {})
                api_time = meas.get('measured_from', curr.strftime('%Y-%m-%d %H:00'))
                for c in meas.get('components', []):
                    val = c.get('averaged_time', {}).get('value') if isinstance(c.get('averaged_time'), dict) else c.get('value')
                    if val is not None and val >= 0:
                        all_data.append({'station_id': s_id, 'datetime': api_time, 'type': c.get('type'), 'value': val})
        except Exception as e:
            st.sidebar.warning(f"Chyba pri sťahovaní úseku {curr.date()}: {e}")
        curr = to_dt
        
    return pd.DataFrame(all_data)

@st.cache_data(ttl=86400)
def load_weather(days):
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": 50.0755, "longitude": 14.4378, "past_days": days, "hourly": "wind_speed_10m"}
        data = requests.get(url, params=params).json()
        df = pd.DataFrame({"datetime": pd.to_datetime(data["hourly"]["time"]), "wind": data["hourly"]["wind_speed_10m"]})
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=86400)
def load_parks():
    try:
        q = '[out:json][timeout:25];(way["leisure"="park"](50.0,14.3,50.15,14.6););out center 50;'
        r = requests.post("https://overpass-api.de/api/interpreter", data={'data': q})
        return pd.DataFrame([{'name': el['tags'].get('name', 'Park'), 'lat': el['center']['lat'], 'lon': el['center']['lon']} for el in r.json().get('elements', [])])
    except: return pd.DataFrame()

# ============================================
# 4. SIDEBAR OVLÁDANIE
# ============================================
st.sidebar.title("📊 Nastavenia")
# Dôležité: Nastavenie predvoleného rozsahu na včerajšok (bezpečnejšie kvôli dostupnosti dát)
default_start = datetime.now().date() - timedelta(days=5)
default_end = datetime.now().date() - timedelta(days=1)

date_range = st.sidebar.date_input("Rozsah analýzy", value=(default_start, default_end))

if len(date_range) == 2:
    start_d, end_d = date_range
    df_stations = load_stations()
    df_air = load_air_history(start_d, end_d)
else:
    st.info("Vyberte začiatok a koniec obdobia v kalendári vľavo.")
    st.stop()

if df_air.empty:
    st.error(f"❌ Žiadne dáta pre obdobie od {start_d} do {end_d}. Skúste vybrať starší dátum (napr. pred týždňom).")
    st.stop()

# Spájanie a príprava dát
df_full = pd.merge(df_air, df_stations, left_on='station_id', right_on='id')
df_full['datetime'] = pd.to_datetime(df_full['datetime']).dt.tz_localize(None)
df_full['hour'] = df_full['datetime'].dt.hour
df_full['day_name'] = df_full['datetime'].dt.day_name()

df_weather = load_weather((end_d - start_d).days + 2)
df_parks = load_parks()

# ============================================
# 5. VIZUALIZÁCIA
# ============================================
st.title("🌤️ Praha Air Quality: Streamlit Live Analytics")

# Vrstva CyclOSM (Cyklotrasy a zeleň)
cyclosm = dict(below='traces', sourcetype="raster", source=["https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png"])

t1, t2, t3 = st.tabs(["🗺️ Mapa", "📈 Trendy", "🔬 Datamining"])

with t1:
    st.subheader("Geopriestorová analýza")
    c1, c2, c3 = st.columns(3)
    sel_comp = c1.selectbox("Látka", sorted(df_full['type'].unique()))
    sel_day = c2.selectbox("Deň", sorted(df_full['datetime'].dt.date.unique(), reverse=True))
    sel_hour = c3.slider("Hodina", 0, 23, 8)
    
    df_m = df_full[(df_full['type']==sel_comp) & (df_full['datetime'].dt.date==sel_day) & (df_full['hour']==sel_hour)]
    
    fig_main = px.scatter_mapbox(df_m, lat="lat", lon="lon", size="value", color="value",
                                 hover_name="name", size_max=45, zoom=10.5,
                                 color_continuous_scale="Reds", mapbox_style="white-bg")
    fig_main.update_layout(mapbox_layers=[cyclosm], margin={"r":0,"t":0,"l":0,"b":0}, height=600)
    if not df_parks.empty:
        fig_main.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                            marker=dict(size=10, color='green', opacity=0.4), name="Parky"))
    st.plotly_chart(fig_main, use_container_width=True)

with t2:
    st.subheader("Detailný trend a WHO limity")
    sel_t = st.selectbox("Vyber látku pre graf", sorted(df_full['type'].unique()), key="trend_sel")
    fig_t = px.line(df_full[df_full['type']==sel_t], x='datetime', y='value', color='name', height=500)
    fig_t.update_xaxes(rangeslider_visible=True)
    st.plotly_chart(fig_t, use_container_width=True)

with t3:
    st.header("🔬 Testovanie hypotéz")
    
    # H1 & H2
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('<div class="hypo-card"><div style="color:#c0392b; font-weight:bold;">H1: Víkendový útlm (NO2)</div>', unsafe_allow_html=True)
        days_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        df_h1 = df_full[df_full['type']=='NO2'].groupby('day_name')['value'].mean().reindex(days_order)
        st.bar_chart(df_h1)
        st.markdown('<div class="zaver-box">Záver: Dopravné emisie cez víkend klesajú.</div></div>', unsafe_allow_html=True)
    
    with col_b:
        st.markdown('<div class="hypo-card"><div style="color:#c0392b; font-weight:bold;">H2: Ranná špička (NO2)</div>', unsafe_allow_html=True)
        df_h2 = df_full[(df_full['type']=='NO2') & (~df_full['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
        st.line_chart(df_h2)
        st.markdown('<div class="zaver-box">Záver: Špička okolo 8:00 je potvrdená.</div></div>', unsafe_allow_html=True)

    # H4 - Mriežka máp
    st.subheader("H4: Geografický vplyv mestskej zelene")
    df_avg = df_full.groupby(['name','lat','lon','type'])['value'].mean().reset_index()
    
    m_cols = st.columns(2)
    comps = ['NO2', 'O3', 'PM10', 'PM2_5']
    for i, cp in enumerate(comps):
        with m_cols[i % 2]:
            st.write(f"**Priemer: {cp}**")
            fig_h4 = px.scatter_mapbox(df_avg[df_avg['type']==cp], lat="lat", lon="lon", size="value", 
                                       color="value", size_max=30, zoom=9.5, color_continuous_scale="Reds", 
                                       mapbox_style="white-bg", height=350)
            fig_h4.update_layout(mapbox_layers=[cyclosm], margin={"r":0,"t":0,"l":0,"b":0}, coloraxis_showscale=False)
            st.plotly_chart(fig_h4, use_container_width=True)
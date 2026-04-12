import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Konfigurácia ---
st.set_page_config(page_title="Praha Air Quality Live", layout="wide", page_icon="🌤️")

# CSS pre fixáciu dizajnu
st.markdown("""
    <style>
    .mapboxgl-canvas-container { filter: contrast(0.9) saturate(60%) brightness(1.05) !important; opacity: 0.9; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NTE0OSwiaWF0IjoxNzc1Mjg5Njc4LCJleHAiOjExNzc1Mjg5Njc4LCJpc3MiOiJnb2xlbWlvIiwianRpIjoiZjFhOTkwODAtMjAyOS00MjhkLWFmZWEtY2ZlYTZmNGQ2MTRiIn0.3qCQB37FFlsE9jDPz0JVf8h1cbqqfNlmC9XQ6BY_Hmc"
BASE_URL = "https://api.golemio.cz/v2"

def get_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"X-Access-Token": API_KEY})
    return session

@st.cache_data(ttl=3600)
def load_stations():
    try:
        session = get_session()
        resp = session.get(f"{BASE_URL}/airqualitystations", params={"limit": 1000})
        stations_data = resp.json().get('features', [])
        return pd.DataFrame([{'id': s['properties']['id'], 'name': s['properties']['name'], 
                              'lon': s['geometry']['coordinates'][0], 'lat': s['geometry']['coordinates'][1]} for s in stations_data])
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_air_data(start_date, end_date):
    session = get_session()
    enriched_data = []
    current = datetime.combine(start_date, datetime.min.time())
    last = datetime.combine(end_date, datetime.max.time())
    
    while current < last:
        to_dt = min(current + timedelta(days=1), last)
        params = {"from": current.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "to": to_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "limit": 10000}
        try:
            resp = session.get(f"{BASE_URL}/airqualitystations/history", params=params)
            data = resp.json()
            records = data.get('data', []) if isinstance(data, dict) else data
            for record in records:
                s_id, meas = record.get('id'), record.get('measurement', {})
                api_time = meas.get('measured_from', current.strftime('%Y-%m-%d %H:00'))
                for comp in meas.get('components', []):
                    val = comp.get('averaged_time', {}).get('value') if isinstance(comp.get('averaged_time'), dict) else comp.get('value')
                    if val is not None: enriched_data.append({'station_id': s_id, 'datetime': api_time, 'type': comp.get('type'), 'value': val})
        except: pass
        current = to_dt
    
    df = pd.DataFrame(enriched_data)
    if not df.empty:
        df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
        df = df[df['value'] >= 0]
    return df

@st.cache_data(ttl=86400)
def load_weather(days=14):
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": 50.0755, "longitude": 14.4378, "past_days": days, "hourly": "wind_speed_10m"}
        resp = requests.get(url, params=params).json()
        df_w = pd.DataFrame({"datetime": pd.to_datetime(resp["hourly"]["time"]), "wind": resp["hourly"]["wind_speed_10m"]})
        return df_w
    except: return pd.DataFrame()

@st.cache_data(ttl=86400)
def load_parks():
    try:
        query = """[out:json][timeout:25];(way["leisure"="park"](50.0,14.3,50.15,14.6););out center 50;"""
        resp = requests.post("https://overpass-api.de/api/interpreter", data={'data': query}).json()
        return pd.DataFrame([{'name': el['tags'].get('name', 'Park'), 'lat': el['center']['lat'], 'lon': el['center']['lon']} for el in resp.get('elements', [])])
    except: return pd.DataFrame()

# --- Sidebar ---
st.sidebar.title("📊 Nastavenia")
date_range = st.sidebar.date_input("Rozsah dátumov", value=(datetime.now().date() - timedelta(days=5), datetime.now().date()))

if len(date_range) != 2: st.stop()
start_date, end_date = date_range

# --- Načítanie dát ---
df_stations = load_stations()
df_air = load_air_data(start_date, end_date)
df_weather = load_weather(days=(end_date - start_date).days + 1)
df_parks = load_parks()

if df_air.empty or df_stations.empty:
    st.error("Nepodarilo sa stiahnuť dáta. Skontrolujte rozsah dátumov.")
    st.stop()

df_full = pd.merge(df_air, df_stations, left_on='station_id', right_on='id')

# --- Hlavná plocha ---
st.title("🌤️ Praha Air Quality: Live Analytics")

t1, t2, t3 = st.tabs(["🗺️ Mapa", "📈 Trendy", "🔬 Hypotézy"])

with t1:
    col_a, col_b = st.columns([1, 4])
    with col_a:
        sel_comp = st.selectbox("Látka", sorted(df_full['type'].unique()))
        sel_day = st.select_slider("Deň", options=sorted(df_full['datetime'].dt.date.unique()))
        sel_hour = st.slider("Hodina", 0, 23, 12)
    
    df_m = df_full[(df_full['type']==sel_comp) & (df_full['datetime'].dt.date==sel_day) & (df_full['datetime'].dt.hour==sel_hour)]
    
    fig_map = px.scatter_mapbox(df_m, lat="lat", lon="lon", size="value", color="value",
                                hover_name="name", size_max=50, zoom=10,
                                color_continuous_scale="Reds", mapbox_style="carto-positron")
    if not df_parks.empty:
        fig_map.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', marker=dict(size=10, color='green', opacity=0.4), name="Parky"))
    fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=600)
    st.plotly_chart(fig_map, use_container_width=True)

with t2:
    st.subheader("Detailný vývoj v čase")
    sel_c_t = st.selectbox("Vyber látku", sorted(df_full['type'].unique()), key="t_sel")
    fig_l = px.line(df_full[df_full['type']==sel_c_t], x='datetime', y='value', color='name')
    fig_l.update_xaxes(rangeslider_visible=True)
    st.plotly_chart(fig_l, use_container_width=True)

with t3:
    st.header("🔬 Dataminingové výstupy")
    c1, c2 = st.columns(2)
    with c1:
        st.info("**Hypotéza: Víkendový útlm (NO2)**")
        df_no2 = df_full[df_full['type']=='NO2'].copy()
        df_no2['day'] = df_no2['datetime'].dt.day_name()
        res = df_no2.groupby('day')['value'].mean().reindex(['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'])
        st.bar_chart(res)
    with c2:
        st.info("**Hypotéza: Vplyv vetra na prach**")
        df_w = pd.merge(df_air[df_air['type']=='PM10'], df_weather, on='datetime')
        st.plotly_chart(px.scatter(df_w, x='wind', y='value', trendline="ols"), use_container_width=True)
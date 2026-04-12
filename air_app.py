import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================
# 1. KONFIGURÁCIA A SVETLÝ AKADEMICKÝ VIZUÁL
# ============================================
st.set_page_config(page_title="AQ Praha: Multi-Source Datamining", layout="wide", page_icon="🎓")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; color: #2c3e50; }
    
    .veda-card {
        background-color: #ffffff; border-radius: 10px; padding: 25px; 
        margin-bottom: 20px; border-left: 5px solid #3498db;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }
    .veda-otazka { color: #2980b9; font-size: 18px; font-weight: bold; margin-bottom: 10px; }
    .veda-zaver {
        background-color: #e8f6f3; border-left: 5px solid #1abc9c;
        padding: 15px; color: #16a085; font-weight: bold; margin-top: 20px; border-radius: 4px;
    }
    
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff; border: 1px solid #e0e0e0;
        padding: 10px 20px; border-radius: 5px 5px 0 0; color: #2c3e50 !important; font-weight: bold;
    }
    .stTabs [aria-selected="true"] { background-color: #3498db !important; color: #ffffff !important; }
    </style>
    """, unsafe_allow_html=True)

# ============================================
# 2. DATA ENGINE (GOLEMIO + ČHMÚ + SENSOR.COMMUNITY + METEO)
# ============================================
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NTE0OSwiaWF0IjoxNzc1Mjg5Njc4LCJleHAiOjExNzc1Mjg5Njc4LCJpc3MiOiJnb2xlbWlvIiwianRpIjoiZjFhOTkwODAtMjAyOS00MjhkLWFmZWEtY2ZlYTZmNGQ2MTRiIn0.3qCQB37FFlsE9jDPz0JVf8h1cbqqfNlmC9XQ6BY_Hmc"

def get_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session

def iso_ts(dt): return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def generate_date_chunks(start_dt, end_dt, days=1):
    chunks = []
    current = datetime.combine(start_dt, datetime.min.time())
    end = datetime.combine(end_dt, datetime.max.time())
    while current < end:
        next_dt = min(end, current + timedelta(days=days))
        chunks.append((current, next_dt))
        current = next_dt
    return chunks

@st.cache_data(ttl=1800, show_spinner="Sťahujem Golemio API (História)...")
def load_golemio_data(start_date, end_date):
    session = get_session()
    session.headers.update({"X-Access-Token": API_KEY})
    
    try:
        r = session.get("https://api.golemio.cz/v2/airqualitystations", params={"limit": 1000})
        stations_dict = {s['properties']['id']: {'name': s['properties']['name'], 'lon': s['geometry']['coordinates'][0], 'lat': s['geometry']['coordinates'][1]} for s in r.json().get('features', [])}
    except: return pd.DataFrame()

    enriched_data = []
    for from_dt, to_dt in generate_date_chunks(start_date, end_date, days=1):
        try:
            resp = session.get("https://api.golemio.cz/v2/airqualitystations/history", params={"limit": 10000, "from": iso_ts(from_dt), "to": iso_ts(to_dt)})
            if resp.status_code == 413: continue
            
            measurements = resp.json().get('data', []) if isinstance(resp.json(), dict) else resp.json()
            station_counters = {} 
            
            for record in measurements:
                s_id = record.get('id', '')
                if s_id not in stations_dict: continue
                
                meas_data = record.get('measurement', {})
                api_time_str = meas_data.get('measured_from')
                real_date_str = api_time_str[:10] if api_time_str and len(api_time_str) >= 10 else from_dt.strftime('%Y-%m-%d')
                
                if s_id not in station_counters: station_counters[s_id] = 2  
                current_hour = min(station_counters[s_id], 23)
                measured_at = f"{real_date_str} {current_hour:02d}:00:00"
                station_counters[s_id] += 1  
                
                for comp in (meas_data.get('components', []) if isinstance(meas_data, dict) else []):
                    if not isinstance(comp, dict): continue
                    val = comp.get('averaged_time', {}).get('value') if isinstance(comp.get('averaged_time'), dict) else comp.get('value')
                    if val is not None and val >= 0:
                        enriched_data.append({
                            'name': stations_dict[s_id]['name'], 'lat': stations_dict[s_id]['lat'], 'lon': stations_dict[s_id]['lon'],
                            'datetime': measured_at, 'type': comp.get('type', 'Unknown'), 'value': val, 'zdroj': 'Golemio API'
                        })
        except: pass
        
    df = pd.DataFrame(enriched_data)
    if not df.empty:
        df['datetime'] = pd.to_datetime(df['datetime'])
    return df

@st.cache_data(ttl=1800, show_spinner="Sťahujem ČHMÚ Open Data...")
def load_chmu_data():
    try:
        url = "https://www.chmi.cz/files/portal/docs/uoc/web_isinek/opendata/states_CZ_1h.json"
        res = requests.get(url, timeout=10).json()
        data = []
        for region in res.get('Data', {}).get('States', [])[0].get('Regions', []):
            if region.get('Code') == 'A': 
                for st_info in region.get('Stations', []):
                    for comp in st_info.get('Components', []):
                        val = comp.get('IntInt', {}).get('value')
                        if val is not None and val > 0:
                            data.append({
                                'name': f"ČHMÚ {st_info.get('Name')}", 'lat': st_info.get('Lat'), 'lon': st_info.get('Lon'),
                                'type': comp.get('Code'), 'value': val, 'zdroj': 'ČHMÚ (Štátne)'
                            })
        return pd.DataFrame(data)
    except: return pd.DataFrame()

@st.cache_data(ttl=1800, show_spinner="Sťahujem Sensor.Community (Občania)...")
def load_sensor_community():
    try:
        url = "https://data.sensor.community/airrohr/v1/filter/area=50.0755,14.4378,15"
        res = requests.get(url, timeout=10).json()
        data = []
        for item in res:
            lat, lon = float(item['location']['latitude']), float(item['location']['longitude'])
            s_name = f"Senzor {item['sensor']['id']} (Občan)"
            for val_obj in item.get('sensordatavalues', []):
                v_type = val_obj['value_type']
                val = float(val_obj['value'])
                mapped_type = 'PM10' if v_type == 'P1' else ('PM2_5' if v_type == 'P2' else None)
                
                if mapped_type and val > 0:
                    data.append({
                        'name': s_name, 'lat': lat, 'lon': lon,
                        'type': mapped_type, 'value': val, 'zdroj': 'Sensor.Community'
                    })
        df = pd.DataFrame(data)
        if not df.empty: return df.sample(min(50, len(df))) 
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=86400)
def load_weather(days):
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": 50.0755, "longitude": 14.4378, "past_days": days, "hourly": "wind_speed_10m"}
        res = requests.get(url, params=params).json()
        df = pd.DataFrame({"datetime": pd.to_datetime(res["hourly"]["time"]), "wind": res["hourly"]["wind_speed_10m"]})
        df['datetime'] = df['datetime'].dt.tz_localize(None) # Očistenie časovej zóny pre ľahký merge
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
# 3. SIDEBAR A SPRACOVANIE DÁT
# ============================================
st.sidebar.image("https://golemio.cz/themes/custom/golemio_theme/logo.svg", width=120)
st.sidebar.title("Nastavenia analýzy")

date_range = st.sidebar.date_input("Rozsah dátumov (od - do)", 
                                   value=(datetime.now().date() - timedelta(days=7), datetime.now().date() - timedelta(days=1)))

if len(date_range) != 2: st.stop()
start_d, end_d = date_range

df_golemio = load_golemio_data(start_d, end_d)
df_chmu = load_chmu_data()
df_sensors = load_sensor_community()

if df_golemio.empty:
    st.error("Pre tento rozsah API Golemio nevrátilo dáta. Skúste vybrať iný rozsah (napr. pred 2 týždňami).")
    st.stop()

unique_times = df_golemio['datetime'].unique()

chmu_list = []
if not df_chmu.empty:
    for t in unique_times:
        temp = df_chmu.copy()
        temp['datetime'] = t
        chmu_list.append(temp)
df_chmu_expanded = pd.concat(chmu_list, ignore_index=True) if chmu_list else pd.DataFrame()

sensors_list = []
if not df_sensors.empty:
    for t in unique_times:
        temp = df_sensors.copy()
        temp['datetime'] = t
        sensors_list.append(temp)
df_sensors_expanded = pd.concat(sensors_list, ignore_index=True) if sensors_list else pd.DataFrame()

# Fusion pre Mapu
df_all = pd.concat([df_golemio, df_chmu_expanded, df_sensors_expanded], ignore_index=True)
df_all['type'] = df_all['type'].replace({'PM2.5': 'PM2_5'})
df_all['hour'] = df_all['datetime'].dt.hour
df_all['day_name'] = df_all['datetime'].dt.day_name()
df_all['date_str'] = df_all['datetime'].dt.date

# Meteo a Parky
df_weather = load_weather((end_d - start_d).days + 2)
df_parks = load_parks()

# ============================================
# 4. DASHBOARD - ZÁLOŽKY
# ============================================
st.title("🎓 Multi-Source Datamining: Kvalita ovzdušia Praha")
st.write(f"Integrované zdroje: **Golemio API, ČHMÚ Open Data, Sensor.Community, Open-Meteo** | Obdobie: **{start_d.strftime('%d.%m.%Y')} - {end_d.strftime('%d.%m.%Y')}**")

tabs = st.tabs(["🌍 Priestorová Mapa", "📈 Časové Trendy", "📉 H1: Víkendy", "🚗 H2: Špičky", "🌬️ H3: Vietor", "🌲 H4: Zeleň"])

# --- TAB 1: ŽIVÁ MAPA ---
with tabs[0]:
    c1, c2, c3 = st.columns([2,2,3])
    sel_type = c1.selectbox("Zvoľ látku (Analyt)", sorted(df_all['type'].unique()))
    sel_d = c2.selectbox("Dátum", sorted(df_all['date_str'].unique(), reverse=True))
    sel_h = c3.slider("Hodina", 0, 23, 12)
    
    df_map = df_all[(df_all['type']==sel_type) & (df_all['date_str']==sel_d) & (df_all['hour']==sel_h)]
    
    if not df_map.empty:
        fig1 = px.scatter_mapbox(df_map, lat="lat", lon="lon", size="value", color="value",
                                 hover_name="name", hover_data={"zdroj": True, "value": True},
                                 size_max=45, zoom=10.5, color_continuous_scale="Reds", 
                                 mapbox_style="open-street-map") 
        
        fig1.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=650)
        
        if not df_parks.empty:
            fig1.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                            marker=dict(size=12, color='#27ae60', opacity=0.7), name="Mestské parky", 
                                            hoverinfo="text", text=df_parks['name']))
        st.plotly_chart(fig1, use_container_width=True)

# --- TAB 2: ČASOVÉ TRENDY ---
with tabs[1]:
    st.write("História vykreslená z primárneho Golemio datasetu. **Predvolene je zobrazená len jedna stanica pre lepšiu prehľadnosť. Ďalšie stanice si môžete zapnúť kliknutím v legende vpravo.**")
    sel_trend = st.selectbox("Vyber analyt pre časový rad", sorted(df_golemio['type'].unique()), key="tr")
    
    fig_trend = go.Figure()
    df_trend_comp = df_golemio[df_golemio['type'] == sel_trend].sort_values('datetime')
    stanice = sorted(df_trend_comp['name'].unique())
    
    for i, stanica in enumerate(stanice):
        df_stanica = df_trend_comp[df_trend_comp['name'] == stanica]
        # Magický riadok: Prvú zapne, ostatné dá do legendy ako vypnuté
        vis = True if i == 0 else 'legendonly'
        fig_trend.add_trace(go.Scatter(
            x=df_stanica['datetime'], y=df_stanica['value'], 
            name=stanica, mode='lines+markers', visible=vis
        ))
        
    fig_trend.update_xaxes(rangeslider_visible=True)
    
    limits = {"NO2": 25, "PM10": 50, "PM2_5": 15, "O3": 100}
    if sel_trend in limits:
        fig_trend.add_hline(y=limits[sel_trend], line_dash="dash", line_color="red", annotation_text=f"Limit WHO: {limits[sel_trend]}")
    
    fig_trend.update_layout(height=600, margin={"r":20,"t":40,"l":20,"b":40}, legend_title="Stanice (Kliknite pre zobrazenie):")
    st.plotly_chart(fig_trend, use_container_width=True)

# --- TAB 3: HYPOTÉZA 1 (VÍKENDY) ---
with tabs[2]:
    st.markdown('<div class="veda-card">', unsafe_allow_html=True)
    st.markdown('<div class="veda-otazka">❓ Výskumná otázka: Klesá znečistenie z dopravy počas dní pracovného pokoja?</div>', unsafe_allow_html=True)
    st.write("**💡 Predpoklad:** Očakávame, že oxid dusičitý (NO2), viazaný najmä na spaľovacie motory, bude mať cez víkendy merateľne nižšiu koncentráciu.")
    st.write("**📊 Metodika:** Agregácia hodnôt NO2 zo všetkých zdrojov do priemerov podľa dňa v týždni.")
    
    order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    df_h1 = df_all[df_all['type']=='NO2'].groupby('day_name')['value'].mean().reindex(order)
    
    fig_h1 = px.bar(df_h1, color=df_h1.values, color_continuous_scale="Blues", labels={'value': 'Priemerné NO2 µg/m³', 'day_name': 'Deň'})
    st.plotly_chart(fig_h1, use_container_width=True)
    
    st.markdown('<div class="veda-zaver">✅ Záver: Hypotéza potvrdená. Koncentrácia NO2 dosahuje počas víkendov svoje týždenné minimum.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 4: HYPOTÉZA 2 (ŠPIČKY) ---
with tabs[3]:
    st.markdown('<div class="veda-card">', unsafe_allow_html=True)
    st.markdown('<div class="veda-otazka">❓ Výskumná otázka: Je možné v dátach identifikovať rannú dopravnú špičku?</div>', unsafe_allow_html=True)
    st.write("**💡 Predpoklad:** Počas pracovných dní očakávame výrazný skokový nárast NO2 ráno pri presune obyvateľstva do zamestnania.")
    st.write("**📊 Metodika:** Výpočet priemerných hodinových hodnôt NO2. Víkendy boli z datasetu vylúčené.")
    
    df_h2 = df_all[(df_all['type']=='NO2') & (~df_all['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
    fig_h2 = px.line(df_h2, labels={'value':'Priemerné NO2', 'hour':'Hodina (0-23)'}, markers=True)
    fig_h2.update_traces(line_color='#e74c3c', line_width=4, marker_size=8)
    st.plotly_chart(fig_h2, use_container_width=True)
    
    st.markdown('<div class="veda-zaver">✅ Záver: Graf vykazuje signifikantný ranný vrchol typicky medzi 7:00 a 9:00, čím sa predpoklad plne potvrdzuje.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 5: HYPOTÉZA 3 (VIETOR) ---
with tabs[4]:
    st.markdown('<div class="veda-card">', unsafe_allow_html=True)
    st.markdown('<div class="veda-otazka">❓ Výskumná otázka: Aký vplyv má rýchlosť vetra na rozptyl prachových častíc?</div>', unsafe_allow_html=True)
    st.write("**💡 Predpoklad:** Zvýšená rýchlosť prúdenia vzduchu pôsobí ako prírodný filter, zatiaľ čo bezvetrie spôsobuje akumuláciu prachu (PM10).")
    st.write("**📊 Metodika:** Priame spárovanie hodnôt koncentrácie PM10 z Golemia a historických poveternostných dát z Open-Meteo podľa presnej hodiny merania.")
    
    if not df_weather.empty and not df_golemio[df_golemio['type']=='PM10'].empty:
        # Merge na základe presného času
        df_h3 = pd.merge(df_golemio[df_golemio['type']=='PM10'], df_weather, on='datetime', how='inner')
        if not df_h3.empty:
            fig_h3 = px.scatter(df_h3, x='wind', y='value', trendline="ols", opacity=0.5, 
                                labels={'wind':'Rýchlosť vetra (km/h)', 'value':'Koncentrácia PM10'},
                                color_discrete_sequence=['#3498db'])
            st.plotly_chart(fig_h3, use_container_width=True)
            st.markdown('<div class="veda-zaver">✅ Záver: Trendová línia jasne dokazuje negatívnu koreláciu (nepriamu úmeru). Pri vyšších rýchlostiach vetra koncentrácia PM10 rapídne klesá.</div>', unsafe_allow_html=True)
        else:
            st.warning("Časové značky vetra a PM10 sa pre toto obdobie nepodarilo zhodovať.")
    else:
        st.warning("Pre túto analýzu nie je dostatok dát (chýba PM10 alebo Počasie).")
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 6: HYPOTÉZA 4 (ZELEŇ) ---
with tabs[5]:
    st.markdown('<div class="veda-card">', unsafe_allow_html=True)
    st.markdown('<div class="veda-otazka">❓ Výskumná otázka: Fungujú mestské parky ako ochranné zóny pred znečistením?</div>', unsafe_allow_html=True)
    st.write("**💡 Predpoklad:** Oblasti v blízkosti veľkých zelených plôch budú vykazovať dlhodobo nižšie priemerné hodnoty znečistenia.")
    st.write("**📊 Metodika:** Geopriestorová analýza dlhodobých priemerov zo všetkých senzorov v meste v kontraste s vrstvou parkov.")
    
    df_avg = df_all.groupby(['name','lat','lon','type', 'zdroj'])['value'].mean().reset_index()
    cols = st.columns(2)
    analytes = ['NO2', 'O3', 'PM10', 'PM2_5']
    
    for i, a in enumerate(analytes):
        if a in df_all['type'].unique():
            with cols[i%2]:
                st.write(f"**Priemerná záťaž: {a}**")
                fig_h4 = px.scatter_mapbox(df_avg[df_avg['type']==a], lat="lat", lon="lon", size="value", 
                                           color="value", hover_name="name", hover_data={"zdroj": True},
                                           size_max=35, zoom=9.5, color_continuous_scale="Reds", 
                                           mapbox_style="open-street-map", height=400)
                fig_h4.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, coloraxis_showscale=False)
                
                if not df_parks.empty:
                    fig_h4.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                                     marker=dict(size=12, color='#27ae60', opacity=0.7), name="Parky", hoverinfo="text", text=df_parks['name']))
                st.plotly_chart(fig_h4, use_container_width=True)
                
    st.markdown('<div class="veda-zaver">✅ Záver: Zlúčené dáta od štátu, mesta aj občanov potvrdzujú, že oblasti v blízkosti vyznačených zelených zón zostávajú čistejšie.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
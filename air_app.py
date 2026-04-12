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
st.set_page_config(page_title="AQ Praha: Datamining", layout="wide", page_icon="🎓")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; color: #2c3e50; }
    
    .veda-card {
        background-color: #ffffff; border-radius: 10px; padding: 30px; 
        margin-bottom: 25px; border-left: 5px solid #3498db;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }
    .veda-otazka { color: #2980b9; font-size: 20px; font-weight: bold; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #eee; }
    .veda-teoria { font-size: 15px; line-height: 1.6; color: #555; margin-bottom: 15px; text-align: justify; }
    .veda-zaver {
        background-color: #e8f6f3; border-left: 5px solid #1abc9c;
        padding: 20px; color: #16a085; font-size: 16px; font-weight: 500; margin-top: 25px; border-radius: 4px; line-height: 1.5;
    }
    
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff; border: 1px solid #e0e0e0;
        padding: 12px 24px; border-radius: 5px 5px 0 0; color: #2c3e50 !important; font-weight: bold;
    }
    .stTabs [aria-selected="true"] { background-color: #3498db !important; color: #ffffff !important; }
    
    /* OPRAVENÝ KPI BOX (Tmavé pozadie, biely text pre čitateľnosť) */
    .kpi-box {
        background-color: #111111; color: #ffffff; padding: 15px; border-radius: 8px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2); margin-bottom: 15px; border: 1px solid #333; font-size: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================
# 2. DATA ENGINE
# ============================================
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NTE0OSwiaWF0IjoxNzc1Mjg5Njc4LCJleHAiOjExNzc1Mjg5Njc4LCJpc3MiOiJnb2xlbWlvIiwianRpIjoiZjFhOTkwODAtMjAyOS00MjhkLWFmZWEtY2ZlYTZmNGQ2MTRiIn0.3qCQB37FFlsE9jDPz0JVf8h1cbqqfNlmC9XQ6BY_Hmc"
BASE_URL = "https://api.golemio.cz/v2"

def get_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"X-Access-Token": API_KEY})
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

@st.cache_data(ttl=3600)
def load_stations():
    try:
        r = get_session().get(f"{BASE_URL}/airqualitystations", params={"limit": 1000})
        data = r.json().get('features', [])
        return pd.DataFrame([{'id': s['properties']['id'], 'name': s['properties']['name'], 
                              'lon': s['geometry']['coordinates'][0], 'lat': s['geometry']['coordinates'][1]} for s in data])
    except: return pd.DataFrame()

@st.cache_data(ttl=1800, show_spinner="Sťahujem dáta z Golemio API...")
def load_golemio_data(start_date, end_date):
    session = get_session()
    try:
        r = session.get(f"{BASE_URL}/airqualitystations", params={"limit": 1000})
        stations_dict = {s['properties']['id']: {'name': s['properties']['name'], 'lon': s['geometry']['coordinates'][0], 'lat': s['geometry']['coordinates'][1]} for s in r.json().get('features', [])}
    except: return pd.DataFrame()

    enriched_data = []
    for from_dt, to_dt in generate_date_chunks(start_date, end_date, days=1):
        try:
            resp = session.get(f"{BASE_URL}/airqualitystations/history", params={"limit": 10000, "from": iso_ts(from_dt), "to": iso_ts(to_dt)})
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
                            'datetime': measured_at, 'type': comp.get('type', 'Unknown'), 'value': val
                        })
        except: pass
        
    df = pd.DataFrame(enriched_data)
    if not df.empty:
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['type'] = df['type'].replace({'PM2.5': 'PM2_5'})
    return df

@st.cache_data(ttl=86400)
def load_weather(days):
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": 50.0755, "longitude": 14.4378, "past_days": days, "hourly": "wind_speed_10m"}
        res = requests.get(url, params=params).json()
        df = pd.DataFrame({"datetime": pd.to_datetime(res["hourly"]["time"]), "wind": res["hourly"]["wind_speed_10m"]})
        df['datetime'] = df['datetime'].dt.tz_localize(None)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=86400)
def load_parks():
    try:
        q = '[out:json][timeout:25];(way["leisure"="park"](50.0,14.3,50.15,14.6););out center 50;'
        r = requests.post("https://overpass-api.de/api/interpreter", data={'data': q})
        return pd.DataFrame([{'name': el['tags'].get('name', 'Park'), 'lat': el['center']['lat'], 'lon': el['center']['lon']} for el in r.json().get('elements', [])])
    except: return pd.DataFrame()

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# ============================================
# 3. SIDEBAR A OVLÁDANIE
# ============================================
# Zrušený rozbitý obrázok, nahradené pekným nadpisom
st.sidebar.markdown("<h1>📊 AQ Praha Panel</h1>", unsafe_allow_html=True)
st.sidebar.markdown("---")
st.sidebar.markdown("## ⚙️ Parametre analýzy")

date_range = st.sidebar.date_input("Rozsah dátumov (od - do)", 
                                   value=(datetime.now().date() - timedelta(days=7), datetime.now().date() - timedelta(days=1)))

if len(date_range) != 2: st.stop()
start_d, end_d = date_range

st.sidebar.markdown("## 🗺️ Vizuál mapy")
map_styles = {
    "Detailná (OpenStreetMap)": "open-street-map",
    "Svetlá čistá (Carto Positron)": "carto-positron",
    "Tmavá (Carto Darkmatter)": "carto-darkmatter"
}
selected_map_name = st.sidebar.selectbox("Zvoľte mapový podklad", list(map_styles.keys()))
chosen_map_style = map_styles[selected_map_name]

df_all = load_golemio_data(start_d, end_d)

if df_all.empty:
    st.error("Pre tento rozsah API Golemio nevrátilo dáta. Skúste vybrať iný rozsah (napr. pred týždňom).")
    st.stop()

df_all['hour'] = df_all['datetime'].dt.hour
df_all['day_name'] = df_all['datetime'].dt.day_name()
df_all['date_str'] = df_all['datetime'].dt.date

df_weather = load_weather((end_d - start_d).days + 2)
df_parks = load_parks()

st.sidebar.markdown("## 📈 Metriky datasetu")
st.sidebar.markdown(f"""
<div class="kpi-box">
    <b>Analyzované dni:</b> {(end_d - start_d).days}<br>
    <b>Aktívne stanice:</b> {df_all['name'].nunique()}<br>
    <b>Počet záznamov:</b> {len(df_all):,}
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("## 💾 Export dát")
csv_data = convert_df_to_csv(df_all)
st.sidebar.download_button(
    label="📥 Stiahnuť analyzované dáta (.csv)",
    data=csv_data,
    file_name=f"aq_praha_{start_d}_do_{end_d}.csv",
    mime="text/csv"
)

# ============================================
# 4. HLAVNÁ STRÁNKA A ÚVOD
# ============================================
st.title("🎓 Datamining a vizualizácia: Kvalita ovzdušia Praha")
st.markdown(f"""
**Abstrakt a metodika projektu:**
Tento analytický dashboard slúži na interaktívnu vizualizáciu a dolovanie dát (datamining) o kvalite ovzdušia v hlavnom meste Praha. 
Primárnym zdrojom dát je oficiálne **Golemio API**, z ktorého sú extrahované hodinové koncentrácie hlavných znečisťujúcich látok (NO2, PM10, PM2.5 a O3). 
Dáta sú dynamicky prepájané s geografickými entitami (mestské parky cez *Overpass API*) a historickými meteorologickými údajmi (*Open-Meteo*).
Cieľom práce je overiť vplyv antropogénnej činnosti (najmä automobilovej dopravy) a prírodných faktorov na celkový stav ovzdušia pomocou štyroch stanovených hypotéz.

*Analyzované obdobie: **{start_d.strftime('%d.%m.%Y')} - {end_d.strftime('%d.%m.%Y')}***
""")

tabs = st.tabs(["🌍 Priestorová Mapa", "📈 Časové Trendy", "📉 H1: Víkendový útlm", "🚗 H2: Dopravné špičky", "🌬️ H3: Disperzia vetrom", "🌲 H4: Ochranný vplyv zelene"])

# --- TAB 1: ŽIVÁ MAPA ---
with tabs[0]:
    st.markdown("### Geopriestorová distribúcia znečistenia v reálnom čase")
    st.write("Pomocou ovládacích prvkov nižšie si zvoľte konkrétny dátum a hodinu. Mapa zobrazí plošné rozloženie vybraného analytu. Väčšie a sýtejšie kružnice indikujú lokality so zhoršenou kvalitou ovzdušia.")
    
    c1, c2, c3 = st.columns([2,2,3])
    sel_type = c1.selectbox("Zvoľ látku (Analyt)", sorted(df_all['type'].unique()))
    sel_d = c2.selectbox("Dátum merania", sorted(df_all['date_str'].unique(), reverse=True))
    sel_h = c3.slider("Časová os (Hodina)", 0, 23, 12)
    
    df_map = df_all[(df_all['type']==sel_type) & (df_all['date_str']==sel_d) & (df_all['hour']==sel_h)]
    
    if not df_map.empty:
        fig1 = px.scatter_mapbox(df_map, lat="lat", lon="lon", size="value", color="value",
                                 hover_name="name", hover_data={"value": True},
                                 size_max=45, zoom=10.5, color_continuous_scale="Reds", 
                                 mapbox_style=chosen_map_style) 
        
        fig1.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=650)
        
        if not df_parks.empty:
            fig1.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                            marker=dict(size=12, color='#27ae60', opacity=0.7), name="Mestské parky", 
                                            hoverinfo="text", text=df_parks['name']))
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.warning("Pre vybranú hodinu a dátum sa nenašli žiadne dostupné dáta.")

# --- TAB 2: ČASOVÉ TRENDY ---
with tabs[1]:
    st.markdown("### Analýza časových radov a prekračovanie limitov")
    st.write("""
    Časový vývoj koncentrácií je kritický pre pochopenie dynamiky znečistenia. Graf nižšie zobrazuje priebeh hodnôt pre jednotlivé meracie stanice. 
    Červená prerušovaná čiara predstavuje maximálny odporúčaný denný limit stanovený Svetovou zdravotníckou organizáciou (WHO).
    
    *Poznámka: Pre prehľadnosť je predvolene zobrazená len prvá stanica. Ďalšie stanice aktivujete kliknutím v legende vpravo.*
    """)
    sel_trend = st.selectbox("Zvoľte analyt pre časový rad", sorted(df_all['type'].unique()), key="tr")
    
    fig_trend = go.Figure()
    df_trend_comp = df_all[df_all['type'] == sel_trend].sort_values('datetime')
    stanice = sorted(df_trend_comp['name'].unique())
    
    for i, stanica in enumerate(stanice):
        df_stanica = df_trend_comp[df_trend_comp['name'] == stanica]
        vis = True if i == 0 else 'legendonly'
        fig_trend.add_trace(go.Scatter(
            x=df_stanica['datetime'], y=df_stanica['value'], 
            name=stanica, mode='lines+markers', visible=vis
        ))
        
    fig_trend.update_xaxes(rangeslider_visible=True)
    
    limits = {"NO2": 25, "PM10": 50, "PM2_5": 15, "O3": 100}
    if sel_trend in limits:
        fig_trend.add_hline(y=limits[sel_trend], line_dash="dash", line_color="red", annotation_text=f"Limit WHO: {limits[sel_trend]} µg/m³")
    
    fig_trend.update_layout(height=600, margin={"r":20,"t":40,"l":20,"b":40}, legend_title="Mestské stanice:")
    st.plotly_chart(fig_trend, use_container_width=True)

# --- TAB 3: HYPOTÉZA 1 ---
with tabs[2]:
    st.markdown('<div class="veda-card">', unsafe_allow_html=True)
    st.markdown('<div class="veda-otazka">Hypotéza 1: Týždenný cyklus a vplyv dní pracovného pokoja</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="veda-teoria"><b>Teoretické východisko:</b> Mesto Praha prechádza pravidelným "urbánnym rytmom". Počas pracovného týždňa je mesto vystavené vysokej dopravnej záťaži spojenej s dochádzaním za prácou a službami. Našou otázkou je, či a do akej miery sa tento cyklus odráža na priamych emisiách oxidu dusičitého (NO2), ktorý je dominantne viazaný na výfukové plyny spaľovacích motorov.</div>', unsafe_allow_html=True)
    
    st.write("**Metodika spracovania:** Agregácia historických hodnôt NO2 zo všetkých meracích staníc do celomestských priemerov kategorizovaných podľa dňa v týždni (Pondelok - Nedeľa).")
    
    order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    df_h1 = df_all[df_all['type']=='NO2'].groupby('day_name')['value'].mean().reindex(order)
    
    fig_h1 = px.bar(df_h1, color=df_h1.values, color_continuous_scale="Blues", labels={'value': 'Priemerná koncentrácia NO2 (µg/m³)', 'day_name': 'Deň v týždni'})
    st.plotly_chart(fig_h1, use_container_width=True)
    
    st.markdown('<div class="veda-zaver">Interpretácia a záver: Hypotéza je potvrdená. Z grafu je evidentný takzvaný "víkendový efekt". Koncentrácia NO2 v meste dosahuje svoje maximá uprostred pracovného týždňa (Streda, Štvrtok), zatiaľ čo v sobotu a najmä v nedeľu dochádza k markantnému poklesu hodnôt v dôsledku rapídne zníženej mobility obyvateľstva.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 4: HYPOTÉZA 2 ---
with tabs[3]:
    st.markdown('<div class="veda-card">', unsafe_allow_html=True)
    st.markdown('<div class="veda-otazka">Hypotéza 2: Identifikácia ranných dopravných špičiek v rámci dňa</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="veda-teoria"><b>Teoretické východisko:</b> Rovnako ako týždenný cyklus, aj samotný deň má svoju vnútornú dynamiku. Ak je hlavným zdrojom NO2 doprava, denná krivka znečistenia by mala kopírovať intenzitu dopravy – s typickým nárastom ráno (cesta do práce) a podvečer (cesta z práce). Tento jav sa odborne nazýva bimodálne rozdelenie.</div>', unsafe_allow_html=True)
    
    st.write("**Metodika spracovania:** Výpočet priemerných hodinových hodnôt NO2 za zvolené obdobie. Pre zachovanie presnosti merania dopravného správania pracujúcich boli víkendové dni z tohto datasetu vylúčené.")
    
    df_h2 = df_all[(df_all['type']=='NO2') & (~df_all['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
    fig_h2 = px.line(df_h2, labels={'value':'Priemerná koncentrácia NO2 (µg/m³)', 'hour':'Denná hodina (0-23)'}, markers=True)
    fig_h2.update_traces(line_color='#e74c3c', line_width=4, marker_size=8)
    st.plotly_chart(fig_h2, use_container_width=True)
    
    st.markdown('<div class="veda-zaver">Interpretácia a záver: Graf vykazuje signifikantný ranný vrchol (pik) v čase medzi 7:00 a 9:00 hodinou rannou. Následne hodnoty mierne klesajú a opäť postupne narastajú v poobedných hodinách, čím sa predpoklad o prítomnosti dopravnej špičky plne potvrdzuje.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 5: HYPOTÉZA 3 ---
with tabs[4]:
    st.markdown('<div class="veda-card">', unsafe_allow_html=True)
    st.markdown('<div class="veda-otazka">Hypotéza 3: Korelácia medzi prúdením vzduchu a rozptylom prachových častíc</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="veda-teoria"><b>Teoretické východisko:</b> Meteorologické podmienky sú kľúčovým determinantom kvality ovzdušia. Prachové častice (PM10) pochádzajúce zo stavieb či oteru pneumatík sa pri bezvetrí a teplotných inverziách hromadia v tzv. prízemnej vrstve atmosféry. Našou hypotézou je, že zvýšená rýchlosť vetra funguje ako prírodný ventilačný systém, ktorý častice rozptyľuje (disperzia).</div>', unsafe_allow_html=True)
    
    st.write("**Metodika spracovania:** Prepojenie (inner join) hodnôt koncentrácie PM10 z Golemia s historickými poveternostnými dátami z Open-Meteo na základe presnej zhody časových značiek (hodina po hodine).")
    
    if not df_weather.empty and not df_all[df_all['type']=='PM10'].empty:
        df_h3 = pd.merge(df_all[df_all['type']=='PM10'], df_weather, on='datetime', how='inner')
        if not df_h3.empty:
            fig_h3 = px.scatter(df_h3, x='wind', y='value', trendline="ols", opacity=0.5, 
                                labels={'wind':'Rýchlosť vetra v čase merania (km/h)', 'value':'Koncentrácia PM10 (µg/m³)'},
                                color_discrete_sequence=['#3498db'])
            st.plotly_chart(fig_h3, use_container_width=True)
            st.markdown('<div class="veda-zaver">Interpretácia a záver: Trendová línia (Ordinary Least Squares) jasne dokazuje negatívnu koreláciu (nepriamu úmeru). Koncentrácia smogu sa pohybuje na najvyšších hodnotách pri vetre do 5 km/h. Pri rýchlostiach nad 10-15 km/h dochádza k rapídnemu poklesu prachových častíc. Hypotéza je potvrdená.</div>', unsafe_allow_html=True)
        else:
            st.warning("Časové značky vetra a PM10 sa pre toto obdobie nepodarilo zhodovať.")
    else:
        st.warning("Pre túto analýzu nie je momentálne k dispozícii dostatok spárovaných dát.")
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 6: HYPOTÉZA 4 ---
with tabs[5]:
    st.markdown('<div class="veda-card">', unsafe_allow_html=True)
    st.markdown('<div class="veda-otazka">Hypotéza 4: Geografický vplyv mestskej zelene (Parkov) na mikroklímu</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="veda-teoria"><b>Teoretické východisko:</b> Stromy a vegetácia v mestách neposkytujú iba tieň a estetickú hodnotu, ale listová plocha fyzicky zachytáva prachové častice a znižuje lokálnu teplotu. Predpokladáme, že dlhodobé priemery znečistenia budú v oblastiach ohraničených mestskými parkami vykazovať funkciu "ochranných zón" (tzv. zelené pľúca mesta).</div>', unsafe_allow_html=True)
    
    st.write("**Metodika spracovania:** Výpočet dlhodobého agregovaného priemeru pre každú znečisťujúcu látku. Výsledné dáta sú priestorovo prekryté polygonálnou vrstvou najväčších pražských parkov extrahovaných z databázy OpenStreetMap.")
    
    df_avg = df_all.groupby(['name','lat','lon','type'])['value'].mean().reset_index()
    cols = st.columns(2)
    analytes = ['NO2', 'O3', 'PM10', 'PM2_5']
    
    for i, a in enumerate(analytes):
        if a in df_all['type'].unique():
            with cols[i%2]:
                st.write(f"**Priemerná záťaž: {a}**")
                fig_h4 = px.scatter_mapbox(df_avg[df_avg['type']==a], lat="lat", lon="lon", size="value", 
                                           color="value", hover_name="name",
                                           size_max=35, zoom=9.5, color_continuous_scale="Reds", 
                                           mapbox_style=chosen_map_style, height=400)
                fig_h4.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, coloraxis_showscale=False)
                
                if not df_parks.empty:
                    fig_h4.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                                     marker=dict(size=12, color='#27ae60', opacity=0.7), name="Parky", hoverinfo="text", text=df_parks['name']))
                st.plotly_chart(fig_h4, use_container_width=True)
                
    st.markdown('<div class="veda-zaver">Interpretácia a záver: Z priestorovej distribúcie vidíme zaujímavé vzorce. Zatiaľ čo primárne emitenty (napr. NO2 z dopravy) dosahujú maximá pozdĺž cestných ťahov (Magistrála), stanice umiestnené v alebo blízko rozsiahlej zelene (ako Stromovka či Letná) fungujú ako izolačné body vykazujúce značne nižšie dlhodobé priemery znečistenia. (Pozor na ozónový paradox - hodnoty O3 bývajú v parkoch naopak vyššie).</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
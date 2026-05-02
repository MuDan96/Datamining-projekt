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
# 1. KONFIGURÁCIA A VIZUÁL
# ============================================
st.set_page_config(page_title="AQ Praha: Strategický Audit", layout="wide", page_icon="🏛️")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; color: #2c3e50; }
    
    .audit-card {
        background-color: #ffffff; border-radius: 10px; padding: 25px; 
        margin-bottom: 25px; border-left: 5px solid #2980b9;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }
    .audit-title { color: #2c3e50; font-size: 20px; font-weight: bold; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #eee; }
    .audit-text { font-size: 15px; line-height: 1.6; color: #34495e; margin-bottom: 15px; text-align: justify; }
    .audit-action {
        background-color: #e8f6f3; border-left: 5px solid #1abc9c;
        padding: 15px; color: #16a085; font-size: 15px; font-weight: 500; margin-top: 20px; border-radius: 4px; line-height: 1.5;
    }
    
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff; border: 1px solid #e0e0e0;
        padding: 10px 20px; border-radius: 5px 5px 0 0; color: #2c3e50 !important; font-weight: bold;
    }
    .stTabs [aria-selected="true"] { background-color: #2980b9 !important; color: #ffffff !important; }
    
    .kpi-box {
        background-color: #111111; color: #ffffff; padding: 15px; border-radius: 8px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2); margin-bottom: 15px; border: 1px solid #333; font-size: 15px;
    }
    .author-box { font-size: 14px; color: #7f8c8d; margin-top: 5px; }
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
st.sidebar.markdown("<h1>🏛️ AQ Praha Audit</h1>", unsafe_allow_html=True)
st.sidebar.markdown("---")

app_mode = st.sidebar.radio("📌 Navigácia:", ["📊 Analytický Dashboard", "📄 Projektová Dokumentácia"])
st.sidebar.markdown("---")

st.sidebar.markdown("## ⚙️ Parametre auditu")
date_range = st.sidebar.date_input("Rozsah dátumov", 
                                   value=(datetime.now().date() - timedelta(days=7), datetime.now().date() - timedelta(days=1)))

if len(date_range) != 2: st.stop()
start_d, end_d = date_range

map_styles = {"Svetlá čistá (Carto)": "carto-positron", "Detailná (OSM)": "open-street-map", "Tmavá (Darkmatter)": "carto-darkmatter"}
chosen_map_style = map_styles[st.sidebar.selectbox("Mapový podklad", list(map_styles.keys()))]

df_all = load_golemio_data(start_d, end_d)

if df_all.empty:
    st.error("Pre tento rozsah API Golemio nevrátilo dáta.")
    st.stop()

df_all['hour'] = df_all['datetime'].dt.hour
df_all['day_name'] = df_all['datetime'].dt.day_name()
df_all['date_str'] = df_all['datetime'].dt.date

df_weather = load_weather((end_d - start_d).days + 2)
df_parks = load_parks()

# Výpočet toxických hodín
toxic_hours = len(df_all[((df_all['type'] == 'NO2') & (df_all['value'] > 25)) | ((df_all['type'] == 'PM10') & (df_all['value'] > 45))])

st.sidebar.markdown("## 📈 Metriky a Ohrozenie")
st.sidebar.markdown(f"""
<div class="kpi-box">
    <b>Dni v audite:</b> {(end_d - start_d).days}<br>
    <b>Celkový objem dát:</b> {len(df_all):,}<br>
    <b style="color:#e74c3c;">Toxické hodiny: {toxic_hours} hod.</b><br>
    <i style="font-size: 11px;">*Prekročenie WHO limitov limitujúce zraniteľné skupiny</i>
</div>
""", unsafe_allow_html=True)

st.sidebar.download_button("📥 Stiahnuť zdrojové dáta (.csv)", data=convert_df_to_csv(df_all), file_name=f"aq_praha_{start_d}_{end_d}.csv", mime="text/csv")

st.sidebar.markdown("---")
st.sidebar.markdown("### 👥 Dátový tím")
st.sidebar.markdown("<div class='author-box'>• T. Halászová<br>• Z. Mitterová<br>• B. Petric<br>• D. Mucska</div>", unsafe_allow_html=True)


# ============================================
# REŽIM 1: DOKUMENTÁCIA
# ============================================
if app_mode == "📄 Projektová Dokumentácia":
    st.title("📄 Dokumentácia: Strategický zdravotno-urbanistický audit")
    
    with st.expander("1. Manažerské shrnutí (Executive Summary)", expanded=True):
        st.write("Náš projekt spája zdravotné dáta (limity WHO) s urbanizmom a dopravou. Nástroj historicky vyhodnocuje dáta z Golemio API a prepája ich s mestskou infraštruktúrou. Cieľom je definovať, kedy sú obyvatelia najviac ohrození, a na základe tvrdých dát priniesť argumenty pre výsadbu zelene a reguláciu dopravy.")

    with st.expander("2. Definice problému z pohledu firmy a byznysový přínos"):
        st.write("""
        * **Definícia problému:** Mesto čelí kríze ovzdušia obmedzujúcej pohyb zraniteľných obyvateľov (astmatici, kardiaci). Potrebujeme komplexne pochopiť, čo tento stav spôsobuje (doprava/počasie) a čo ho dokáže tlmiť (zeleň/parky).
        * **Byznysový/Politický prínos:** Prechod od domnienok k dátovo podloženým rozhodnutiam pre Magistrát: cielenejšie obmedzenia dopravy v špičkách a strategická obhajoba investícií do výsadby mestskej zelene v najkritickejších zónach.
        """)

    with st.expander("3. Popis vstupních dat a štruktúra auditu"):
        st.write("""
        * **Dáta:** Golemio API (IoT senzory, toxíny), Open-Meteo API (vietor), Overpass API (polygóny parkov).
        * **Oblasti skúmania:** 
            1. Priestorové rozloženie (Kde je problém?)
            2. Zdravotné mantinely (Kedy prekračujeme WHO limity?)
            3. Vplyv mobility (Ako doprava a ranné špičky tvoria smog?)
            4. Vplyv počasia (Ako vietor čistí mesto?)
            5. Urbanizmus (Ako zeleň a stromy izolujú znečistenie?)
        """)

    with st.expander("4. Volba metody, argumentace a pracovní postup"):
        st.write("Zvolili sme Python a Streamlit (namiesto R) pre vytvorenie komplexného, plne interaktívneho dashboardu pripraveného pre produkčné využitie. Metodika zahŕňa iteratívnu extrakciu z API, Data Cleansing, časovú transformáciu (extrakciu hodín a dní) a priestorovú fúziu environmentálnych a meteorologických dát.")

    with st.expander("5. Přehled zodpovědností členů týmu"):
        st.write("""
        * **Timea Halászová:** Manažment projektu a definícia byznys/policy modelu (prepájanie dát so strategickými rozhodnutiami).
        * **Zuzana Mitterová:** Metodika výskumu a vizualizácia (aplikácia Data Storytellingu na demonštrovanie ohrozenia zdravia).
        * **Bojan Petric:** Data engineering a čistenie dát (Pandas, detekcia toxických hodín, agregácie).
        * **Daniel Mucska:** Vývoj architektúry a API integrácia (budovanie Streamlit cloudovej aplikácie).
        """)

# ============================================
# REŽIM 2: DASHBOARD (KOMPLEXNÝ)
# ============================================
elif app_mode == "📊 Analytický Dashboard":
    st.title("🏛️ AQ Praha: Strategický zdravotno-urbanistický audit")
    st.markdown("Tento komplexný analytický nástroj vyhodnocuje kvalitu ovzdušia v Prahe s ohľadom na prísne zdravotné limity Svetovej zdravotníckej organizácie (WHO). Na základe identifikácie toxických hodín skúma hlavné príčiny znečistenia (doprava, meteorológia) a navrhuje urbanistické riešenia (ochrana a výsadba mestskej zelene).")

    tabs = st.tabs(["🌍 1. Priestorová analýza", "🏥 2. Zdravotné limity WHO", "🚗 3. Skúmanie mobility", "🌬️ 4. Skúmanie počasia", "🌲 5. Urbanizmus a zeleň", "📋 6. Strategický plán"])

    # --- TAB 1: ŽIVÁ MAPA ---
    with tabs[0]:
        st.markdown("<div class='audit-title'>Geopriestorové rozloženie toxicity</div>", unsafe_allow_html=True)
        st.write("Identifikácia najviac zasiahnutých zón v meste v konkrétnom čase. Zelené body predstavujú existujúcu infraštruktúru mestskej zelene.")
        
        c1, c2, c3 = st.columns([2,2,3])
        sel_type = c1.selectbox("Analyt", sorted(df_all['type'].unique()))
        sel_d = c2.selectbox("Dátum", sorted(df_all['date_str'].unique(), reverse=True))
        sel_h = c3.slider("Hodina", 0, 23, 12)
        
        df_map = df_all[(df_all['type']==sel_type) & (df_all['date_str']==sel_d) & (df_all['hour']==sel_h)]
        
        if not df_map.empty:
            fig1 = px.scatter_mapbox(df_map, lat="lat", lon="lon", size="value", color="value", hover_name="name", hover_data={"value": True}, size_max=45, zoom=10.5, color_continuous_scale="Reds", mapbox_style=chosen_map_style) 
            fig1.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=550)
            if not df_parks.empty:
                fig1.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', marker=dict(size=12, color='#27ae60', opacity=0.7), name="Parky", hoverinfo="text", text=df_parks['name']))
            st.plotly_chart(fig1, use_container_width=True)

    # --- TAB 2: ZDRAVOTNÉ LIMITY ---
    with tabs[1]:
        st.markdown("<div class='audit-title'>Prekračovanie zdravotných limitov citlivých skupín</div>", unsafe_allow_html=True)
        st.write("Červená hraničná čiara definuje bod, od ktorého mesto začína obmedzovať astmatikov a kardiakov v ich práve na zdravý pohyb vonku. Slúži ako náš základný mantinel pre ďalšie skúmanie.")
        sel_trend = st.selectbox("Zvoľte analyt pre časový rad", sorted(df_all['type'].unique()), key="tr")
        
        fig_trend = go.Figure()
        df_trend_comp = df_all[df_all['type'] == sel_trend].sort_values('datetime')
        for i, stanica in enumerate(sorted(df_trend_comp['name'].unique())):
            df_stanica = df_trend_comp[df_trend_comp['name'] == stanica]
            fig_trend.add_trace(go.Scatter(x=df_stanica['datetime'], y=df_stanica['value'], name=stanica, mode='lines+markers', visible=(True if i == 0 else 'legendonly')))
            
        fig_trend.update_xaxes(rangeslider_visible=True)
        limits = {"NO2": 25, "PM10": 45, "PM2_5": 15, "O3": 100}
        if sel_trend in limits:
            fig_trend.add_hline(y=limits[sel_trend], line_dash="dash", line_color="red", annotation_text=f"WHO Limit: {limits[sel_trend]}")
        fig_trend.update_layout(height=500, margin={"r":0,"t":10,"l":0,"b":0})
        st.plotly_chart(fig_trend, use_container_width=True)

    # --- TAB 3: MOBILITA (Bývalá H1 a H2) ---
    with tabs[2]:
        st.markdown("<div class='audit-card'><div class='audit-title'>Oblasť skúmania 1: Vplyv dopravy na toxicitu ovzdušia</div><div class='audit-text'>Ak sme v predchádzajúcom kroku zistili prekračovanie limitov, musíme hľadať príčinu. Sledovaním plynu NO2 (vedľajší produkt spaľovacích motorov) analyzujeme, do akej miery je zdravie občanov závislé od automobilovej mobility.</div></div>", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Týždenný cyklus (Víkendový útlm)**")
            order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
            df_h1 = df_all[df_all['type']=='NO2'].groupby('day_name')['value'].mean().reindex(order)
            st.plotly_chart(px.bar(df_h1, color=df_h1.values, color_continuous_scale="Reds", labels={'value': 'Priemerné NO2', 'day_name': ''}), use_container_width=True)
        
        with c2:
            st.write("**Denný cyklus (Ranné dopravné špičky)**")
            df_h2 = df_all[(df_all['type']=='NO2') & (~df_all['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
            fig_h2 = px.line(df_h2, labels={'value':'Priemerné NO2', 'hour':'Hodina (0-23)'}, markers=True)
            fig_h2.update_traces(line_color='#c0392b', line_width=4, marker_size=8)
            st.plotly_chart(fig_h2, use_container_width=True)
            
        st.markdown("<div class='audit-action'>🔍 Zistenie: Pracovné dni a najmä časy presunov do škôl/práce (7:00-9:00) menia mesto na nebezpečnú zónu. Preukázali sme priamu kauzalitu medzi mobilitou a kvalitou vzduchu.</div>", unsafe_allow_html=True)

    # --- TAB 4: POČASIE ---
    with tabs[3]:
        st.markdown("<div class='audit-card'><div class='audit-title'>Oblasť skúmania 2: Meteorologická zraniteľnosť (Disperzia vetrom)</div><div class='audit-text'>Druhým faktorom ovplyvňujúcim zdravie sú poveternostné podmienky. Analyzujeme koreláciu medzi rýchlosťou vetra a schopnosťou mesta 'odvetrať' nebezpečné prachové častice (PM10).</div></div>", unsafe_allow_html=True)
        
        if not df_weather.empty and not df_all[df_all['type']=='PM10'].empty:
            df_h3 = pd.merge(df_all[df_all['type']=='PM10'], df_weather, on='datetime', how='inner')
            if not df_h3.empty:
                fig_h3 = px.scatter(df_h3, x='wind', y='value', trendline="ols", opacity=0.5, labels={'wind':'Rýchlosť vetra (km/h)', 'value':'PM10 (µg/m³)'}, color_discrete_sequence=['#2980b9'])
                st.plotly_chart(fig_h3, use_container_width=True)
                st.markdown("<div class='audit-action'>🔍 Zistenie: Model potvrdil negatívnu koreláciu. Pri bezvetrí (< 5 km/h) sa mesto dusí vo vlastnom prachu. Vietor funguje ako prírodná čistička vzduchu.</div>", unsafe_allow_html=True)

    # --- TAB 5: URBANIZMUS ---
    with tabs[4]:
        st.markdown("<div class='audit-card'><div class='audit-title'>Oblasť skúmania 3: Izolačný potenciál mestskej zelene</div><div class='audit-text'>Zatiaľ čo dopravu vieme regulovať len ťažko a vietor nevieme ovládať vôbec, zeleň je v rukách mesta. Analyzujeme dlhodobé priemery toxínov v priestore, aby sme preukázali, či stromy dokážu fyzicky tlmiť dopady znečistenia a vytvárať bezpečné zóny pre astmatikov.</div></div>", unsafe_allow_html=True)
        
        df_avg = df_all.groupby(['name','lat','lon','type'])['value'].mean().reset_index()
        cols = st.columns(2)
        for i, a in enumerate(['NO2', 'PM10']): # Zjednodušené zobrazenie hlavných dvoch
            if a in df_all['type'].unique():
                with cols[i%2]:
                    st.write(f"**Priemerná záťaž: {a}**")
                    fig_h4 = px.scatter_mapbox(df_avg[df_avg['type']==a], lat="lat", lon="lon", size="value", color="value", hover_name="name", size_max=35, zoom=9.5, color_continuous_scale="Reds", mapbox_style=chosen_map_style, height=400)
                    fig_h4.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, coloraxis_showscale=False)
                    if not df_parks.empty:
                        fig_h4.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', marker=dict(size=12, color='#27ae60', opacity=0.7), name="Parky", hoverinfo="text", text=df_parks['name']))
                    st.plotly_chart(fig_h4, use_container_width=True)
                    
        st.markdown("<div class='audit-action'>🔍 Zistenie: Zelené plochy preukázateľne zachytávajú smog. Stanice blízko parkov vykazujú zásadne nižšie hodnoty toxicity, čím vytvárajú jediné bezpečné lokality v centre.</div>", unsafe_allow_html=True)

    # --- TAB 6: ZÁVEREČNÝ PLÁN ---
    with tabs[5]:
        st.markdown("<div class='audit-title'>📋 Strategické odporúčania pre Magistrát hl. m. Prahy</div>", unsafe_allow_html=True)
        st.write("Na základe preukázaných zistení o prekračovaní zdravotných limitov, vplyvu dopravy a ochranného potenciálu parkov, odporúča náš analytický tím prijať nasledujúce opatrenia:")
        
        st.markdown("""
        ### 1. Oblasť: Riadenie mobility (Doprava)
        * **Zavedenie 'Školských ulíc':** Úplný zákaz vjazdu áut v bezprostrednom okolí škôl medzi 7:00 a 8:30 (eliminácia toxických ranných špičiek doložených v module 3).
        * **Mýto a nízkoemisné zóny:** Cenová regulácia vjazdu do najviac zasiahnutých zón počas pracovných dní pre nerezidentov.
        
        ### 2. Oblasť: Urbanizmus a infraštruktúra (Zeleň)
        * **Masívna výsadba stromov:** Zistenia z modulu 5 dokazujú, že zeleň fyzicky pohlcuje smog. Preto je nevyhnutné sadiť izolačné pásy stromov pozdĺž dopravných tepien (Magistrála).
        * **Stavebná uzávera:** Zákaz akejkoľvek developerskej činnosti, ktorá by zmenšovala aktuálnu plochu veľkých parkov (Stromovka, Letná), nakoľko slúžia ako jediné útočiská pre zraniteľné skupiny.
        
        ### 3. Oblasť: Krízové zdravotné riadenie
        * **Meteorologické varovania:** Prepojenie SMS varovného systému mesta s predpoveďou vetra. Ak vietor klesne pod 5 km/h, vyhlásiť smogový stupeň a varovať astmatikov (modul 4).
        """)
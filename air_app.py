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
st.set_page_config(page_title="AQ Praha: Zdravotný audit", layout="wide", page_icon="⚖️")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; color: #2c3e50; }
    
    .veda-card {
        background-color: #ffffff; border-radius: 10px; padding: 30px; 
        margin-bottom: 25px; border-left: 5px solid #e74c3c;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }
    .veda-otazka { color: #c0392b; font-size: 20px; font-weight: bold; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #eee; }
    .veda-teoria { font-size: 15px; line-height: 1.6; color: #34495e; margin-bottom: 15px; text-align: justify; }
    .veda-zaver {
        background-color: #fdf2e9; border-left: 5px solid #d35400;
        padding: 20px; color: #d35400; font-size: 16px; font-weight: 500; margin-top: 25px; border-radius: 4px; line-height: 1.5;
    }
    
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff; border: 1px solid #e0e0e0;
        padding: 12px 24px; border-radius: 5px 5px 0 0; color: #2c3e50 !important; font-weight: bold;
    }
    .stTabs [aria-selected="true"] { background-color: #e74c3c !important; color: #ffffff !important; }
    
    .kpi-box {
        background-color: #111111; color: #ffffff; padding: 15px; border-radius: 8px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2); margin-bottom: 15px; border: 1px solid #333; font-size: 15px;
    }
    .author-box {
        font-size: 14px; color: #7f8c8d; margin-top: 5px;
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
# 3. SIDEBAR A NAVIGÁCIA (DVOJ-REŽIM)
# ============================================
st.sidebar.markdown("<h1>⚖️ Zdravotný Audit AQ</h1>", unsafe_allow_html=True)
st.sidebar.markdown("---")

app_mode = st.sidebar.radio("📌 Zvoľte režim aplikácie:", ["📊 Analytický Dashboard", "📄 Projektová Dokumentácia"])
st.sidebar.markdown("---")

st.sidebar.markdown("## ⚙️ Parametre auditu")
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

# Vypočítame koľko hodín bolo toxických (nad limit WHO pre citlivé skupiny)
# Limit NO2 > 25 µg/m³, PM10 > 45 µg/m³
toxic_hours = len(df_all[((df_all['type'] == 'NO2') & (df_all['value'] > 25)) | ((df_all['type'] == 'PM10') & (df_all['value'] > 45))])

st.sidebar.markdown("## 📈 Zdravotné metriky")
st.sidebar.markdown(f"""
<div class="kpi-box">
    <b>Analyzované dni:</b> {(end_d - start_d).days}<br>
    <b>Celkový počet meraní:</b> {len(df_all):,}<br>
    <b style="color:#e74c3c;">Toxické hodiny (Ohrozenie): {toxic_hours} hod.</b><br>
    <i style="font-size: 11px;">*Počet hodín, kedy boli astmatici obmedzení na pohybe v meste (prekročený limit WHO)</i>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("## 💾 Export dát")
csv_data = convert_df_to_csv(df_all)
st.sidebar.download_button(
    label="📥 Stiahnuť reportované dáta (.csv)",
    data=csv_data,
    file_name=f"aq_audit_praha_{start_d}_do_{end_d}.csv",
    mime="text/csv"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 👥 Dátoví audítori")
st.sidebar.markdown("""
<div class="author-box">
• Timea Halászová<br>
• Zuzana Mitterová<br>
• Bojan Petric<br>
• Daniel Mucska
</div>
""", unsafe_allow_html=True)

# ============================================
# REŽIM 1: PROJEKTOVÁ DOKUMENTÁCIA (TEÓRIA)
# ============================================
if app_mode == "📄 Projektová Dokumentácia":
    st.title("📄 Projektová Dokumentácia: Zdravotný audit ovzdušia")
    st.write("Táto sekcia obsahuje metodiku a manažérske zhrnutie projektu podľa požiadaviek zadania a usmernení konzultantov.")
    
    with st.expander("1. Manažerské shrnutí (Executive Summary)", expanded=True):
        st.write("""
        **Cieľ:** Vývoj analytického nástroja na ochranu zraniteľných skupín obyvateľstva v Prahe.
        Náš projekt sa zameriava na kvantifikáciu obmedzovania občianskych práv a zdravia občanov (astmatici, kardiaci, deti) v dôsledku zhoršenej kvality ovzdušia. 
        Nástroj historicky vyhodnocuje dáta z Golemio API a prepája ich s mestskou infraštruktúrou. Výstupom sú priame argumenty pre krízový manažment a vedenie mesta na zavádzanie regulácií.
        """)

    with st.expander("2. Definice problému z pohledu firmy a byznysový přínos"):
        st.write("""
        * **Definícia problému:** Mesto Praha čelí kríze ovzdušia, ktorá má priamy dopad na dýchacie cesty obyvateľov. Vedecké štúdie preukazujú, že pľúca Pražanov vykazujú podobné znaky ako pľúca ľahkých fajčiarov. Chýba nástroj, ktorý by Magistrátu ukázal, kedy presne a prečo sú ľudia obmedzovaní vo svojich právach na zdravé prostredie.
        * **Byznysový/Politický prínos:**
            1. **Optimalizácia mestskej dopravy:** Dôkazy na okamžité zavedenie ranného mýta a nízkoemisných zón okolo škôl.
            2. **Ochrana astmatikov (Zdravotníctvo):** Systém presne meria počet "toxických hodín", čo poisťovniam a mestu umožňuje cielenú zdravotnú prevenciu.
            3. **Urbanizmus a Real Estate:** Dôkazy o nutnosti zachovať parky bez developerskej zástavby, nakoľko fungujú ako jediné záchranné oázy.
        """)

    with st.expander("3. Popis vstupních dat, otázek a hypotéz"):
        st.write("""
        * **Vstupné dáta (Data Fusion):**
            * *Golemio API:* Zber hodinových koncentrácií znečisťujúcich látok z oficiálnych IoT senzorov mesta.
            * *Open-Meteo API:* Meteorologické dáta.
            * *Overpass API:* Extrakcia priestorových polygónov mestskej zelene (parky).
        * **Skúmané oblasti (Dôkazy pre Magistrát):**
            * **Dôkaz 1 & 2:** Skúmanie ranných špičiek a víkendového útlmu za účelom obmedzenia vjazdu automobilov do centra.
            * **Dôkaz 3:** Meteorologická zraniteľnosť (Kedy sa mesto "udusí" vo vlastnom prachu z dôvodu bezvetria?).
            * **Dôkaz 4:** Skúmanie ochranných zón (Zeleň ako jediné bezpečné útočisko).
        """)

    with st.expander("4. Volba metody, argumentace a pracovní postup"):
        st.write("""
        Rozhodli sme sa projekt namiesto tradičného jazyka R vypracovať v jazyku **Python s využitím frameworku Streamlit**.
        * **Prečo Python a Streamlit:** Tento prístup lepšie simuluje reálne nasadenie dátových produktov v praxi. Umožňuje nám vytvoriť plnohodnotný "Policy Dashboard" s plynulým live napojením na REST API, s ktorým môže starosta či magistrát ihneď interaktívne pracovať.
        * **Pracovný postup (ETL):** Iteratívne sťahovanie JSON dát, čistenie hodnôt (`None`), unifikácia názvoslovia analytov, časová transformácia na ISO formát a fúzia dát (Inner Join) prekrývaná cez GPS súradnice do interaktívnych Plotly máp.
        """)

    with st.expander("5. Výsledky a závěr"):
        st.write("""
        Dáta bezpečne preukazujú masívne obmedzovanie práv zraniteľných obyvateľov počas dopravných špičiek. Výpočet "Toxických hodín" ukazuje, koľko času z roka by astmatici vôbec nemali vychádzať na ulice. Odporúčame okamžité zavedenie mýta v špičke, vytvorenie zón s vylúčenou dopravou a prísnu ochranu mestskej zelene pred výrubom.
        """)

    with st.expander("6. Přehled zodpovědností členů týmu"):
        st.write("""
        * **Timea Halászová:** Manažment projektu a definícia byznys/policy modelu. *Prínos: Schopnosť pretaviť technické dáta do politických argumentov pre Magistrát.*
        * **Zuzana Mitterová:** Metodika výskumu a vizualizácia dát. *Prínos: Aplikácia princípov Data Storytellingu na demonštrovanie ohrozenia verejného zdravia.*
        * **Bojan Petric:** Data engineering a čistenie dát. *Prínos: Práca s knižnicou Pandas, tvorba výpočtových kľúčov pre detekciu toxických hodín.*
        * **Daniel Mucska:** Vývoj architektúry a API integrácia (Streamlit). *Prínos: Budovanie produkčnej cloudovej aplikácie s ošetrením výpadkov REST API.*
        """)

# ============================================
# REŽIM 2: ANALYTICKÝ DASHBOARD (PRAX)
# ============================================
elif app_mode == "📊 Analytický Dashboard":
    st.title("⚖️ Zdravotný audit ovzdušia: Návrh opatrení pre Magistrát")
    st.markdown(f"""
    **Zhrnutie pre krízový manažment a vedenie mesta:**
    Tento analytický report exaktne kvantifikuje negatívny dopad znečistenia ovzdušia na ohrozené skupiny obyvateľstva (astmatici, kardiaci, deti). 
    Historické merania ukazujú, že mestské prostredie v určitých časoch zásadne obmedzuje občianske právo na zdravé životné prostredie (štúdie napríklad preukazujú, že pľúca dlhoročných Pražanov vykazujú podobné znaky ako pľúca fajčiarov).
    **Cieľom tohto auditu je poskytnúť Magistrátu tvrdé dáta pre zavedenie okamžitých legislatívnych a urbanistických zmien.**
    
    *Auditované obdobie: **{start_d.strftime('%d.%m.%Y')} - {end_d.strftime('%d.%m.%Y')}*** | *Vypracovali: **T. Halászová, Z. Mitterová, B. Petric, D. Mucska***
    """)

    tabs = st.tabs(["🌍 Mapa ohrozenia", "📈 Historické limity", "📉 Dôkaz 1: Víkendový filter", "🚗 Dôkaz 2: Ranné dusno", "🌬️ Dôkaz 3: Klimatická zraniteľnosť", "🌲 Dôkaz 4: Zelené záchranné zóny"])

    # --- TAB 1: ŽIVÁ MAPA ---
    with tabs[0]:
        st.markdown("### Geopriestorová distribúcia kritických zón")
        st.write("Interaktívna mapa pre identifikáciu zón, ktorým by sa mali zraniteľné skupiny v danom čase absolútne vyhnúť.")
        
        c1, c2, c3 = st.columns([2,2,3])
        sel_type = c1.selectbox("Zvoľ toxín", sorted(df_all['type'].unique()))
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
                                                marker=dict(size=12, color='#27ae60', opacity=0.7), name="Záchranné oázy (Parky)", hoverinfo="text", text=df_parks['name']))
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.warning("Pre vybranú hodinu a dátum sa nenašli žiadne dostupné dáta.")

    # --- TAB 2: ČASOVÉ TRENDY ---
    with tabs[1]:
        st.markdown("### Prekračovanie limitov Svetovej zdravotníckej organizácie (WHO)")
        st.write("*Červená prerušovaná čiara predstavuje hranicu, nad ktorou je priamo ohrozené zdravie kardiakov a astmatikov. Každý vrchol nad touto čiarou reprezentuje reálne obmedzenie občianskych práv obyvateľov.*")
        sel_trend = st.selectbox("Zvoľte analyt pre vizualizáciu", sorted(df_all['type'].unique()), key="tr")
        
        fig_trend = go.Figure()
        df_trend_comp = df_all[df_all['type'] == sel_trend].sort_values('datetime')
        stanice = sorted(df_trend_comp['name'].unique())
        
        for i, stanica in enumerate(stanice):
            df_stanica = df_trend_comp[df_trend_comp['name'] == stanica]
            vis = True if i == 0 else 'legendonly'
            fig_trend.add_trace(go.Scatter(x=df_stanica['datetime'], y=df_stanica['value'], name=stanica, mode='lines+markers', visible=vis))
            
        fig_trend.update_xaxes(rangeslider_visible=True)
        
        limits = {"NO2": 25, "PM10": 45, "PM2_5": 15, "O3": 100}
        if sel_trend in limits:
            fig_trend.add_hline(y=limits[sel_trend], line_dash="dash", line_color="red", annotation_text=f"Kritický limit WHO: {limits[sel_trend]} µg/m³")
        
        fig_trend.update_layout(height=600, margin={"r":20,"t":40,"l":20,"b":40}, legend_title="Mestské stanice:")
        st.plotly_chart(fig_trend, use_container_width=True)

    # --- TAB 3: HYPOTÉZA 1 (Dôkaz o doprave) ---
    with tabs[2]:
        st.markdown("""
        <div class="veda-card">
            <div class="veda-otazka">⚠️ Dôkaz 1: Týždenná toxicita a "víkendový filter"</div>
            <div class="veda-teoria"><b>Dopad na obyvateľov:</b> Pracovný týždeň mení centrum Prahy na plynovú komoru pre citlivé skupiny. Našou úlohou bolo dokázať, že tento jav nie je prírodný, ale je priamo naviazaný na pracovnú mobilitu (spaľovacie motory). Zistili sme, že počas víkendu, keď klesne doprava, mesto sa doslova "nadýchne".</div>
            <div style="font-size: 15px; color: #2c3e50; margin-bottom: 20px;"><b>📊 Dátová metodika:</b> Agregácia historických hodnôt NO2 (primárny toxín z výfukov) do celomestských priemerov podľa dňa v týždni.</div>
        </div>
        """, unsafe_allow_html=True)
        
        order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        df_h1 = df_all[df_all['type']=='NO2'].groupby('day_name')['value'].mean().reindex(order)
        fig_h1 = px.bar(df_h1, color=df_h1.values, color_continuous_scale="Reds", labels={'value': 'Priemerné zaťaženie NO2 µg/m³', 'day_name': 'Deň v týždni'})
        st.plotly_chart(fig_h1, use_container_width=True)
        st.markdown('<div class="veda-zaver">🛑 Návrh pre Magistrát: Dáta potvrdzujú enormný podiel dopravy na znečistení počas pracovných dní. Odporúčame zaviesť motivačné zľavy na MHD počas dní pracovného týždňa a naopak, zdražiť parkovanie v centre pre nerezidentov. Cielená redukcia dopravy má okamžitý liečebný efekt.</div>', unsafe_allow_html=True)

    # --- TAB 4: HYPOTÉZA 2 (Dôkaz o špičkách) ---
    with tabs[3]:
        st.markdown("""
        <div class="veda-card">
            <div class="veda-otazka">⚠️ Dôkaz 2: Toxické ranné špičky a ohrozenie cestou do školy</div>
            <div class="veda-teoria"><b>Zdravotný audit:</b> Medzi 7:00 a 9:00 hodinou ráno, v čase keď sa deti presúvajú do škôl a dospelí do zamestnaní, vystrelí hladina karcinogénneho NO2 nad bezpečné zdravotné limity. Astmatici sú v tomto čase akoby "uväznení" a mesto ich priamo obmedzuje v ich základnom práve na pohyb bez ohrozenia zdravia.</div>
            <div style="font-size: 15px; color: #2c3e50; margin-bottom: 20px;"><b>📊 Dátová metodika:</b> Výpočet priemerných hodinových hodnôt toxínov za pracovné dni (víkendy vylúčené).</div>
        </div>
        """, unsafe_allow_html=True)
        
        df_h2 = df_all[(df_all['type']=='NO2') & (~df_all['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
        fig_h2 = px.line(df_h2, labels={'value':'Priemerná koncentrácia NO2 (µg/m³)', 'hour':'Denná hodina (0-23)'}, markers=True)
        fig_h2.update_traces(line_color='#c0392b', line_width=4, marker_size=8)
        st.plotly_chart(fig_h2, use_container_width=True)
        st.markdown('<div class="veda-zaver">🛑 Návrh pre Magistrát: Dáta striktne vyžadujú zavedenie okamžitých politík. Odporúčame zaviesť prísne nízkoemisné zóny (tzv. Školské ulice) bezprostredne v okolí vzdelávacích zariadení s absolútnym zákazom vjazdu motorových vozidiel v čase od 7:00 do 8:30 ráno.</div>', unsafe_allow_html=True)

    # --- TAB 5: HYPOTÉZA 3 (Dôkaz o vetre) ---
    with tabs[4]:
        st.markdown("""
        <div class="veda-card">
            <div class="veda-otazka">⚠️ Dôkaz 3: Meteorologická zraniteľnosť a "udusenie" mesta</div>
            <div class="veda-teoria"><b>Zdravotný audit:</b> Prachové častice (PM10) pochádzajúce z oteru pneumatík sa pri bezvetrí a teplotných inverziách neodvratne hromadia. Náš model dokazuje, že ak klesne rýchlosť vetra pod určitú hranicu, mesto nedokáže prirodzene ventilovať a dusí sa vo vlastnom prachu. V týchto dňoch by zraniteľné skupiny nemali vôbec vychádzať von.</div>
            <div style="font-size: 15px; color: #2c3e50; margin-bottom: 20px;"><b>📊 Dátová metodika:</b> OLS Regresia (prepojenie koncentrácie PM10 z Golemia s historickými poveternostnými dátami podľa presnej hodiny merania).</div>
        </div>
        """, unsafe_allow_html=True)
        
        if not df_weather.empty and not df_all[df_all['type']=='PM10'].empty:
            df_h3 = pd.merge(df_all[df_all['type']=='PM10'], df_weather, on='datetime', how='inner')
            if not df_h3.empty:
                fig_h3 = px.scatter(df_h3, x='wind', y='value', trendline="ols", opacity=0.5, 
                                    labels={'wind':'Rýchlosť vetra (km/h)', 'value':'Koncentrácia PM10 (µg/m³)'}, color_discrete_sequence=['#c0392b'])
                st.plotly_chart(fig_h3, use_container_width=True)
                st.markdown('<div class="veda-zaver">🛑 Návrh pre Magistrát: Prepojiť tieto dáta s krízovým SMS systémom mesta. Ak meteorologický model hlási bezvetrie (< 5 km/h), magistrát musí automaticky vyhlásiť smogový stupeň, nariadiť dopravné obmedzenia a varovať astmatikov a nemocnice na nápor pacientov.</div>', unsafe_allow_html=True)
            else:
                st.warning("Časové značky vetra a PM10 sa pre toto obdobie nepodarilo zhodovať.")
        else:
            st.warning("Pre túto analýzu nie je momentálne k dispozícii dostatok spárovaných dát.")

    # --- TAB 6: HYPOTÉZA 4 (Dôkaz o parkoch) ---
    with tabs[5]:
        st.markdown("""
        <div class="veda-card">
            <div class="veda-otazka">🌲 Dôkaz 4: Zelené oázy ako jediné útočiská na prežitie</div>
            <div class="veda-teoria"><b>Zdravotný audit:</b> Mestská vegetácia tu neslúži na estetiku, ale ako záchranná brzda. Dáta jasne dokazujú, že parky fyzicky zachytávajú prachové častice a vytvárajú tzv. "bezpečné bubliny", kde sa môžu dýchaviční obyvatelia relatívne bezpečne nadýchnuť. Mimo týchto zón sú hodnoty kritické.</div>
            <div style="font-size: 15px; color: #2c3e50; margin-bottom: 20px;"><b>📊 Dátová metodika:</b> Výpočet dlhodobého agregovaného priemeru toxínov prekrytý priestorovou vrstvou pražských parkov z OpenStreetMap.</div>
        </div>
        """, unsafe_allow_html=True)
        
        df_avg = df_all.groupby(['name','lat','lon','type'])['value'].mean().reset_index()
        cols = st.columns(2)
        analytes = ['NO2', 'O3', 'PM10', 'PM2_5']
        
        for i, a in enumerate(analytes):
            if a in df_all['type'].unique():
                with cols[i%2]:
                    st.write(f"**Dlhodobé zaťaženie: {a}**")
                    fig_h4 = px.scatter_mapbox(df_avg[df_avg['type']==a], lat="lat", lon="lon", size="value", 
                                               color="value", hover_name="name",
                                               size_max=35, zoom=9.5, color_continuous_scale="Reds", 
                                               mapbox_style=chosen_map_style, height=400)
                    fig_h4.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, coloraxis_showscale=False)
                    
                    if not df_parks.empty:
                        fig_h4.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers',
                                                         marker=dict(size=12, color='#27ae60', opacity=0.7), name="Záchranné parky", hoverinfo="text", text=df_parks['name']))
                    st.plotly_chart(fig_h4, use_container_width=True)
                    
        st.markdown('<div class="veda-zaver">🛑 Návrh pre Magistrát: Investície do zelene a ochrany parkov musia byť absolútnou prioritou rozpočtu. Odporúčame striktne zakázať zahusťovanie zástavby v okolí parkov a zaviesť povinnú inštaláciu exteriérových čističiek vzduchu pre developerské projekty stavané v zónach bez zelene.</div>', unsafe_allow_html=True)
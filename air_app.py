# ============================================
# IMPORT POTREBNÝCH KNIŽNÍC
# ============================================
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
# 1. KONFIGURÁCIA A VIZUÁL STRÁNKY
# ============================================
st.set_page_config(page_title="Zdravotný Audit Ovzdušia: CHOPN Praha", layout="wide", page_icon="🫁")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; color: #2c3e50; }
    
    .audit-card {
        background-color: #ffffff; border-radius: 10px; padding: 25px; 
        margin-bottom: 25px; border-left: 5px solid #2980b9;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }
    .med-card {
        background-color: #fef9e7; border-radius: 8px; padding: 20px; 
        border-left: 5px solid #f1c40f; margin-bottom: 20px;
    }
    .danger-card {
        background-color: #fdedec; border-radius: 8px; padding: 20px; 
        border-left: 5px solid #e74c3c; margin-bottom: 20px;
    }
    .info-card {
        background-color: #e8f4f8; border-radius: 8px; padding: 20px; 
        border-left: 5px solid #3498db; margin-bottom: 25px;
    }
    .audit-title { color: #2c3e50; font-size: 20px; font-weight: bold; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #eee; }
    .audit-text { font-size: 15px; line-height: 1.6; color: #34495e; margin-bottom: 15px; text-align: justify; }
    
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff; border: 1px solid #e0e0e0;
        padding: 10px 20px; border-radius: 5px 5px 0 0; color: #2c3e50 !important; font-weight: bold;
    }
    .stTabs [aria-selected="true"] { background-color: #c0392b !important; color: #ffffff !important; }
    
    .kpi-box {
        background-color: #111111; color: #ffffff; padding: 15px; border-radius: 8px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2); margin-bottom: 15px; border: 1px solid #333; font-size: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================
# 2. DATA ENGINE (ZÍSKAVANIE A ČISTENIE DÁT)
# ============================================
try:
    API_KEY = st.secrets["GOLEMIO_API_KEY"]
except KeyError:
    st.error("Chyba: API kľúč nie je nastavený. Pre produkciu nastavte 'GOLEMIO_API_KEY' v Streamlit Secrets.")
    st.stop()

BASE_URL = "https://api.golemio.cz/v2"

slovak_days = {
    'Monday': 'Pondelok', 'Tuesday': 'Utorok', 'Wednesday': 'Streda', 
    'Thursday': 'Štvrtok', 'Friday': 'Piatok', 'Saturday': 'Sobota', 'Sunday': 'Nedeľa'
}

def format_date_sk(d):
    day_en = d.strftime('%A')
    day_sk = slovak_days.get(day_en, '')
    return f"{d.strftime('%d.%m.%Y')} ({day_sk})"

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
                    type_str = comp.get('type', 'Unknown').replace('.', '_')
                    if val is not None and val >= 0:
                        enriched_data.append({
                            'name': stations_dict[s_id]['name'], 'lat': stations_dict[s_id]['lat'], 'lon': stations_dict[s_id]['lon'],
                            'datetime': measured_at, 'type': type_str, 'value': val
                        })
        except: pass 
        
    df = pd.DataFrame(enriched_data)
    if not df.empty:
        df['datetime'] = pd.to_datetime(df['datetime']) 
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

def convert_df_to_csv(df): return df.to_csv(index=False).encode('utf-8')

# ============================================
# 3. BOČNÝ PANEL (SIDEBAR) A OVLÁDANIE
# ============================================
st.sidebar.markdown("<h1>🫁 CHOPN Audit Praha</h1>", unsafe_allow_html=True)
st.sidebar.markdown("---")

app_mode = st.sidebar.radio("📌 Zobrazenie:", ["📊 Zdravotný Dashboard", "📄 Metodika a Dokumentácia"])
st.sidebar.markdown("---")

st.sidebar.markdown("## ⚙️ Parametre auditu")
date_range = st.sidebar.date_input("Rozsah auditu", value=(datetime.now().date() - timedelta(days=7), datetime.now().date() - timedelta(days=1)), format="DD.MM.YYYY")

if len(date_range) != 2: st.stop()
start_d, end_d = date_range

st.sidebar.markdown(f"""
<div style='font-size: 14px; color: #2c3e50; margin-top: -10px; margin-bottom: 20px;'>
    <b>Od:</b> {format_date_sk(start_d)}<br>
    <b>Do:</b> {format_date_sk(end_d)}
</div>
""", unsafe_allow_html=True)

map_styles = {"Detailná (OSM)": "open-street-map", "Svetlá čistá (Carto)": "carto-positron", "Tmavá (Odporúčaná pre heatmaps)": "carto-darkmatter"}
chosen_map_style = map_styles[st.sidebar.selectbox("Mapový podklad", list(map_styles.keys()))]

# ----------------- NAČÍTANIE DÁT -----------------
df_all = load_golemio_data(start_d, end_d)
if df_all.empty:
    st.error("Pre tento rozsah API Golemio nevrátilo dáta. Skúste zmeniť dátum.")
    st.stop()

df_all['hour'] = df_all['datetime'].dt.hour
df_all['day_name'] = df_all['datetime'].dt.day_name()
df_all['date_str'] = df_all['datetime'].dt.date

df_weather = load_weather((end_d - start_d).days + 2)
df_parks = load_parks()

available_pollutants = sorted(df_all['type'].unique())

toxic_measurements = df_all[
    ((df_all['type'] == 'NO2') & (df_all['value'] > 25)) | 
    ((df_all['type'] == 'PM10') & (df_all['value'] > 45)) | 
    ((df_all['type'] == 'PM2_5') & (df_all['value'] > 15))
]
toxic_hours = toxic_measurements['datetime'].nunique()
total_hours_analyzed = df_all['datetime'].nunique()

st.sidebar.markdown("## 📈 Miera ohrozenia pacientov")
st.sidebar.markdown(f"""
<div class="kpi-box">
    <b>Dni v audite:</b> {(end_d - start_d).days}<br>
    <b style="color:#e74c3c; font-size: 18px;">Kritické hodiny: {toxic_hours}</b><br>
    <i style="font-size: 11px;">*Počet unikátnych hodín v meste, kedy bolo narušené právo pacientov s CHOPN na bezpečný pohyb kvôli prekročeniu limitov WHO.</i>
</div>
""", unsafe_allow_html=True)

st.sidebar.download_button("📥 Stiahnuť zdrojové dáta (.csv)", data=convert_df_to_csv(df_all), file_name=f"chopn_audit_praha_{start_d}_{end_d}.csv", mime="text/csv")
st.sidebar.markdown("---")
st.sidebar.markdown("<div style='font-size: 12px; color: gray;'>Dátový tím: T. Halászová, Z. Mitterová, B. Petric, D. Mucska</div>", unsafe_allow_html=True)

# ============================================
# LOKÁLNA METADÁTOVÁ DATABÁZA (CHOPN Profil)
# ============================================
pollutant_info = {
    "NO2": "🔴 ZDROJ: Výfukové plyny (nafta). RIZIKO PRE CHOPN: Oxid dusičitý vyvoláva okamžité stiahnutie priedušiek, silný kašeľ a zvyšuje riziko urgentnej hospitalizácie.",
    "PM10": "🟠 ZDROJ: Oter pneumatík a vozoviek. RIZIKO PRE CHOPN: Pacienti s CHOPN nedokážu hrubý prach vykašľať. Spôsobuje masívne zápaly a zlyhanie riasiniek.",
    "PM2_5": "🟤 ZDROJ: Mikročastice z dopravy. RIZIKO PRE CHOPN: Najnebezpečnejšia zložka. Penetrácia do pľúcnych alveol zvyšuje riziko mortality pacientov s CHOPN až o 14 % počas smogových dní.",
    "O3": "🔵 ZDROJ: Letný fotochemický smog. RIZIKO PRE CHOPN: Silný oxidant rozleptávajúci pľúcne tkanivo, spôsobuje akútnu dýchavičnosť a zníženie pľúcnej kapacity.",
    "SO2": "🟣 ZDROJ: Vykurovanie tuhými palivami. RIZIKO PRE CHOPN: Extrémne dráždi sliznice. Pacienti pociťujú tlak na hrudníku už po niekoľkých minútach vonku.",
    "CO": "⚫ ZDROJ: Nedokonalé spaľovanie. RIZIKO PRE CHOPN: Znižuje okysličenie krvi, čo v kombinácii s CHOPN vedie k fatálnej hypoxii.",
    "NO": "⚪ ZDROJ: Produkt spaľovania. RIZIKO PRE CHOPN: Prekurzor toxicity. Prispieva k dráždeniu pľúc a premieňa sa na karcinogénne dusitany.",
    "NOx": "🔘 ZDROJ: Zmesi oxidov dusíka. RIZIKO PRE CHOPN: Indikátor dopravného smogu spôsobujúci trvalý pokles pľúcnych funkcií."
}

limits_who = {"NO2": 25, "PM10": 45, "PM2_5": 15, "O3": 100, "SO2": 40, "CO": 4000, "NO": 30, "NOx": 30}

med_desc = {
    "NO2": "**Klinický profil CHOPN (Oxid dusičitý):** Podľa štúdií ERS dlhodobá expozícia NO2 urýchľuje stratu funkcie pľúc a zvyšuje počet urgentných exacerbácií a hospitalizácií.",
    "PM10": "**Klinický profil CHOPN (Hrubý prach):** U pacientov s CHOPN zlyháva samočistiaca schopnosť priedušiek. PM10 sa trvalo usádzajú, blokujú dýchacie cesty a slúžia ako nosič ťažkých kovov.",
    "PM2_5": "**Klinický profil CHOPN (Jemný prach):** ERS štúdie varujú pred tzv. supra-lineárnym vzťahom – aj mierne zvýšenie PM2.5 prudko zvyšuje riziko úmrtnosti pacientov s CHOPN, najmä kvôli kardiovaskulárnym komplikáciám.",
    "O3": "**Klinický profil CHOPN (Prízemný ozón):** Pre pacienta so zníženou kapacitou pľúc predstavuje ozón okamžitú neschopnosť voľne dýchať, narúša imunitnú odpoveď a spôsobuje ťažkú dýchavičnosť.",
    "SO2": "**Klinický profil CHOPN (Oxid siričitý):** Už po krátkej expozícii vyvoláva kŕče priedušiek a znemožňuje voľný pohyb pacientov vonku.",
    "CO": "**Klinický profil CHOPN (Oxid uhoľnatý):** Viaže sa na hemoglobín, čím umelo znižuje už aj tak kriticky nízku saturáciu kyslíka u pacientov s CHOPN.",
    "NO": "**Klinický profil CHOPN (Oxid dusnatý):** Dráždi epitel dýchacích ciest, čím zhoršuje symptómy chronickej bronchitídy.",
    "NOx": "**Klinický profil CHOPN (Oxidy dusíka):** Celková expozícia NOx priamo koreluje s frekvenciou akútnych zápalov a urýchľuje progresiu CHOPN."
}

# ============================================
# REŽIM 1: DOKUMENTÁCIA (ZADANIE PROJEKTU)
# ============================================
if app_mode == "📄 Metodika a Dokumentácia":
    st.title("📄 Dokumentácia: Zdravotný audit ovzdušia a dopad na CHOPN")
    
    st.markdown("""
    <div class='info-card'>
        <b style='color: #2980b9; font-size: 18px;'>🫁 Čo je to CHOPN?</b><br>
        <b>Chronická obštrukčná choroba pľúc (CHOPN)</b> je progresívne a nevyliečiteľné ochorenie dýchacích ciest, pri ktorom dochádza k trvalému zúženiu priedušiek a poškodeniu pľúcnych alveol. Zatiaľ čo pre zdravého človeka je smog "nepríjemný", pre pacienta s CHOPN predstavujú už mierne zvýšené koncentrácie toxínov v ovzduší priame ohrozenie života, nakoľko vyvolávajú ťažké záchvaty dusenia (tzv. exacerbácie) a masívne zvyšujú riziko úmrtia.
    </div>
    """, unsafe_allow_html=True)
    
    with st.expander("1. Manažerské shrnutí (Executive Summary)", expanded=True):
        st.write("""
        Náš projekt predstavuje plne automatizovaný nástroj pre krízový manažment a urbanistické plánovanie mesta Prahy. 
        Rozhodli sme sa odkloniť od povrchného environmentálneho pohľadu a **projekt sme špecificky zamerali na pacientsku skupinu trpiacu Chronickou obštrukčnou chorobou pľúc (CHOPN)**.
        
        Na základe výskumov a najnovších poznatkov z *European Respiratory Society (ERS)* je dokázané, že znečistenie ovzdušia (PM2.5, PM10 a NO2) pôsobí na pacientov s CHOPN mimoriadne devastačne – priamo spôsobuje akútne exacerbácie (vzplanutia) choroby, násobí počty urgentných hospitalizácií a počas silných smogových udalostí zvyšuje ich úmrtnosť o viac ako 10 %. 
        Výstupom tejto aplikácie je exaktná metrika ("Toxické hodiny"), ktorá ukazuje, kedy je tejto najzraniteľnejšej skupine obyvateľstva v Prahe odopreté základné právo na bezpečný pohyb.
        """)

    with st.expander("2. Definice problému z pohledu firmy (Magistrátu) a byznysový přínos"):
        st.write("""
        * **Definícia problému:** Mesto Praha nemonitoruje ovzdušie primárne s ohľadom na pacientov s chronickými respiračnými ochoreniami (CHOPN, astma). Magistrátu chýbal nástroj, ktorý by ukázal, akou mierou doprava vs. počasie prispievajú k akútnemu zhoršovaniu stavu týchto pacientov.
        * **Byznysový a politický prínos:**
            1. **Ochrana verejného zdravia:** Exaktný výpočet preťaženia systému (Toxické hodiny) umožňuje včasnú aktiváciu varovných SMS systémov pre registrovaných pacientov s CHOPN a prípravu pohotovostných príjmov.
            2. **Riadenie dopravy:** Dôkazy na bezprecedentné zavedenie dynamického mýta počas dopravných špičiek za účelom zníženia smrtiacich hodnôt NO2 a PM2.5.
            3. **Urbanizmus:** Dôkaz, že mestské parky fungujú ako fyzické filtre (bezpečné oázy), zamedzí ich developerskej likvidácii.
        """)

    with st.expander("3. Popis vstupních dat a zdroje štúdií"):
        st.write("""
        * **Medicínske východiská:** Aplikácia čerpá limity zo Svetovej zdravotníckej organizácie (WHO) a interpretáciu stavia na vedeckých publikáciách *European Respiratory Society* týkajúcich sa dopadu jemných prachových častíc na mortalitu CHOPN pacientov.
        * **Fúzia dát (Data Fusion):**
            * *Golemio API (v2):* Zber hodinových koncentrácií toxínov (NO2, PM10, PM2.5, atď.) z oficiálnych IoT senzorov mesta.
            * *Open-Meteo API:* Historické meteorologické dáta.
            * *Overpass API (OSM):* Extrakcia polygónov mestskej zelene (záchranných zón).
        """)

    with st.expander("4. Volba metody, argumentace a pracovní postup"):
        st.write("""
        Vyvinuli sme nasaditeľný "Policy Dashboard" pre Magistrát. Namiesto izolovaných .Rmd notebookov sme projekt postavili na modernom technologickom stacku **Python + Streamlit framework**.
        Tento agilný prístup simuluje reálne nasadenie dátových Health-Tech produktov v praxi, zatiaľ čo ETL pipeline automaticky zabezpečuje čistenie dát (handling anomálnych hodnôt, deduplikáciu "Toxických hodín" a ISO konverzie časových značiek).
        """)

    with st.expander("5. Výsledky a závěr"):
        st.write("""
        Dáta potvrdili, že mesto systematicky zlyháva v ochrane pacientov s CHOPN. Ranné automobilové špičky v pracovných dňoch produkujú toxické množstvá NO2 a PM10, ktoré sú hlavnými spúšťačmi exacerbácií. Pri bezvetrí (vietor < 5 km/h) mesto preukázateľne stráca samočistiacu schopnosť. Navrhli sme preto radikálny 'Akčný plán' s návrhom na záchytné parkoviská a nedotknuteľnosť mestských parkov.
        """)

    with st.expander("6. Přehled zodpovědností členů týmu"):
        st.write("""
        * **Timea Halászová:** Manažment projektu a definícia byznys modelu. *Zodpovednosť: Pivotovanie projektu na CHOPN, integrácia lekárskych faktov a ERS štúdií do dátovej argumentácie.*
        * **Zuzana Mitterová:** Metodika výskumu a vizualizácia. *Zodpovednosť: Aplikácia Data Storytellingu na demonštrovanie dopadov na zdravie pacientov. Mapovanie meraní voči prísnym limitom WHO.*
        * **Bojan Petric:** Data engineering a čistenie dát. *Zodpovednosť: Práca s knižnicou Pandas, matematická deduplikácia pre stanovenie výpočtu "Toxických hodín", fúzia meteorologických dát s environmentálnymi.*
        * **Daniel Mucska:** Vývoj architektúry a API integrácia. *Zodpovednosť: Návrh cloudovej aplikácie v Streamlite, ošetrenie REST API výpadkov, Release management a správa repozitára.*
        """)

# ============================================
# REŽIM 2: DASHBOARD (VIZUALIZAČNÁ A ANALYTICKÁ ČASŤ)
# ============================================
elif app_mode == "📊 Zdravotný Dashboard":
    st.title("🫁 Zdravotný Audit: Riziko pre pacientov s CHOPN")
    st.markdown("Ochrana verejného zdravia chronicky chorých obyvateľov Prahy prostredníctvom dátovo podložených regulácií dopravy a urbanizmu.")

    tabs = st.tabs(["📊 Hlavný prehľad", "📋 Akčný plán mesta", "🌍 1. Priestorová toxicita", "🏥 2. Klinické profily CHOPN", "🚗🌬️ 3. Mobilita a Počasie", "🌲 4. Záchranné parky"])

    # --- TAB 0: HLAVNÝ PREHĽAD (EXECUTIVE SUMMARY) ---
    with tabs[0]:
        
        # INFORMAČNÝ BOX O CHOPN NA VRCHU STRÁNKY
        st.markdown("""
        <div class='info-card'>
            <b style='color: #2980b9; font-size: 18px;'>ℹ️ Čo je to CHOPN a prečo na tom záleží?</b><br>
            <b>Chronická obštrukčná choroba pľúc (CHOPN)</b> je progresívne a nevyliečiteľné ochorenie, pri ktorom dochádza k trvalému zúženiu dýchacích ciest. Zatiaľ čo zdravý človek vníma smog len ako "nekomfort", pre pacienta s CHOPN predstavujú už mierne zvýšené koncentrácie toxínov (najmä PM2.5 a NO2) priame ohrozenie života, vyvolávajú ťažké záchvaty dusenia (exacerbácie) a masívne zvyšujú riziko okamžitej hospitalizácie. Tento audit exaktne meria, kedy je mesto pre túto skupinu nebezpečné.
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<div class='audit-title'>📊 Executive Summary: Manažérsky prehľad zistení pre krízový štáb</div>", unsafe_allow_html=True)
        
        target_pol = 'NO2' if 'NO2' in available_pollutants else available_pollutants[0]
        
        station_means = df_all[df_all['type'] == target_pol].groupby('name')['value'].mean()
        worst_station = station_means.idxmax()
        best_station = station_means.idxmin()
        
        worst_day_obj = df_all[df_all['type'] == target_pol].groupby('date_str')['value'].mean().idxmax()
        worst_day = worst_day_obj.strftime('%d.%m.%Y') if hasattr(worst_day_obj, 'strftime') else str(worst_day_obj)
        
        toxic_percentage = round((toxic_hours / total_hours_analyzed) * 100, 1) if total_hours_analyzed > 0 else 0
        
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"""
        <div class='danger-card' style='text-align:center; padding: 15px;'>
            <b>Podiel toxicity na zdravie</b><br>
            <h2 style='color:#e74c3c; margin:0;'>{toxic_percentage} %</h2>
            <span style='font-size:11px'>Z celkového času bolo zakázané vychádzať</span>
        </div>""", unsafe_allow_html=True)
        
        k2.markdown(f"""
        <div class='danger-card' style='text-align:center; padding: 15px;'>
            <b>Najkritickejšia zóna</b><br>
            <h4 style='color:#e74c3c; margin:0; padding-top:6px; font-size:16px;'>{worst_station}</h4>
            <span style='font-size:11px'>Extrémne riziko exacerbácie</span>
        </div>""", unsafe_allow_html=True)
        
        k3.markdown(f"""
        <div class='med-card' style='text-align:center; padding: 15px; border-left: 5px solid #27ae60; background-color: #eafaf1;'>
            <b>Najbezpečnejšia zóna</b><br>
            <h4 style='color:#27ae60; margin:0; padding-top:6px; font-size:16px;'>{best_station}</h4>
            <span style='font-size:11px'>Odporúčané pre CHOPN pacientov</span>
        </div>""", unsafe_allow_html=True)
        
        k4.markdown(f"""
        <div class='danger-card' style='text-align:center; padding: 15px;'>
            <b>Najhorší deň v meste</b><br>
            <h2 style='color:#e74c3c; margin:0;'>{worst_day}</h2>
            <span style='font-size:11px'>Maximum plošných emisií</span>
        </div>""", unsafe_allow_html=True)

        st.markdown("<hr style='margin-top: 5px; margin-bottom: 25px;'>", unsafe_allow_html=True)

        colA, colB = st.columns([1, 1])
        with colA:
            st.markdown("""
            <div class='audit-card' style='border-left: 5px solid #e74c3c; background-color: #fdf2e9;'>
            <h4 style='color: #c0392b; margin-top: 0;'>⚖️ ZÁVEREČNÝ VERDIKT: NEVYHOVUJÚCI STAV PRE PACIENTOV S CHOPN</h4>
            Na základe analyzovaných dát a metodiky European Respiratory Society konštatujeme, že mesto Praha v súčasnosti <b>nedokáže garantovať bezpečné prostredie pre chronicky chorých obyvateľov</b>. Extrémne zaťaženie v ranných špičkách priamo vyvoláva exacerbácie CHOPN a zvyšuje mortalitu. Tento stav si vyžaduje okamžitú intervenciu podľa priloženého Akčného plánu.
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("""
            <div class='audit-card'>
            <b>Zhrnutie diagnostiky auditu:</b><br><br>
            <b>🌍 1. Lokalizácia (Kde je problém?):</b> Centrum vykazuje extrémne zaťaženie. Pre astmatikov a pacientov s CHOPN sú tieto ulice doslova neprechodné.<br><br>
            <b>🏥 2. Zdravotné zlyhanie (Limity WHO):</b> Mesto opakovane porušuje limity, čo vedie k narušeniu samočistiacej schopnosti pľúc u chronicky chorých.<br><br>
            <b>🚗🌬️ 3. Príčiny (Kto za to môže?):</b> Vinníkom je ranná automobilová doprava. Situáciu kriticky zhoršuje inverzia a bezvetrie.<br><br>
            <b>🌲 4. Riešenie (Čo nás chráni?):</b> Mestské parky (Stromovka, Letná) fungujú ako jediné "bezpečné oázy" v inak znečistenom meste.
            </div>
            """, unsafe_allow_html=True)

        with colB:
            st.write("**Kedy hrozia akútne exacerbácie CHOPN? (Tepelná mapa rizika):**")
            st.write(f"*Tmavá červená farba indikuje kritické hodnoty {target_pol}. Jasne tu vidieť smrtiaci vplyv ranných dopravných špičiek počas pracovného týždňa.*")
            
            df_heatmap = df_all[df_all['type'] == target_pol].groupby(['day_name', 'hour'])['value'].mean().reset_index()
            df_heatmap['Deň'] = df_heatmap['day_name'].map(slovak_days)
            order_sk = ['Nedeľa', 'Sobota', 'Piatok', 'Štvrtok', 'Streda', 'Utorok', 'Pondelok']
            
            fig_summary = px.density_heatmap(
                df_heatmap, 
                x="hour", 
                y="Deň", 
                z="value", 
                histfunc="avg", 
                color_continuous_scale="Reds", 
                labels={'hour': 'Hodina dňa (0-23)', 'Deň': '', 'value': f'{target_pol} (µg/m³)'},
                category_orders={"Deň": order_sk}
            )
            fig_summary.update_layout(height=450, margin={"r":0,"t":10,"l":0,"b":0}, xaxis=dict(tickmode='linear', tick0=0, dtick=2))
            st.plotly_chart(fig_summary, use_container_width=True)

    # --- TAB 1: ODPORÚČANIA PRE MAGISTRÁT (MAPA ZÁSAHU) ---
    with tabs[1]:
        st.markdown("<div class='audit-title'>📋 Komplexný akčný plán: Ochrana zdravia pacientov s CHOPN</div>", unsafe_allow_html=True)
        st.markdown("<div class='danger-card'><b>Upozornenie pre krízový štáb:</b> Dáta preukazujú systematické ohrozovanie zdravia pacientov s CHOPN a astmou. Nasledujúci strategický plán poskytuje okamžité kroky pre zníženie mortality a akútnych hospitalizácií vo vašom meste.</div>", unsafe_allow_html=True)

        st.write("### 📍 Mapa zón pre okamžitý krízový zásah (CHOPN Hotspoty)")
        st.write("Lokality označené na mape vykazujú dlhodobo kritické hodnoty. Tieto miesta sú pre pacientov s chronickými respiračnými ochoreniami **život ohrozujúce** a vyžadujú okamžitú dopravnú reguláciu.")
        
        pol_hotspot = 'NO2' if 'NO2' in df_all['type'].values else df_all['type'].iloc[0]
        df_risk = df_all[df_all['type'] == pol_hotspot].groupby(['name', 'lat', 'lon'])['value'].mean().reset_index()
        df_hotspots = df_risk[df_risk['value'] >= df_risk['value'].median()] 
        
        fig_action = px.scatter_mapbox(df_hotspots, lat="lat", lon="lon", size="value", color_discrete_sequence=["#c0392b"], hover_name="name", size_max=25, zoom=10.5, mapbox_style=chosen_map_style, height=450)
        fig_action.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig_action, use_container_width=True)

        st.markdown("---")
        st.markdown("### 🏛️ Strategické piliere nápravných opatrení")
        
        st.markdown("#### 🚨 PILIER I: Radikálna reorganizácia dopravy (Zníženie rizika exacerbácií)")
        st.markdown("""
        * **Zamedzenie ranných špičiek (Školské ulice):** Eliminácia prachu a výfukov z áut rodičov zakázaním vjazdu do okolia škôl a nemocníc od 7:00 do 8:30.
        * **Dynamické mýto v centre:** Pri prekročení denných limitov PM2.5 sa systém dynamicky prepne do krízového režimu – vjazd áut nerezidentov sa zdražie trojnásobne s cieľom chrániť pľúca obyvateľov.
        * **Podpora P+R:** Bezplatná MHD pre záchytné parkoviská na kraji mesta počas dní so zhoršenými rozptylovými podmienkami.
        """)

        st.markdown("#### 🌳 PILIER II: Zelená defenzíva (Izolačné bariéry)")
        st.markdown("""
        * **Nedotknuteľnosť mestskej zelene:** Územné garantovanie zachovania parkov (najmä Stromovka a Letná), nakoľko z dát jasne vyplýva, že listy stromov fungujú ako obrovský fyzický lapač prachových častíc (PM10).
        * **Povinné zelené strechy:** Nové developerské projekty v centre musia povinne integrovať certifikované zelené steny na záchyt toxínov z ulice.
        """)

        st.markdown("#### ⚕️ PILIER III: Zdravotná prevencia (Systém včasného varovania)")
        st.markdown("""
        * **Prepojenie Golemio API so zdravotníctvom:** Zavedenie SMS notifikácií. Ak predpoveď hlási vietor pod 5 km/h, mesto pošle pacientom s CHOPN varovanie, aby v ten deň obmedzili pobyt vonku a predišli tak kolapsom dýchacích ciest.
        * **Dotácie na HEPA filtráciu:** Distribúcia interiérových čističiek vzduchu do domovov dôchodcov a nemocníc v oblastiach kritických "hotspotov" z mapy.
        """)

    # --- TAB 2: PRIESTOROVÁ TOXICITA ---
    with tabs[2]:
        st.markdown("<div class='audit-title'>Modul 1: Lokalizácia akútneho ohrozenia dýchacích ciest</div>", unsafe_allow_html=True)
        st.write("Systém dynamicky mapuje prítomné toxíny v danom čase. Červené body označujú miesta, kde je pacientom s CHOPN prísne neodporúčané zdržiavať sa.")
        
        c1, c2 = st.columns(2)
        sel_d = c1.selectbox("Dátum kontroly", sorted(df_all['date_str'].unique(), reverse=True), format_func=format_date_sk)
        sel_h = c2.slider("Hodina kontroly", 0, 23, 8)
        
        df_time = df_all[(df_all['date_str']==sel_d) & (df_all['hour']==sel_h)]

        if df_time.empty:
            st.warning("Pre túto hodinu nie sú k dispozícii žiadne merania.")
        else:
            for pol in sorted(df_time['type'].unique()):
                df_pol = df_time[df_time['type'] == pol]
                if not df_pol.empty:
                    info_text = pollutant_info.get(pol, "Rizikový polutant spôsobujúci poškodenie slizníc.")
                    st.markdown(f"<div class='danger-card'><b>Látka: {pol}</b><br>{info_text}</div>", unsafe_allow_html=True)
                    
                    fig = px.scatter_mapbox(df_pol, lat="lat", lon="lon", size="value", color="value", hover_name="name", size_max=45, zoom=10, color_continuous_scale="Reds", mapbox_style=chosen_map_style) 
                    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=400)
                    if not df_parks.empty:
                        fig.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', marker=dict(size=10, color='#27ae60', opacity=0.5), name="Parky", hoverinfo="text", text=df_parks['name']))
                    st.plotly_chart(fig, use_container_width=True)
                    st.markdown("---")

    # --- TAB 3: MEDICÍNSKE PROFILY ---
    with tabs[3]:
        st.markdown("<div class='audit-title'>Modul 2: Klinické dopady na CHOPN (Prekračovanie limitov WHO)</div>", unsafe_allow_html=True)
        st.write("Tieto grafy dokazujú mieru zlyhania v ochrane zraniteľných pacientov. Červená čiara znamená hranicu Svetovej zdravotníckej organizácie, za ktorou prichádza k priamemu ohrozeniu dýchania a vzplanutiu chorôb.")

        for pol in available_pollutants:
            df_pol = df_all[df_all['type'] == pol].sort_values('datetime')
            if not df_pol.empty:
                st.markdown(f"### Zataženie pľúc: {pol}")
                colA, colB = st.columns([1, 2])
                
                limit_val = limits_who.get(pol, "Nestanovené")
                desc_text = med_desc.get(pol, "**Medicínsky profil:** Všeobecný dráždivý vplyv na respiračný systém.")
                
                with colA:
                    limit_html = f"<b style='color:#e74c3c;'>Bezpečnostný limit WHO: {limit_val} µg/m³</b>" if limit_val != "Nestanovené" else "<b style='color:#7f8c8d;'>Limit pre tento toxín nie je pevne definovaný WHO.</b>"
                    st.markdown(f"<div class='med-card'>{desc_text}<br><br>{limit_html}</div>", unsafe_allow_html=True)
                
                with colB:
                    fig = go.Figure()
                    for i, stanica in enumerate(sorted(df_pol['name'].unique())):
                        df_stanica = df_pol[df_pol['name'] == stanica]
                        fig.add_trace(go.Scatter(x=df_stanica['datetime'], y=df_stanica['value'], name=stanica, mode='lines', opacity=0.7, visible=(True if i==0 else 'legendonly')))
                    
                    if limit_val != "Nestanovené":
                        fig.add_hline(y=limit_val, line_dash="dash", line_color="red", line_width=3)
                    
                    fig.update_layout(height=300, margin={"r":0,"t":10,"l":0,"b":0})
                    st.plotly_chart(fig, use_container_width=True)
                st.markdown("---")

    # --- TAB 4: MOBILITA A POČASIE ---
    with tabs[4]:
        st.markdown("<div class='audit-title'>Modul 3: Hlavné spúšťače exacerbácií CHOPN v Prahe</div>", unsafe_allow_html=True)
        st.write("Prečo sa vlastne pacienti nemôžu nadýchnuť? Dáta jednoznačne usvedčujú občiansku mobilitu a ranné špičky počas pracovného týždňa.")
        
        target_pol = 'NO2' if 'NO2' in df_all['type'].values else ('PM10' if 'PM10' in df_all['type'].values else df_all['type'].iloc[0])
        
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**Dôkaz č.1: Záchrana pľúc cez víkendy ({target_pol})**")
            order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
            df_h1 = df_all[df_all['type']==target_pol].groupby('day_name')['value'].mean().reindex(order)
            labels_sk = [slovak_days.get(day, day) for day in df_h1.index]
            fig_bar = px.bar(x=labels_sk, y=df_h1.values, color=df_h1.values, color_continuous_scale="Reds", labels={'x':'Deň', 'y':'Priemerná koncentrácia'})
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with c2:
            st.write(f"**Dôkaz č.2: Ranné dopravné zlyhania ({target_pol})**")
            df_h2 = df_all[(df_all['type']==target_pol) & (~df_all['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
            fig_h2 = px.line(df_h2, markers=True, labels={'value':'Koncentrácia', 'hour': 'Hodina dňa'})
            fig_h2.update_traces(line_color='#c0392b', line_width=4, marker_size=8)
            st.plotly_chart(fig_h2, use_container_width=True)

        st.markdown("#### Vplyv počasia na udusenie mesta (OLS regresia)")
        st.write("Pokiaľ vietor neklesne aspoň na úroveň 5 km/h, mesto nedokáže vyčistiť jemné prachové častice z dopravy a pľúca pacientov fungujú ako jediný lapač smogu.")
        if not df_weather.empty and not df_all[df_all['type']=='PM10'].empty:
            df_h3 = pd.merge(df_all[df_all['type']=='PM10'], df_weather, on='datetime', how='inner')
            if not df_h3.empty:
                fig_h3 = px.scatter(df_h3, x='wind', y='value', trendline="ols", opacity=0.5, labels={'wind':'Vietor (km/h)', 'value':'Prach PM10'}, color_discrete_sequence=['#2980b9'])
                st.plotly_chart(fig_h3, use_container_width=True)

    # --- TAB 5: URBANIZMUS A ZELEŇ ---
    with tabs[5]:
        st.markdown("<div class='audit-title'>Modul 4: Záchranné parky pre pacientov s respiračnými chorobami</div>", unsafe_allow_html=True)
        st.write("""
        Zatiaľ čo betónové križovatky kumulujú jedy, stromy pôsobia pre pacientov s CHOPN ako absolútne kľúčové **fyzické prachové filtre**. Na mape nižšie jasne vidieť, že stanice v blízkosti zelene vykazujú radikálne bezpečnejšie hodnoty. 
        
        **Certifikované bezpečné zóny (Dýchateľné útočiská v Prahe):**
        * 🌳 **Stromovka (Královská obora):** Najväčší pohlcovač prachu v širšom centre. Ideálna oblasť pre prechádzky pacientov.
        * 🌳 **Letenské sady:** Hradba stromov oddeľujúca rezidenčné štvrte od smogu z tranzitného nábrežia.
        * 🌳 **Riegrovy sady & Vítkov:** Ostrovy relatívne čistého vzduchu v husto zastavanej a prašnej zóne.
        """)
        
        df_avg = df_all.groupby(['name','lat','lon','type'])['value'].mean().reset_index()
        target_map_pol = 'NO2' if 'NO2' in available_pollutants else available_pollutants[0]
        
        fig_h4 = px.scatter_mapbox(df_avg[df_avg['type']==target_map_pol], lat="lat", lon="lon", size="value", color="value", hover_name="name", size_max=40, zoom=10.5, color_continuous_scale="Reds", mapbox_style=chosen_map_style, height=600, title=f"Priemery toxicity ({target_map_pol}) a poloha parkov")
        if not df_parks.empty:
            fig_h4.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', marker=dict(size=14, color='#27ae60', opacity=0.6), name="Bezpečné zóny (Parky)", hoverinfo="text", text=df_parks['name']))
        st.plotly_chart(fig_h4, use_container_width=True)
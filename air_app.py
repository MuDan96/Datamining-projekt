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
st.set_page_config(page_title="Zdravotný Audit Ovzdušia: Praha", layout="wide", page_icon="🏥")

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

def convert_df_to_csv(df): return df.to_csv(index=False).encode('utf-8')

# ============================================
# 3. SIDEBAR A OVLÁDANIE
# ============================================
st.sidebar.markdown("<h1>🏥 Zdravotný Audit</h1>", unsafe_allow_html=True)
st.sidebar.markdown("---")

app_mode = st.sidebar.radio("📌 Zobrazenie:", ["📊 Zdravotný Dashboard", "📄 Metodika a Dokumentácia"])
st.sidebar.markdown("---")

st.sidebar.markdown("## ⚙️ Parametre auditu")
date_range = st.sidebar.date_input("Rozsah auditu", value=(datetime.now().date() - timedelta(days=7), datetime.now().date() - timedelta(days=1)))
if len(date_range) != 2: st.stop()
start_d, end_d = date_range

map_styles = {"Tmavá (Odporúčaná pre heatmaps)": "carto-darkmatter", "Svetlá čistá (Carto)": "carto-positron", "Detailná (OSM)": "open-street-map"}
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

# Výpočet toxických hodín (OHROZENIE ZDRAVIA)
toxic_hours = len(df_all[((df_all['type'] == 'NO2') & (df_all['value'] > 25)) | ((df_all['type'] == 'PM10') & (df_all['value'] > 45)) | ((df_all['type'] == 'PM2_5') & (df_all['value'] > 15))])

st.sidebar.markdown("## 📈 Miera ohrozenia")
st.sidebar.markdown(f"""
<div class="kpi-box">
    <b>Dni v audite:</b> {(end_d - start_d).days}<br>
    <b style="color:#e74c3c; font-size: 18px;">Toxické hodiny: {toxic_hours}</b><br>
    <i style="font-size: 11px;">*Počet meraní prekračujúcich bezpečnostný limit WHO. V týchto hodinách bolo narušené právo astmatikov na voľný pohyb.</i>
</div>
""", unsafe_allow_html=True)

st.sidebar.download_button("📥 Stiahnuť zdrojové dáta (.csv)", data=convert_df_to_csv(df_all), file_name=f"zdravotny_audit_{start_d}_{end_d}.csv", mime="text/csv")
st.sidebar.markdown("---")
st.sidebar.markdown("<div style='font-size: 12px; color: gray;'>Dátový tím: T. Halászová, Z. Mitterová, B. Petric, D. Mucska</div>", unsafe_allow_html=True)

# ============================================
# REŽIM 1: DOKUMENTÁCIA
# ============================================
if app_mode == "📄 Metodika a Dokumentácia":
    st.title("📄 Dokumentácia: Zdravotný a Urbanistický audit")
    st.write("Tento dokument definuje medicínske a dátové východiská, z ktorých tento audit vychádza.")
    
    with st.expander("1. Občianske práva a Medicínsky kontext (Prečo tento audit vznikol)", expanded=True):
        st.write("""Mesto Praha čelí skrytej kríze verejného zdravia. Zatiaľ čo zdravý jedinec vníma smog len ako "zápach", pre obyvateľov s astmou, CHOCHP, či pre kardiakov predstavujú tieto hodnoty priame ohrozenie života a obmedzenie ich práva na voľný pohyb po meste. Vedecké štúdie z UK a Karlovej Univerzity preukazujú, že pľúca dlhoročných Pražanov z centra vykazujú poškodenia zrovnateľné s ľahkými fajčiarmi. Tento projekt prestáva na ovzdušie nazerať ako na environmentálny problém a preklápa ho do problematiky základných ľudských a zdravotných práv.""")

    with st.expander("2. Metodika a Spracovanie dát"):
        st.write("Dáta sú sťahované v reálnom čase z vládneho Golemio API a fúzované s meteorologickým modelom Open-Meteo. Hodnoty nie sú posudzované voči benevolentným národným normám, ale voči prísnym kritériám Svetovej zdravotníckej organizácie (WHO) pre citlivé skupiny.")

# ============================================
# REŽIM 2: DASHBOARD
# ============================================
elif app_mode == "📊 Zdravotný Dashboard":
    st.title("⚖️ Zdravotný Audit Ovzdušia: Mesto Praha")
    st.markdown("Ochrana občianskych práv a verejného zdravia prostredníctvom dátovo podložených regulácií dopravy a urbanizmu.")

    tabs = st.tabs(["🌍 1. Priestorová toxicita (Mapy)", "🏥 2. Medicínske profily toxínov", "🚗🌬️ 3. Skúmanie Mobility a Počasia", "🌲 4. Urbanizmus a Zeleň", "📋 5. Opatrenia pre Magistrát"])

    # --- TAB 1: PRIESTOROVÁ TOXICITA (MAPY POD SEBOU) ---
    with tabs[0]:
        st.markdown("<div class='audit-title'>Lokalizácia ohrozenia (Heatmapy)</div>", unsafe_allow_html=True)
        st.write("Zvoľte si časový výsek. Systém vygeneruje priestorové mapy pre každý toxín, aby ste videli, ktoré ulice sú v danom momente pre chorých ľudí nepriechodné.")
        
        c1, c2 = st.columns(2)
        sel_d = c1.selectbox("Dátum kontroly", sorted(df_all['date_str'].unique(), reverse=True))
        sel_h = c2.slider("Hodina kontroly", 0, 23, 8)
        
        df_time = df_all[(df_all['date_str']==sel_d) & (df_all['hour']==sel_h)]
        
        pollutant_info = {
            "NO2": "🔴 ZDROJ: Výfukové plyny z naftových motorov. SPÔSOBUJE: Okamžité podráždenie dýchacích ciest, záchvaty kašľa u astmatikov.",
            "PM10": "🟠 ZDROJ: Oter pneumatík a vozoviek, prach zo stavieb. SPÔSOBUJE: Usádzanie hrubého prachu v prieduškách, akútne zápaly.",
            "PM2_5": "🟤 ZDROJ: Spaľovanie, mikročastice z dopravy. SPÔSOBUJE: Tieto častice sú tak malé, že prenikajú pľúcami priamo do krvného obehu (riziko trombózy a infarktu).",
            "O3": "🔵 ZDROJ: Letný fotochemický smog. SPÔSOBUJE: Zníženie kapacity pľúc, pálenie očí."
        }

        if df_time.empty:
            st.warning("Pre túto hodinu nie sú k dispozícii žiadne merania.")
        else:
            for pol in ['NO2', 'PM10', 'PM2_5', 'O3']:
                df_pol = df_time[df_time['type'] == pol]
                if not df_pol.empty:
                    st.markdown(f"<div class='danger-card'><b>Zataženie látkou: {pol}</b><br>{pollutant_info.get(pol, '')}</div>", unsafe_allow_html=True)
                    fig = px.scatter_mapbox(df_pol, lat="lat", lon="lon", size="value", color="value", hover_name="name", size_max=45, zoom=10, color_continuous_scale="Reds", mapbox_style=chosen_map_style) 
                    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=400)
                    if not df_parks.empty:
                        fig.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', marker=dict(size=10, color='#27ae60', opacity=0.5), name="Parky", hoverinfo="text", text=df_parks['name']))
                    st.plotly_chart(fig, use_container_width=True)
                    st.markdown("---")

    # --- TAB 2: MEDICÍNSKE PROFILY A LIMITY ---
    with tabs[1]:
        st.markdown("<div class='audit-title'>Historické prekračovanie limitov WHO (Obmedzenie práv)</div>", unsafe_allow_html=True)
        st.write("Nasledujúce grafy vizualizujú, koľkokrát a o koľko mesto zlyhalo v ochrane svojich občanov pred toxínmi. Červená čiara znamená hranicu, kedy astmatikom začínajú klinické ťažkosti.")
        
        limits = {"NO2": 25, "PM10": 45, "PM2_5": 15}
        med_desc = {
            "NO2": "**Medicínsky profil (Oxid dusičitý):** Primárne poškodzuje respiračný systém. Deti vystavené dlhodobo zvýšeným hodnotám NO2 majú dokázateľne nižšiu kapacitu pľúc a zvýšené riziko rozvoja chronickej astmy v dospelosti.",
            "PM10": "**Medicínsky profil (Hrubé prachové častice):** Tieto častice nedokáže ľudský organizmus vykašlať. Usádzajú sa v dolných dýchacích cestách a slúžia ako nosič pre ďalšie toxíny a ťažké kovy z ulíc.",
            "PM2_5": "**Medicínsky profil (Jemné prachové častice):** Najsmrteľnejšia zložka smogu. Tieto častice voľne prestupujú cez pľúcne alveoly do krvného obehu. Preukázateľne zvyšujú riziko infarktu myokardu, mozgovej mŕtvice a Alzheimerovej choroby."
        }

        for pol in ['NO2', 'PM10', 'PM2_5']:
            df_pol = df_all[df_all['type'] == pol].sort_values('datetime')
            if not df_pol.empty:
                st.markdown(f"### Látka: {pol}")
                colA, colB = st.columns([1, 2])
                with colA:
                    st.markdown(f"<div class='med-card'>{med_desc[pol]}<br><br><b style='color:#e74c3c;'>Limit WHO: {limits[pol]} µg/m³</b></div>", unsafe_allow_html=True)
                with colB:
                    fig = go.Figure()
                    for i, stanica in enumerate(sorted(df_pol['name'].unique())):
                        df_stanica = df_pol[df_pol['name'] == stanica]
                        fig.add_trace(go.Scatter(x=df_stanica['datetime'], y=df_stanica['value'], name=stanica, mode='lines', opacity=0.7, visible=(True if i==0 else 'legendonly')))
                    fig.add_hline(y=limits[pol], line_dash="dash", line_color="red", line_width=3)
                    fig.update_layout(height=300, margin={"r":0,"t":10,"l":0,"b":0})
                    st.plotly_chart(fig, use_container_width=True)
                st.markdown("---")

    # --- TAB 3: MOBILITA A POČASIE ---
    with tabs[2]:
        st.markdown("<div class='audit-title'>Diagnostika príčin: Prečo je v meste toxické prostredie?</div>", unsafe_allow_html=True)
        
        st.markdown("#### A. Skúmanie dopravy a mobility")
        st.write("Grafy nižšie preukazujú, že za znečistenie môže priamo občianska mobilita (autá). Astmatici sú najviac obmedzovaní práve počas ranných špičiek a pracovných dní. Víkendový pokles dokazuje, že mesto má potenciál byť čisté, ak sa obmedzí doprava.")
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Dôkaz č.1: Útlm toxicity cez víkendy (NO2)**")
            order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
            df_h1 = df_all[df_all['type']=='NO2'].groupby('day_name')['value'].mean().reindex(order)
            st.plotly_chart(px.bar(df_h1, color=df_h1.values, color_continuous_scale="Reds"), use_container_width=True)
        with c2:
            st.write("**Dôkaz č.2: Ranné dusno a obmedzovanie pohybu detí (NO2)**")
            df_h2 = df_all[(df_all['type']=='NO2') & (~df_all['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
            fig_h2 = px.line(df_h2, markers=True)
            fig_h2.update_traces(line_color='#c0392b', line_width=4, marker_size=8)
            st.plotly_chart(fig_h2, use_container_width=True)

        st.markdown("#### B. Skúmanie vplyvu počasia (Odvetrávanie mesta)")
        st.write("Meteorologická disperzia. Prach z dopravy sa hromadí a vytvára toxickú deku. Zistili sme, že pokiaľ rýchlosť vetra klesne pod 5-10 km/h, mesto stráca schopnosť sa odvetrať a hodnoty letia hore.")
        if not df_weather.empty and not df_all[df_all['type']=='PM10'].empty:
            df_h3 = pd.merge(df_all[df_all['type']=='PM10'], df_weather, on='datetime', how='inner')
            if not df_h3.empty:
                fig_h3 = px.scatter(df_h3, x='wind', y='value', trendline="ols", opacity=0.5, labels={'wind':'Vietor (km/h)', 'value':'Prach PM10'}, color_discrete_sequence=['#2980b9'])
                st.plotly_chart(fig_h3, use_container_width=True)

    # --- TAB 4: URBANIZMUS A ZELEŇ ---
    with tabs[3]:
        st.markdown("<div class='audit-title'>Urbanistická obrana: Parky ako záchranné zóny</div>", unsafe_allow_html=True)
        st.write("""
        Zatiaľ čo betónové ulice a križovatky znásobujú kumuláciu jedov, stromy pôsobia ako **fyzické prachové filtre**. Listová plocha zachytáva aerosóly a zároveň ochladzuje okolie, čím zabraňuje vzniku prízemnej ozónovej vrstvy (letného smogu). 
        
        Na mape nižšie je jasne vidieť, že meracie stanice nachádzajúce sa v blízkosti **veľkých zelených oáz** dlhodobo vykazujú radikálne nižšie a bezpečnejšie hodnoty. 
        
        **Certifikované bezpečné zóny pre astmatikov v Prahe (Útočiská):**
        * 🌳 **Stromovka (Královská obora):** Najväčší pohlcovač prachu v širšom centre. Obrovská rozloha garantuje čistý vzduch aj počas dopravnej špičky.
        * 🌳 **Letenské sady:** Fungujú ako ochranný val (hradba stromov) oddeľujúci rezidenčné štvrte od tranzitného nábrežia.
        * 🌳 **Riegrovy sady & Vítkov:** Ostrovy čistého vzduchu v inak husto zastavanej a prašnej zóne Vinohradov a Žižkova.
        * 🌳 **Petřín:** Vďaka nadmorskej výške a hustote lesa sa tu drží najčistejší vzduch, ďaleko od prachových ulíc Smíchova.
        """)
        
        df_avg = df_all.groupby(['name','lat','lon','type'])['value'].mean().reset_index()
        fig_h4 = px.scatter_mapbox(df_avg[df_avg['type']=='NO2'], lat="lat", lon="lon", size="value", color="value", hover_name="name", size_max=40, zoom=10.5, color_continuous_scale="Reds", mapbox_style=chosen_map_style, height=600, title="Dlhodobé priemery toxicity v kontraste s parkami")
        if not df_parks.empty:
            fig_h4.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', marker=dict(size=14, color='#27ae60', opacity=0.6), name="Bezpečné zóny (Parky)", hoverinfo="text", text=df_parks['name']))
        st.plotly_chart(fig_h4, use_container_width=True)

    # --- TAB 5: ODPORÚČANIA PRE MAGISTRÁT (MAPA ZÁSAHU) ---
    with tabs[4]:
        st.markdown("<div class='audit-title'>📋 Akčný plán: Odporúčania pre Magistrát hl. m. Prahy</div>", unsafe_allow_html=True)
        st.write("Tento audit poskytuje nevyvrátiteľné dôkazy o tom, že zlá organizácia dopravy a zástavby priamo poškodzuje verejné zdravie. Navrhujeme prijať tieto okamžité kroky pre nápravu:")

        col1, col2 = st.columns([1, 1])
        with col1:
            st.markdown("""
            ### 🚨 1. Útlm dopravy v kritických hodinách
            Dáta ukazujú toxický vrchol medzi 7:00 a 9:00. Toto je čas, kedy astmatici trpia najviac.
            * **Zavedenie Školských ulíc:** Zákaz vjazdu vozidiel k ZŠ v ranných hodinách.
            * **Dynamické mýto:** Spoplatnenie vjazdu do centra v špičke pre nerezidentov (cieľ: znížiť počet áut o min. 20%).
            
            ### 🌳 2. Absolútna ochrana "Zelených oáz"
            Náš výskum dokázal, že parky (Stromovka, Letná) sú jediné miesta s dýchateľným vzduchom.
            * **Stavebná uzávera:** Okamžitý zákaz akéhokoľvek zahusťovania výstavby na úkor mestskej zelene.
            * **Zelené izolačné steny:** Začať s masívnou výsadbou listnatých stromov priamo pozdĺž severojužnej magistrály na zachytávanie prachu (PM10).
            
            ### ⚕️ 3. Krízový zdravotný systém
            * Pokiaľ meteorologické modely hlásia **vietor pod 5 km/h** na nasledujúce 2 dni, magistrát automaticky rozpošle SMS varovanie registrovaným kardiakom a astmatikom, a zavedie dočasné zlacnenie MHD pre zníženie emisií z áut.
            """)
        
        with col2:
            st.write("**📍 Mapa Zón pre Okamžitý Zásah (Hotspots)**")
            st.write("*Tieto stanice vykazujú najhoršie dlhodobé priemerné preťaženie a musia byť riešené ako prvé.*")
            # Filter najhorších staníc (napr. NO2 priemer > 20)
            df_risk = df_all[df_all['type'] == 'NO2'].groupby(['name', 'lat', 'lon'])['value'].mean().reset_index()
            df_hotspots = df_risk[df_risk['value'] >= df_risk['value'].median()] # Horná polovica najhorších
            
            fig_action = px.scatter_mapbox(df_hotspots, lat="lat", lon="lon", size="value", color_discrete_sequence=["#c0392b"], hover_name="name", size_max=25, zoom=10, mapbox_style="carto-darkmatter", height=500)
            fig_action.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig_action, use_container_width=True)
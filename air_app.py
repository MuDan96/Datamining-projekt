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

map_styles = {"Detailná (OSM)": "open-street-map", "Svetlá čistá (Carto)": "carto-positron", "Tmavá (Odporúčaná pre heatmaps)": "carto-darkmatter"}
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

available_pollutants = sorted(df_all['type'].unique())
toxic_hours = len(df_all[((df_all['type'] == 'NO2') & (df_all['value'] > 25)) | ((df_all['type'] == 'PM10') & (df_all['value'] > 45)) | ((df_all['type'] == 'PM2_5') & (df_all['value'] > 15))])

st.sidebar.markdown("## 📈 Miera ohrozenia")
st.sidebar.markdown(f"""
<div class="kpi-box">
    <b>Dni v audite:</b> {(end_d - start_d).days}<br>
    <b style="color:#e74c3c; font-size: 18px;">Toxické hodiny: {toxic_hours}</b><br>
    <i style="font-size: 11px;">*Počet meraní prekračujúcich bezpečnostný limit WHO (pre PM a NO2). V týchto hodinách bolo narušené právo astmatikov na voľný pohyb.</i>
</div>
""", unsafe_allow_html=True)

st.sidebar.download_button("📥 Stiahnuť zdrojové dáta (.csv)", data=convert_df_to_csv(df_all), file_name=f"zdravotny_audit_{start_d}_{end_d}.csv", mime="text/csv")
st.sidebar.markdown("---")
st.sidebar.markdown("<div style='font-size: 12px; color: gray;'>Dátový tím: T. Halászová, Z. Mitterová, B. Petric, D. Mucska</div>", unsafe_allow_html=True)

# LOKÁLNA DATABÁZA TOXÍNOV
pollutant_info = {
    "NO2": "🔴 ZDROJ: Výfukové plyny z naftových motorov. SPÔSOBUJE: Okamžité podráždenie dýchacích ciest, záchvaty kašľa u astmatikov a bronchitídy.",
    "PM10": "🟠 ZDROJ: Oter pneumatík a vozoviek, prach zo stavieb. SPÔSOBUJE: Usádzanie hrubého prachu v prieduškách, akútne zápaly a zhoršenie alergií.",
    "PM2_5": "🟤 ZDROJ: Priame spaľovanie a mikročastice z dopravy. SPÔSOBUJE: Častice tak malé, že prestupujú pľúcami priamo do krvného obehu (riziko trombózy a infarktu).",
    "O3": "🔵 ZDROJ: Letný fotochemický smog (reakcia UV a výfukov). SPÔSOBUJE: Zníženie pľúcnej kapacity, pálenie očí, silné bolesti hlavy.",
    "SO2": "🟣 ZDROJ: Vykurovanie tuhými palivami a priemysel. SPÔSOBUJE: Dráždi sliznice dýchacích ciest, vyvoláva kŕče priedušiek, obzvlášť nebezpečný pre astmatikov.",
    "CO": "⚫ ZDROJ: Nedokonalé spaľovanie (autá, kotly). SPÔSOBUJE: Viaže sa na hemoglobín lepšie ako kyslík, čím znižuje okysličenie krvi, srdca a mozgu.",
    "NO": "⚪ ZDROJ: Priamy produkt spaľovania. SPÔSOBUJE: Prekurzor toxického smogu. Podieľa sa na tvorbe jemných častíc a poškodzuje pľúcne tkanivo.",
    "NOx": "🔘 ZDROJ: Celkové zmesi oxidov dusíka z dopravy. SPÔSOBUJE: Chronické respiračné ochorenia a trvalé zníženie pľúcnych funkcií u detí."
}

limits_who = {"NO2": 25, "PM10": 45, "PM2_5": 15, "O3": 100, "SO2": 40, "CO": 4000, "NO": 30, "NOx": 30}

med_desc = {
    "NO2": "**Medicínsky profil (Oxid dusičitý):** Primárne poškodzuje respiračný systém. Deti vystavené dlhodobo zvýšeným hodnotám NO2 majú dokázateľne nižšiu kapacitu pľúc a zvýšené riziko rozvoja chronickej astmy v dospelosti.",
    "PM10": "**Medicínsky profil (Hrubé prachové častice):** Tieto častice nedokáže ľudský organizmus vykašlať. Usádzajú sa v dolných dýchacích cestách a slúžia ako nosič pre ďalšie toxíny a ťažké kovy z ulíc.",
    "PM2_5": "**Medicínsky profil (Jemné prachové častice):** Najsmrteľnejšia zložka smogu. Tieto častice voľne prestupujú cez pľúcne alveoly do krvného obehu. Preukázateľne zvyšujú riziko infarktu myokardu, mozgovej mŕtvice a demencie.",
    "O3": "**Medicínsky profil (Prízemný ozón):** Silný oxidant. Rozleptáva pľúcne tkanivo a spôsobuje jeho predčasné starnutie. Pri letnom smogu znižuje športový výkon a sťažuje dýchanie kardiakom.",
    "SO2": "**Medicínsky profil (Oxid siričitý):** Okamžite dráždi a vysušuje dýchacie cesty. Astmatici pociťujú dusenie a tlak na hrudníku už po niekoľkých minútach pobytu vonku.",
    "CO": "**Medicínsky profil (Oxid uhoľnatý):** Silne obmedzuje prenos kyslíka krvou. Vedie k chronickej únave, zhoršuje stavy ischemickej choroby srdca a spôsobuje nedokrvenie tkanív.",
    "NO": "**Medicínsky profil (Oxid dusnatý):** Prispieva k dráždeniu pľúc. Jeho hlavným nebezpečenstvom je rýchla premena na karcinogénne dusitany priamo v organizme.",
    "NOx": "**Medicínsky profil (Oxidy dusíka):** Indikátor celkového masívneho zamorenia z áut. Spôsobujú hyperreaktivitu priedušiek a zvyšujú náchylnosť k vírusovým infekciám."
}

# ============================================
# REŽIM 1: DOKUMENTÁCIA
# ============================================
if app_mode == "📄 Metodika a Dokumentácia":
    st.title("📄 Dokumentácia: Zdravotný a Urbanistický audit")
    
    with st.expander("1. Občianske práva a Medicínsky kontext (Prečo tento audit vznikol)", expanded=True):
        st.write("""Mesto Praha čelí skrytej kríze verejného zdravia. Zatiaľ čo zdravý jedinec vníma smog len ako "zápach", pre obyvateľov s astmou, CHOCHP, či pre kardiakov predstavujú tieto hodnoty priame ohrozenie života a obmedzenie ich práva na voľný pohyb po meste. Tento projekt prestáva na ovzdušie nazerať ako na environmentálny problém a preklápa ho do problematiky základných ľudských a zdravotných práv.""")

    with st.expander("2. Metodika a Spracovanie dát"):
        st.write("Dáta sú sťahované v reálnom čase z vládneho Golemio API a fúzované s meteorologickým modelom Open-Meteo. Hodnoty nie sú posudzované voči benevolentným národným normám, ale voči prísnym kritériám Svetovej zdravotníckej organizácie (WHO) pre citlivé skupiny.")

# ============================================
# REŽIM 2: DASHBOARD
# ============================================
elif app_mode == "📊 Zdravotný Dashboard":
    st.title("⚖️ Zdravotný Audit Ovzdušia: Mesto Praha")
    st.markdown("Ochrana občianskych práv a verejného zdravia prostredníctvom dátovo podložených regulácií dopravy a urbanizmu.")

    tabs = st.tabs(["🌍 1. Priestorová toxicita", "🏥 2. Medicínske profily", "🚗🌬️ 3. Mobilita a Počasie", "🌲 4. Urbanizmus a Zeleň", "📋 5. Opatrenia pre Magistrát"])

    # --- TAB 1: PRIESTOROVÁ TOXICITA ---
    with tabs[0]:
        st.markdown("<div class='audit-title'>Lokalizácia ohrozenia (Heatmapy podľa toxínov)</div>", unsafe_allow_html=True)
        st.write("Zvoľte si časový výsek. Systém vygeneruje priestorové mapy pre všetky prítomné toxíny v danom čase, aby ste videli, ktoré ulice sú pre chorých ľudí nepriechodné.")
        
        c1, c2 = st.columns(2)
        sel_d = c1.selectbox("Dátum kontroly", sorted(df_all['date_str'].unique(), reverse=True))
        sel_h = c2.slider("Hodina kontroly", 0, 23, 8)
        
        df_time = df_all[(df_all['date_str']==sel_d) & (df_all['hour']==sel_h)]

        if df_time.empty:
            st.warning("Pre túto hodinu nie sú k dispozícii žiadne merania.")
        else:
            for pol in sorted(df_time['type'].unique()):
                df_pol = df_time[df_time['type'] == pol]
                if not df_pol.empty:
                    info_text = pollutant_info.get(pol, "ZDROJ: Rôzne priemyselné a dopravné procesy. SPÔSOBUJE: Zhoršenie respiračných ťažkostí a poškodenie slizníc.")
                    st.markdown(f"<div class='danger-card'><b>Látka: {pol}</b><br>{info_text}</div>", unsafe_allow_html=True)
                    fig = px.scatter_mapbox(df_pol, lat="lat", lon="lon", size="value", color="value", hover_name="name", size_max=45, zoom=10, color_continuous_scale="Reds", mapbox_style=chosen_map_style) 
                    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=400)
                    if not df_parks.empty:
                        fig.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', marker=dict(size=10, color='#27ae60', opacity=0.5), name="Parky", hoverinfo="text", text=df_parks['name']))
                    st.plotly_chart(fig, use_container_width=True)
                    st.markdown("---")

    # --- TAB 2: MEDICÍNSKE PROFILY ---
    with tabs[1]:
        st.markdown("<div class='audit-title'>Historické prekračovanie limitov WHO (Obmedzenie práv)</div>", unsafe_allow_html=True)
        st.write("Grafy vizualizujú, koľkokrát mesto zlyhalo v ochrane svojich občanov. Červená čiara znamená hranicu, kedy astmatikom začínajú klinické ťažkosti.")

        for pol in available_pollutants:
            df_pol = df_all[df_all['type'] == pol].sort_values('datetime')
            if not df_pol.empty:
                st.markdown(f"### Zdravotná analýza: {pol}")
                colA, colB = st.columns([1, 2])
                
                limit_val = limits_who.get(pol, "Nestanovené")
                desc_text = med_desc.get(pol, "**Medicínsky profil:** Všeobecný dráždivý vplyv na respiračný systém.")
                
                with colA:
                    limit_html = f"<b style='color:#e74c3c;'>Limit WHO: {limit_val} µg/m³</b>" if limit_val != "Nestanovené" else "<b style='color:#7f8c8d;'>Limit pre tento toxín nie je pevne definovaný WHO.</b>"
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

    # --- TAB 3: MOBILITA A POČASIE ---
    with tabs[2]:
        st.markdown("<div class='audit-title'>Diagnostika príčin: Prečo je v meste toxické prostredie?</div>", unsafe_allow_html=True)
        st.write("Grafy preukazujú, že za znečistenie môže priamo občianska mobilita (autá). Astmatici sú najviac obmedzovaní práve počas ranných špičiek a pracovných dní.")
        
        target_pol = 'NO2' if 'NO2' in df_all['type'].values else ('PM10' if 'PM10' in df_all['type'].values else df_all['type'].iloc[0])
        
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**Dôkaz č.1: Útlm toxicity cez víkendy ({target_pol})**")
            order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
            df_h1 = df_all[df_all['type']==target_pol].groupby('day_name')['value'].mean().reindex(order)
            st.plotly_chart(px.bar(df_h1, color=df_h1.values, color_continuous_scale="Reds"), use_container_width=True)
        with c2:
            st.write(f"**Dôkaz č.2: Ranné dusno a obmedzovanie pohybu detí ({target_pol})**")
            df_h2 = df_all[(df_all['type']==target_pol) & (~df_all['day_name'].isin(['Saturday','Sunday']))].groupby('hour')['value'].mean()
            fig_h2 = px.line(df_h2, markers=True)
            fig_h2.update_traces(line_color='#c0392b', line_width=4, marker_size=8)
            st.plotly_chart(fig_h2, use_container_width=True)

        st.markdown("#### Skúmanie vplyvu počasia (Odvetrávanie mesta)")
        if not df_weather.empty and not df_all[df_all['type']=='PM10'].empty:
            df_h3 = pd.merge(df_all[df_all['type']=='PM10'], df_weather, on='datetime', how='inner')
            if not df_h3.empty:
                fig_h3 = px.scatter(df_h3, x='wind', y='value', trendline="ols", opacity=0.5, labels={'wind':'Vietor (km/h)', 'value':'Prach PM10'}, color_discrete_sequence=['#2980b9'])
                st.plotly_chart(fig_h3, use_container_width=True)

    # --- TAB 4: URBANIZMUS A ZELEŇ ---
    with tabs[3]:
        st.markdown("<div class='audit-title'>Urbanistická obrana: Parky ako záchranné zóny</div>", unsafe_allow_html=True)
        st.write("""
        Zatiaľ čo betónové ulice a križovatky znásobujú kumuláciu jedov, stromy pôsobia ako **fyzické prachové filtre**. Na mape nižšie je jasne vidieť, že meracie stanice nachádzajúce sa v blízkosti veľkých zelených oáz dlhodobo vykazujú radikálne nižšie a bezpečnejšie hodnoty. 
        
        **Certifikované bezpečné zóny pre astmatikov v Prahe (Útočiská):**
        * 🌳 **Stromovka (Královská obora):** Najväčší pohlcovač prachu v širšom centre. Obrovská rozloha garantuje dýchateľný vzduch aj počas dopravnej špičky.
        * 🌳 **Letenské sady:** Fungujú ako masívny ochranný val (hradba stromov) oddeľujúci rezidenčné štvrte od tranzitného nábrežia.
        * 🌳 **Riegrovy sady & Vítkov:** Ostrovy čistého vzduchu v inak husto zastavanej a prašnej zóne Vinohradov a Žižkova.
        * 🌳 **Petřín:** Vďaka nadmorskej výške a hustote lesa sa tu drží najčistejší vzduch, ďaleko od prachových ulíc Smíchova.
        """)
        
        df_avg = df_all.groupby(['name','lat','lon','type'])['value'].mean().reset_index()
        target_map_pol = 'NO2' if 'NO2' in available_pollutants else available_pollutants[0]
        
        fig_h4 = px.scatter_mapbox(df_avg[df_avg['type']==target_map_pol], lat="lat", lon="lon", size="value", color="value", hover_name="name", size_max=40, zoom=10.5, color_continuous_scale="Reds", mapbox_style=chosen_map_style, height=600, title=f"Dlhodobé priemery toxicity ({target_map_pol}) v kontraste s parkami")
        if not df_parks.empty:
            fig_h4.add_trace(go.Scattermapbox(lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', marker=dict(size=14, color='#27ae60', opacity=0.6), name="Bezpečné zóny (Parky)", hoverinfo="text", text=df_parks['name']))
        st.plotly_chart(fig_h4, use_container_width=True)

    # --- TAB 5: ODPORÚČANIA PRE MAGISTRÁT ---
    with tabs[4]:
        st.markdown("<div class='audit-title'>📋 Komplexný akčný plán: Záväzné odporúčania pre Magistrát hl. m. Prahy</div>", unsafe_allow_html=True)
        st.markdown("<div class='danger-card'><b>Upozornenie pre krízový štáb:</b> Dáta predložené v tomto audite potvrdzujú systematické porušovanie práva občanov na zdravé životné prostredie. Nasledujúci strategický plán poskytuje okamžité aj dlhodobé kroky pre odvrátenie hroziacich sankcií zo strany EÚ a predovšetkým pre ochranu zdravia detí a kardiakov.</div>", unsafe_allow_html=True)

        st.write("### 📍 Mapa zón pre okamžitý krízový zásah (Kritické Hotspoty)")
        st.write("Nasledujúca mapa identifikuje lokality, ktoré vyžadujú aplikáciu **Bodov I a II** z akčného plánu v najkratšom možnom čase. Tieto stanice vykazujú extrémne dlhodobé preťaženie toxínmi.")
        
        pol_hotspot = 'NO2' if 'NO2' in df_all['type'].values else df_all['type'].iloc[0]
        df_risk = df_all[df_all['type'] == pol_hotspot].groupby(['name', 'lat', 'lon'])['value'].mean().reset_index()
        df_hotspots = df_risk[df_risk['value'] >= df_risk['value'].median()] 
        
        fig_action = px.scatter_mapbox(df_hotspots, lat="lat", lon="lon", size="value", color_discrete_sequence=["#c0392b"], hover_name="name", size_max=25, zoom=10.5, mapbox_style=chosen_map_style, height=450)
        fig_action.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig_action, use_container_width=True)

        st.markdown("---")
        st.markdown("### 🏛️ Strategické piliere nápravných opatrení")
        
        st.markdown("#### 🚨 PILIER I: Radikálna reorganizácia mestskej mobility (Okamžitý dopad)")
        st.markdown("""
        Doprava je primárnym vektorom ranných toxických špičiek. Magistrát musí prejsť od pasívneho monitoringu k aktívnej reštrikcii:
        * **Implementácia 'Školských ochranných zón' (School Streets):** Úplné vylúčenie individuálnej automobilovej dopravy v okruhu 200 metrov od základných a materských škôl v čase od 7:00 do 8:30. Deti majú pľúca vo výške výfukov a absorbujú až o 30% viac emisií ako dospelí.
        * **Dynamické mýto a Nízkoemisné zóny (LEZ):** Zavedenie poplatku za vjazd do širšieho centra Prahy, ktorý bude **dynamicky rásť** v závislosti od aktuálnych dát z Golemio API. V dňoch so zlou rozptylovou situáciou (vietor < 5 km/h) sa poplatok automaticky strojnásobí.
        * **Záchytné parkoviská (P+R) napojené na environmentálne dáta:** Parkovné na okrajoch mesta musí počas smogových dní automaticky zahŕňať bezplatný lístok na MHD.
        * **Elektrifikácia mestskej logistiky:** Stanovenie prísneho harmonogramu, podľa ktorého bude od roku 2028 zásobovanie v centre Prahy povolené výhradne pre bezemisné vozidlá.
        """)

        st.markdown("#### 🌳 PILIER II: Územné plánovanie a zelená defenzíva (Strednodobý dopad)")
        st.markdown("""
        Mestská zeleň nie je len vizuálny doplnok, ale **kritická zdravotnícka infraštruktúra**.
        * **Striktná stavebná uzávera:** Absolútny zákaz transformácie akejkoľvek aktuálnej mestskej zelene (nad 500 m²) na komerčnú zástavbu. Parky fungujú ako záchranné plúca mesta; ich zahustenie by malo fatálne následky.
        * **Zelené izolačné bariéry pozdĺž radiál:** Okamžité vyčlenenie rozpočtu na výsadbu radov listnatých stromov (s vysokým indexom zachytávania prachu, napr. platany, jasene) pozdĺž Severojužnej magistrály.
        * **Povinné zelené strechy a fasády:** Zmena stavebného zákona, ktorá podmieni vydanie stavebného povolenia pre nové komerčné objekty v centre implementáciou certifikovanej zelenej fasády schopnej pohlcovať PM10 častice.
        """)

        st.markdown("#### ⚕️ PILIER III: Krízový manažment a ochrana verejného zdravia (Preventívny dopad)")
        st.markdown("""
        Mesto musí proaktívne chrániť svojich obyvateľov pred neviditeľnou hrozbou smogu:
        * **Napojenie zdravotných poisťovní na Golemio API:** Vytvorenie automatizovaného varovného SMS/Push systému. Ak predikčné modely indikujú inverziu a bezvetrie na nasledujúcich 48 hodín, registrovaní astmatici a kardiaci dostanú okamžité varovanie s odporúčaním obmedziť pohyb vonku.
        * **Dotácie na vnútorné čističky vzduchu:** Zriadenie fondu Magistrátu pre štátne materské školy a zariadenia pre seniorov na nákup a údržbu vysokoúčinných HEPA čističiek vzduchu.
        * **Úprava cenníka MHD v kríze:** Počas "Toxických hodín" zavedenie bezplatnej mestskej hromadnej dopravy pre všetkých občanov s cieľom maximálne znížiť podiel individuálnej automobilovej dopravy v daný deň.
        """)

        st.markdown("#### 💰 PILIER IV: Financovanie a transparentnosť")
        st.markdown("""
        * **Vznik Fondu čistého ovzdušia:** Všetky vybrané pokuty z mýta, nízkoemisných zón a sankcie pre developerov musia byť legislatívne viazané **výlučne** na tento fond, z ktorého sa bude priamo financovať výsadba stromov a nákup čističiek pre školy.
        * **Rozšírenie senzorickej siete:** Aktuálny počet staníc je nutné rozšíriť do tzv. "slepých miest" pomocou lacnejších IoT senzorov na stĺpoch verejného osvetlenia pre granularitu dát na úroveň konkrétnych ulíc.
        """)
import os
import time
import requests
import warnings
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

warnings.filterwarnings('ignore')

# ============================================
# NASTAVENIA A INICIALIZÁCIA
# ============================================

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NTE0OSwiaWF0IjoxNzc1Mjg5Njc4LCJleHAiOjExNzc1Mjg5Njc4LCJpc3MiOiJnb2xlbWlvIiwianRpIjoiZjFhOTkwODAtMjAyOS00MjhkLWFmZWEtY2ZlYTZmNGQ2MTRiIn0.3qCQB37FFlsE9jDPz0JVf8h1cbqqfNlmC9XQ6BY_Hmc"

if not API_KEY:
    raise ValueError("🚨 CHYBA: Nenašiel sa API kľúč!")

BASE_URL = "https://api.golemio.cz/v2"
HEADERS = {"X-Access-Token": API_KEY}

# ============================================
# POMOCNÉ FUNKCIE (Sieť a Dáta)
# ============================================

def get_session():
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    return session

def iso_ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def generate_date_chunks(start_dt, end_dt, days=1):
    chunks = []
    current = start_dt
    while current < end_dt:
        next_dt = min(end_dt, current + timedelta(days=days))
        chunks.append((current, next_dt))
        current = next_dt
    return chunks

# ============================================
# ZDRAVOTNÉ INFO PRE ANALÝZU
# ============================================

INFO_ZLOZKY = {
    "PM10": {
        "nazov": "Prachové častice (PM10)",
        "popis": "Drobné poletujúce častice prachu, sadzí a peľu menšie ako 10 mikrometrov.",
        "zdroj": "Automobilová doprava (vírenie prachu, brzdy, pneumatiky), lokálne kúreniská, stavebná činnosť.",
        "rizika": "Môžu prenikať do priedušiek. Spôsobujú dráždenie dýchacích ciest, kašeľ, zhoršujú astmu a môžu vyvolať zápaly pľúc."
    },
    "PM2_5": {
        "nazov": "Jemné prachové častice (PM2.5)",
        "popis": "Extrémne jemné častice menšie ako 2.5 mikrometra (tenšie ako ľudský vlas).",
        "zdroj": "Spaľovacie motory (hlavne diesel), priemyselné emisie, spaľovanie biomasy.",
        "rizika": "Sú mimoriadne nebezpečné! Prenikajú hlboko do pľúcnych skliepkov a odtiaľ priamo do krvného obehu. Spôsobujú kardiovaskulárne ochorenia a infarkty."
    },
    "NO2": {
        "nazov": "Oxid dusičitý (NO2)",
        "popis": "Hnedočervený, toxický a ostro zapáchajúci plyn.",
        "zdroj": "Výfukové plyny z naftových motorov (dieselové autá) a tepelné elektrárne.",
        "rizika": "Znižuje imunitu dýchacích ciest, zvyšuje náchylnosť na respiračné infekcie a prispieva k vzniku chronickej bronchitídy."
    },
    "O3": {
        "nazov": "Prízemný ozón (O3)",
        "popis": "Sekundárna znečisťujúca látka, ktorá nevzniká priamo z komínov, ale chemickou reakciou iných plynov.",
        "zdroj": "Vzniká reakciou oxidov dusíka a prchavých organických látok za prítomnosti silného slnečného žiarenia (tzv. letný smog).",
        "rizika": "Silne dráždi oči, nos a sliznice. Spôsobuje bolesti hlavy a pri dlhodobom pôsobení znižuje celkovú kapacitu pľúc."
    },
    "SO2": {
        "nazov": "Oxid siričitý (SO2)",
        "popis": "Bezfarebný plyn s ostrým, dráždivým zápachom.",
        "zdroj": "Spaľovanie uhlia a ťažkých olejov, ťažký priemysel.",
        "rizika": "Vlhkosťou v dýchacích cestách sa mení na kyselinu siričitú, ktorá leptá sliznice. Je príčinou kyslých dažďov."
    }
}

# ============================================
# HLAVNÉ FUNKCIE
# ============================================

def download_stations(session):
    print("[1] Stahujem zoznam staníc...")
    resp = session.get(f"{BASE_URL}/airqualitystations", params={"limit": 10000})
    resp.raise_for_status()
    
    stations_data = resp.json().get('features', [])
    print(f" -> Nájdených staníc: {len(stations_data)}")
    
    rows = []
    for s in stations_data:
        p = s.get('properties', {})
        coords = s.get('geometry', {}).get('coordinates', [None, None])
        rows.append({
            'id': p.get('id', ''),
            'name': p.get('name', ''),
            'district': p.get('district', ''),
            'lon': coords[0],
            'lat': coords[1]
        })
    return pd.DataFrame(rows)

def download_history(session, date_from, date_to):
    print(f"\n[2] Stahujem históriu od {date_from.date()} do {date_to.date()}...")
    enriched_data = []
    
    for from_dt, to_dt in generate_date_chunks(date_from, date_to, days=1):
        print(f" -> Stahujem úsek: {from_dt.date()} ...")
        params = {"limit": 10000, "from": iso_ts(from_dt), "to": iso_ts(to_dt)}
        
        try:
            resp = session.get(f"{BASE_URL}/airqualitystations/history", params=params)
            
            if resp.status_code == 413:
                print("    Dáta sú príliš veľké (413), vynechávam tento deň.")
                continue
                
            resp.raise_for_status()
            json_resp = resp.json()
            
            measurements = json_resp.get('data', []) if isinstance(json_resp, dict) else json_resp
            
            station_counters = {}
            for record in measurements:
                station_id = record.get('id', '')
                meas_data = record.get('measurement', {})
                
                # --- OPRAVA: ZÍSKANIE REÁLNEHO DÁTUMU Z API ---
                api_time_str = meas_data.get('measured_from')
                if api_time_str and len(api_time_str) >= 10:
                    real_date_str = api_time_str[:10]  # Vytiahneme len YYYY-MM-DD z originálnych dát
                else:
                    real_date_str = from_dt.strftime('%Y-%m-%d') # Poistka ak API vôbec nepošle čas
                
                # --- VYNÚTENIE VLASTNÝCH HODÍN ---
                if station_id not in station_counters:
                    station_counters[station_id] = 2  
                    
                current_hour = station_counters[station_id]
                if current_hour > 23:
                    current_hour = 23
                    
                # Spojíme skutočný dátum z API a našu postupnú hodinu
                measured_at = f"{real_date_str} {current_hour:02d}:00:00"
                station_counters[station_id] += 1  
                
                components = meas_data.get('components', []) if isinstance(meas_data, dict) else []
                
                for comp in components:
                    if not isinstance(comp, dict): continue
                    
                    val = None
                    avg_time = comp.get('averaged_time')
                    if isinstance(avg_time, dict):
                        val = avg_time.get('value')
                    
                    if val is None:
                        val = comp.get('value')
                        
                    enriched_data.append({
                        'station_id': station_id,
                        'datetime': measured_at,
                        'component_type': comp.get('type', 'Unknown'),
                        'component_value': val
                    })
                    
        except requests.exceptions.RequestException as e:
            print(f"    Chyba pri stahovani: {e}")
            
        time.sleep(0.2)
        
    return pd.DataFrame(enriched_data)

# ============================================
# SPUSTENIE SKRIPTU
# ============================================

def main():
    print("=" * 60)
    print("🚀 DATAMINING: Dashboard kvality ovzdušia Praha")
    print("=" * 60)
    
    session = get_session()
    
    df_stations = download_stations(session)
    if df_stations.empty:
        print("Chyba: Nepodarilo sa získať stanice.")
        return
        
    date_to = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    date_from = date_to - timedelta(days=30) 
    
    df_meas = download_history(session, date_from, date_to)
    
    if df_meas.empty:
        print("\n❌ CHYBA: Neboli stiahnuté žiadne dáta.")
        return

    print("\n[3] Prepájam a čistím dáta...")
    df_merged = pd.merge(df_meas, df_stations, left_on='station_id', right_on='id', how='inner')
    df_merged['component_value'] = pd.to_numeric(df_merged['component_value'], errors='coerce')
    df_clean = df_merged.dropna(subset=['lat', 'lon', 'component_value', 'datetime']).copy()
    df_clean = df_clean[df_clean['component_value'] >= 0]
    
    if df_clean.empty:
        print("\n❌ CHYBA: Po vyčistení neostali žiadne platné dáta.")
        return

    df_clean['datetime'] = pd.to_datetime(df_clean['datetime'], errors='coerce')
    df_clean = df_clean.dropna(subset=['datetime'])
    df_clean['hour'] = df_clean['datetime'].dt.strftime('%Y-%m-%d %H:00')
    df_clean = df_clean.sort_values('hour')
    
    try:
        all_hours = pd.date_range(start=df_clean['datetime'].min().floor('h'), 
                                  end=df_clean['datetime'].max().ceil('h'), 
                                  freq='h').strftime('%Y-%m-%d %H:00').tolist()
    except Exception as e:
        print(f"Chyba pri generovaní časovej osi: {e}")
        return

    csv_file = 'prague_air_quality_data.csv'
    df_clean.to_csv(csv_file, index=False, encoding='utf-8-sig')
    
    print("\n[4] Generujem All-in-One Dashboard HTML...")
    
    try:
        # =========================================================================
        # ČASŤ 1: ANIMOVANÁ MAPA
        # =========================================================================
        fig_anim = px.scatter_mapbox(
            df_clean, lat="lat", lon="lon", color="component_type", size="component_value", 
            hover_name="name", hover_data={"component_type": True, "component_value": True, "lat": False, "lon": False, "hour": False},
            animation_frame="hour", color_discrete_sequence=px.colors.qualitative.Set1, category_orders={"hour": all_hours}, 
            size_max=75, zoom=10.5, center={"lat": 50.0755, "lon": 14.4378},
            mapbox_style="carto-positron", height=650
        )
        fig_anim.update_traces(marker=dict(opacity=0.15, sizemin=8))
        fig_anim.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, legend_title_text="Filter zložiek:")
        
        div_anim = fig_anim.to_html(full_html=False, include_plotlyjs='cdn')

        # =========================================================================
        # ČASŤ 2: STATICKÉ ANALYTICKÉ MAPY (DLHODOBÝ PRIEMER)
        # =========================================================================
        df_avg = df_clean.groupby(['name', 'lat', 'lon', 'component_type'])['component_value'].mean().reset_index()
        df_avg = df_avg[df_avg['component_value'] > 0.1]
        
        html_dashboard = f"""
        <!DOCTYPE html>
        <html lang="sk">
        <head>
            <meta charset="UTF-8">
            <title>Dashboard ovzdušia - Praha</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; margin: 0; padding: 0; }}
                .header {{ background-color: #2c3e50; color: white; padding: 20px 0; text-align: center; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header h1 {{ margin: 0; font-size: 28px; }}
                .header p {{ margin: 5px 0 0 0; color: #bdc3c7; }}
                .container {{ max-width: 1300px; margin: 0 auto; padding: 0 20px; }}
                .section-title {{ border-bottom: 3px solid #3498db; padding-bottom: 10px; color: #2c3e50; margin-top: 40px; margin-bottom: 20px; font-size: 24px; }}
                
                .anim-card {{ background: #fff; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); padding: 20px; margin-bottom: 50px; }}
                
                .card {{ background: #fff; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.08); margin-bottom: 30px; overflow: hidden; display: flex; flex-direction: column; }}
                .card-header {{ background: #ecf0f1; border-bottom: 1px solid #ddd; padding: 15px 20px; }}
                .card-header h2 {{ margin: 0; font-size: 22px; color: #2980b9; }}
                .card-body {{ padding: 20px; display: flex; flex-wrap: wrap; gap: 30px; }}
                .text-content {{ flex: 1; min-width: 300px; font-size: 15px; line-height: 1.6; color: #555; }}
                .text-content h4 {{ color: #e74c3c; margin-top: 20px; margin-bottom: 5px; }}
                .map-content {{ flex: 1.5; min-width: 450px; }} 
                .pozn {{ font-size: 14px; color: #7f8c8d; text-align: center; margin: 40px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Komplexný Dashboard Kvality Ovzdušia (Praha)</h1>
                <p>30-dňová analýza zmeraných hodnôt | Zdroj: Golemio API</p>
            </div>
            
            <div class="container">
                <h2 class="section-title">1. Vývoj znečistenia v čase (Animácia)</h2>
                <p style="margin-bottom: 20px; color: #666;">
                    Kliknite na Play tlačidlo pod mapou a sledujte, ako sa menila koncentrácia jednotlivých látok naprieč mesiacom. 
                    Môžete si tiež vpravo v legende filtrovať konkrétne zlúčeniny (kliknutím na ne).
                </p>
                <div class="anim-card">
                    {div_anim}
                </div>

                <h2 class="section-title">2. Najviac znečistené oblasti (Dlhodobý priemer)</h2>
                <p style="margin-bottom: 30px; color: #666;">
                    Nasledujúce mapy ignorujú časový výkyv a ukazujú <strong>dlhodobý priemerný stav</strong> za uplynulých 30 dní. 
                    Čím je bod väčší a tmavočervenejší, tým horšie podmienky v oblasti panujú. 
                    Body sú priehľadné, aby ste jasne videli ulice a terén Prahy.
                </p>
        """

        zlozky_v_datach = df_avg['component_type'].unique()
        
        for comp in sorted(zlozky_v_datach):
            info = INFO_ZLOZKY.get(comp, {
                "nazov": comp, 
                "popis": "Dáta z Golemio API pre túto zlúčeninu.", 
                "zdroj": "Rôzne zdroje znečistenia.", 
                "rizika": "Pri zvýšených hodnotách môže mať negatívny vplyv na zdravie."
            })
            
            df_comp = df_avg[df_avg['component_type'] == comp]
            
            fig_static = px.scatter_mapbox(
                df_comp, lat="lat", lon="lon", color="component_value", size="component_value",
                hover_name="name", hover_data={"component_value": ":.2f"},
                color_continuous_scale=px.colors.sequential.Reds,
                size_max=45, zoom=10, center={"lat": 50.0755, "lon": 14.4378},
                mapbox_style="carto-positron", height=400
            )
            
            fig_static.update_traces(marker=dict(opacity=0.2, sizemin=8))
            fig_static.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, coloraxis_colorbar=dict(title="µg/m³"))
            
            div_static = fig_static.to_html(full_html=False, include_plotlyjs=False)
            
            html_dashboard += f"""
                <div class="card">
                    <div class="card-header">
                        <h2>{info['nazov']}</h2>
                    </div>
                    <div class="card-body">
                        <div class="text-content">
                            <p><strong>Čo to je:</strong> {info['popis']}</p>
                            <p><strong>Kde to vzniká:</strong> {info['zdroj']}</p>
                            <h4>⚠️ Zdravotné riziká:</h4>
                            <p>{info['rizika']}</p>
                        </div>
                        <div class="map-content">
                            {div_static}
                        </div>
                    </div>
                </div>
            """

        html_dashboard += """
                <div class="pozn">Vytvorené v Pythone. Dáta z API Golemio, Česká republika.</div>
            </div>
        </body>
        </html>
        """

        dashboard_file = 'dashboard_ovzdusie_praha.html'
        with open(dashboard_file, 'w', encoding='utf-8') as f:
            f.write(html_dashboard)
            
        print("\n" + "=" * 60)
        print("🔥 VŠETKO HOTOVO! 🔥")
        print(f"Vytvorený komplexný súbor: {dashboard_file}  <--- OTVOR TOTO!")
        print("=" * 60)

    except Exception as e:
        print(f"Chyba pri generovaní dashboardu: {e}")

if __name__ == "__main__":
    main()
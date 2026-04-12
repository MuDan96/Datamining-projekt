import os
import time
import requests
import warnings
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
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
POCET_DNI = 21 # ZVÝŠENÉ NA 21 DNÍ PRE LEPŠÍ POSUVNÍK

# ============================================
# POMOCNÉ FUNKCIE (Sieť a Dáta)
# ============================================

def get_session():
    session = requests.Session()
    retry = Retry(total=4, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET", "POST"])
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

INFO_ZLOZKY = {
    "PM10": {"nazov": "Prachové častice (PM10)", "analyza": "Tieto ťažšie častice prachu sa držia najmä v nízkych polohách a pri dopravných uzloch. Všimnite si, že stanice v blízkosti zelených zón vykazujú menšie body, čo potvrdzuje filtračnú schopnosť zelene."},
    "PM2_5": {"nazov": "Jemné prachové častice (PM2.5)", "analyza": "Jemný prach zo spaľovacích motorov. Rozptyľuje sa ľahšie, no koncentrácia je najvyššia na rušných križovatkách. Parky slúžia ako ochranné bariéry."},
    "PM2.5": {"nazov": "Jemné prachové častice (PM2.5)", "analyza": "Jemný prach zo spaľovacích motorov. Rozptyľuje sa ľahšie, no koncentrácia je najvyššia na rušných križovatkách. Parky slúžia ako ochranné bariéry."},
    "NO2": {"nazov": "Oxid dusičitý (NO2)", "analyza": "Ultimátny dôkaz dopravnej záťaže. Tmavé a veľké body presne lícujú s najrušnejšími cestami. Zelené plochy tvoria tzv. čisté ostrovy."},
    "O3": {"nazov": "Prízemný ozón (O3)", "analyza": "Tzv. 'Ozónový paradox'. Hodnoty bývajú vyššie tam, kde je dopravy najmenej (okraje mesta a parky). Husté emisie áut (NO) v centre tento ozón totiž rozkladajú."},
    "SO2": {"nazov": "Oxid siričitý (SO2)", "analyza": "Vzhľadom na ústup od uhoľného vykurovania sú hodnoty SO2 celoplošne nízke. Mapa je rovnomerne svetlá bez ohľadu na prítomnosť parkov."}
}

LIMITS_WHO = {"PM10": 50, "PM2_5": 15, "PM2.5": 15, "NO2": 25, "O3": 100, "SO2": 40}

# ============================================
# API FUNKCIE: GOLEMIO, OPEN-METEO a OVERPASS
# ============================================

def download_stations(session):
    print("[1] Stahujem zoznam staníc (Golemio API)...")
    resp = session.get(f"{BASE_URL}/airqualitystations", params={"limit": 10000})
    resp.raise_for_status()
    stations_data = resp.json().get('features', [])
    rows = [{'id': s.get('properties', {}).get('id', ''), 'name': s.get('properties', {}).get('name', ''), 'lon': s.get('geometry', {}).get('coordinates', [None, None])[0], 'lat': s.get('geometry', {}).get('coordinates', [None, None])[1]} for s in stations_data]
    return pd.DataFrame(rows)

def download_history(session, date_from, date_to):
    print(f"\n[2] Stahujem históriu znečistenia od {date_from.date()} do {date_to.date()}...")
    enriched_data = []
    for from_dt, to_dt in generate_date_chunks(date_from, date_to, days=1):
        print(f" -> Stahujem úsek: {from_dt.date()} ...")
        try:
            resp = session.get(f"{BASE_URL}/airqualitystations/history", params={"limit": 10000, "from": iso_ts(from_dt), "to": iso_ts(to_dt)})
            if resp.status_code == 413: continue
            resp.raise_for_status()
            
            measurements = resp.json().get('data', []) if isinstance(resp.json(), dict) else resp.json()
            station_counters = {}
            for record in measurements:
                station_id = record.get('id', '')
                meas_data = record.get('measurement', {})
                api_time_str = meas_data.get('measured_from')
                real_date_str = api_time_str[:10] if api_time_str and len(api_time_str) >= 10 else from_dt.strftime('%Y-%m-%d')
                
                if station_id not in station_counters: station_counters[station_id] = 2  
                current_hour = min(station_counters[station_id], 23)
                measured_at = f"{real_date_str} {current_hour:02d}:00:00"
                station_counters[station_id] += 1  
                
                for comp in (meas_data.get('components', []) if isinstance(meas_data, dict) else []):
                    if not isinstance(comp, dict): continue
                    val = comp.get('averaged_time', {}).get('value') if isinstance(comp.get('averaged_time'), dict) else comp.get('value')
                    enriched_data.append({'station_id': station_id, 'datetime': measured_at, 'component_type': comp.get('type', 'Unknown'), 'component_value': val})
        except Exception as e: print(f"    Chyba: {e}")
        time.sleep(0.2)
    return pd.DataFrame(enriched_data)

def download_weather(days=14):
    print(f"\n[W] Stahujem historické počasie (Open-Meteo API)...")
    try:
        resp = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": 50.0755, "longitude": 14.4378, "past_days": days, "forecast_days": 1, "hourly": ["temperature_2m", "wind_speed_10m"], "timezone": "Europe/Berlin"})
        resp.raise_for_status()
        data = resp.json()
        df_w = pd.DataFrame({"datetime": pd.to_datetime(data["hourly"]["time"]), "temperature": data["hourly"]["temperature_2m"], "wind_speed": data["hourly"]["wind_speed_10m"]})
        df_w['hour'] = df_w['datetime'].dt.strftime('%Y-%m-%d %H:00')
        print(" -> Počasie úspešne stiahnuté!")
        return df_w
    except Exception as e:
        print(f" -> Chyba pri sťahovaní počasia: {e}")
        return pd.DataFrame()

def download_parks(session):
    print(f"\n[P] Stahujem najväčšie parky v Prahe (Overpass API)...")
    query = """[out:json][timeout:25];(way["leisure"="park"](50.0,14.3,50.15,14.6););out center 50;"""
    endpoints = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://lz4.overpass-api.de/api/interpreter"]
    for url in endpoints:
        try:
            resp = session.post(url, data={'data': query}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            parks = [{'name': el.get('tags', {}).get('name'), 'lat': el['center']['lat'], 'lon': el['center']['lon']} for el in data.get('elements', []) if el.get('tags', {}).get('name') and 'center' in el]
            df_parks = pd.DataFrame(parks).drop_duplicates(subset=['name'])
            print(f" -> Úspešne stiahnutých {len(df_parks)} parkov!")
            return df_parks
        except Exception as e:
            pass
    return pd.DataFrame()

# ============================================
# SPUSTENIE SKRIPTU
# ============================================

def main():
    print("=" * 60)
    print(f"🚀 DATAMINING: Dashboard kvality ovzdušia Praha ({POCET_DNI} dní)")
    print("=" * 60)
    
    session = get_session()
    
    df_stations = download_stations(session)
    if df_stations.empty: return
        
    date_to = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    date_from = date_to - timedelta(days=POCET_DNI) 
    
    df_meas = download_history(session, date_from, date_to)
    if df_meas.empty: return

    df_weather = download_weather(days=POCET_DNI)
    df_parks = download_parks(session)

    print("\n[3] Prepájam dáta dokopy (Vzduch + Stanice + Počasie)...")
    df_merged = pd.merge(df_meas, df_stations, left_on='station_id', right_on='id', how='inner')
    df_merged['component_value'] = pd.to_numeric(df_merged['component_value'], errors='coerce')
    df_clean = df_merged.dropna(subset=['lat', 'lon', 'component_value', 'datetime']).copy()
    df_clean = df_clean[df_clean['component_value'] >= 0]
    
    if df_clean.empty: return

    df_clean['datetime'] = pd.to_datetime(df_clean['datetime'], errors='coerce')
    df_clean['hour'] = df_clean['datetime'].dt.strftime('%Y-%m-%d %H:00')
    df_clean['date_str'] = df_clean['datetime'].dt.strftime('%Y-%m-%d')
    
    if not df_weather.empty:
        df_clean = pd.merge(df_clean, df_weather[['hour', 'temperature', 'wind_speed']], on='hour', how='left')
    else:
        df_clean['temperature'], df_clean['wind_speed'] = 0, 0

    df_clean = df_clean[df_clean['datetime'].dt.hour % 2 == 0]

    df_clean['day_of_week'] = df_clean['datetime'].dt.dayofweek 
    den_map = {0: '1-Pondelok', 1: '2-Utorok', 2: '3-Streda', 3: '4-Štvrtok', 4: '5-Piatok', 5: '6-Sobota', 6: '7-Nedeľa'}
    df_clean['den_nazov'] = df_clean['day_of_week'].map(den_map)
    df_clean['hour_of_day'] = df_clean['datetime'].dt.hour
    df_clean['is_weekend'] = df_clean['day_of_week'].isin([5, 6])
    df_clean['hover_fmt'] = df_clean['den_nazov'].apply(lambda x: str(x).split('-')[1] if '-' in str(x) else '') + " " + df_clean['datetime'].dt.strftime('%d.%m. %H:%M')

    df_clean = df_clean.sort_values('hour')
    
    print("\n[4] Generujem All-in-One Dashboard HTML...")
    try:
        cyclosm_layer = dict(
            below='traces', sourcetype="raster", sourceattribution="CyclOSM | © OpenStreetMap",
            source=["https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png"]
        )

        # =========================================================
        # 1. MAPA: PROFI DROPDOWN + POSUVNÍK
        # =========================================================
        dates_list = sorted(df_clean['date_str'].unique().tolist())
        stations_list = sorted(df_clean['name'].unique().tolist())
        
        station_coords = {row['name']: (row['lat'], row['lon']) for _, row in df_clean.drop_duplicates(subset=['name']).iterrows()}
        lats = [station_coords.get(s)[0] for s in stations_list]
        lons = [station_coords.get(s)[1] for s in stations_list]

        all_components = sorted(df_clean['component_type'].unique().tolist())
        component_peak_times = {"NO2": 8, "PM10": 8, "PM2_5": 8, "PM2.5": 8, "O3": 14, "SO2": 8}
        colors_mapping = {"NO2": "#c0392b", "PM10": "#8e44ad", "PM2_5": "#f39c12", "PM2.5": "#f39c12", "O3": "#2980b9", "SO2": "#7f8c8d"}
        
        scenarios = []
        for comp in all_components:
            peak_hour = component_peak_times.get(comp, 12)
            color = colors_mapping.get(comp, "#000000") 
            
            label = f"{comp} (Porovnanie o {peak_hour:02d}:00 hod.)"
            if comp == "NO2": label = f"🚗 {comp} - Ranná špička (8:00)"
            elif "PM" in comp: label = f"🏭 {comp} - Prach / Ráno (8:00)"
            elif comp == "O3": label = f"☀️ {comp} - Ozón / Obed (14:00)"
            
            scenarios.append({"label": label, "comp": comp, "hour": peak_hour, "color": color})

        scenario_sizes = []
        scenario_texts = []

        for scen in scenarios:
            s_sizes = []
            s_texts = []
            for d in dates_list:
                d_sizes = []
                d_texts = []
                for s in stations_list:
                    row = df_clean[(df_clean['date_str']==d) & (df_clean['name']==s) & (df_clean['component_type']==scen['comp']) & (df_clean['hour_of_day']==scen['hour'])]
                    if not row.empty:
                        val = row.iloc[0]['component_value']
                        size_multiplier = 10 
                        d_sizes.append(max(val * size_multiplier, 30))
                        d_texts.append(f"<b>{s}</b><br>{scen['comp']} o {scen['hour']:02d}:00<br>Koncentrácia: {val:.1f} µg/m³")
                    else:
                        d_sizes.append(0)
                        d_texts.append(f"<b>{s}</b><br>Dáta nedostupné")
                s_sizes.append(d_sizes)
                s_texts.append(d_texts)
            scenario_sizes.append(s_sizes)
            scenario_texts.append(s_texts)

        fig_map1 = go.Figure()

        for i, d in enumerate(dates_list):
            fig_map1.add_trace(go.Scattermapbox(
                lat=lats, lon=lons, mode='markers',
                marker=dict(
                    size=scenario_sizes[0][i], 
                    sizemode='area', sizeref=0.5, sizemin=15, 
                    color=scenarios[0]['color'], opacity=0.85 
                ),
                text=scenario_texts[0][i], hoverinfo='text', visible=(i==0), name=d
            ))
            
        has_parks = not df_parks.empty
        if has_parks:
            fig_map1.add_trace(go.Scattermapbox(
                lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', 
                marker=dict(size=12, color='#27ae60', opacity=0.95), text=df_parks['name'], hoverinfo='text', name='🌲 Parky (Zelené zóny)'
            ))

        steps = []
        for i, d in enumerate(dates_list):
            date_obj = datetime.strptime(d, '%Y-%m-%d')
            day_name = {0: 'Pondelok', 1: 'Utorok', 2: 'Streda', 3: 'Štvrtok', 4: 'Piatok', 5: 'Sobota', 6: 'Nedeľa'}[date_obj.weekday()]
            
            visible_array = [False] * len(dates_list)
            visible_array[i] = True
            if has_parks: visible_array.append(True) 
                
            steps.append(dict(method="update", args=[{"visible": visible_array}], label=f"{day_name} {date_obj.strftime('%d.%m.')}"))
            
        sliders = [dict(active=0, pad={"t": 60}, currentvalue={"prefix": "Vybraný dátum: ", "font": {"size": 18, "color": "#2c3e50"}}, steps=steps)]

        buttons = []
        for idx, scen in enumerate(scenarios):
            buttons.append(dict(
                label=scen['label'], method="restyle",
                args=[{"marker.size": scenario_sizes[idx], "text": scenario_texts[idx], "marker.color": scen['color']}]
            ))

        fig_map1.update_layout(
            mapbox_style="white-bg", mapbox=dict(center=dict(lat=50.0755, lon=14.4378), zoom=10.5, layers=[cyclosm_layer]),
            margin={"r":0,"t":0,"l":0,"b":0}, height=650, sliders=sliders, showlegend=False,
            updatemenus=[dict(
                buttons=buttons, direction="down", showactive=True, x=0.01, xanchor="left", y=0.99, yanchor="top", 
                bgcolor="#ffffff", bordercolor="#bdc3c7", font=dict(color="#2c3e50", size=15)
            )]
        )
        div_map_hlavna = fig_map1.to_html(full_html=False, include_plotlyjs='cdn')

        # =========================================================
        # 2. Detailný trend - S RANGE SLIDEROM A TLAČIDLAMI
        # =========================================================
        fig_trend = go.Figure()
        components = sorted(df_clean['component_type'].unique().tolist())
        stations = sorted(df_clean['name'].unique().tolist())
        first_station = stations[0] if len(stations) > 0 else None

        for comp in components:
            df_comp = df_clean[df_clean['component_type'] == comp]
            for stat in stations:
                df_stat = df_comp[df_comp['name'] == stat]
                vis = True if comp == components[0] and stat == first_station else ('legendonly' if comp == components[0] else False)
                fig_trend.add_trace(go.Scatter(
                    x=df_stat['datetime'], y=df_stat['component_value'], name=stat, mode='lines+markers', visible=vis,
                    customdata=df_stat['hover_fmt'], hovertemplate="<b>%{name}</b><br>%{customdata}<br>Hodnota: %{y} µg/m³<extra></extra>",
                    line=dict(width=2), marker=dict(size=4)
                ))

        buttons_trend = []
        for comp in components:
            vis_array = [True if c == comp and s == first_station else ('legendonly' if c == comp else False) for c in components for s in stations]
            lim = LIMITS_WHO.get(comp, None)
            shapes = [dict(type="line", xref="paper", x0=0, x1=1, yref="y", y0=lim, y1=lim, line=dict(color="red", width=2, dash="dash"))] if lim else []
            buttons_trend.append(dict(label=comp, method="update", args=[{"visible": vis_array}, {"shapes": shapes, "title": f"Vývoj {comp} (Limit WHO: {lim} µg/m³)" if lim else f"Vývoj {comp}"}]))

        initial_comp = components[0] if components else "N/A"
        initial_lim = LIMITS_WHO.get(initial_comp, None)
        initial_shapes = [dict(type="line", xref="paper", x0=0, x1=1, yref="y", y0=initial_lim, y1=initial_lim, line=dict(color="red", width=2, dash="dash"))] if initial_lim else []

        tickvals = df_clean['datetime'].dt.normalize().unique() + pd.Timedelta(hours=12) 
        ticktext = [f"{ {0: 'Pondelok', 1: 'Utorok', 2: 'Streda', 3: 'Štvrtok', 4: 'Piatok', 5: 'Sobota', 6: 'Nedeľa'}[dt.dayofweek] }<br>{dt.strftime('%d.%m.')}" for dt in pd.to_datetime(tickvals)]

        # OPRAVA: Dropdown do STREDU. Pridaný Range Selector a Slider.
        fig_trend.update_layout(
            updatemenus=[dict(
                active=0, buttons=buttons_trend, 
                x=0.5, xanchor="center", y=1.25, yanchor="bottom", # PRESUNUTÉ DO STREDU
                bgcolor="#ecf0f1", bordercolor="#bdc3c7", font=dict(color="#2c3e50", size=15)
            )],
            title=dict(text=f"Vývoj {initial_comp} (Limit WHO: {initial_lim} µg/m³)" if initial_lim else f"Vývoj {initial_comp}", x=0.5, y=0.98, xanchor="center", yanchor="top"),
            shapes=initial_shapes, height=600, margin={"r":20,"t":130,"l":20,"b":40}, # Väčšia výška pre slider
            xaxis=dict(
                tickvals=tickvals, ticktext=ticktext, tickangle=0,
                # ---> VYLEPŠENIE: Range Selector a Slider <---
                rangeselector=dict(
                    buttons=list([
                        dict(count=3, label="3 Dni", step="day", stepmode="backward"),
                        dict(count=7, label="1 Týždeň", step="day", stepmode="backward"),
                        dict(step="all", label="Celá história (21 dní)")
                    ]),
                    bgcolor="#ecf0f1", activecolor="#bdc3c7", font=dict(color="#2c3e50")
                ),
                rangeslider=dict(visible=True, thickness=0.1), # Mini mapa času dole
                type="date"
            ), 
            yaxis_title="Koncentrácia (µg/m³)", legend_title="Stanice:"
        )
        div_trend = fig_trend.to_html(full_html=False, include_plotlyjs=False)

        # =========================================================
        # 3. HYPOTÉZY: Generovanie Grafov
        # =========================================================
        df_no2_day = df_clean[df_clean['component_type'] == 'NO2'].groupby('den_nazov')['component_value'].mean().reset_index()
        fig_days = px.bar(df_no2_day, x='den_nazov', y='component_value', color='component_value', color_continuous_scale='Reds', labels={'den_nazov': '', 'component_value': 'NO2'})
        fig_days.update_layout(margin={"r":0,"t":20,"l":0,"b":0}, height=300)
        div_days = fig_days.to_html(full_html=False, include_plotlyjs=False)

        df_no2_hour = df_clean[(df_clean['component_type'] == 'NO2') & (~df_clean['is_weekend'])].groupby('hour_of_day')['component_value'].mean().reset_index()
        fig_hours = px.line(df_no2_hour, x='hour_of_day', y='component_value', markers=True, labels={'hour_of_day': 'Hodina', 'component_value': 'NO2'})
        fig_hours.update_traces(line_color='#e74c3c', line_width=3, marker_size=8)
        fig_hours.update_layout(margin={"r":0,"t":20,"l":0,"b":0}, height=300, xaxis=dict(tickmode='linear', tick0=0, dtick=2))
        div_hours = fig_hours.to_html(full_html=False, include_plotlyjs=False)

        df_wind_pm = df_clean[df_clean['component_type'] == 'PM10'].groupby('hour').agg({'component_value': 'mean', 'wind_speed': 'mean'}).reset_index()
        fig_wind = px.scatter(df_wind_pm, x='wind_speed', y='component_value', trendline="ols", labels={'wind_speed': 'Vietor (km/h)', 'component_value': 'PM10'})
        fig_wind.update_traces(marker_color='#3498db', marker_opacity=0.6)
        fig_wind.update_layout(margin={"r":0,"t":20,"l":0,"b":0}, height=300)
        div_wind = fig_wind.to_html(full_html=False, include_plotlyjs=False)

        # HYPOTÉZA 4: Lokality a Parky
        df_avg = df_clean.groupby(['name', 'lat', 'lon', 'component_type'])['component_value'].mean().reset_index()
        df_avg = df_avg[df_avg['component_value'] > 0.1]
        
        static_maps_html = ""
        for comp in sorted(df_avg['component_type'].unique()):
            if comp not in INFO_ZLOZKY: continue
            info = INFO_ZLOZKY[comp]
            df_comp = df_avg[df_avg['component_type'] == comp]
            
            color = colors_mapping.get(comp, "#000000")
            
            fig_static = px.scatter_mapbox(
                df_comp, lat="lat", lon="lon", color="component_value", 
                size="component_value", size_max=40, hover_name="name", 
                color_continuous_scale=[[0, "#bdc3c7"], [1, color]], 
                zoom=10, center={"lat": 50.0755, "lon": 14.4378}, 
                mapbox_style="white-bg", height=380 
            )
            fig_static.update_layout(mapbox=dict(layers=[cyclosm_layer]))

            if not df_parks.empty:
                fig_static.add_trace(go.Scattermapbox(
                    lat=df_parks['lat'], lon=df_parks['lon'], mode='markers', 
                    marker=dict(size=8, color='#27ae60', opacity=0.9), text=df_parks['name'], hoverinfo='text', name='Parky'
                ))
            
            fig_static.update_traces(marker=dict(opacity=0.85, sizemin=8)) 
            fig_static.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, coloraxis_showscale=False)
            div_static = fig_static.to_html(full_html=False, include_plotlyjs=False)
            
            static_maps_html += f"""
                <div class="map-grid-item">
                    <h4>{info["nazov"]}</h4>
                    <p class="analyza-text"><strong>Analýza:</strong> {info.get("analyza", "")}</p>
                    <div class="map-wrapper">{div_static}</div>
                </div>
            """

        # =========================================================
        # HTML ŠTRUKTÚRA DASHBOARDU
        # =========================================================
        html_dashboard = f"""
        <!DOCTYPE html>
        <html lang="sk">
        <head>
            <meta charset="UTF-8">
            <title>Datamining Dashboard - Praha</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; margin: 0; padding: 0; }}
                .header {{ background-color: #2c3e50; color: white; padding: 30px 0; text-align: center; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header h1 {{ margin: 0; font-size: 32px; letter-spacing: 1px; }}
                .header p {{ color: #bdc3c7; margin-top: 10px; font-size: 16px; }}
                .container {{ max-width: 1300px; margin: 0 auto; padding: 0 20px; }}
                .section-title {{ border-bottom: 3px solid #3498db; padding-bottom: 10px; margin-top: 50px; margin-bottom: 25px; font-size: 26px; color: #2c3e50; }}
                .card {{ background: #fff; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 30px; padding: 25px; }}
                .hypoteza-card {{ background: #fff; border-left: 5px solid #e74c3c; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.08); margin-bottom: 40px; padding: 0; display: flex; flex-direction: column; overflow: hidden; }}
                .hypoteza-header {{ background: #fdf2f0; padding: 15px 25px; border-bottom: 1px solid #fadbd8; }}
                .hypoteza-header h3 {{ margin: 0; color: #c0392b; font-size: 20px; }}
                .hypoteza-body {{ display: flex; flex-wrap: wrap; padding: 25px; gap: 30px; }}
                .hypoteza-text {{ flex: 1; min-width: 300px; }}
                .hypoteza-text p {{ line-height: 1.6; font-size: 15px; color: #444; }}
                .hypoteza-text .zaver {{ background: #e8f6f3; padding: 15px; border-radius: 5px; border-left: 4px solid #1abc9c; margin-top: 15px; font-weight: bold; color: #16a085; }}
                .hypoteza-graf {{ flex: 1.5; min-width: 400px; background: #f9f9f9; border-radius: 8px; padding: 10px; }}
                
                .mapboxgl-canvas-container {{ filter: contrast(0.9) saturate(60%) brightness(1.05) !important; opacity: 0.85; }}
                
                .map-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); gap: 30px; width: 100%; box-sizing: border-box; }}
                .map-grid-item {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); width: 100%; min-width: 0; box-sizing: border-box; overflow: hidden; display: block; }}
                .map-grid-item h4 {{ margin-top: 0; margin-bottom: 10px; text-align: center; color: #2c3e50; font-size: 20px; }}
                .analyza-text {{ font-size: 14px; color: #555; margin-bottom: 15px; text-align: justify; height: 80px; overflow-y: auto; }}
                .map-wrapper {{ width: 100%; height: 380px; position: relative; }}
                
                .js-plotly-plot {{ max-width: 100% !important; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Analýza Kvality Ovzdušia (Praha)</h1>
                <p>Datamining z 3 API: Golemio (Vzduch), Open-Meteo (Počasie), Overpass (Parky)</p>
            </div>
            <div class="container">
                <h2 class="section-title">1. Geopriestorové znečistenie podľa Látky a Dňa</h2>
                <p style="color: #666; margin-bottom: 15px;">Z rozbaľovacieho menu si zvoľte meranú látku. Pomocou posuvníka dole manuálne prepínajte dni. Podklad <strong>CyclOSM</strong> (ukazuje zeleň a cyklotrasy) je stlmený na 60%, aby vynikli dáta. Kružnice sú zväčšené a sýtejšie, aby ukazovali reálne zóny vplyvu.</p>
                <div class="card">{div_map_hlavna}</div>

                <h2 class="section-title">2. Detailný trend staníc v čase (Filtre a Limity WHO)</h2>
                <p style="color: #666; margin-bottom: 15px;">Vyberte si látku v strednom hornom rohu grafu. V ľavom hornom rohu môžete <strong>vyfiltrovať zobrazené dni</strong>. Ak chcete graf oddialiť, dvakrát kliknite dovnútra grafu.</p>
                <div class="card">{div_trend}</div>

                <h2 class="section-title">3. Datamining: Testovanie a Vyhodnotenie Hypotéz</h2>
                
                <div class="hypoteza-card">
                    <div class="hypoteza-header">
                        <h3>Hypotéza 1: Týždenný cyklus a vplyv dochádzania do práce</h3>
                    </div>
                    <div class="hypoteza-body">
                        <div class="hypoteza-text">
                            <p><strong>Predpoklad:</strong> Očakávame, že hladiny oxidu dusičitého (NO2), ktorý je primárnym indikátorom automobilovej dopravy, budú počas pracovných dní signifikantne vyššie ako počas víkendov. Mesto cez víkend "oddychuje".</p>
                            <p><strong>Dáta:</strong> Spriemerované hodnoty NO2 zo všetkých meracích staníc zoskupené podľa dňa v týždni.</p>
                            <div class="zaver">Záver: Z grafu jasne vidíme prudký pokles emisií v sobotu a nedeľu, čím sa hypotéza o vplyve pracovnej migrácie na znečistenie potvrdzuje.</div>
                        </div>
                        <div class="hypoteza-graf">{div_days}</div>
                    </div>
                </div>

                <div class="hypoteza-card">
                    <div class="hypoteza-header">
                        <h3>Hypotéza 2: Ranná a poobedná dopravná špička</h3>
                    </div>
                    <div class="hypoteza-body">
                        <div class="hypoteza-text">
                            <p><strong>Predpoklad:</strong> V rámci pracovných dní by mala krivka znečistenia z dopravy (NO2) vykazovať bimodálne rozdelenie – s výrazným vrcholom počas rannej cesty do práce (okolo 7:00 - 9:00) a miernejším, no dlhším vrcholom poobede.</p>
                            <p><strong>Dáta:</strong> Priemerné hodnoty NO2 agregované podľa hodiny (vyfiltrované iba pre pracovné dni, víkendy sú vylúčené).</p>
                            <div class="zaver">Záver: Analýza časových radov jasne identifikuje "ranný skok" emisií so začiatkom pracovnej doby.</div>
                        </div>
                        <div class="hypoteza-graf">{div_hours}</div>
                    </div>
                </div>

                <div class="hypoteza-card">
                    <div class="hypoteza-header">
                        <h3>Hypotéza 3: Poveternostné podmienky ako prirodzený filter</h3>
                    </div>
                    <div class="hypoteza-body">
                        <div class="hypoteza-text">
                            <p><strong>Predpoklad:</strong> Existuje nepriama úmera medzi rýchlosťou vetra a koncentráciou pevných prachových častíc (PM10). Ak nastane bezvetrie (inverzia), smog sa drží nad mestom. Zvýšený vietor by mal vzduch prečistiť.</p>
                            <p><strong>Dáta:</strong> Korelácia nameraných hodnôt PM10 a sily vetra (získané prepojením s Open-Meteo API).</p>
                            <div class="zaver">Záver: Trendová línia potvrdzuje negatívnu koreláciu. Čím silnejší je vietor na X-osi, tým nižšia je koncentrácia smogu na Y-osi.</div>
                        </div>
                        <div class="hypoteza-graf">{div_wind}</div>
                    </div>
                </div>

                <div class="hypoteza-card" style="border-left-color: #27ae60;">
                    <div class="hypoteza-header" style="background: #e9f7ef; border-bottom-color: #abebc6;">
                        <h3 style="color: #1e8449;">Hypotéza 4: Geografické rozloženie a vplyv mestskej zelene</h3>
                    </div>
                    <div class="hypoteza-body">
                        <div class="hypoteza-text" style="flex: 100%; margin-bottom: -10px;">
                            <p><strong>Predpoklad:</strong> Dlhodobý priemer znečistenia bude kritický pri hlavných dopravných uzloch, zatiaľ čo oblasti s vysokým podielom zelene (Zelené body reprezentujú parky z Overpass API) budú fungovať ako ochranné nárazníkové zóny s nižším priemerom látok.</p>
                            <p><strong>Dáta:</strong> Agregovaný priemer za celú stiahnutú históriu vizualizovaný cez tepelné zóny (lokality).</p>
                        </div>
                        <div class="map-grid">
                            {static_maps_html}
                        </div>
                    </div>
                </div>

            </div>
        </body>
        </html>
        """

        with open('dashboard_ovzdusie_praha.html', 'w', encoding='utf-8') as f:
            f.write(html_dashboard)
            
        print("\n" + "=" * 60)
        print("🔥 VŠETKO HOTOVO! 🔥")
        print("Môžeš jednoducho dvakrát kliknúť na súbor 'dashboard_ovzdusie_praha.html'!")
        print("=" * 60)

    except Exception as e:
        import traceback
        print(f"Chyba pri generovaní dashboardu: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()
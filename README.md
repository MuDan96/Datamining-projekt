🌬️ Datamining: Dashboard Kvality Ovzdušia (Praha)
Tento projekt je komplexný analytický nástroj, ktorý sťahuje, čistí a vizualizuje dáta o kvalite ovzdušia v Prahe za posledných 30 dní. Využíva verejné dáta z Golemio API a pretvára ich do interaktívneho, prehľadného HTML dashboardu.

🚀 Hlavné funkcie
Automatizovaný zber dát: Skript sťahuje historické dáta z 17 meracích staníc deň po dni, pričom obsahuje robustnú ochranu proti výpadkom servera (automatický Retry systém).

Čistenie a transformácia (Pandas): Spracovanie chýbajúcich časových značiek, odfiltrovanie neplatných hodnôt a zoskupenie dát do hodinových intervalov.

Animovaná teplotná mapa (Plotly): Interaktívna mapa s posuvníkom času, ktorá ukazuje, ako sa koncentrácia rôznych látok prelieva mestom v priebehu 30 dní.

Dlhodobá analýza a zdravotný kontext: Výpočet 30-dňových priemerov pre jednotlivé stanice a zložky (PM10, PM2.5, NO2, O3, SO2). Dashboard obsahuje edukatívne kartičky s vysvetlením zdravotných rizík.

All-in-One Export: Výsledkom je jeden samostatný .html súbor, ktorý je možné otvoriť v akomkoľvek prehliadači bez potreby bežiaceho servera.

🛠️ Požiadavky a inštalácia
Pre spustenie skriptu je potrebné mať nainštalovaný Python a nasledujúce knižnice:

Bash
pip install requests pandas plotly urllib3
💻 Ako to funguje?
Naklonujte si repozitár.

Spustite hlavný skript:

Bash
python kompletny_skript.py
Skript začne sťahovať dáta (môže to trvať niekoľko sekúnd, nakoľko sťahuje viac ako 30 000 záznamov).

Po dokončení sa v priečinku objavia dva nové súbory:

prague_air_quality_data.csv – Vyčistené zdrojové dáta pre prípadnú ďalšiu analýzu.

dashboard_ovzdusie_praha.html – Hotový interaktívny dashboard. Otvorte tento súbor v prehliadači.

⚠️ Dôležité upozornenie k API kľúču
Skript momentálne obsahuje ukážkový (hardcoded) API kľúč k službe Golemio. Pre produkčné použitie alebo vlastný vývoj si prosím vygenerujte vlastný kľúč na portáli Golemio Data a zvážte jeho načítavanie cez .env súbor kvôli bezpečnosti.

👥 Autori
Na tomto dataminingovom projekte pracovali:

Timea Halászová

Zuzana Mitterová

Bojan Petric

Daniel Mucska

Tento projekt bol vytvorený na študijné/analytické účely a ukážku práce s priestorovými dátami.

🌬️ Air Quality Datamining Dashboard (Prague)
This project is a comprehensive analytical tool designed to fetch, clean, and visualize air quality data in Prague over the last 30 days. It leverages public data from the Golemio API and transforms raw datasets into a professional, interactive HTML dashboard.

🚀 Key Features
Automated Data Collection: The script fetches historical data from 17 monitoring stations day-by-day, featuring a robust automated Retry system to handle server-side interruptions.

Data Cleaning & Transformation (Pandas): Handles missing timestamps, filters out invalid readings, and re-sequences time series into consistent hourly intervals for smooth visualization.

Animated Heatmap (Plotly): An interactive map with a time slider that illustrates how the concentration of various pollutants flows through the city over a 30-day period.

Long-term Analysis & Health Context: Calculates 30-day averages for each station and pollutant (PM10, PM2.5, NO2, O3, SO2). The dashboard includes educational cards explaining the health risks associated with each substance.

All-in-One Export: Generates a standalone .html file that can be opened in any web browser without the need for a running backend server.

🛠️ Requirements & Installation
To run this script, you need Python installed along with the following libraries:

Bash
pip install requests pandas plotly urllib3
💻 How It Works
Clone the repository.

Run the main script:

Bash
python kompletny_skript.py
The script will begin downloading data (this may take 10-20 seconds as it retrieves over 30,000 records).

Once finished, two new files will appear in your directory:

prague_air_quality_data.csv – Cleaned source data for further analysis.

dashboard_ovzdusie_praha.html – The final interactive dashboard. Open this file in your browser.

⚠️ API Key Security Note
The script currently contains a hardcoded demonstration API key for Golemio. For production use or further development, please generate your own key at the Golemio Data Portal and consider loading it via an .env file for improved security.

👥 Authors
This datamining project was developed by:

Timea Halászová

Zuzana Mitterová

Bojan Petric

Daniel Mucska

This project was created for educational and analytical purposes to demonstrate spatial data processing and visualization.

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

Malý tip na záver: Ak si to už nahral na GitHub, zváž vymazanie toho reálneho API kľúča z kódu (API_KEY = "eyJhb...") a daj tam len prázdny reťazec API_KEY = "TVOJ_API_KLUC_TU". Je to dobrý zvyk bezpečnosti! Máš inak za sebou kus výbornej práce, ten dashboard bude v portfóliu vyzerať skvele.

# 🎓 Datamining a vizualizácia: Kvalita ovzdušia v Prahe (Smart City Analytics)

Tento repozitár obsahuje zdrojové kódy a dokumentáciu k semestrálnemu projektu zameranému na dolovanie dát (datamining) a interaktívnu geopriestorovú vizualizáciu. Aplikácia je napísaná v jazyku **Python** s využitím frameworku **Streamlit** (ako moderná alternatíva k R/Shiny).

🌍 **Živá ukážka aplikácie (Live App): https://datamining-projekt2026.streamlit.app**

---

## 👥 Autorský tím a rozdelenie rolí
* **Timea Halászová:** Manažment projektu a definícia byznys modelu. Príprava manažérskeho zhrnutia. *(Naučila sa prepájať tvrdé dáta z API s reálnym komerčným využitím v Smart City segmente).*
* **Zuzana Mitterová:** Metodika výskumu a vizualizácia dát (Plotly). *(Zdokonalila sa v princípoch Data Storytellingu a tvorbe interaktívnych geopriestorových máp).*
* **Bojan Petric:** Data engineering a čistenie dát. *(Osvojil si prácu s knižnicou Pandas, tvorbu agregačných funkcií a riešenie anomálií v reálnych senzorických dátach).*
* **Daniel Mucska:** Vývoj architektúry a API integrácia (Streamlit). *(Naučil sa budovať robustné dátové pipeline, parsovať komplexné JSON štruktúry a ošetrovať výpadky serverov).*

---

## 📊 1. Manažérske zhrnutie (Executive Summary)
Náš projekt predstavuje plne automatizovaný dataminingový dashboard, ktorý v reálnom čase integruje dáta z nezávislých API rozhraní. Nástroj spracováva historické aj aktuálne dáta o kvalite ovzdušia v Prahe a vizualizuje ich v 4D priestore (geolokácia + čas). Výstupom sú exaktné vedecké dôkazy o vplyve dopravy a prírodných faktorov na znečistenie, podané vo forme interaktívnych reportov pre top manažment mesta a urbanistov.

## 💼 2. Definícia problému a byznysový prínos
* **Definícia problému:** Mesto Praha čelí zníženej kvalite života obyvateľov kvôli smogovým situáciám. Chýba však centralizovaný nástroj, ktorý by na jedno kliknutie koreloval stav ovzdušia s dopravnými špičkami, poveternostnými podmienkami a mapou mestskej zelene.
* **Byznysový prínos:**
  1. **Optimalizácia dopravy:** Nástroj exaktne identifikuje kritické hodiny a úseky, čo umožňuje efektívnejšie riadenie dopravy (dynamické mýto, nízkoemisné zóny).
  2. **Real Estate a urbanizmus:** Potvrdenie "ochrannej funkcie" parkov poskytuje tvrdé dáta pri naceňovaní nehnuteľností v blízkosti zelene.
  3. **Zdravotníctvo:** Predikcia smogových cyklov umožňuje včasné varovanie rizikových skupín obyvateľstva.

## 🧬 3. Vstupné dáta a metodika (Data Fusion)
Projekt spája dáta z 3 nezávislých zdrojov pomocou metódy *Inner Join* cez časové a priestorové kľúče:
* **Golemio API (v2):** Primárny zdroj. Zber hodinových koncentrácií znečisťujúcich látok (NO2, PM10, PM2.5, O3) z oficiálnych IoT senzorov mesta.
* **Open-Meteo API:** Historické meteorologické dáta (rýchlosť vetra) priradené k časovým značkám senzorov.
* **Overpass API (OpenStreetMap):** Extrakcia priestorových polygónov mestskej zelene (najväčšie pražské parky).

**Pracovný postup čistenia (ETL):** Skript ošetruje chýbajúce hodnoty (`None`), odstraňuje anomálne záporné hodnoty senzorov, unifikuje názvoslovie analytov a extrahuje z ISO časových značiek nové premenné (`hour`, `day_name`) pre potreby agregácie.

## 🔬 4. Skúmané oblasti a metodika
Projekt opustil prístup statických "hypotéz" a využíva komplexné skúmanie problému od definície limitov až po riešenia:
1. **Zdravotné mantinely:** Kvantifikácia hodín, počas ktorých boli prekročené limity WHO pre zraniteľné skupiny (astmatici).
2. **Dopravná záťaž:** Identifikácia zdrojov smogu – analýza víkendového útlmu a ranných dopravných špičiek.
3. **Počasie:** Modelovanie vplyvu sily vetra na disperziu (rozptyl) jemných prachových častíc.
4. **Urbanizmus:** Geopriestorová analýza ochranného vplyvu mestskej zelene (parkov) voči znečisteniu z okolitých ulíc.

## 💡 5. Výsledky a závery
Všetky 4 definované hypotézy boli na základe dolovania dát úspešne **verifikované**:
* Dáta jednoznačne usvedčujú individuálnu automobilovú dopravu ako hlavného emitenta NO2 (signifikantný pokles cez víkendy a jasne identifikovateľné ranné špičky).
* Štatistická OLS regresia dokázala, že vietor čistí mesto od prachu (inverzná korelácia).
* Geopriestorové mapy potvrdili, že oblasti v bezprostrednom okolí mestských parkov fungujú ako ochranné zóny s najčistejším ovzduším v meste.

---

## 🛠️ Návod na spustenie projektu lokálne

Projekt vyžaduje nainštalovaný **Python 3.14+**.

**1. Klonovanie repozitára:**

git clone [https://github.com/MuDan96/Datamining-projekt.git](https://github.com/MuDan96/Datamining-projekt.git)
_cd Datamining-projekt_

**2. Inštalácia potrebných knižníc:**

Aplikácia využíva knižnice definované v súbore requirements.txt. Nainštalujete ich príkazom:

_pip install -r requirements.txt_

**3. Spustenie Streamlit servera:**

_streamlit run air_app.py_

_Následne sa automaticky otvorí prehliadač s bežiacim dashboardom na adrese http://localhost:8501._

### 3. Súbor: `requirements.txt`
*Ak by si ho náhodou na GitHube nemal aktuálny, musí obsahovať presne toto:*

```text
streamlit
pandas
plotly
requests
numpy
statsmodels
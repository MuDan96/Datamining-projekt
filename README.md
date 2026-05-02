# 🏥 Zdravotný a Urbanistický Audit Ovzdušia: Mesto Praha (Smart City Analytics)

Tento repozitár obsahuje zdrojové kódy a dokumentáciu k semestrálnemu projektu zameranému na dolovanie dát (datamining). Odklonili sme sa od čisto environmentálneho pohľadu a projekt sme preklopili do roviny **ochrany občianskych práv a verejného zdravia**.

Aplikácia je napísaná v jazyku **Python** s využitím frameworku **Streamlit**. K tomuto kroku sme pristúpili (namiesto využitia .Rmd) z dôvodu, že Streamlit nám umožňuje postaviť plnohodnotnú cloudovú dátovú aplikáciu (Policy Dashboard) s plynulým live napojením na REST API, čím lepšie simulujeme reálne nasadenie dátových produktov v praxi.

🌍 **Živá ukážka aplikácie (Live App): https://datamining-projekt2026.streamlit.app**

---

## 🤝 Metodika tímovej spolupráce a správa repozitára
*Na základe spätnej väzby k projektu transparentne deklarujeme náš postup spolupráce:*
Projekt sme nestavali ako sériu oddelených statických analýz, ale ako ucelený, navzájom previazaný softvérový produkt s interaktívnym GUI. Klasické merge-ovanie menších častí kódu od viacerých ľudí do jedného front-end súboru by spôsobovalo konflikty v užívateľskom prostredí. Preto sme zvolili agilný prístup **Pair-programmingu (spoločného kódovania) cez videohovory na MS Teams so zdieľaním obrazovky.** Všetka analytická a biznisová logika vzišla zo spoločných tímových diskusií, pričom jeden člen tímu (Daniel Mucska) zastával rolu *Release Managera* a z dôvodu udržania stability CI/CD pipeline pushoval spoločne schválený kód do tohto Git repozitára.

## 👥 Autorský tím a rozdelenie rolí
* **Timea Halászová:** Manažment projektu a definícia byznys/policy modelu. *(Zodpovednosť: Pretavenie technických dát do strategických a medicínskych argumentov pre Magistrát, definovanie ohrozenia občianskych práv).*
* **Zuzana Mitterová:** Metodika výskumu a vizualizácia dát (Plotly). *(Zodpovednosť: Aplikácia Data Storytellingu na demonštrovanie ohrozenia zdravia. Mapovanie meraní voči prísnym limitom WHO).*
* **Bojan Petric:** Data engineering a čistenie dát. *(Zodpovednosť: Práca s knižnicou Pandas, agregácie, fúzia meteorologických dát s environmentálnymi, stanovenie matematického výpočtu pre "Toxické hodiny").*
* **Daniel Mucska:** Vývoj architektúry a API integrácia (Streamlit). *(Zodpovednosť: Návrh cloudovej aplikácie, ošetrenie REST API requestov, Release management a správa repozitára).*

---

## 📊 1. Manažérske zhrnutie (Executive Summary)
Náš projekt predstavuje plne automatizovaný nástroj pre krízový manažment mesta. Nástroj historicky vyhodnocuje dáta z vládneho Golemio API, prepája ich s mestskou infraštruktúrou (parky) a meteorológiou. Výstupom sú exaktné dôkazy o tom, kedy sú obyvatelia (najmä astmatici a deti) obmedzovaní vo svojom voľnom pohybe kvôli toxicite. Aplikácia poskytuje Magistrátu priame argumenty na zavádzanie tvrdých regulácií.

## 💼 2. Definícia problému a prínos pre Magistrát
* **Definícia problému:** Mesto Praha čelí skrytej kríze verejného zdravia. Pre zraniteľné skupiny obyvateľstva predstavuje súčasný stav ovzdušia priame ohrozenie života a obmedzenie práva na voľný pohyb. Magistrátu chýbal nástroj, ktorý by exaktne identifikoval zdroje (autá vs. počasie) a priamo obhajoval investície do obranných mechanizmov (zeleň).
* **Byznysový / Politický prínos:**
  1. **Riadenie dopravy:** Poskytnutie dát (ranné špičky) na zavedenie dynamického mýta a zákazov vjazdu k školám.
  2. **Urbanizmus:** Dodanie vedeckých dôkazov, že parky fungujú ako fyzické filtre (bezpečné oázy), čím sa zabezpečí ich ochrana pred developerskou výstavbou.
  3. **Zdravotná prevencia:** Výpočet "Toxických hodín" umožňuje včasné SMS varovanie pre obyvateľstvo.

## 🧬 3. Vstupné dáta a metodika (Data Fusion)
Projekt spája dáta z 3 nezávislých zdrojov pomocou metódy *Inner Join* cez časové a priestorové kľúče:
* **Golemio API (v2):** Primárny zdroj. Zber hodinových koncentrácií všetkých zachytených toxínov (NO2, PM10, PM2.5, O3, SO2, CO, atď.) z IoT senzorov mesta.
* **Open-Meteo API:** Historické meteorologické dáta (rýchlosť vetra) pre modelovanie disperzie.
* **Overpass API (OpenStreetMap):** Extrakcia priestorových polygónov mestskej zelene.

**Dátové mantinely:** Namiesto benevolentných národných noriem aplikácia vyhodnocuje všetky dáta výlučne voči prísnym kritériám Svetovej zdravotníckej organizácie (WHO).

## 🔬 4. Štruktúra auditu (Oblasti skúmania)
1. **Priestorová toxicita:** Mapovanie (Heatmapy) preukazujúce, ktoré ulice sú v daný čas pre chorých ľudí nepriechodné.
2. **Medicínske profily:** Kvantifikácia zlyhaní mesta v ochrane zdravia (prekračovanie limitov WHO).
3. **Mobilita a Počasie:** Diagnostika príčin. Analýza víkendového útlmu, ranných dopravných špičiek a vplyvu sily vetra na odvetrávanie mesta.
4. **Urbanistická obrana:** Priestorové dôkazy o tom, že mestské parky znižujú dlhodobé priemery toxicity a slúžia ako záchranné zóny.

## 💡 5. Závery a Strategický plán
Dáta bezpečne preukázali systematické obmedzovanie práv zraniteľných obyvateľov (extrémy počas ranných špičiek, závislosť na vetre). Na základe týchto zistení obsahuje aplikácia **komplexný akčný plán**, ktorý odporúča 4 piliere zásahu:
1. Radikálna reorganizácia mestskej mobility (Školské ulice, dynamické mýto).
2. Zelená defenzíva (Stavebné uzávery na parky, izolačné bariéry pozdĺž radiál).
3. Krízový zdravotný systém (SMS varovania pri bezvetrí).
4. Vznik Fondu čistého ovzdušia.

---

## 🛠️ Návod na spustenie projektu lokálne

Aplikácia je primárne nasadená v cloude (Streamlit Community Cloud). Pre lokálne otestovanie hodnotiteľmi postupujte nasledovne (vyžaduje sa **Python 3.8+**):

**1. Klonovanie repozitára:**
```bash
git clone [https://github.com/MuDan96/Datamining-projekt.git](https://github.com/MuDan96/Datamining-projekt.git)
cd Datamining-projekt
2. Inštalácia potrebných knižníc:
Aplikácia využíva knižnice definované v súbore requirements.txt. Nainštalujete ich príkazom:

Bash
pip install -r requirements.txt
3. Spustenie vývojového servera:

Bash
streamlit run air_app.py
Následne sa automaticky otvorí prehliadač s bežiacim dashboardom na adrese http://localhost:8501.
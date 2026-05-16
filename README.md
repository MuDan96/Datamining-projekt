# 🫁 Zdravotný Audit Ovzdušia: Riziko pre pacientov s CHOPN v Prahe (Smart City Analytics)

Tento repozitár obsahuje zdrojové kódy a dokumentáciu k semestrálnemu projektu zameranému na dolovanie dát (datamining). Odklonili sme sa od čisto environmentálneho pohľadu a projekt sme preklopili do roviny **ochrany verejného zdravia špecifickej pacientskej skupiny trpiacej Chronickou obštrukčnou chorobou pľúc (CHOPN)**.

Aplikácia je napísaná v jazyku **Python** s využitím frameworku **Streamlit**. K tomuto kroku sme pristúpili (namiesto využitia .Rmd) z dôvodu, že Streamlit nám umožňuje postaviť plnohodnotnú cloudovú dátovú aplikáciu (Health-Tech Dashboard) s plynulým live napojením na REST API, čím lepšie simulujeme reálne nasadenie dátových produktov v praxi.

🌍 **Živá ukážka aplikácie (Live App): https://datamining-projekt2026.streamlit.app**

---

## 🤝 Metodika tímovej spolupráce a správa repozitára
*Na základe spätnej väzby k projektu transparentne deklarujeme náš postup spolupráce:*
Projekt sme nestavali ako sériu oddelených statických analýz, ale ako ucelený, navzájom previazaný softvérový produkt s interaktívnym GUI. Klasické merge-ovanie menších častí kódu od viacerých ľudí do jedného front-end súboru by spôsobovalo konflikty v užívateľskom prostredí. Preto sme zvolili agilný prístup **Pair-programmingu (spoločného kódovania) cez videohovory na MS Teams so zdieľaním obrazovky.** Všetka analytická a biznisová logika vzišla zo spoločných tímových diskusií, pričom jeden člen tímu (Daniel Mucska) zastával rolu *Release Managera* a z dôvodu udržania stability CI/CD pipeline pushoval spoločne schválený kód do tohto Git repozitára.

## 👥 Autorský tím a rozdelenie rolí
* **Timea Halászová:** Manažment projektu a definícia byznys/policy modelu. *(Zodpovednosť: Pivotovanie projektu na CHOPN, integrácia lekárskych faktov a štúdií ERS do dátovej argumentácie).*
* **Zuzana Mitterová:** Metodika výskumu a vizualizácia dát (Plotly). *(Zodpovednosť: Aplikácia Data Storytellingu na demonštrovanie dopadov na zdravie pacientov. Mapovanie meraní voči prísnym limitom WHO).*
* **Bojan Petric:** Data engineering a čistenie dát. *(Zodpovednosť: Práca s knižnicou Pandas, matematická deduplikácia pre stanovenie exaktného výpočtu "Toxických hodín", fúzia meteorologických dát s environmentálnymi).*
* **Daniel Mucska:** Vývoj architektúry a API integrácia (Streamlit). *(Zodpovednosť: Návrh cloudovej aplikácie, ošetrenie REST API výpadkov, Release management a správa repozitára).*

---

## 📊 1. Manažérske zhrnutie (Executive Summary)
Na základe výskumov *European Respiratory Society (ERS)* je dokázané, že znečistenie ovzdušia pôsobí na pacientov s CHOPN devastačne – spôsobuje akútne exacerbácie a zvyšuje úmrtnosť. Náš automatizovaný nástroj historicky vyhodnocuje dáta z vládneho Golemio API a prepája ich s mestskou infraštruktúrou. Výstupom je exaktná metrika ("Toxické hodiny"), ktorá Magistrátu ukazuje, kedy je tejto najzraniteľnejšej skupine obyvateľstva v Prahe odopreté základné právo na bezpečný pohyb.

## 💼 2. Definícia problému a prínos pre Magistrát
* **Definícia problému:** Odhaduje sa, že v Prahe žije až 80 000 obyvateľov ohrozených CHOPN (z toho 20 000 aktívne liečených). Mesto nemonitoruje ovzdušie primárne s ohľadom na tieto chronické respiračné ochorenia a chýbal nástroj, ktorý by ukázal, akou mierou doprava prispieva k zhoršovaniu ich stavu.
* **Byznysový / Politický prínos:**
  1. **Ochrana zdravia (Prevencia):** Výpočet preťaženia systému umožňuje včasnú aktiváciu varovných SMS systémov pre pacientov s CHOPN a prípravu pohotovostných príjmov.
  2. **Riadenie dopravy:** Dôkazy na bezprecedentné zavedenie dynamického mýta počas dopravných špičiek za účelom zníženia smrtiacich hodnôt NO2 a PM2.5.
  3. **Urbanizmus:** Dôkaz, že mestské parky fungujú ako fyzické filtre (bezpečné oázy), čím sa zamedzí ich developerskej likvidácii.

## 🧬 3. Vstupné dáta a metodika (Data Fusion)
Aplikácia čerpá limity toxicity zo Svetovej zdravotníckej organizácie (WHO) a interpretáciu stavia na vedeckých publikáciách *ERS*. Samotné dáta spája z 3 nezávislých API zdrojov pomocou metódy *Inner Join*:
* **Golemio API (v2):** Primárny zdroj. Zber hodinových koncentrácií všetkých zachytených toxínov (NO2, PM10, PM2.5, O3, SO2, CO, atď.) z IoT senzorov mesta.
* **Open-Meteo API:** Historické meteorologické dáta (rýchlosť vetra) pre modelovanie disperzie.
* **Overpass API (OpenStreetMap):** Extrakcia priestorových polygónov mestskej zelene.

## 🔬 4. Štruktúra auditu (Oblasti skúmania)
Aplikácia je rozdelená na Manažérsky prehľad, Záväzný Akčný plán a 4 hĺbkové analytické moduly:
1. **Priestorová toxicita:** Mapovanie (Heatmapy) preukazujúce, ktoré lokality predstavujú pre pacientov s CHOPN extrémne riziko.
2. **Klinické profily CHOPN:** Kvantifikácia zlyhaní mesta v ochrane zdravia (prekračovanie limitov WHO).
3. **Mobilita a Počasie:** Diagnostika príčin. Analýza víkendového útlmu, ranných dopravných špičiek a vplyvu sily vetra na odvetrávanie mesta.
4. **Záchranné parky:** Priestorové dôkazy o tom, že mestská zeleň znižuje dlhodobé priemery toxicity.

## 💡 5. Závery a Strategický plán
Dáta bezpečne preukázali systematické obmedzovanie práv pacientov s CHOPN (smrtiace ranné špičky usvedčujúce automobilovú dopravu). Na základe týchto zistení obsahuje aplikácia **komplexný akčný plán**, ktorý odporúča 3 piliere zásahu:
1. Radikálna reorganizácia dopravy (Školské ochranné zóny, dynamické mýto).
2. Zelená defenzíva a urbanizmus (Nedotknuteľnosť parkov, povinné zelené fasády).
3. Zdravotná prevencia (Systém včasného varovania cez VZP a dotácie na HEPA filtráciu).

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
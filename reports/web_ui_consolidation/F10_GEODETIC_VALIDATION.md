# F10 — Validazione geodetica del globo lunare

- **Data:** 2026-11-15
- **Inizio:** 07:47:59 CET · **Fine analisi:** 07:50:57 · **Report chiuso:** ~07:53 (orologio di sistema)
- **Budget:** 30 minuti. Lavoro concluso entro il budget.
- **Vincoli rispettati:** nessuna modifica a codice, dati, DEM, raster, SPICE/Horizons o algoritmi. Nessuna installazione, nessun commit. Tutti gli script di analisi sono in una scratchpad esterna al progetto (sola lettura del GLB e dei DEM).

## VERDETTO GLOBALE: **PARTIAL**

| Sito | Verdetto | Motivo sintetico |
|---|---|---|
| Shackleton | **PASS** alla risoluzione della mesh (~4 km) | Il marker cade a 3,6 km dal punto sorgente (in UV). Il rilievo della mesh correla con il DEM LOLA Site04 (r = 0,94) |
| Nobile | **PASS** alla risoluzione della mesh (~1–3 km) | Il marker cade a 0,7 km dal punto sorgente (in UV). Il rilievo correla con il DEM LOLA Site06 (r = 0,98), nessuno spostamento migliore |
| Connecting Ridge | **PARTIAL** | Il marker cade a 4,7 km dal punto sorgente (in UV). La correlazione con il DEM Site01 è più debole (r = 0,77) e sale a 0,93 con uno spostamento di circa 4,6 km: possibile offset, non risolvibile con questa mesh |

La catena *coordinate sorgente → UV → texture → rilievo della mesh → DEM LOLA (MOON_ME)* è coerente, e lo dimostrano dati indipendenti. La precisione si ferma però alla spaziatura dei vertici della mesh (~4–10 km al polo sud), cioè molto sotto la precisione delle coordinate sorgente (metri).

Restano non dimostrati tre punti:

- il frame dichiarato del GLB, che non ha metadati;
- la verifica del rendering con cattura nel browser;
- l'assenza di un offset di qualche km su Connecting Ridge.

È emersa anche una **discrepanza strutturale** della mesh, documentata nel §5. Non riguarda i marker attuali, ma rende **errata** qualunque proiezione lat/lon → xyz sferica su questo GLB.

---

## 1. Architettura dei sistemi di coordinate

| Livello | Sistema | Fonte / evidenza |
|---|---|---|
| Coordinate dei siti | Latitudine planetocentrica e longitudine est in gradi, derivate dai DEM LOLA PGDA (frame MOON_ME, DE421) | `src/astronomy.py:24-30` (`SITES`, NASA Lunar Surface Data Book 2025-03-18, Tab. A2.1-1); README LOLA |
| Trasporto al frontend | `GET /api/sites` → `{name, latitude_deg, longitude_east_deg}` senza trasformazioni | `src/ui_web/app.py:364-367`; `main.js:276` (mappa su `{lat, lon}`) |
| DEM locali | Stereografica polare sud, `+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737400`, metri, MOON_ME | Header CRS dei TIFF `official-lola/Site0{1,4,6}_final_adj_5mpp_surf.tif` |
| Texture | Equirettangolare 8192 × 4096 JPEG `Moon_8k_Color_v001`, incorporata nel GLB | `images[0]` del GLB |
| Mesh GLB | Unico nodo `Sphere` **senza trasformazione** (no matrix/TRS), 2 021 340 vertici, POSITION/NORMAL/TEXCOORD_0. Raggio 0,9653–1,0003 unità (media 0,9828). Generatore Blender glTF I/O 4.3.47. Nessun metadato di frame o datum | Parsing diretto del chunk JSON del GLB |
| Scena Three.js | Y in alto, destrorso. `moon.scale = 4,5/extent` (2,26459), `moon.position = −center·scale` (centratura sul bounding box). `root` senza trasformazioni. Nessuna rotazione del modello nel render loop: l'autorotazione muove la camera | `main.js:163-170`, `56-57`, `259-266` |
| Marker | Ricerca del vertice la cui UV, letta come `lat = 90 − 180·v` e `lon = 360·u − 180`, è più vicina (minima distanza angolare) al sito. Il marker usa la posizione mondo di quel vertice; normale = `position.normalize()` | `ui/globe-markers.js:21-39` |

**Convenzione effettiva della mesh**, ricavata dai dati: la longitudine della UV coincide con `atan2(−z, x)` del vertice (mediana 0,000°, p99 0,24°).

Ne segue:

- lon 0° → +X;
- lon 90° E → −Z;
- nord → +Y.

È una terna destrorsa con longitudine est positiva, coerente con un frame body-fixed lunare mappato in Y-up. Le alternative (specchiate o ruotate di 90°/180°) sono escluse: residui p99 ≥ 177°, oppure mediana di ±90°.

## 2. Metodo di validazione

Gli script sono nella scratchpad di sessione: `glb.py`, `analyze.py`, `analyze2.py`, `dem.py`, `offset.py`. Usano solo numpy, Pillow e rasterio già presenti.

1. **Estrazione** di POSITION, UV e texture dal GLB, con parsing binario diretto.
2. **Replica esatta di `locateOnModel()`** in Python, per ottenere il vertice scelto, la sua UV, la distanza angolare dal sito e la posizione mondo con la trasformazione di `main.js`.
3. **Coerenza UV ↔ geometria.** Per ogni vertice si confronta la lat/lon letta dalla UV con la lat/lon ricavata dalla direzione geometrica del vertice dal centro del modello.
4. **Convenzione della texture.** Si campiona la luminosità della texture, con la formula UV del codice, su formazioni note e sui loro punti speculari:
   - specchio est/ovest (lon → −lon);
   - specchio nord/sud (lat → −lat).

   Le coordinate delle formazioni sono valori approssimativi noti (±1°) e non vengono dal repository. Il test discrimina solo l'orientamento, non la precisione.
5. **Confronto con il DEM (prova indipendente).** I vertici con lat < −80° vengono proiettati nella stereografica polare dei DEM LOLA:

   - con la lat/lon da UV;
   - con la lat/lon geometrica.

   Per ciascuno si campiona la quota del DEM e se ne calcola la correlazione con il raggio del vertice. Se il rilievo della mesh è registrato sulla geografia, la correlazione deve essere alta.
6. **Stima dell'offset di registrazione.** Si cerca su una griglia lo spostamento (±6 km, passo 500 m) che massimizza la correlazione.

**Distinzione richiesta dal brief:**

- **Validazione geodetica:** i passi 2 e 5–6. Si confronta con il DEM nel frame MOON_ME, cioè con un riferimento indipendente dalla texture.
- **Coerenza visiva:** il passo 4 e la verifica F9 `northIsUp()`. Dicono solo che la texture è orientata secondo la convenzione assunta.
- **Corrispondenza con il DEM:** il passo 5. Riguarda il rilievo geometrico della mesh, non la texture a colori.

## 3. Risultati per ciascun sito

### 3.1 Tabella delle coordinate

| Grandezza | Shackleton | Connecting Ridge | Nobile |
|---|---|---|---|
| Sorgente (lat, lon E) | −89,7668°, −171,8700° | −89,4632°, −137,4900° | −85,4381°, 37,36667° |
| Indice del vertice scelto | 219790 | 1614255 | 216489 |
| UV del vertice | (0,016113; 0,998047) | (0,109375; 0,996174) | (0,603028; 0,974609) |
| Lat/lon da UV | −89,6484°, −174,1992° | −89,3113°, −140,6250° | −85,4297°, 37,0899° |
| **Scarto marker ↔ sorgente (UV)** | **0,1189° = 3,61 km** | **0,1555° = 4,71 km** | **0,0236° = 0,72 km** |
| Posizione locale del GLB | (−0,011775; −0,993079; 0,002342) | (−0,016880; −0,992474; 0,013853) | (0,085888; −0,993609; −0,057389) |
| **Posizione mondo (Three.js)** | (−0,018120; −2,245228; −0,003351) | (−0,029682; −2,243857; 0,022717) | (0,203046; −2,246428; −0,138616) |
| Lat/lon geometrica del vertice | −89,3074°, −168,7500° | −88,7395°, −140,6250° | −84,0648°, 33,7500° |
| Scarto geometrico vertice ↔ sorgente | 0,4599° = 13,95 km | 0,7251° = 21,99 km | 1,4119° = 42,81 km |
| Correlazione rilievo ↔ DEM (UV) | 0,938 (Site04, n = 68) | 0,766 (Site01, n = 56) | 0,979 (Site06, n = 120) |
| Correlazione rilievo ↔ DEM (geometria) | n.d. (32 vertici del polo con raggio identico) | −0,120 (n = 16) | −0,086 (n = 76) |
| Spostamento a correlazione massima | dx −1,5 km, dy +0,5 km (r 0,979) | dx +1,0 km, dy +4,5 km (r 0,932) | dx 0, dy +0,5 km (r 0,980) |
| Verdetto | PASS (~4 km) | PARTIAL | PASS (~1–3 km) |

**Note:**

- km calcolati su R = 1737,4 km.
- Trasformazione dal locale del GLB al mondo: `(P − c)·s`, con c = (−0,003773; −0,001628; 0,003822) e s = 2,264587.
- La lat/lon geometrica è `asin(y/r)`, `atan2(−z, x)` rispetto all'origine locale del GLB.

### 3.2 Commento per sito

- **Shackleton.**
  - I vertici della mesh vicino al polo stanno su anelli di latitudine UV −90°, −89,648°, −89,311°…, quindi passo ≈ 0,34° ≈ 10 km. Il vertice più vicino è a 3,6 km (4 candidati equidistanti): è il limite di quantizzazione, non un errore di convenzione.
  - Il rilievo nell'area Site04 correla a 0,94 con il DEM LOLA.
  - Lo spostamento ottimale (−1,5; +0,5 km) è dentro la spaziatura dei vertici. La regione con correlazione entro 0,02 dal massimo copre dx −3…0 km e dy −2…+3,5 km.
- **Connecting Ridge.**
  - Scarto di quantizzazione: 4,7 km.
  - Correlazione con Site01 a spostamento zero: 0,77, la più bassa dei tre. Con circa +1/+4,5 km sale a 0,93. Può essere un offset reale di qualche km tra mesh e DEM in quest'area, oppure un artefatto: pochi vertici (52–56) e un campione che cambia con lo spostamento ai bordi del DEM da 16 km.
  - Con i dati disponibili **non si può decidere**. Shackleton e Connecting Ridge distano circa 11 km, quindi un offset di 4–5 km è una frazione rilevante della loro separazione.
- **Nobile.**
  - È il caso migliore: a −85,4° i vertici sono più fitti (scarto 0,7 km).
  - La correlazione 0,98 con Site06 è già massima a spostamento zero (l'ottimo è a +0,5 km, irrilevante).

### 3.3 Posizione visiva

- Il marker è un pulsante DOM collocato con `Vector3.project(camera)` della posizione mondo del vertice (`globe-markers.js:94-101`), quindi coincide per costruzione con il punto della mesh.
- Il modello non viene ruotato a runtime, perciò le posizioni mondo calcolate una volta restano valide.
- **In questa fase non è stata fatta una cattura nel browser.** La posizione visiva è verificata analiticamente, non con un'immagine. F9 riporta, come osservazione visiva, che Shackleton e Connecting Ridge cadono nel punto di convergenza polare.

### 3.4 Texture (coerenza visiva, non geodetica)

Luminosità media 0–255 sulla texture con la formula UV del codice (media globale 122):

| Punto | Atteso | Valore | Specchio | Valore |
|---|---|---|---|---|
| Mare Moscoviense (27,3; 147,9) | scuro | 43,9 | lon → −147,9 | 179,0 (altopiano) |
| Mare Moscoviense | scuro | 43,9 | lat → −27,3 | 102,0 |
| Mare Humorum (−24,4; −38,6) | scuro | 27,8 | lon → +38,6 | 94,8 |
| Mare Orientale (−19,4; −92,8) | scuro | 58,0 | lon → +92,8 | 108,8 |
| Tycho (−43,3; −11,4) | chiaro | 200,4 | lon → +11,4 | 124,0 |
| Crisium, Serenitatis, Imbrium | scuri | 35–39 | — | — |

Ne segue:

- la texture è equirettangolare, con lon 0° al centro, est positivo verso destra e nord in alto;
- le ipotesi del codice sono confermate;
- nessuna specchiatura e nessuno sfasamento di 180°, con risoluzione ≈ 1°.

## 4. Corrispondenza con il DEM: cosa dimostra

Il rilievo della mesh (raggio dei vertici) è registrato **nello spazio UV**, non nello spazio geometrico:

- correlazione con la lat/lon da UV: 0,77 / 0,94 / 0,98;
- correlazione con la lat/lon geometrica: −0,12 / n.d. / −0,09.

I DEM LOLA sono un riferimento indipendente in MOON_ME. Quindi le UV della mesh sono geodeticamente registrate sul frame dei DEM con un errore di pochi km, ed è questa la prova che i marker basati su UV sono corretti.

**Esagerazione verticale stimata:** la pendenza raggio/quota vale 0,00151–0,00183 unità/km, contro 0,000566 unità/km attese (1 km su 1737,4 km, con raggio medio 0,9828). Il rilievo è quindi esagerato di **circa 2,7–3,2 volte**, una stima dalla regressione. Non incide sulla posizione orizzontale dei marker, ma il globo non va letto come altimetria in scala reale.

## 5. Discrepanze rilevate (documentate, non corrette)

1. **D1 — La geometria della mesh non è una sfera parametrizzata dalla lat/lon.**
   - La direzione geometrica dei vertici differisce dalla geografia (UV, registrata sul DEM):
     - mediana 4–5 km a medie latitudini;
     - fino a **47 km** a 85–88° di latitudine.
   - Lo scarto è soprattutto in latitudine: i vertici risultano spostati verso l'equatore di circa 0,9° vicino ai poli.
   - **Impatto attuale: nessuno sui marker**, che usano le UV.
   - **Impatto potenziale:** qualunque funzione che converta lat/lon in xyz con la formula sferica (`setFromSphericalCoords`, `cos·cos`, ecc.) sbaglierebbe di 14–43 km sui tre siti. Lo stesso vale per una direzione del Sole o della Terra posta nel frame del modello assumendo lat/lon = direzione: errore fino a ~1,4° vicino al polo.
2. **D2 — Quantizzazione dei marker.**
   - Il marker si aggancia al vertice e non interpola nel triangolo: errore 0,7–4,7 km.
   - Il `aria-label` mostra le coordinate sorgente, non quelle del punto renderizzato. È corretto come dato, ma il punto visivo non ha quella precisione.
3. **D3 — Connecting Ridge.** Possibile offset di registrazione di ~4–5 km rispetto a Site01 (§3.2), non confermato.
4. **D4 — Centratura sul bounding box.**
   - `main.js` centra sul bounding box (c ≈ 0,0038 unità ≈ 6–7 km per asse), non sull'origine del modello. Le direzioni `normal` dei marker e la camera di `focusSite()` sono quindi riferite a un centro spostato di ~10 km.
   - Effetto trascurabile sulla visibilità e sul volo della camera. Diventa rilevante solo se si usano quelle direzioni come direzioni geografiche.
5. **D5 — Rilievo esagerato di circa 3 volte** (§4): il punto del marker è sulla superficie esagerata.
6. **D6 — Fragilità latente.** Le posizioni mondo dei marker sono calcolate una sola volta. Se in futuro il modello venisse ruotato (per esempio per orientare la luce), i marker non seguirebbero. Oggi non accade.

## 6. Limiti dei dati disponibili

- Il GLB non ha metadati di frame, datum o versione della texture. La texture (`Moon_8k_Color_v001`, probabilmente NASA CGI Moon Kit) e il rilievo non dichiarano se sono in MOON_ME o MOON_PA. La differenza ME/PA (~0,9 km in superficie) è sotto la risoluzione della mesh e quindi non è determinabile qui.
- Non c'è un DEM globale o polare a media risoluzione nel repository. I confronti usano solo tre DEM LOLA da 16 × 16 km (5 m/pixel), che contengono 52–128 vertici della mesh ciascuno. Le correlazioni sono robuste per Site04 e Site06, meno per Site01.
- Al polo i vertici distano ~10 km in latitudine. **Nessuna precisione sotto ~1–5 km è verificabile** con questa mesh.
- Coordinate delle formazioni usate nel §3.4: valori noti approssimativi (±1°), non presi dal repository. Servono solo a verificare l'orientamento.
- Nessuna cattura nel browser in questa fase (§3.3).
- La texture a colori non è stata confrontata direttamente con il DEM, per esempio con hillshade o pattern di crateri. Il confronto riguarda il rilievo, che usa le stesse UV della texture.

## 7. Correzioni raccomandate (non applicate, richiedono autorizzazione)

1. **Mantenere** il posizionamento via UV ed evitare qualunque conversione lat/lon → xyz sferica su questo GLB (D1). Se servono direzioni geografiche (Sole, Terra, percorsi), ricavarle dal punto della mesh trovato via UV, oppure documentare l'errore ≤ 47 km.
2. Interpolare dentro il triangolo (coordinate baricentriche sulle UV) invece di agganciarsi al vertice: lo scarto di quantizzazione scende sotto il km (D2).
3. Verificare Connecting Ridge con un DEM più ampio (per esempio il mosaico LOLA polare da 20–60 m/pixel PGDA) o con una mesh più fitta (D3).
4. Aggiungere un test automatico che replichi il §4 (correlazione rilievo ↔ DEM ≥ soglia sui tre siti) come regressione di registrazione.
5. Documentare in UI o nei documenti l'esagerazione verticale di circa 3 volte e il limite di precisione dei marker (~5 km).
6. Se il modello verrà ruotato in futuro, ricalcolare le posizioni dei marker nel loop oppure agganciarli come figli del modello (D6).
7. Fare una cattura headless del polo con i tre marker per chiudere la verifica visiva.

## 8. Tempo impiegato

| Fase | Orario (CET) |
|---|---|
| Inizio | 07:47:59 |
| Lettura di F9 e del codice | 07:48–07:49 |
| Parsing del GLB, analisi UV, geometria e texture | 07:49–07:50 |
| Confronto con il DEM e stima dell'offset | 07:50:23–07:50:48 |
| Fine analisi | 07:50:57 |
| Report | ~07:53 |

Durata secondo l'orologio di sistema: **circa 5 minuti** su 30 disponibili.

---

Il lavoro si ferma qui. Nessuna correzione è stata applicata: serve un'autorizzazione esplicita per qualunque passo successivo.

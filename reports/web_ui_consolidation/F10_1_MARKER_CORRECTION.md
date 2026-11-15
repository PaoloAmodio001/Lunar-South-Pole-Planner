# F10.1 — Correzione e validazione dei marker lunari

- **Data:** 2026-11-15
- **Inizio:** 07:54:42 CET · **Fine verifiche:** 08:01:36 · **Report chiuso:** ~08:05
- **Durata:** circa 11 minuti su 30
- **Riferimento:** `F10_GEODETIC_VALIDATION.md`
- **Skill:** `frontend-design:frontend-design` non usata, perché non ci sono modifiche visive: lo stile dei marker è invariato.

## VERDETTO: **PARTIAL**

| Sito | Metodo | Scarto marker ↔ texture | Prima (vertice F9) | Verdetto |
|---|---|---|---|---|
| Nobile | `barycentric` (dentro il triangolo) | **0,000 km** | 0,715 km | **PASS** |
| Shackleton | `barycentric-closest` | **0,295 km** | 3,607 km | **PASS** sulla texture; registrazione sul DEM a pochi km (evidenza F10) |
| Connecting Ridge | `barycentric-closest` | **0,814 km** | 4,714 km | **PARTIAL**: scarto sulla texture ridotto di 5,8 volte, registrazione sul DEM ancora incerta (0–3 km) |

La correzione funziona: l'errore di quantizzazione (F10 D2) scende di 6–12 volte sui siti polari e si annulla su Nobile.

Il verdetto resta **PARTIAL** per due motivi, che i dati non permettono di chiudere:

- con i soli DEM presenti non si può escludere un offset di registrazione di 0–3 km su Connecting Ridge;
- una nuova scoperta (§3.1): vicino al polo la mappa UV della mesh **non copre** la posizione di Shackleton e di Connecting Ridge. Quei punti della texture non sono mostrati da nessun triangolo.

---

## 1. Backup

`backups/F10_1_markers_20261115-075446/` con `SHA256SUMS`:

| File | SHA-256 prima della modifica |
|---|---|
| `globe-markers.js` | `9f35c296…a55482c2` (originale F9) |
| `main.js` | `deb3839b…5482c2c` (non modificato in F10.1) |
| `test_web_ui_static_assets.py` | `8a02c3c1…57ad` (non modificato in F10.1) |

**Rollback:** `cp backups/F10_1_markers_20261115-075446/globe-markers.js src/ui_web/ui/globe-markers.js`, poi rimuovere `tests/test_globe_marker_geodesy.py` e `tests/js/globe_markers_geodesy.mjs`.

## 2. File modificati

| File | Tipo | Contenuto |
|---|---|---|
| `src/ui_web/ui/globe-markers.js` | modificato (SHA-256 nuovo `27500ea4…cd16`) | Aggiunge `latLonToUv`, `closestBarycentric`, `findUvTriangle`; riscrive `locateOnModel`; `data-method` sul pulsante del marker. API compatibile: `{position, separationDeg}` più `method`, `nearestVertexSeparationDeg`, `triangle`, `lambda`. Marker, proiezione, selezione e `northIsUp` invariati |
| `tests/test_globe_marker_geodesy.py` | nuovo | 16 test (§5) |
| `tests/js/globe_markers_geodesy.mjs` | nuovo | Esegue il modulo reale in Node sul GLB reale, in sola lettura |

**Non modificati:**

- `main.js`, `index.html`, CSS;
- GLB, DEM, raster, SPICE, Horizons, `src/*.py`, dati.

## 3. Metodo matematico

### 3.1 Analisi della mappa UV (nuova evidenza)

La texture è equirettangolare: `u = (lon + 180)/360`, `v = (90 − lat)/180` (F10 §1, §3.4). La GPU campiona la texture interpolando linearmente le UV sul triangolo. Quindi il punto della mesh che **mostra** la lat/lon (φ, λ) è quello le cui UV interpolate valgono (u₀, v₀).

L'analisi dei triangoli del GLB mostra però che:

- l'area UV totale coperta dai triangoli è **0,9375** su 1;
- vicino al polo sud la copertura crolla. Per v ≥ 0,99 (lat < −88,2°) l'area coperta è 0,00062 contro 0,01 attesi, cioè il 6 %. Per v ≥ 0,998 (lat < −89,64°) è lo 0,75 %;
- i triangoli della calotta sono "spicchi" stretti in UV che convergono verso il polo;
- in campionamenti fissi sull'area dei DEM, la frazione di punti coperta da un triangolo UV è:

  | DEM | Copertura |
  |---|---|
  | Site01 (Connecting Ridge) | 34/676 (5 %) |
  | Site04 (Shackleton) | 16/676 (2,4 %) |
  | Site06 (Nobile) | 360/676 (53 %) |

**Conseguenza:**

- Shackleton (v₀ = 0,99870) e Connecting Ridge (v₀ = 0,99702) cadono in zone UV **non coperte**. Nessun punto della mesh mostra esattamente quella parte della texture. Al polo la texture visualizzata è un mosaico di spicchi, non una mappa continua.
- Nobile cade dentro un triangolo.

### 3.2 Algoritmo (`findUvTriangle` + `locateOnModel`)

1. **Contenimento.** Per ogni triangolo (a, b, c) si calcolano le coordinate baricentriche di (u₀, v₀) in UV:

   λa = [(vb − vc)(u₀ − uc) + (uc − ub)(v₀ − vc)] / det, λb analoga, λc = 1 − λa − λb, con det = (vb − vc)(ua − uc) + (uc − ub)(va − vc).

   Se min λ ≥ −10⁻⁹, il marker va in **P = λa·Pa + λb·Pb + λc·Pc**. Per costruzione UV(P) = (u₀, v₀), quindi lo scarto è nullo. Su più triangoli validi si sceglie quello con min λ massimo. Metodo: `barycentric`.
2. **Zona non coperta.** Se nessun triangolo contiene il punto, per ogni triangolo si calcola il punto più vicino a (u₀, v₀) sul triangolo, chiusura compresa (Ericson, *Real-Time Collision Detection* §5.1.5). La metrica è quella equirettangolare locale del sito, isotropa in km:
   - Δx = wrap(Δu)·360·cos φ;
   - Δy = Δv·180;
   - wrap riconduce Δu in [−0,5; 0,5] per la cucitura.

   Il risultato è il **punto visualizzato più vicino** alla lat/lon richiesta. Il marker va in P = Σλ·P con le λ di quel punto. Metodo: `barycentric-closest`.
3. **Garanzia di non peggioramento.** Si calcola sempre anche il vertice più vicino (metodo F9). Se lo scarto angolare esatto del punto baricentrico supera quello del vertice, si usa il vertice (`nearest-vertex`). Non è mai accaduto sui tre siti.
4. **Nessuna conversione sferica** lat/lon → XYZ: la posizione è sempre una combinazione convessa di vertici reali della mesh, trasformata con `matrixWorld` come in F9. Un test lo verifica.

**Giustificazione:**

- Il passo 1 è esatto: è la stessa interpolazione lineare usata dal rasterizzatore per la texture.
- Il passo 2 è un'approssimazione dichiarata. Minimizza la distanza nella metrica locale, mentre lo scarto riportato è la distanza angolare esatta. Un controllo a forza bruta (41 × 41 campioni su 200 triangoli candidati) dà 0,322 km contro 0,295 km per Shackleton e 0,814 contro 0,814 km per Connecting Ridge. Non è stato trovato un punto migliore.

**Costo:** circa 150 ms per sito su 1,01 M triangoli (Node), eseguito una sola volta al caricamento.

## 4. Risultati per sito

Coordinate sorgente: solo `src.astronomy.SITES` (via `/api/sites`). km su R = 1737,4 km.

| Grandezza | Shackleton | Connecting Ridge | Nobile |
|---|---|---|---|
| Sorgente (lat, lon E) | −89,7668°, −171,87° | −89,4632°, −137,49° | −85,4381°, 37,36667° |
| (u₀, v₀) | (0,022583; 0,998704) | (0,118083; 0,997018) | (0,603796; 0,974656) |
| Triangolo | 761192 | 653674 | 135720 |
| λ | (0,3366; 0,6634; 0) | (0,4728; 0,5272; 0) | (0,0232; 0,5019; 0,4749) |
| Posizione locale GLB | (−0,007811; −0,992692; 0,001554) | (−0,013003; −0,991507; 0,013003) | (0,083656; −0,993894; −0,057030) |
| Distanza dal piano del triangolo | 1,1·10⁻¹⁶ | 1,1·10⁻¹⁶ | 1,1·10⁻¹⁶ |
| **Scarto sulla texture (F10.1)** | **0,295 km** | **0,814 km** | **0,000 km** |
| Scarto con il vertice più vicino (F9) | 3,607 km | 4,714 km | 0,715 km |
| Riduzione | ×12,2 | ×5,8 | → 0 |

Posizione mondo: `(P − c)·s`, con c = (−0,003773; −0,001628; 0,003822) e s = 2,264587 (F10 §3.1).

Ne segue:

- per Nobile, lo scarto nullo indica che il marker è nel punto esatto della texture;
- per Shackleton e Connecting Ridge, lo scarto residuo è la distanza fra il sito e la parte di texture effettivamente mostrata, ed è il minimo ottenibile su questa mesh senza modificarla.

### 4.1 Verifica di Connecting Ridge con i DEM esistenti

Lo script è `demtri.py`, archiviato insieme alle catture. Dal `README` LOLA, Site01 è "Connecting ridge" (vedi `SITE_IDENTITY_VALIDATION_REPORT.md`). È l'unico DEM che contiene il sito: `NAC_DTM_ESALL_SR12` non lo contiene.

**Correzione del metodo F10.** In F10 l'insieme dei vertici cambiava con lo spostamento (artefatto dichiarato). Ora il campione è **fisso**:

- 26 × 26 punti del DEM ogni 500 m, a 1,5 km dai bordi;
- la superficie della mesh è interpolata in modo baricentrico in UV, come i marker;
- si cerca lo spostamento (±6 km, passo 1 km) che massimizza la correlazione tra quota DEM e raggio della mesh.

| DEM | Copertura UV | r a spostamento 0 | r massimo (spostamento) | Spostamenti entro 0,02 dal massimo |
|---|---|---|---|---|
| Site01 – Connecting Ridge (raw / media mobile 2 km) | 33/676 | 0,699 / 0,695 | 0,773 / 0,792 (dx 0, dy +3 km) | dx −1…0, dy +1…+4 km |
| Site04 – Shackleton | 0/676 a spostamento 0 | n.d. | 0,924 (dx −2, dy +2 km) | dx −3…−2, dy +2 km |
| Site06 – Nobile | 185/676 | 0,891 / 0,902 | 0,954 / 0,960 (dx 0, dy +2 km) | dx −2…+1, dy −1…+5 km |

**Interpretazione:**

- Per tutti e tre i DEM il massimo cade su dy ≈ +2/+3 km. È **compatibile** con un piccolo offset sistematico della mesh rispetto a MOON_ME vicino al polo, ma i campioni sono pochi e concentrati sugli spicchi UV coperti (5 % in Site01). La finestra di ottimo è ampia: fino a 6 km in dy.
- **Non è dimostrato** né un offset né la sua assenza.
- Per Connecting Ridge la registrazione resta tra 0 e ~3 km, con correlazione massima moderata (0,77–0,79). Quindi **PARTIAL**, come prescrive il brief.
- Per Shackleton vale l'evidenza F10 sui vertici (r = 0,94 a spostamento zero, n = 68). Il campionamento interpolato a spostamento zero non ha punti coperti dentro l'area interna di Site04.

## 5. Test

| Suite | Esito |
|---|---|
| `tests/test_globe_marker_geodesy.py` (nuova) | **16 passed** (0,7 s) |
| Suite completa `python -m pytest -q` | **448 passed**, 0 failed, 7262 warning (le stesse deprecazioni della baseline), 92,8 s. Erano 432 in F9: +16 nuovi |

I nuovi test girano su `node`, sul modulo reale e sul GLB reale. Python verifica i risultati in modo indipendente, rileggendo il GLB con numpy:

- il nodo GLB non ha trasformazioni;
- tutti i siti usano un metodo baricentrico;
- P coincide con Σλ·P dei vertici del triangolo (tolleranza 10⁻⁶), con λ ≥ 0 e somma 1;
- l'UV interpolata, ricalcolata in Python, coincide con lo scarto dichiarato dal JS (10⁻⁶ gradi) e resta sotto 1 km. È un limite di regressione sui valori misurati, non una precisione geodetica;
- Nobile è dentro il triangolo (scarto < 1 m);
- lo scarto non supera mai quello del vertice più vicino; sui siti polari è almeno 4 volte minore;
- i marker stanno nell'emisfero sud (+Y = nord);
- nel modulo non ci sono conversioni sferiche (`setFromSpherical*`, `Spherical(`).

I test vengono saltati (`skip`) se mancano node, il GLB o `node_modules/three`.

**Nota tecnica.** `src/ui_web/package.json` dichiara `"type": "commonjs"`. Il runner importa quindi il modulo ES del browser come `data:` URL, sostituendo solo lo specificatore `'three'` con il file locale di three. Nel browser lo risolve l'importmap.

## 6. Catture e verifica nel browser

Cartella fuori dal progetto: `~/Lunar-South-Pole-Planner_backups/F10_1_marker_screens_20261115-075938/`

- Chrome 157 headless con SwiftShader, profilo Pianificatore, 1440 × 900.
- `prefers-reduced-motion: reduce`, così la rotazione automatica non sposta le catture.
- Script: `markers_capture.mjs` (CDP, nessuna dipendenza). Esiti in `markers_capture.json`. Hash in `SHA256SUMS_screenshots.txt`.

| Cattura | Esito |
|---|---|
| `f10_1_initial_polar.png` | Modello `LOADED`; 3/3 marker visibili; `data-method` = barycentric-closest, barycentric-closest, barycentric; Shackleton `aria-pressed=true` |
| `f10_1_select_Nobile.png` | Click sul marker → `#site` = Nobile, scheda "Nobile −85,44°, 37,37°", solo Nobile premuto |
| `f10_1_select_Connecting_Ridge.png` | Click → `#site` = Connecting Ridge, scheda aggiornata, marker premuto |
| `f10_1_select_Shackleton.png` | Click → `#site` = Shackleton, scheda "−89,77°, −171,87°", marker premuto |
| `f10_1_select_via_dropdown_Nobile.png` | `select` → `change` → marker Nobile premuto |
| Console | **0 errori, 0 avvisi, 0 eccezioni** |

**Coerenza visiva:**

- I tre marker cadono nell'area polare sud della texture.
- Connecting Ridge e Shackleton sono a pochi pixel l'uno dall'altro: a questa scala 11 km valgono circa 1–4 px. Il raggruppamento delle etichette nasconde quella non selezionata, come previsto.
- Nobile cade a circa 30 px verso il bordo visibile, coerente con i ~130 km dal polo in vista obliqua.

**Limiti:** la cattura non può distinguere scarti sotto il km. La verifica di coerenza con la texture a quella scala è quella numerica del §4.

## 7. Esagerazione verticale del modello (documentazione)

| Metodo | Stima |
|---|---|
| F10: regressione raggio del vertice ↔ quota DEM, sui vertici dentro i DEM | 2,7–3,2× |
| F10.1: regressione con la superficie interpolata, campione fisso, spostamento 0 | 1,7–2,1× (Site01 1,69–1,78; Site04 2,02–2,05 con spostamento; Site06 2,06–2,14) |
| Intervallo globale dei raggi della mesh: 0,9653–1,0003, cioè 3,56 % del raggio medio | Indicativo: circa 3× se confrontato con l'escursione altimetrica lunare globale nota (~20 km, ≈1,15 %). Valore di letteratura approssimato, non presente nel repository |

**Conclusione.** Il rilievo del GLB è **esagerato verticalmente**. Il fattore non è determinabile con precisione dai dati disponibili e cade tra **~1,7× e ~3,2×** a seconda del metodo:

- la regressione locale sottostima, perché la mesh filtra il rilievo sotto i ~5 km e la copertura UV al polo è scarsa;
- il confronto globale non è dimostrato con dati del repository.

Il GLB non dichiara il fattore nei metadati. Implicazioni:

- i marker poggiano sulla superficie esagerata;
- il globo non va usato per misure altimetriche;
- l'esagerazione non influisce sulla posizione orizzontale.

## 8. Integrità scientifica

- **164/164 hash scientifici invariati** (`sha256sum -c` sulla lista F9 `sci_hashes_impl.txt`; output in `sci_hashes_check.txt`).
- GLB, DEM, raster, SPICE, Horizons, `src/*.py` e dati non modificati.
- `main.js` è identico al backup.
- Nessuna dipendenza installata: numpy, rasterio, matplotlib, node e Chrome erano già presenti. Nessun commit o push.

## 9. Limiti

1. **La mappa UV non copre il polo** (§3.1). Per Shackleton e Connecting Ridge il marker indica il punto *visualizzato* più vicino (0,30 e 0,81 km). Lo scarto zero è impossibile senza modificare il GLB, cosa vietata.
2. **Registrazione geodetica di Connecting Ridge non conclusa:** possibile offset di 0–3 km, con pochi campioni coperti (5 %).
3. Un offset sistematico di circa dy +2/+3 km è suggerito da tutti e tre i DEM, ma non dimostrato.
4. La metrica del passo 2 è locale ed equirettangolare. A forza bruta lo scarto non migliora, ma non è una minimizzazione geodetica esatta.
5. Il fattore di esagerazione verticale non è determinato con precisione (1,7–3,2×).
6. La cattura nel browser usa SwiftShader con una sola risoluzione (1440 × 900).
7. Il frame del GLB (MOON_ME o MOON_PA, differenza ~0,9 km) resta non determinabile (F10 §6).

## 10. Tempo

| Fase | Orario |
|---|---|
| Inizio, backup | 07:54:42 – 07:54:46 |
| Prima implementazione (solo contenimento) e prova su GLB | → 07:55:56 |
| Scoperta delle zone UV non coperte, analisi e algoritmo closest-point | → 07:57:28 |
| Verifica sui DEM (campione fisso) | → 07:58:33 |
| Test automatici | → 07:59:16 |
| Suite completa (background), cattura nel browser | → 08:01:08 |
| Hash, chiusura dei processi | 08:01:36 |
| Report | ~08:05 |

**Totale circa 11 minuti su 30.**

---

Il lavoro si ferma qui. Nessun'altra attività avviata: serve una nuova autorizzazione.

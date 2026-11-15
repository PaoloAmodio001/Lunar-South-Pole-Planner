# Lunar South Pole — rapporto di stato missione

- Generato UTC: 2026-11-14T20:21:59.261524+00:00
- Run ID: d16dce18-e7e4-438a-83a4-de154fa9c245
- Sito candidato: Connecting Ridge
- Data pianificazione: 2026-10-25
- Orizzonte: 48 ore

## Osservazioni astronomiche caricate

- Sole: 0 campioni
- Terra: 0 campioni
- Fonte: observations already loaded in the application; no network request performed
- Nota: Geometric observations do not alone establish solar power or RF link availability.

## Dati del terreno

- LOLA: presente — `data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif`
- LROC: presente — `data/terrain/reference-lroc/NAC_DTM_ESALL_SR12.TIF`
- Georeferenziazione fisica validata: False

## Selezione del sito lunare

- Stato della selezione: success
- Candidati classificati nel ranking: 20
- Classificazione topografica:
  - EXCLUDED_BY_CONFIGURED_THRESHOLDS: 313
  - ELIGIBLE_NEAR_THRESHOLD: 38
  - ELIGIBLE_WITHIN_CONFIGURED_THRESHOLDS: 49
- Candidato migliore del ranking:
  - name: candidate_r2872_c964
  - grid_row: 2872
  - grid_col: 964
  - score: {'name': 'candidate_r2872_c964', 'score_0_100': 74.14, 'coverage_fraction': 1.0, 'components_0_100': {'slope': 65.66, 'roughness': 86.86}, 'missing_metrics': ('illumination', 'communications', 'confidence'), 'notes': ''}
  - terrain_class: ELIGIBLE_WITHIN_CONFIGURED_THRESHOLDS
- Report dettagliato: `<scratchpad>/e2e/out/site_ranking.json`
- Avviso selezione: Classifica preliminare: non certifica la sicurezza dell'atterraggio.
- Avviso selezione: Il campionamento non analizza ogni pixel del DEM.
- Avviso selezione: Il punteggio usa soltanto pendenza e rugosità.
- Avviso selezione: Illuminazione, comunicazioni e confidenza non sono incluse nel punteggio.
- Avviso selezione: LDEC e TOTERR, se disponibili, sono indicatori diagnostici separati e non modificano il punteggio.
- Avviso selezione: Coordinate e CRS non attestano da soli un frame lunare fisicamente validato.
- Nota: la classificazione topografica è preliminare e non certifica la sicurezza o l'idoneità operativa del sito.

## Pianificazione rover

- distance_m: 133.99494936611666
- estimated_energy_wh: 2.6798989873223333
- max_slope_deg: 19.799291107416934
- cells_expanded: 558
- status: preliminary
- warning: Pianificazione preliminare su DEM. Energia = distanza x consumo costante; non include massa, pendenza energetica, slittamento, ruote, temperatura, incertezza DEM o dinamica del rover. Frame geodetico non validato.
- dem_path: data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif

## Valutazione energetica rover

- Valutazione energetica non disponibile.
- Motivo: valutazione energetica non configurata

## P-System

- Stato journal locale: Disabilitato dalla configurazione
- Eventi nel journal locale: 0
- Eventi dell'esecuzione corrente: 0
- Percorso journal: non applicabile
- Nodo remoto collegato: False

## Limiti e avvertenze

- Geodetic alignment of LOLA/LROC and candidate coordinates is not independently validated.
- No power-system model, RF link budget, rover dynamics, or multi-rover coordination is certified by this report.
- Missing measurements remain missing; no placeholder scientific values are inferred.
- The P-System journal is local unless a real remote protocol integration is configured separately.

## Esecuzione orchestratore

- Stato: completed

### Step

- **descent_hazard_detection**: success
- **site_selection**: success
- **lola_lroc_quality**: success
- **rover_path**: success

### Artefatti

- **descent_hazard_detection**: `<scratchpad>/e2e/out/descent_hazard_report.json`
- **site_selection**: `<scratchpad>/e2e/out/site_ranking.json`
- **lola_lroc_quality**: `<scratchpad>/e2e/out/lola_lroc_quality.json`
- **rover_plan**: `<scratchpad>/e2e/out/rover_plan.json`
- **route_quality**: `<scratchpad>/e2e/out/route_quality.json`
- **rover_route_map**: `<scratchpad>/e2e/out/rover_route_map.png`

### Avvisi dell'orchestratore

- Risultati preliminari, non certificati per operazioni reali.
- Georeferenziazione e frame fisico lunare non validati indipendentemente.
- L'allocazione multi-rover usa distanze euclidee, non percorsi DEM.
- Il journal è locale e non si connette a nodi P-System remoti.


## Sintesi integrata della missione

- Stato selezione siti: success
- Candidati nel ranking: 20
- Candidato migliore — name: candidate_r2872_c964
- Candidato migliore — terrain_class: ELIGIBLE_WITHIN_CONFIGURED_THRESHOLDS
- Candidato migliore — score: {'name': 'candidate_r2872_c964', 'score_0_100': 74.14, 'coverage_fraction': 1.0, 'components_0_100': {'slope': 65.66, 'roughness': 86.86}, 'missing_metrics': ('illumination', 'communications', 'confidence'), 'notes': ''}
- Budget energetico: valutazione non disponibile.
- descent_hazard_detection: success
- descent_risk_map: non disponibile

## Limiti e avvertenze

- Geodetic alignment of LOLA/LROC and candidate coordinates is not independently validated.
- No power-system model, RF link budget, rover dynamics, or multi-rover coordination is certified by this report.
- Missing measurements remain missing; no placeholder scientific values are inferred.
- The P-System journal is local unless a real remote protocol integration is configured separately.
- Avviso orchestratore: Risultati preliminari, non certificati per operazioni reali.
- Avviso orchestratore: Georeferenziazione e frame fisico lunare non validati indipendentemente.
- Avviso orchestratore: L'allocazione multi-rover usa distanze euclidee, non percorsi DEM.
- Avviso orchestratore: Il journal è locale e non si connette a nodi P-System remoti.

## Quadro complessivo dello stato della missione

- Stato complessivo: completed
- Moduli registrati: 4
- Moduli con stato 'success': 4

### Dettaglio dei moduli

- **descent_hazard_detection**: success
- **site_selection**: success
- **lola_lroc_quality**: success
- **rover_path**: success

### Artefatti generati

- descent_hazard_detection: `<scratchpad>/e2e/out/descent_hazard_report.json`
- lola_lroc_quality: `<scratchpad>/e2e/out/lola_lroc_quality.json`
- route_quality: `<scratchpad>/e2e/out/route_quality.json`
- rover_plan: `<scratchpad>/e2e/out/rover_plan.json`
- rover_route_map: `<scratchpad>/e2e/out/rover_route_map.png`
- site_selection: `<scratchpad>/e2e/out/site_ranking.json`

### Avvisi e limitazioni aperte

- Risultati preliminari, non certificati per operazioni reali.
- Georeferenziazione e frame fisico lunare non validati indipendentemente.
- L'allocazione multi-rover usa distanze euclidee, non percorsi DEM.
- Il journal è locale e non si connette a nodi P-System remoti.
- I moduli non presenti nel registro non sono considerati completati. L'assenza di avvisi non costituisce una certificazione di sicurezza.

## Dettaglio delle analisi tecniche

- **Qualità LOLA/LROC**: `<scratchpad>/e2e/out/lola_lroc_quality.json`
  - warnings: ['Confronto diagnostico, non validazione geodetica.', 'CONF 14 indica image matching riuscito, non accuratezza assoluta certificata.', 'CONF 4 è analizzata separatamente perché interpolata o estrapolata.', 'CONF 0 e CONF 1 sono escluse dalle statistiche altimetriche.', 'Le classi CONF non documentate restano irrisolte.', 'Le differenze non sono correzioni da applicare automaticamente alle quote.', 'La confidenza LROC non è una maschera di percorribilità del rover.', 'Il confronto non certifica frame fisico lunare o datum verticale equivalenti.', 'Il ricampionamento non dimostra la co-registrazione fisica dei prodotti.']
- **Qualità del percorso rover**: `<scratchpad>/e2e/out/route_quality.json`
  - status: diagnostic_only
  - distance_m: 133.99494936611666
  - warnings: ['Metriche diagnostiche: non certificano la sicurezza o la percorribilità.', 'La pendenza è stimata dal DEM; non include incertezza altimetrica.', 'Le stime non modellano slittamento, ostacoli, dinamica o limiti meccanici.']
- **Rilevamento dei rischi di discesa**: `<scratchpad>/e2e/out/descent_hazard_report.json`
  - status: preliminary
  - warnings: ['Prototipo software preliminare: non certificato per un atterraggio reale.', 'La scansione sintetica non riproduce geometria, dinamica o limiti reali del lidar.', 'Il confronto presuppone DEM e scansione allineati nello stesso riferimento orizzontale e verticale.', 'La classificazione non costituisce una garanzia di sicurezza.']
- Mappa dei rischi: artefatto non registrato.
- La presenza di un artefatto non equivale a una validazione scientifica o a una certificazione operativa.

## Quadro decisionale della missione

- **Selezione del sito** — success; artefatto: `<scratchpad>/e2e/out/site_ranking.json`
- **Confronto qualitativo LOLA/LROC** — success; artefatto: `<scratchpad>/e2e/out/lola_lroc_quality.json`
- **Analisi dei rischi di discesa** — success; artefatto: `<scratchpad>/e2e/out/descent_hazard_report.json`
- **Mappa dei rischi** — fase non registrata; artefatto non registrato
- **Pianificazione del rover** — success; artefatto: `<scratchpad>/e2e/out/rover_plan.json`
- **Valutazione energetica** — fase non registrata; artefatto non registrato

### Criteri per interpretare il risultato

- Un modulo riuscito indica che la fase software ha prodotto un risultato; non dimostra da solo la validità scientifica del risultato.
- Una fase non configurata o non registrata non deve essere interpretata come superata.
- La selezione topografica non sostituisce le verifiche di georeferenziazione, illuminazione, comunicazione, dinamica del rover e condizioni operative.
- La stima energetica deve essere interpretata secondo le ipotesi e le riserve riportate nel relativo artefatto.
- Decisione operativa finale: non determinabile dal solo riepilogo software; richiede validazione dei dati, dei modelli e dei requisiti della missione.

## Coerenza finale dell'esecuzione

- Stato orchestratore: completed_preliminary
- Moduli eseguiti: 4
- Artefatti registrati: 8
- Avvisi: 4
- Gli esiti preliminary indicano analisi non certificate.

### Avvisi

- Risultati preliminari, non certificati per operazioni reali.
- Georeferenziazione e frame fisico lunare non validati indipendentemente.
- L'allocazione multi-rover usa distanze euclidee, non percorsi DEM.
- Il journal è locale e non si connette a nodi P-System remoti.

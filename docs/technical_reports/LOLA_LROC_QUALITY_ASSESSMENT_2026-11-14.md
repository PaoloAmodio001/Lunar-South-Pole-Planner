# LOLA–LROC Quality Assessment

**Data:** 14 novembre 2026  
**Progetto:** Lunar South Pole Planner  
**Stato:** verifica diagnostica completata  
**Suite di regressione:** 94 test superati

## 1. Obiettivo

Valutare la coerenza altimetrica tra il DEM LOLA e il DTM LROC
nell'area di sovrapposizione, utilizzando le classi di confidenza
LROC disponibili nel prodotto CONF PDS3.

Il confronto è diagnostico: non costituisce una validazione geodetica
né certifica l'accuratezza assoluta dei prodotti.

## 2. Dati utilizzati

- LOLA DEM: `data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif`
- LOLA LDEC: `data/terrain/official-lola/Site04_final_adj_5mpp_ldec.tif`
- LOLA TOTERR: `data/terrain/official-lola/Site04_final_adj_5mpp_toterr.tif`
- LROC DTM: `data/terrain/reference-lroc/NAC_DTM_ESALL_SR12.TIF`
- CONF originale: `data/terrain/reference-lroc/source-check/NAC_DTM_ESALL_SR12_CONF_original.IMG`

Griglia di destinazione: LOLA.  
Ricampionamento DTM LROC: bilineare.  
Ricampionamento CONF: nearest-neighbour.  
Differenza: LROC meno LOLA, in metri.

## 3. Interpretazione dei codici CONF

Nel confronto sono state adottate le seguenti interpretazioni:

- CONF 14: prodotto basato su image matching riuscito; gruppo primario.
- CONF 4: dato interpolato o estrapolato; analizzato separatamente.
- CONF 1: ombra; escluso dalle statistiche altimetriche.
- CONF 0: NoData / fuori dal perimetro valido; escluso.
- CONF 2, 5 e 6: significato non documentato nel contesto della presente
  analisi; mantenuti come classi irrisolte e non inclusi nelle statistiche
  altimetriche principali.

I valori originali CONF sono stati preservati. La copertura geometrica
del raster CONF è stata trattata separatamente dai valori dei pixel.

## 4. Risultato del confronto globale

Sulla griglia LOLA:

| Indicatore | Pixel |
|---|---:|
| LOLA validi | 10.240.000 |
| LROC validi ricampionati | 690.057 |
| Sovrapposizione DEM | 690.057 |
| Pixel coperti da CONF nella sovrapposizione | 690.057 |
| Pixel validi per il confronto (CONF 4 + 14) | 689.709 |

Distribuzione CONF nella sovrapposizione:

| Codice | Pixel |
|---|---:|
| 0 | 119 |
| 1 | 95 |
| 2 | 41 |
| 4 | 20.800 |
| 5 | 43 |
| 6 | 50 |
| 14 | 668.909 |

### 4.1 CONF 14

| Indicatore | Risultato |
|---|---:|
| Pixel | 668.909 |
| MAE | 0,9169 m |
| RMSE | 1,1660 m |
| Mediana differenza | +0,7001 m |
| P95 differenza assoluta | 2,2812 m |
| Massimo assoluto | 18,6874 m |
| Differenze assolute > 10 m | 35 |
| Differenze assolute > 50 m | 0 |

CONF 14 costituisce il gruppo primario del confronto, ma non equivale
a una certificazione di accuratezza assoluta.

### 4.2 CONF 4

| Indicatore | Risultato |
|---|---:|
| Pixel | 20.800 |
| MAE | 1,7400 m |
| RMSE | 6,1725 m |
| Mediana differenza | +0,4247 m |
| P95 differenza assoluta | 4,1996 m |
| Massimo assoluto | 192,2360 m |
| Differenze assolute > 10 m | 61 |
| Differenze assolute > 50 m | 48 |
| Differenze assolute > 100 m | 29 |

CONF 4 presenta una distribuzione degli errori più problematica
e richiede un trattamento distinto dal gruppo CONF 14.

## 5. Analisi degli outlier CONF 4

Sono stati identificati 29 pixel con differenza assoluta superiore
a 100 m, distribuiti in tre aree locali:

| Zona | Outlier > 100 m |
|---|---:|
| A | 5 |
| B | 21 |
| C | 3 |
| **Totale** | **29** |

Le differenze osservate hanno segno diverso tra le aree.
Non emerge quindi un semplice offset verticale costante che possa
spiegare gli scostamenti.

L'ispezione locale di LOLA SURF, LDEC e TOTERR non ha evidenziato
un'anomalia altimetrica LOLA sufficiente, da sola, a spiegare
gli scostamenti superiori a 100 m.

## 6. Verifica della distanza dal bordo LROC

È stata calcolata la distanza tra i centri dei pixel validi CONF 4
e il centro del pixel LROC non valido più vicino sulla griglia LOLA.

Risultato:

- Zona A: 5/5 outlier entro 10 m.
- Zona B: 21/21 outlier entro 10 m.
- Zona C: 3/3 outlier entro 10 m.
- Totale: 29/29 outlier entro 10 m.

Nelle fasce 10–20 m gli errori sono sensibilmente inferiori:

| Zona | Pixel CONF 4 | MAE | RMSE | Massimo assoluto |
|---|---:|---:|---:|---:|
| A | 170 | 0,8040 m | 1,0727 m | 3,4612 m |
| B | 54 | 0,6466 m* | 0,8431 m* | 2,6948 m* |
| C | 55 | 0,8671 m | 1,0279 m | 2,3208 m |

*I valori della fascia 10–20 m provengono dall'analisi delle distanze
per fascia. Il test locale di esclusione a 10 m ha prodotto per la
zona B MAE 0,6406 m, RMSE 0,8333 m e massimo 2,6861 m. Le due
elaborazioni sono mantenute distinte.

La distanza è una misura tra centri di pixel ricampionati, non una
misura geometrica esatta del bordo del DTM sorgente.

## 7. Test controllato di esclusione temporanea a 10 m

È stato eseguito un test indipendente sulle tre finestre locali,
senza modificare i raster originali o la funzione principale.

| Zona | CONF 4 prima: N | MAE prima | RMSE prima | CONF 4 dopo: N | MAE dopo | RMSE dopo | Outlier eliminati |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 593 | 2,6110 m | 17,4249 m | 170 | 0,8040 m | 1,0727 m | 5/5 |
| B | 204 | 16,0441 m | 45,4309 m | 54 | 0,6406 m | 0,8333 m | 21/21 |
| C | 198 | 4,3350 m | 17,5332 m | 55 | 0,8650 m | 1,0211 m | 3/3 |

Dopo l'esclusione temporanea:

- non rimangono outlier superiori a 10 m nelle tre finestre;
- tutti i 29 outlier originari risultano esclusi;
- CONF 14 resta invariata nelle tre finestre;
- il test non modifica dati sorgente né applica maschere permanenti.

Il numero di pixel CONF 4 esclusi è rispettivamente 423, 150 e 143.
Questa esclusione è quindi sostanziale nelle finestre esaminate e non
deve essere generalizzata automaticamente all'intero sito.

## 8. Decisione tecnica

Si propone la seguente classificazione operativa:

1. **CONF 14 — riferimento primario:** utilizzabile per il confronto
   altimetrico diagnostico.
2. **CONF 4 oltre 10 m dal bordo:** dato interpolato/estrapolato,
   da utilizzare con cautela.
3. **CONF 4 entro 10 m dal bordo:** dato a qualità critica,
   da segnalare e da escludere solo nelle analisi che adottano
   esplicitamente il criterio sperimentale.
4. **CONF 0 e CONF 1:** esclusi dalle statistiche altimetriche.
5. **CONF 2, 5 e 6:** classi irrisolte, non utilizzate nel confronto
   altimetrico principale.

La soglia di 10 m è un criterio diagnostico sperimentale verificato
nelle tre finestre A, B e C. Non è una soglia scientifica universale
né una maschera definitiva del prodotto.

## 9. Limiti e verifiche ancora necessarie

- Il test di esclusione è locale e non copre l'intera area CONF 4.
- La distanza è calcolata sulla griglia LOLA ricampionata.
- La validità dei pixel LROC dipende anche dal comportamento del
  ricampionamento bilineare vicino ai NoData.
- Non è stata dimostrata una causa fisica univoca degli outlier.
- Il confronto non certifica la co-registrazione geodetica o
  l'equivalenza dei datum verticali.
- CONF 14 non garantisce accuratezza assoluta.
- La confidenza LROC non rappresenta una maschera di percorribilità
  del rover.
- Non applicare correzioni altimetriche automatiche sulla base
  di queste differenze.

Per una soglia operativa definitiva occorre estendere la verifica
a tutto il perimetro LROC e, preferibilmente, confrontare il bordo
del raster sorgente con una misura di distanza geometrica indipendente.

## 10. Riproducibilità

Materiali principali:

- `src/lola_lroc_quality.py`
- `scripts/analyze_lroc_edge_outliers.py`
- `scripts/diagnose_lola_lroc_outliers.py`
- `scripts/test_conf4_edge_exclusion.py`
- `audit-reports/lola-lroc-quality-real-20261114.json`
- `audit-reports/lola-lroc-conf4-outliers-20261114.csv`
- `audit-reports/lola-lroc-local-shift-test-20261114.csv`
- `audit-reports/lola-lroc-edge-analysis-20261114/`
- `audit-reports/lola-lroc-edge-exclusion-test-20261114/`

Suite completa eseguita dopo le modifiche:

`python -m pytest -q`

**Esito: 94 passed.**

---

**Conclusione:** l'analisi evidenzia una forte associazione tra gli
outlier CONF 4 e la prossimità al bordo della copertura LROC nelle
tre zone investigate. Il criterio di 10 m è utile come indicatore
diagnostico locale, ma non è ancora validato come regola globale
per il pianificatore lunare.

---

# APPENDICE A — APPROFONDIMENTO SU GRIGLIA LROC

**Data dell'integrazione:** 14 novembre 2026
**Metodo:** LOLA ricampionato sulla griglia nativa LROC da 2 m.
**Stato:** analisi diagnostica aggiuntiva.

## A.1 Distinzione metodologica

Questa analisi utilizza una griglia differente da quella del confronto
principale descritto nelle sezioni precedenti.

- Griglia di destinazione: LROC, 2 m/pixel.
- LOLA SURF: ricampionamento bilineare.
- LOLA LDEC: ricampionamento nearest-neighbour.
- LOLA TOTERR: ricampionamento bilineare.
- Differenza: LROC meno LOLA, in metri.

I risultati di questa appendice non devono essere sommati o confrontati
direttamente con i conteggi della precedente analisi sulla griglia LOLA.

## A.2 Confronto sulla griglia LROC

Pixel validi: 4.313.020.

| Indicatore | Risultato |
|---|---:|
| Bias medio | +0,7517 m |
| Mediana | +0,6992 m |
| MAE | 0,9563 m |
| RMSE | 2,8606 m |
| P95 differenza assoluta | 2,3251 m |
| Massimo positivo | +477,3155 m |
| Massimo negativo | -145,3589 m |

Distribuzione delle differenze assolute:

| Percentile | Differenza |
|---|---:|
| P50 | 0,772 m |
| P90 | 1,941 m |
| P95 | 2,325 m |
| P97 | 2,586 m |
| P99 | 3,185 m |
| P99,5 | 3,654 m |
| P99,9 | 5,864 m |

Sono stati individuati 726 pixel con differenza assoluta superiore
a 10 m, distribuiti in 31 gruppi connessi.

## A.3 Anomalie CONF14

Sulla griglia LROC sono stati individuati 206 pixel CONF14 con
differenza assoluta superiore a 10 m.

| Indicatore | Risultato |
|---|---:|
| Numero anomalie | 206 |
| Bias medio | +9,996 m |
| MAE | 11,269 m |
| Massimo assoluto | 17,634 m |
| TOTERR mediano | 0,947 m |
| TOTERR P90 | 3,148 m |
| TOTERR P95 | 3,807 m |

Distribuzione LDEC sulle anomalie:

| LDEC | Pixel |
|---|---:|
| 0 | 174 |
| 1 | 32 |

Nessuna anomalia CONF14 di questo insieme si trova entro 20 m
da un pixel CONF4 o INVALID. Soltanto 15 risultano entro 50 m
e 105 entro 100 m. Le distanze sono state calcolate sulla griglia
LROC, con ricerca limitata a 100 m.

Questo risultato mostra che la prossimità alle classi CONF4 e INVALID
non spiega da sola le anomalie CONF14.

## A.4 Distribuzione geografica

Le 206 anomalie CONF14 sono state raggruppate in 9 componenti
connesse, usando adiacenza a 8 pixel.

I tre gruppi maggiori comprendono 185 pixel:

| Gruppo | Pixel | Differenza massima | Centro X | Centro Y |
|---|---:|---:|---:|---:|
| 1 | 87 | 11,05 m | -2414 | -4884 |
| 2 | 58 | 17,63 m | -2350 | -5082 |
| 3 | 40 | 15,20 m | -1464 | -6128 |

## A.5 Verifica LOLA sulla griglia originale

Sono state analizzate tre finestre locali di 21 x 21 celle sulla
griglia LOLA originale da 5 m, corrispondenti ai tre gruppi principali.

| Gruppo | LDEC=0 | LDEC>=1 | TOTERR mediano |
|---|---:|---:|---:|
| 1 | 428/441 | 13/441 | 0,655 m |
| 2 | 424/441 | 17/441 | 0,571 m |
| 3 | 406/441 | 35/441 | 0,536 m |

Tutte le 441 celle di ciascuna finestra presentano valori validi
nei raster SURF, LDEC e TOTERR.

Il prodotto LOLA SURF documenta il riempimento delle celle vuote
mediante interpolazione. La presenza di valori SURF nelle celle
con LDEC=0 è pertanto coerente con la metodologia del prodotto.

Questi risultati suggeriscono una copertura di ritorni LOLA molto
limitata nelle finestre analizzate. Non dimostrano da soli che
l'interpolazione sia la causa delle differenze altimetriche.

## A.6 Compatibilità dei riferimenti spaziali

I metadati dei prodotti mostrano:

- proiezione polare stereografica;
- latitudine di origine -90 gradi;
- meridiano centrale 0 gradi;
- raggio lunare 1.737.400 m;
- falsi offset pari a zero;
- AREA_OR_POINT=Area per entrambi.

Le rappresentazioni numeriche della proiezione sono compatibili.

Rimane tuttavia una differenza nei metadati del datum:
LROC dichiara D_Moon, mentre il CRS LOLA riporta DATUM unknown.
La documentazione LOLA indica il riferimento MOON_ME / DE421.

La documentazione LROC descrive le quote come altezza rispetto
alla sfera/ellissoide definita dagli assi della mappa.

Queste informazioni non costituiscono una dimostrazione completa
dell'equivalenza dei riferimenti fisici e verticali. La co-registrazione
geodetica e l'equivalenza altimetrica restano pertanto da verificare.

## A.7 Interpretazione e limiti

Le anomalie CONF14 sono concentrate in nove gruppi geografici.
Nei tre gruppi maggiori, la maggior parte delle celle LOLA analizzate
ha LDEC=0.

Questo è compatibile con l'ipotesi che la ricostruzione interpolata
del prodotto LOLA contribuisca alle differenze locali.

Non è tuttavia possibile attribuire una causa univoca agli scostamenti.
In particolare:

- LDEC=0 non dimostra da solo l'assenza di informazioni LOLA vicine.
- TOTERR non rappresenta una correzione della quota.
- Un TOTERR basso non certifica l'accordo con LROC.
- CONF14 indica correlazione stereo riuscita, non accuratezza assoluta.
- La differenza tra due DEM non equivale a un errore assoluto misurato.

Non sono state applicate correzioni ai raster originali.

## A.8 Conclusione integrativa

Il confronto sulla griglia LROC conferma la presenza di anomalie
localizzate anche all'interno della classe CONF14.

La loro distribuzione e la bassa densità di ritorni LOLA nelle finestre
esaminate costituiscono evidenze utili per ulteriori verifiche
sulla metodologia di interpolazione e sulla compatibilità dei prodotti.

Non è ancora dimostrata una causa fisica univoca né l'equivalenza
completa dei riferimenti verticali.

Per l'impiego nel Lunar South Pole Planner si raccomanda di mantenere
separate le classi di qualità LROC, le informazioni di copertura LOLA
e le incertezze altimetriche. Non applicare correzioni automatiche
sulla base delle sole differenze osservate.

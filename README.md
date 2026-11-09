# WECO Noor (non ufficiale) per Home Assistant

Integrazione custom per leggere i dati del tuo impianto WECO (app `com.weco.noor`)
tramite il cloud, ricavata da **analisi statica** dell'app ufficiale v1.3.0.
Non e' un'API documentata da WECO: puo' cambiare o smettere di funzionare
senza preavviso, ed e' pensata per uso personale sul proprio account.

## Cosa fa

- Login col tuo account (email + password).
- Lettura periodica della telemetria in tempo reale dell'inverter/colonnina
  (ogni 60 secondi) e dei dati di energia giornaliera (ogni 5 cicli, ~5 minuti).
- Crea un sensore per ogni campo numerico trovato nella risposta del server.
  I nomi dei campi sono quelli grezzi restituiti dal server, perche' il loro
  significato esatto non e' documentato: controlla i valori confrontandoli
  con l'app ufficiale prima di fidartene per automazioni importanti.

## Limiti conosciuti

- **Nessun refresh/logout noto**: se il token scade, il client rifa' il login
  in automatico con le credenziali salvate.
- **2FA non supportata**: se il tuo account ha l'autenticazione a due fattori
  attiva, la configurazione fallira' con un errore esplicito.
- **Endpoint energia non verificato per tutte le famiglie di dispositivo**:
  per gli inverter viene usato `getInverterHomeEnergyV2` (`V3` solo per la
  famiglia ThMax, dtc 4101/4104). Se risulta vuoto o in errore, prova a
  scambiare V2/V3 in `const.py`.
- **Colonnine di ricarica (EV)**: viene letta solo la telemetria
  (`getChargePoint`); l'endpoint di energia per questi dispositivi non e'
  stato individuato e non viene interrogato.
- **Sistemi in parallelo** (piu' inverter collegati insieme) non sono gestiti:
  l'integrazione configura un singolo dispositivo per volta.
- **Traffico in HTTP, non HTTPS**: e' l'app stessa a funzionare cosi', non
  una scelta di questa integrazione.
- Password ed email vengono salvate nella configurazione della integrazione
  (nello storage cifrato di Home Assistant), perche' servono per rifare il
  login quando il token scade.

## Installazione

1. Copia la cartella `custom_components/weco_noor` dentro la cartella
   `config/custom_components/` della tua installazione di Home Assistant.
2. Riavvia Home Assistant.
3. Vai in Impostazioni -> Dispositivi e servizi -> Aggiungi integrazione,
   cerca "WECO Noor" e segui la procedura guidata: email, password, scelta
   dell'impianto e del dispositivo.
4. Dopo il primo aggiornamento compariranno le entita' sensore, una per ogni
   campo numerico trovato nella risposta del server.

## Se qualcosa non torna

- Se non compare nessun sensore, o i valori sembrano sbagliati, guarda i log
  di Home Assistant (Impostazioni -> Sistema -> Log) cercando "weco_noor":
  lì si vede la risposta grezza in caso di errore.
- Se conosci il significato reale di qualche campo (per esempio dal
  confronto con l'app), puoi rinominare il sensore corrispondente senza
  toccare il codice, dalle impostazioni dell'entita' in Home Assistant.

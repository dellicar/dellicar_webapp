DELLICAR NOLEGGIO WEB APP - V1

Questa è una web app reale in Flask con database SQLite locale.

FUNZIONI:
- Dashboard
- Clienti
- Veicoli
- Nuovo noleggio
- Chiusura noleggio / restituzione
- Contratto stampabile / salvabile in PDF
- Impostazioni azienda Dellicar
- Dati demo caricabili dal pulsante in alto

COME AVVIARLA SU MAC:
1) Apri Terminale nella cartella del progetto
2) Crea ambiente virtuale:
   python3 -m venv .venv
3) Attiva ambiente:
   source .venv/bin/activate
4) Installa dipendenze:
   pip install -r requirements.txt
5) Avvia app:
   python app.py
6) Apri nel browser:
   http://127.0.0.1:5000

NOTE:
- Il database è il file dellicar.db
- Per il PDF: apri il contratto e usa Stampa / Salva PDF
- Per iPad o uso multi-dispositivo, il passo successivo è pubblicarla online su un server o Render/Railway.

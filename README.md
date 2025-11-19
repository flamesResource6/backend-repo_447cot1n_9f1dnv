Stk Barbershop - Programări

Instrucțiuni de instalare și rulare

1) Cerințe
- Node.js pentru frontend
- Python 3 pentru backend

2) Configurare variabile de mediu (SMTP)
Creează fișierul .env în backend cu următorul conținut și adaptează valorile:

SMTP_HOST=smtp.exemplu.com
SMTP_PORT=587
SMTP_USER=utilizator@example.com
SMTP_PASS=parola_smtp
MAIL_FROM=programari@stkbarbershop.ro
MAIL_TO=stkbarbershop@gmail.com
SMTP_USE_TLS=true

3) Instalare dependențe
- Frontend: npm install
- Backend: vor fi instalate automat prin mediul de rulare

4) Pornire servere
- Rulează comanda de start din acest mediu (vor porni automat frontend pe portul 3000 și backend pe portul 8000).
- Dacă rulezi local:
  - Frontend: npm run dev (din folderul frontend)
  - Backend: python main.py (din folderul backend) sau uvicorn main:app --host 0.0.0.0 --port 8000

5) Configurare frontend pentru API
Creează fișierul .env în frontend și setează:
VITE_BACKEND_URL=http://localhost:8000

6) Testare trimitere email
- Deschide aplicația frontend.
- Completează formularul cu date valide (telefon corect, dată/oră în viitor).
- Completează captcha (suma celor două numere afișate).
- Trimite formularul.
- Verifică adresa setată în MAIL_TO pentru mesajul primit.

7) Securitate
- Rate limiting simplu IP-based este activ pe endpoint-ul de programare.
- Validările sunt efectuate și pe server (telefon, serviciu, dată/oră, captcha).
- Datele sensibile SMTP se setează doar în variabile de mediu și nu trebuie incluse în cod.

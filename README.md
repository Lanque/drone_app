# FrameScout

Filmivõtete asukohtade planeerimise rakendus. Salvesta võttepaiku kaardile,
lisa produktsioonimärkmeid ning vaata tuult ja parimaid valgusaegu.

## Käivita projekt lokaalselt

Eeldused: Python 3.13+, PostgreSQL ja pgAdmin või muu PostgreSQL klient.

```powershell
git clone <sinu-repo-aadress>
cd drone-locations
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Seadista `.env` failis PostgreSQL-i ühendusandmed. Seda faili ei tohi Git-i
lisada.

Loo PostgreSQL-is andmebaas `drone_locations` ning käivita selle sees
[`database/schema.sql`](database/schema.sql). Seejärel käivita rakendus:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Ava `http://127.0.0.1:8010`.

## Välised teenused

- Sunrise-Sunset API ei vaja võtit ja näitab golden/blue hour'i aegu.
- OpenWeather on valikuline. Lisa `OPENWEATHER_API_KEY` `.env` faili, kui
  soovid tuulekiirust; ilma selleta jääb ülejäänud rakendus tööle.
- Google Street View on planeeritud valikuline funktsioon. Ära lisa Google'i
  võtit Git-i.

## Turvalisus

`.env` sisaldab paroole ja API võtmeid ning on `.gitignore` failis. Jaga ainult
`.env.example` faili, kus on väljade nimed, mitte päris väärtused.

# Pocketwise

Pocketwise is a personal expense tracker built with Vue 3 (Options API), Vuetify 3, FastAPI, and SQLite. It is designed to work well on desktop and mobile screens and includes the core features needed to understand spending habits.

## Features

- Add, edit, and delete expense entries
- Expense fields for title, amount, category, date, payment method, and notes
- Search expenses and filter by category
- Monthly total, average transaction, and entry count
- Category spending mix with top-category callout
- Six-month spending trend
- CSV export
- Light/dark theme toggle
- Responsive Vuetify navigation drawer, cards, dialog, form, and data table
- Starts with an empty personal ledger so the dashboard never invents spending data

## Run locally

The quickest way to install dependencies and start both services is:

```bash
make start
```

Then open `http://localhost:5173`. Press `Ctrl+C` to stop both the frontend and backend.

To install dependencies without starting the services:

```bash
make install
```

Start the API:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Production build

The Docker image builds the Vue app and serves it from FastAPI. SQLite is stored at `/data/expenses.db` so it can be backed by a persistent volume.

```bash
docker build -t pocketwise .
docker run --rm -p 8000:8000 -v pocketwise-data:/data pocketwise
```

Open `http://localhost:8000`.

## Hosting

The included `render.yaml` is ready for Render:

1. Push this repository to GitHub.
2. In Render, choose **New Blueprint** and select the repository.
3. Render will use the Dockerfile and create a 1 GB persistent disk at `/data`.
4. Deploy and open the generated `onrender.com` URL.

The free Render tier does not include persistent disks. Use the `starter` plan in `render.yaml` if entries must survive deploys and restarts. For a free demo deployment, remove the `plan` and `disk` entries, but SQLite data will be ephemeral.

## API

- `GET /api/expenses`
- `POST /api/expenses`
- `PUT /api/expenses/{id}`
- `DELETE /api/expenses/{id}`
- `GET /api/analytics/summary`
- `GET /api/analytics/categories`
- `GET /api/analytics/monthly`
- `GET /api/expenses/export`

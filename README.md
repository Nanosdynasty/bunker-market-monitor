# Bunker Market Monitor

A compact Flask proof of concept that compares source-timestamped bunker price observations from Bulugo, OilPriceAPI, and uploaded Excel workbooks. It monitors up to 15 ports, preserves source identity, accumulates history in SQLite, and keeps the last successful values visible when a refresh fails.

The app starts in **clearly labelled demo mode** so the UI can be reviewed without credentials. Demo prices are generated fixtures and must not be treated as market data.

## What it does

- Dashboard with dynamic port cards and an interactive price-history chart.
- Visible vertical `Price (USD/MT)` axis and hover/touch tooltips with exact values.
- Side-by-side provider comparison with absolute and percentage spreads.
- Source diagnostics, quotas, timestamps, errors, and normalized row preview.
- Light/dark themes, responsive layouts, and browser polling while the page is open.
- Server refresh target of 30 minutes, with quota checks, cooldowns, and a database lease to prevent overlapping jobs.
- `/health` liveness and `/ready` database readiness endpoints.

## Upload your own Excel workbook

Open **Sources**, choose **Upload an Excel price file**, and select an `.xlsx` workbook. The app reads saved cell values with `openpyxl`, imports normalized prices into SQLite as an **Excel upload** source, and displays them on Dashboard, Compare, the interactive chart, and the Sources preview.

Supported workbook shapes include:

- Long-form columns such as `Port`, `Fuel grade`, `Price`, and optional `Timestamp`, `Country`, and `Region`.
- One row per port with separate `VLSFO`, `HSFO`/`IFO380`, and `MGO` columns.
- Matrix sheets where ports are merged or repeated headings, fuel grades are subheadings, and dates run down the first column.

Only `.xlsx` files up to 20 MB are accepted by default. Formula text is not executed: the app reads the result last saved by Excel. Missing cached results and Excel errors are reported in the upload diagnostics. The temporary raw workbook is deleted after parsing; normalized observations remain in SQLite.

An upload is a snapshot. Render or any other hosted server cannot watch a folder on your computer. After changing the local workbook, upload it again. Continuous updates require a separate OneDrive, SharePoint, or Google Sheets API connector.

## Connect a cloud workbook (Azure or Render)

Use **Sources → Connect Microsoft account** to sign in, then browse OneDrive or paste a OneDrive/SharePoint sharing link. The server stores the selected drive/item reference in the session and checks Graph metadata every five minutes. It downloads and imports the workbook only when its ETag or saved modification time changes. The browser never calls Graph directly.

Before using this mode, register an app in Microsoft Entra ID with supported account types that include personal Microsoft accounts and organizational accounts. Add delegated Microsoft Graph permissions `User.Read`, `Files.Read`, and `offline_access`, create a client secret **value**, and register these redirect URIs:

- Local: `http://localhost:5070/auth/callback`
- Azure App Service: `https://<app-name>.azurewebsites.net/auth/callback`

Set `MSAL_CLIENT_ID`, `MSAL_CLIENT_SECRET`, `MSAL_TENANT=common`, and the matching `MSAL_REDIRECT_URI` as service environment variables. On Azure, set `DATABASE_PATH=/home/data/bunker-market-monitor.db` and enable **Always On**. On Render, use the persistent disk path from `render.yaml`. A restart clears in-memory token caches, so users may need to sign in again.

The workbook must be saved and fully synced to OneDrive/SharePoint before a change is visible. Excel formulas are not executed by this app; it reads the values cached by Excel at the last save. A local `C:\...` path cannot be watched by Azure.

## Important data and licensing note

This repository does not scrape public price pages. Both providers require an account/API key and may restrict which datasets, ports, and display use are permitted. Before enabling live mode, confirm that your account terms permit internal display and temporary storage of observations.

Prices are indications, not executable supplier quotes. The app does not average providers. A provider failure leaves the previous data visible and marks the source unavailable or stale.

## Run locally

1. Install Python 3.12.
2. Open a terminal in this repository.
3. Create and activate a virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   python -m pip install -r requirements-dev.txt
   ```

5. Copy `.env.example` to `.env`. For local demo mode, change `DATABASE_PATH` to an empty value or remove that line, and set `SESSION_COOKIE_SECURE=false`.
6. Load the environment and start the app:

   ```powershell
   Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object { $name,$value = $_ -split '=',2; [Environment]::SetEnvironmentVariable($name,$value,'Process') }
   python app.py
   ```

7. Open `http://127.0.0.1:5070`.

## Connect live providers

### Bulugo

1. Create or sign in to a Bulugo account.
2. Open **Dashboard → Developer Settings**.
3. Request/confirm bunker-price API access for this internal dashboard.
4. Generate a bearer-token API key.
5. Set `BULUGO_API_KEY` on the server.

The adapter calls `GET https://my.bulugo.com/api/v1/prices?limit=500` with `Authorization: Bearer <key>`.

### OilPriceAPI

1. Create an OilPriceAPI account and copy the key from its dashboard.
2. Confirm the account is entitled to the marine/bunker-fuels dataset and your intended internal display/storage.
3. Set `OILPRICEAPI_KEY` on the server.

The adapter calls `GET https://api.oilpriceapi.com/v1/bunker-fuels/all` with `Authorization: Token <key>`. If this dataset is not enabled, Sources will show the entitlement error while preserving prior data.

### Switch from demo to live

After both keys work, set `DEMO_MODE=false` and restart the service. Existing demo rows should be removed before production evaluation by deleting the local SQLite database or creating a fresh persistent disk. Do not mix demo rows with live observations.

## Deploy on Render

1. Push this repository to GitHub. Keep it private and never commit `.env` or API keys.
2. In Render, choose **New → Blueprint** and connect the repository.
3. Render reads `render.yaml` and creates one Python web service plus a 1 GB persistent disk.
4. In the service environment, enter `BULUGO_API_KEY` and `OILPRICEAPI_KEY` as secret values.
5. Deploy first with `DEMO_MODE=true` to verify the UI and health endpoint.
6. Confirm provider rights and keys, set `DEMO_MODE=false`, use a fresh database, and redeploy.
7. Verify:
   - `https://<service>.onrender.com/health`
   - `https://<service>.onrender.com/ready`
   - Dashboard, Compare, Sources, manual refresh, and dark mode.

The persistent disk requires a paid Render instance. Without a disk, SQLite history is ephemeral and may disappear after a restart or redeployment. Keep `--workers 1`; the background scheduler runs inside the web process, and multiple workers would create duplicate schedules. The database lease is an additional safety guard.

## Tests

Run:

```powershell
pytest -q
```

The test suite uses temporary SQLite databases and mocked HTTP responses. No provider key or network access is required.

## Manual acceptance checklist

- [ ] Demo mode is visibly labelled on Dashboard and Sources.
- [ ] Fifteen monitored port cards render responsively.
- [ ] Selecting a port updates the chart.
- [ ] VLSFO/HSFO/MGO and 24H/7D/30D/All controls update the chart.
- [ ] The chart has a vertical USD/MT price scale.
- [ ] Hovering or tapping a point shows timestamp, provider, grade, and exact price.
- [ ] Compare shows source values separately and calculates spread when at least two exist.
- [ ] Sources shows configuration, quota, errors, last success, and normalized rows.
- [ ] Upload a supported `.xlsx` in Sources and confirm the Excel values appear in the cards, comparison table, chart, and normalized preview.
- [ ] Change a price and upload the workbook again; confirm the Excel source is replaced while API history remains intact.
- [ ] Light/dark choice survives a reload.
- [ ] A simulated provider failure leaves previous values visible and marks the provider unavailable.
- [ ] Restarting with a persistent database retains accumulated history.

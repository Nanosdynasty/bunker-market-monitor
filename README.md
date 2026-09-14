# Bunker Market Monitor

A compact Flask proof of concept that reads bunker prices exclusively from a saved Excel workbook in OneDrive or SharePoint. It checks the cloud workbook every five minutes, preserves the last successful values after failures, and displays the workbook data in a minimal dashboard.

## What it does

- Dashboard with dynamic port cards and an interactive price-history chart.
- Visible vertical `Price (USD/MT)` axis and hover/touch tooltips with exact values.
- Excel source diagnostics, timestamps, errors, worksheet selection, and normalized row preview.
- Light/dark themes, responsive layouts, and browser polling while the page is open.
- Server refresh target of five minutes with metadata checks and overlap protection.
- `/health` liveness and `/ready` database readiness endpoints.

## Upload your own Excel workbook

Open **Sources**, choose **Upload an Excel price file**, and select an `.xlsx` workbook. The app reads saved cell values with `openpyxl`, imports normalized prices into SQLite as an **Excel upload** source, and displays them on Dashboard, Compare, the interactive chart, and the Sources preview.

Supported workbook shapes include:

- Long-form columns such as `Port`, `Fuel grade`, `Price`, and optional `Timestamp`, `Country`, and `Region`.
- One row per port with separate `VLSFO`, `HSFO`/`IFO380`, and `MGO` columns.
- Matrix sheets where ports are merged or repeated headings, fuel grades are subheadings, and dates run down the first column.

Only `.xlsx` files up to 20 MB are accepted by default. Formula text is not executed: the app reads the result last saved by Excel. Missing cached results and Excel errors are reported in the upload diagnostics. The temporary raw workbook is deleted after parsing; normalized observations remain in SQLite.

The local upload is a snapshot for testing. For automatic updates, connect the cloud copy below.

## Connect a cloud workbook (Azure or Render)

Use **Sources → Connect Microsoft account** to sign in, then browse OneDrive or paste a OneDrive/SharePoint sharing link. The server stores the selected drive/item reference in the session and checks Graph metadata every five minutes. It downloads and imports the workbook only when its ETag or saved modification time changes. The browser never calls Graph directly.

Before using this mode, register an app in Microsoft Entra ID with supported account types that include personal Microsoft accounts and organizational accounts. Add delegated Microsoft Graph permissions `User.Read`, `Files.Read`, and `offline_access`, create a client secret **value**, and register these redirect URIs:

- Local: `http://localhost:5070/auth/callback`
- Azure App Service: `https://<app-name>.azurewebsites.net/auth/callback`

Set `MSAL_CLIENT_ID`, `MSAL_CLIENT_SECRET`, `MSAL_TENANT=common`, and the matching `MSAL_REDIRECT_URI` as service environment variables. On Azure, set `DATABASE_PATH=/home/data/bunker-market-monitor.db` and enable **Always On**. On Render, use the persistent disk path from `render.yaml`. A restart clears in-memory token caches, so users may need to sign in again.

The workbook must be saved and fully synced to OneDrive/SharePoint before a change is visible. Excel formulas are not executed by this app; it reads the values cached by Excel at the last save. A local `C:\...` path cannot be watched by Azure.

## Important workbook note

The app reads the values saved by Excel, including cached formula results. It does not execute Reuters Workspace formulas. Excel must save the workbook and OneDrive/SharePoint must finish syncing before a change can appear. Prices are indications, not executable supplier quotes.

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

5. Copy `.env.example` to `.env`, set `SESSION_COOKIE_SECURE=false`, and use the local callback URI.
6. Load the environment and start the app:

   ```powershell
   Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object { $name,$value = $_ -split '=',2; [Environment]::SetEnvironmentVariable($name,$value,'Process') }
   python app.py
   ```

7. Open `http://127.0.0.1:5070`.

## Deploy on Azure App Service

1. Create a Linux App Service using Python 3.12 and connect it to this private GitHub repository.
2. Use `gunicorn --workers 1 --threads 4 --timeout 90 --bind 0.0.0.0:$PORT app:app` as the startup command.
3. Add `MSAL_CLIENT_ID`, `MSAL_CLIENT_SECRET`, `MSAL_TENANT=common`, `MSAL_REDIRECT_URI`, `SECRET_KEY`, `DATABASE_PATH=/home/data/bunker-market-monitor.db`, `SESSION_COOKIE_SECURE=true`, `GRAPH_REFRESH_INTERVAL_MINUTES=5`, and `ENABLE_SCHEDULER=true` as App Service settings.
4. In Entra, register `https://<app-name>.azurewebsites.net/auth/callback` as a Web redirect URI and grant delegated `User.Read`, `Files.Read`, and `offline_access`.
5. Enable Always On, restart the App Service, and verify `/health` and `/ready`.
6. Open **Sources → Connect Microsoft account**, select the OneDrive/SharePoint workbook, and choose its worksheet.

Azure stores normalized observations and workbook metadata in SQLite at `/home/data`. Tokens are cached in memory, so a restart may require sign-in again. Keep one worker because the scheduler runs in the web process.

## Tests

Run:

```powershell
pytest -q
```

The test suite uses temporary SQLite databases and mocked workbook/provider responses. No external API key or network access is required.

## Manual acceptance checklist

- [ ] No prices appear before an Excel workbook is connected.
- [ ] Selecting a port updates the chart.
- [ ] VLSFO/HSFO/MGO and 24H/7D/30D/All controls update the chart.
- [ ] The chart has a vertical USD/MT price scale.
- [ ] Hovering or tapping a point shows timestamp, provider, grade, and exact price.
- [ ] Sources shows cloud file, worksheet, modification time, last check, and errors.
- [ ] Connect a supported `.xlsx` in OneDrive/SharePoint and confirm values appear.
- [ ] Change and save a value, wait for cloud sync, and confirm it appears after a five-minute check.
- [ ] Light/dark choice survives a reload.
- [ ] A cloud download failure leaves previous values visible and marks the workbook stale.
- [ ] Restarting with a persistent database retains accumulated history.

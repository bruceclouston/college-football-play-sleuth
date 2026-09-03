# College Football Play Sleuth — Onboarding for Other Sports

This doc is for anyone at FanDuel who wants to fork this app to build the
equivalent tool for a different sport (NFL, NBA, MLB, NHL, etc.). It covers
what the app does, how it's built, what's generic vs. college-football-specific,
and how to get your own version running and deployed.

- **Live app (this CFB version):** https://cfb-play-sleuth-2283893114343682.aws.databricksapps.com
- **Source repo:** https://github.com/bruceclouston/college-football-play-sleuth
  (private — ask **Bruce Clouston** (bruce.clouston@fanduel.com) for access)
- **Workspace:** `fdg-analytics` (https://fdg-analytics.cloud.databricks.com)

## What it does

Queries play-by-play data for a year/week/season/division: any play type (or
an OR-group of types), an optional minimum-yards-gained filter, and an
optional "penalty only" view that attributes each penalty to the offense or
defense by parsing the play text. Runs as a small FastAPI server + a plain
HTML/JS frontend, deployed as a Databricks App so it's internal-only and
shareable with a URL — no third-party hosting, no plaintext secrets.

## Dependencies (have these ready before you start)

**Accounts / access**
- A GitHub account, added as a collaborator on this repo (ask Bruce), so you
  can fork or branch from working code instead of starting blank.
- A Databricks account with access to the `fdg-analytics` workspace, and a
  working `DEFAULT` profile (`databricks auth login` — if that fails, run the
  `smi-core:databricks-doctor` skill first).
- An API key (or internal data access) for your sport's data source — see
  "Step 0" below. If it's an external API, sign up for a key before writing
  any code.

**Tools (local machine)**
- `git`
- `uv` (Python package/env manager — install via `winget install astral-sh.uv`
  on Windows, or see astral.sh/uv). Don't use system `pip`/`venv` directly.
- `databricks` CLI (`winget install Databricks.DatabricksCLI` on Windows).
- If you're behind FanDuel's corporate network: expect TLS interception
  (`CERTIFICATE_VERIFY_FAILED` errors) on both `uv`'s own downloads and the
  app's own API calls. Fixes are documented inline below — don't skip past
  them assuming your network is broken.

**Skills to load in Claude Code** (all referenced again inline where relevant)
- `smi-core:databricks-doctor` — fixes Databricks auth
- `smi-core:databricks-setup-config` — one-time workspace defaults wizard
- `smi-core:databricks-setup-project` — scaffolds the project as a proper
  Databricks Asset Bundle (DAB)
- `smi-core:databricks-define-resource` / `smi-core:databricks-python-apps` —
  the app resource (`app.yaml` / `resources/*.app.yml`) format and platform
  rules (port binding, secrets, permissions)

## What to build for your sport (paste this brief to your own Claude session)

> Build me a small internally-hosted web app called "[Sport] Play Sleuth"
> that queries [Sport]'s play-by-play data. I want to:
> - Pick a time period (season/week/date range — whatever your sport's data
>   is bucketed by) and optionally a division/league/conference filter.
> - Pick one or more play/event types from the *real* vocabulary the API
>   exposes (not a guessed list) — no selection means "any type."
> - Optionally filter to plays with a minimum stat threshold (yards, points,
>   distance — whatever's the closest equivalent to "yardsGained").
> - Optionally show only plays/events that include a penalty or foul, and
>   tell me which team (offense or defense, or the sport's equivalent) it's
>   attributed to, with an "unattributed" bucket for anything it can't
>   confidently parse.
> - See results in a table and export them as CSV.
> - Keep the API key server-side only — it must never reach the browser.
> - Deploy it as a Databricks App in the `fdg-analytics` workspace (not a
>   third-party host), with the API key stored as a Databricks secret, and
>   grant the right people access.
>
> Reference implementation: https://github.com/bruceclouston/college-football-play-sleuth
> (a working example built the same way, for college football). Read its
> ONBOARDING.md first — it documents the architecture, what to reuse vs.
> rewrite, and specific bugs/gotchas already hit and fixed once, so you don't
> repeat them.

That's the shape of the deliverable — a working local Claude session can take
that brief plus this document and build the whole thing end to end, including
the deployment. The rest of this doc is the detail behind each piece of that
brief.

## Architecture (what's generic vs. sport-specific)

```
server/
  cfbd_client.py   <- ONLY sport-specific file: talks to the upstream API
  filters.py       <- generic predicate query engine + penalty-text parsing
  main.py          <- FastAPI routes, all generic
static/
  index.html/.css/.js  <- generic UI (play-type multi-select, yards filter,
                           penalty toggle, results table, CSV export)
scripts/
  cfbd_explore.py  <- standalone, no-dependency script for exploring a new
                       API's vocabulary/fields before wiring up filters
```

The core design principle: **the query engine (`run_query` in `filters.py`)
doesn't know anything about football.** It filters a list of play dicts by
`playType` (OR-group), `yardsGained >= min_yards`, and optionally "does the
text contain a penalty/foul keyword, and which team does it name." That
generalizes to any sport whose data has a comparable shape: a list of discrete
plays/events, each with a type, a text description, a yardage-or-equivalent
stat, and two teams (offense/defense or equivalent).

**To port this to another sport, you mainly rewrite `cfbd_client.py`** (the
API client + caching) and adjust `filters.py`/`main.py` only where the new
API's field names or vocabulary genuinely differ.

## Step 0: find your sport's data source — and verify it before building

Before writing any app code, use `scripts/cfbd_explore.py` as a template for a
throwaway exploration script against your sport's API. Answer these questions
first, because assumptions here caused real bugs in the CFB version:

1. **What's the authoritative vocabulary for play/event types?** CFBD exposes
   `GET /plays/types`. Don't hand-guess type strings — pull the real list.
2. **What are the exact field names and casing?** Pull one raw record and
   read it directly. CFBD uses camelCase (`playType`, `playText`,
   `yardsGained`) — don't assume snake_case.
3. **Do server-side filters actually work?** We found CFBD's own `playType`
   query param on `/plays` silently returns zero rows for a type that
   demonstrably exists in the unfiltered data. **Don't trust a server-side
   filter until you've proven it against unfiltered data** — this app always
   pulls the full week and filters locally as a result.
4. **How does "penalty" (or your sport's foul/violation concept) show up in
   the text?** For CFBD, it's `"<Team> Penalty, <foul> ..."` — the team name
   comes *before* the keyword, not after (we initially assumed the opposite
   and it silently produced 0% attribution). Check a real sample before
   writing the regex in `filters.py`'s `penalized_side()`.
5. **Are violations/incidents also emitted as their own standalone event
   type**, separate from being embedded in another play's text? For CFBD,
   yes (`playType == "Penalty"`) — but those standalone rows are **not**
   reliably linkable back to a specific preceding play type (a false start
   can occur several plays before an unrelated punt, with no field tying them
   together). We deliberately chose to only count embedded penalties for a
   "penalties on play type X" query, and documented that as a known
   limitation rather than guessing at a linkage. Check whether your sport's
   API has the same ambiguity before assuming you can "just join on drive ID"
   or similar.

If you're pulling from an **external public API** (like CFBD), also check:

- **Rate limits / API key signup** — CFBD requires a free key from
  https://collegefootballdata.com/key. Your sport's equivalent will have its
  own signup process.
- **Corporate network TLS.** FanDuel's network intercepts TLS with its own
  root CA. Plain `httpx`/`urllib` calls can fail with
  `CERTIFICATE_VERIFY_FAILED` because the intercepting cert isn't in
  `certifi`'s bundle (it *is* trusted by Windows/the OS though).
  `cfbd_client.py` works around this with the `truststore` package, pointing
  `httpx` at the OS trust store — reuse that pattern.

If you're pulling from an **internal FanDuel dataset** instead of a public
API (e.g. NumberFire/Zack Attack data, or a Databricks table), you don't need
`truststore` or an API key/secret at all — check the `smi-core:query-zack-attack`
skill and related Databricks data-access skills for the approved patterns, and
consider whether OBO (on-behalf-of) auth is more appropriate than a single
shared credential in that case.

## Local dev setup

1. Get your API key (or internal data access), clone the repo, `cp
   .env.example .env` and paste it in.
2. `uv venv .venv` (or `python -m venv .venv`), then `uv pip install -r
   requirements.txt` (or `pip install -r requirements.txt`).
3. `uvicorn server.main:app --reload --port 8000`, open http://localhost:8000.

If you're behind FanDuel's network and hit TLS errors installing `uv` itself
or pulling packages, set `UV_SYSTEM_CERTS=1` in the environment for `uv`
commands — same root cause as above.

## Deployment (Databricks Apps)

This runs as a **plain Databricks App** — no SQL warehouse or Unity Catalog
access, since it never touches Databricks data directly (it's calling an
external API from the server). Key files:

- `app.py` / `app.yaml` — the app's own entry point (`python app.py`, which
  reads `DATABRICKS_APP_PORT` and binds uvicorn to `0.0.0.0` — **never
  `localhost`**, that causes 502s). `app.yaml` declares env vars injected
  from Databricks secrets via `valueFrom:`.
- `resources/<name>.app.yml` — the bundle's app resource: name (**≤26 chars,
  lowercase, hyphens only**), `source_code_path`, any secret resources, and
  the `permissions:` block (who can open the app — see below).
- `databricks.yml`, `shared/`, `pyproject.toml`, etc. — standard SMI/FanDuel
  DAB project scaffold, generated via the `databricks-setup-project` skill's
  `init_project.py`. Use the `smi-core:databricks-setup-config`,
  `databricks-setup-project`, and `databricks-define-resource` skills — they
  encode the org's conventions (secret scope patterns, `app.yml` schema,
  common gotchas) far better than reinventing it from scratch.

### The pattern for API keys

Don't use a plaintext env var. Create a Databricks secret scope and reference
it from the app resource:

```
databricks secrets create-scope <your_scope_name>
databricks secrets put-secret --json '{"scope": "<your_scope_name>", "key": "<your_key_name>", "string_value": "<the-actual-key>"}'
```

```yaml
# resources/<name>.app.yml
resources:
  apps:
    your-app-name:
      resources:
        - name: "your-api-key"
          secret:
            scope: <your_scope_name>
            key: <your_key_name>
            permission: "READ"
```

```yaml
# app.yaml
env:
  - name: YOUR_API_KEY
    valueFrom: your-api-key
```

### Deploy / redeploy / grant access

```
databricks bundle validate      # check syntax before touching the live app
databricks bundle deploy        # uploads code — does NOT restart the app
databricks bundle run <app-name>  # applies config + (re)starts it — required after deploy
```

**Access control** lives in the `permissions:` block of `resources/<name>.app.yml`
— it's not automatic. By default only your own service principal can open a
newly created app. To open it to everyone in the workspace:

```yaml
permissions:
  - service_principal_name: ${bundle.target}.your-app-name
    level: CAN_MANAGE
  - group_name: users
    level: CAN_USE
```

(Use a specific `group_name` or a list of `user_name` entries instead of
`users` if you want narrower access.) Verify after deploying:
`databricks apps get-permissions <app-name>`.

⚠️ Some Databricks CLI operations can silently wipe OBO `user_api_scopes` on
redeploy if your app uses them — re-check after every deploy if applicable.
This app doesn't use OBO at all (no per-user Databricks data access), so it
isn't affected, but it's a documented gotcha worth knowing if your sport's
version does need OBO.

## Known rough edges to expect (and re-verify for your sport)

- Any "attribute this event to a team by parsing text" logic is inherently
  fragile to wording changes in the source data. Keep — and check — an
  "unattributed" bucket rather than silently guessing.
- A stat like `yardsGained` can bundle in adjustments from a penalty on the
  same play, so a threshold filter can occasionally include a play that
  wouldn't otherwise qualify. Sanity-check a few edges after building your
  sport's equivalent filter.
- The results table needs `table-layout: fixed` with explicit column widths
  plus a horizontally-scrolling wrapper (`.table-scroll { overflow-x: auto }`)
  — without both, a long free-text column collapses to a tiny width and wraps
  into absurdly tall rows. Already fixed in `static/styles.css`; keep it if
  you're reusing the frontend as-is.

## Questions

Ping **Bruce Clouston** (bruce.clouston@fanduel.com) for repo access, a walk
through the architecture, or help with the first Databricks Apps deploy.

# Project Purpose · Phase One — working PILOT (SAMPLE DATA ONLY)

A working pilot of Jim Shields' relationship database + AI-agent dashboard, built to match the vendor brief
(section 7 acceptance tests) and The it Crowd proposal. **Every person, company, email, phone and URL is fictional.**
Emails use the reserved `.example` domain, phones use 555-01xx, all rows are tagged SAMPLE. No real Outlook,
LinkedIn, Microsoft 365 or AI model account is connected.

## Run it
```bash
cd /workspace/project-purpose/pilot
./run.sh                               # regenerates sample data, rebuilds DB, serves http://127.0.0.1:8765
.venv/bin/python tests/acceptance.py   # runs the section-7 acceptance tests on a fresh temp DB (prints PASS/FAIL)
.venv/bin/python screenshots.py        # re-captures screenshots/ from the running server (headless Chromium)
```
Stack: Python 3.13, FastAPI, SQLite, rapidfuzz, one HTML/JS page (no build step). Data: `data/pilot_SAMPLE.db`.

## What's in the box
| Path | What |
|---|---|
| `gen_sample.py` → `sample_data/` | 150 fictional people → `outlook_contacts_SAMPLE.csv` (109 rows, Outlook export columns + stub Graph ID), `linkedin_Connections_SAMPLE.csv` (105 rows, real Connections.csv layout incl. the "Notes:" preamble), `public_company_directory_SAMPLE.csv`, `public_updates_SAMPLE.json` (simulated monitor feed), `expected_SAMPLE.json` (answer key for tests). Built-in traps: 50 exact duplicates (same email / name+company / duplicate rows inside Outlook / conflicting titles), 8 nickname or typo variants (Jim↔James, "Emil"↔"Emily"), 6 job changes, 3 different people who share a name, plus missing emails, cities, titles and companies. |
| `pp/core.py` | Importers with source IDs + per-field provenance; dedupe/merge/unmerge; tiers; template bios; Monitor change proposals; Outlook write-back stub; audit log with revert. |
| `pp/query.py` | Filter engine + rule-based natural-language parser (shows the filters it used, and how many records were excluded because a field is Unknown). |
| `app.py`, `static/index.html` | Dashboard + JSON API. |
| `tests/acceptance.py`, `tests/last_run.txt` | The acceptance tests and the latest output. |
| `screenshots/` | Main screens. |

## How it maps to the brief
- **Provenance on every field:** Outlook = *Verified* (Jim's own records); LinkedIn export = *Participant-provided*; Outlook notes/categories, manual adds and private notes = *User note*; bios = *AI summary*; anything missing = *Unknown* (never guessed). Approved public-source corrections become *Verified* with the source URL, date and confidence.
- **Master record + source records:** every row stays in `source_record` unchanged (raw JSON + original Graph ID / LinkedIn URL + import batch). Merges move links, never data, so a merge can be reversed exactly.
- **Dedupe:** score ≥95 auto-links (same email, same LinkedIn URL, same full name + same company). Nicknames, near-name typos and same-name-different-company go to the review queue (Merge / Not the same person). Rejected pairs are not raised again. A manual add is never auto-merged.
- **Tiers 1–5:** rule-based, multi-attribute, each with a written evidence reason ("Past role: Founder, X 2003–2012 (Outlook notes)"). Tier 5 = insufficient information. Owner Priority (High/Medium/Low/None) and follow-up are owner-only. The code refuses any `agent:` actor, and every edit is logged.
- **Bios:** 2–4 sentence factual template built only from stored facts, with numbered citations. Gaps read "Unknown". Labeled AI summary / template mode.
- **Change detection:** the Monitor job reads the simulated public feed → proposals with source, date, confidence. Nothing applies until approved; optional Outlook write-back (stub) saves a before-image; Undo restores both.
- **Dashboard:** home (KPIs, recent changes, review items, stale profiles, segment mix), People & Ask (NL box + filters for source, industry, state, city, company, role, tier, priority, founder/owner, stale/follow-up/conflicts + CSV export), person card (details with provenance, conflicting values from other sources, bio + sources, tier reasons, private notes, source records, possible duplicates, history with Revert), review queue, recent changes/audit with Undo, add person, import (upload Outlook CSV / Connections.csv, run monitor).
- **Exports:** filtered CSV (`/api/export.csv`) and full JSON (`/api/export.json`: master, sources, field provenance, roles, decisions, audit). That JSON is the hand-off path for Eightfold / Project Purpose later.

## Real vs stubbed in this pilot
| Area | Pilot | Production |
|---|---|---|
| Outlook | Sample CSV in Outlook export format + stub Graph IDs; write-back goes to a simulated mailbox table | Microsoft Graph, delegated sign-in (User.Read, offline_access, Contacts.Read → Contacts.ReadWrite only when write-back is enabled), delta sync, before-image + conflict check on write-back |
| LinkedIn | Sample Connections.csv | Jim's own export uploaded on a set cadence (quarterly suggested). No API assumption, no scraping, no automation |
| Public-source monitor | Static JSON feed of 5 fictional findings | Scheduled checks of company sites, press releases, state/SEC filings and any licensed provider you choose, with citations |
| Industry | Sample company directory | Verified company reference data plus enrichment |
| Bios / NL questions | Deterministic templates + rule-based parser (no LLM key on the box) | Enterprise LLM (no training on data) for bios and question→filter translation, still citing sources and showing the filters |
| Auth / hosting | Local only, no login, binds 127.0.0.1 | Azure in Jim's tenant, Entra ID sign-in + MFA, named users, Key Vault secrets, managed Postgres (encrypted, nightly backups, PITR), private notes in a separate restricted partition, Graph read/write logging |
| Scale | ~150 people, in-process filtering | Indexed SQL/vector search, background jobs, monitoring |

No secrets are used or stored. Nothing here has been pushed to GitHub.

## Private share link (secret-link gate)
- `.share_token` (chmod 600, git-ignored) holds a random token. Opening `/?k=<token>` once sets an HttpOnly cookie (30 days) and redirects to `/`. Any request without a valid token or cookie gets a plain 404.
- **Reset demo** (header button, `POST /api/reset`) rebuilds the fictional sample database.
- `./start_public.sh` restarts the server and a Cloudflare quick tunnel and prints `https://<random>.trycloudflare.com/?k=<token>`. **On this box the tunnel cannot connect:** outbound QUIC/TCP 7844 to the Cloudflare edge is blocked (TLS EOF). Run it from a machine whose network allows it, or host the app elsewhere.
- Rotate the token: `rm .share_token && ./start_public.sh`. Old links and cookies stop working at once.

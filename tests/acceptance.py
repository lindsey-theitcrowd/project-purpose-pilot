"""Runs the brief's section-7 pilot acceptance tests against a FRESH database built from SAMPLE data.
Usage:  .venv/bin/python tests/acceptance.py
"""
import os, sys, csv, io, json, re, hashlib, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
TMP = os.path.join(tempfile.mkdtemp(), "acceptance_SAMPLE.db"); os.environ["PP_DB"] = TMP; os.environ["PP_NO_GATE"] = "1"
from fastapi.testclient import TestClient
import app as appmod
from pp import core, query
con = appmod.con; client = TestClient(appmod.app)
SD = os.path.join(HERE, "sample_data"); EXP = json.load(open(os.path.join(SD, "expected_SAMPLE.json")))
results = []

def test(name):
    def deco(fn):
        checks = []
        def ck(cond, msg): checks.append((bool(cond), msg))
        try: fn(ck)
        except Exception as e: checks.append((False, f"exception: {e!r}"))
        ok = all(c for c, _ in checks); results.append((name, ok))
        print(f"\n[{'PASS' if ok else 'FAIL'}] {name}")
        for c, m in checks: print(f"   {'✓' if c else '✗'} {m}")
        return fn
    return deco

def idx_of(source_id):  # generator index embedded in SAMPLE ids, used only by the test to play "human reviewer"
    m = re.search(r"SAMPLE-(\d{4})", source_id) or re.search(r"-(\d{4})$", source_id)
    return int(m.group(1)) - (1000 if "linkedin" in source_id else 0)

def raw_hash(): return hashlib.sha256("".join(r[0] for r in con.execute("SELECT raw_json FROM source_record WHERE source!='manual' ORDER BY id")).encode()).hexdigest()

@test("1a. Import from Outlook (Microsoft Graph stub: sample Outlook export with stub Graph IDs)")
def t1a(ck):
    rows = list(csv.DictReader(open(os.path.join(SD, "outlook_contacts_SAMPLE.csv"))))
    n = con.execute("SELECT count(*) FROM source_record WHERE source='outlook'").fetchone()[0]
    ck(n == len(rows) == EXP["outlook_rows"], f"Outlook record count reconciles: file {len(rows)} rows = {n} source records")
    ids = {r[0] for r in con.execute("SELECT source_id FROM source_record WHERE source='outlook'")}
    ck(ids == {r["Contact ID (Graph stub)"] for r in rows}, "Every original Outlook contact ID is preserved")
    ck(con.execute("SELECT count(*) FROM outlook_stub").fetchone()[0] == len(rows), "Simulated Outlook mailbox holds the same contacts (for reversible write-back)")
    prov = {r[0] for r in con.execute("SELECT DISTINCT provenance FROM field_value fv JOIN source_record s ON s.id=fv.source_record_id WHERE s.source='outlook'")}
    ck(prov <= {"Verified", "User note"}, f"Outlook fields carry provenance classes {sorted(prov)}")

@test("1b. Import from an authorized LinkedIn export (Connections.csv format)")
def t1b(ck):
    n = con.execute("SELECT count(*) FROM source_record WHERE source='linkedin'").fetchone()[0]
    ck(n == EXP["linkedin_rows"], f"LinkedIn record count reconciles: {EXP['linkedin_rows']} rows = {n} source records (export 'Notes:' preamble skipped)")
    urls = {r[0] for r in con.execute("SELECT source_id FROM source_record WHERE source='linkedin'")}
    ck(all(u.startswith("https://www.linkedin.com/in/sample-") for u in urls) and len(urls) == n, "Every LinkedIn profile URL kept as the source ID")
    prov = {r[0] for r in con.execute("SELECT DISTINCT provenance FROM field_value fv JOIN source_record s ON s.id=fv.source_record_id WHERE s.source='linkedin'")}
    ck(prov == {"Participant-provided"}, "LinkedIn fields labeled Participant-provided")
    orphans = con.execute("SELECT count(*) FROM person p WHERE status='active' AND NOT EXISTS (SELECT 1 FROM source_record s WHERE s.person_id=p.id)").fetchone()[0]
    ck(orphans == 0, "Every master record links to at least one original source record")

@test("2. Deduplication with a review queue and source-preserving master records")
def t2(ck):
    auto = con.execute("SELECT count(*) FROM match_candidate WHERE status='auto_merged'").fetchone()[0]
    exp_auto = len(EXP["auto_email"]) + len(EXP["auto_name_company"]) + len(EXP["title_conflict"]) + len(EXP["outlook_internal_dupe"])
    ck(auto == exp_auto, f"Exact matches auto-linked: {auto} (expected {exp_auto})")
    pend = [dict(r) for r in con.execute("SELECT * FROM match_candidate WHERE status='pending'")]
    exp_q = len(EXP["review_nickname"]) + len(EXP["review_job_change"]) + len(EXP["review_homonym"])
    ck(len(pend) == exp_q, f"Ambiguous pairs sent to review queue: {len(pend)} (expected {exp_q}: nicknames, job changes, same-name different people)")
    h0 = raw_hash(); approved = rejected = wrong = 0
    for m in pend:   # reviewer decision via the API, as a human would click it
        ia = {idx_of(x["source_id"]) for x in core.summary(con, m["person_a"], light=True)["source_records"]}
        ib = {idx_of(x["source_id"]) for x in core.summary(con, m["person_b"], light=True)["source_records"]}
        same = bool(ia & ib)
        r = client.post(f"/api/match/{m['id']}/{'approve' if same else 'reject'}"); wrong += r.status_code != 200
        approved += same; rejected += not same
    ck(wrong == 0 and rejected == len(EXP["review_homonym"]), f"Reviewer approved {approved} merges, rejected {rejected} 'not the same person' via the API")
    active = len(core.active_ids(con))
    ck(active == EXP["true_people"], f"Master records after review = {active} (true number of sample people = {EXP['true_people']})")
    ck(raw_hash() == h0 and con.execute("SELECT count(*) FROM source_record").fetchone()[0] == EXP["outlook_rows"] + EXP["linkedin_rows"],
       "Source records unchanged by merges (hash identical, none deleted)")
    last = con.execute("SELECT id, before_json FROM audit WHERE action='merge' ORDER BY id DESC LIMIT 1").fetchone()
    drop = json.loads(last["before_json"])["drop"]["id"]
    client.post(f"/api/audit/{last['id']}/revert")
    ck(len(core.active_ids(con)) == EXP["true_people"] + 1 and con.execute("SELECT status FROM person WHERE id=?", (drop,)).fetchone()[0] == "active",
       f"One merge reversed: record #{drop} split back out with its own source records")
    core.merge(con, json.loads(last["before_json"])["keep"]["id"], drop, "owner (pilot)"); con.commit()
    acts = {r[0] for r in con.execute("SELECT DISTINCT action FROM audit")}
    ck({"auto_merge", "merge", "reject_match", "revert"} <= acts, "All decisions logged (auto_merge, merge, reject_match, revert)")

@test("3. Factual summaries and role-based segments for a representative sample")
def t3(ck):
    ids = core.active_ids(con)[::6][:25]; bad_cite = guessed = 0
    for i in ids:
        s = core.summary(con, i); b = s["bio"]
        cites = {int(x) for x in re.findall(r"\[(\d+)\]", b["text"])}
        if not cites <= {x["n"] for x in b["sources"]}: bad_cite += 1
        if s["city"]["value"] == "Unknown" and "Location: Unknown" not in b["text"] and s["state"]["value"] == "Unknown": guessed += 1
        has_city = con.execute("SELECT 1 FROM field_value WHERE person_id=? AND field='city' AND is_current=1", (i,)).fetchone()
        if not has_city and s["city"]["value"] != "Unknown": guessed += 1
    ck(len(ids) == 25, "Spot-check sample of 25 records")
    ck(bad_cite == 0, "Every bio citation [n] points to a listed source")
    ck(guessed == 0, "Missing facts are shown as Unknown, never guessed")
    ck(all(core.summary(con, i)["bio"]["provenance"] == "AI summary" for i in ids), "Bios are labeled AI summary (template mode, no LLM key)")
    allsum = query.all_summaries(con)
    multi = sum(1 for s in allsum if len(s["tier_set"]) > 1)
    ck(multi > 0, f"Multi-segment preserved: {multi} people hold more than one tier")
    ck(all(t["reason"] for s in allsum for t in s["tiers"]), "Every segment has a written evidence reason")
    t5 = [s for s in allsum if s["tier_set"] == [5]]
    ck(t5 and all("Insufficient" in s["tiers"][0]["reason"] for s in t5), f"Tier 5 used only for insufficient information ({len(t5)} people)")
    ck({s["primary_tier"] for s in allsum} == {1, 2, 3, 4, 5}, "All five tiers represented")

@test("4. Natural-language queries, filters and editable owner priorities")
def t4(ck):
    rows = query.all_summaries(con)
    manual = {
        "Show contacts who founded or ran businesses in Texas": lambda s: s["ran_business"] and s["state"]["value"] == "TX",
        "Which people are in private equity?": lambda s: "Private Equity" in ({s["industry"]["value"]} | {r["industry"] for r in s["roles"]}),
        "Who is associated with manufacturing?": lambda s: "Manufacturing" in ({s["industry"]["value"]} | {r["industry"] for r in s["roles"]}),
    }
    for q, fn in manual.items():
        r = client.post("/api/ask", json={"q": q}).json()
        exp = {s["id"] for s in rows if fn(s)}
        ck({x["id"] for x in r["rows"]} == exp and r["chips"], f"“{q}” → {r['count']} people, matches manual filter; filters shown: {r['chips']}")
    r = client.get("/api/people", params={"industry": "Manufacturing", "state": "TX", "tier": "1"}).json()
    exp = {s["id"] for s in rows if s["industry"]["value"] == "Manufacturing" and s["state"]["value"] == "TX" and 1 in s["tier_set"]}
    ck({x["id"] for x in r["rows"]} == exp, f"Filter combination (Manufacturing + TX + Tier 1) → {r['count']} people, correct")
    pid = rows[0]["id"]
    client.post(f"/api/person/{pid}/priority", json={"priority": "High", "follow_up": True})
    client.post(f"/api/person/{pid}/priority", json={"priority": "Medium"})
    p = con.execute("SELECT owner_priority, follow_up FROM person WHERE id=?", (pid,)).fetchone()
    ck(p["owner_priority"] == "Medium" and p["follow_up"] == 1, "Owner Priority edited (None → High → Medium) and follow-up flag set")
    n = con.execute("SELECT count(*) FROM audit WHERE action='set_priority' AND entity_id=?", (pid,)).fetchone()[0]
    ck(n == 2, "Both priority edits logged in the audit trail")
    try: core.set_priority(con, pid, "Low", actor="agent:classify"); blocked = False
    except PermissionError: blocked = True
    ck(blocked and con.execute("SELECT count(*) FROM audit WHERE action='set_priority' AND actor LIKE 'agent%'").fetchone()[0] == 0,
       "AI agent is blocked from changing Owner Priority (never written by AI)")

@test("5. Public-information change detection, proposed correction and approval")
def t5(ck):
    props = [dict(r) for r in con.execute("SELECT * FROM change_proposal WHERE status='pending'")]
    ck(len(props) == 5 and all(p["source_url"] and p["found_date"] and p["confidence"] is not None for p in props),
       f"{len(props)} proposed corrections raised by the Monitor job, each with source URL, date and confidence")
    c = next(p for p in props if p["field"] == "title" and p["confidence"] > 0.9)
    before = core.summary(con, c["person_id"], light=True)["title"]["value"]
    ck(before == c["old_value"], f"Before approval the master record still says “{before}” (nothing auto-applied)")
    contact = next(x["source_id"] for x in core.summary(con, c["person_id"], light=True)["source_records"] if x["source"] == "outlook")
    ol_before = client.get(f"/api/outlook_stub/{contact}").json()["Job Title"]
    client.post(f"/api/change/{c['id']}/approve", json={"writeback": True})
    s = core.summary(con, c["person_id"], light=True)
    ck(s["title"]["value"] == c["new_value"] and s["title"]["provenance"] == "Verified" and s["title"]["source_url"] == c["source_url"],
       f"Approved: title now “{s['title']['value']}”, labeled Verified with source {s['title']['source_url']}")
    ck(client.get(f"/api/outlook_stub/{contact}").json()["Job Title"] == c["new_value"], "Optional Outlook write-back applied to the stub mailbox after approval")
    aid = con.execute("SELECT id FROM audit WHERE action='approve_change' AND entity_id=?", (c["id"],)).fetchone()[0]
    client.post(f"/api/audit/{aid}/revert")
    ck(core.summary(con, c["person_id"], light=True)["title"]["value"] == before and client.get(f"/api/outlook_stub/{contact}").json()["Job Title"] == ol_before,
       "Revert restored the prior master value AND the Outlook before-image")
    low = next(p for p in props if p["confidence"] < 0.5)
    client.post(f"/api/change/{low['id']}/reject")
    ck(con.execute("SELECT status FROM change_proposal WHERE id=?", (low["id"],)).fetchone()[0] == "rejected", "Low-confidence (42%) ambiguous proposal rejected; nothing changed")
    client.post(f"/api/change/{props[1]['id']}/approve", json={})  # leave one approved correction in the trail

@test("6. Manual add, export, audit trail and path to Eightfold / Project Purpose")
def t6(ck):
    r = client.post("/api/people", json={"first_name": "Avery", "last_name": "Testperson-SAMPLE", "title": "Founder", "company": "Sample Widget Works",
                                         "industry": "Manufacturing", "city": "Dallas", "state": "TX", "email": "avery@samplewidget.example",
                                         "relationship_origin": "Introduced by (sample) board contact at SAMPLE PE dinner", "owner_priority": "High",
                                         "note": "SAMPLE private note"}).json()
    s = core.summary(con, r["id"])
    ck(s["title"]["provenance"] == "User note" and s["relationship_origin"].startswith("Introduced"), "New person stored with provenance (User note) and relationship origin")
    ck(1 in s["tier_set"] and s["owner_priority"] == "High", "New person segmented (Tier 1, founder) and keeps owner-set priority")
    exist = core.summary(con, core.active_ids(con)[5], light=True)
    r2 = client.post("/api/people", json={"first_name": exist["name"].split()[0], "last_name": exist["name"].split()[-1], "company": exist["company"]["value"]}).json()
    ck(len(r2["possible_duplicates"]) >= 1, f"Adding a person who already exists ({exist['name']}) queues a possible duplicate instead of auto-merging")
    csv_text = client.get("/api/export.csv").text
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    ck(len(rows) == len(core.active_ids(con)) and "bio_ai_summary" in rows[0] and all(r["data_note"] == "SAMPLE DATA - fictional" for r in rows),
       f"CSV export complete and readable: {len(rows)} rows × {len(rows[0])} columns")
    j = client.get("/api/export.json").json()
    ck(all(k in j for k in ("person", "source_record", "field_value", "audit")), "Full JSON export (master, sources, provenance, audit) for portability / Eightfold hand-off")
    acts = {r[0] for r in con.execute("SELECT DISTINCT action FROM audit")}
    need = {"import", "auto_merge", "merge", "reject_match", "set_priority", "monitor_run", "approve_change", "reject_change", "revert", "add_person", "export"}
    ck(need <= acts, f"Audit trail covers every pilot action: {sorted(acts)}")

print("\n" + "=" * 60)
for n, ok in results: print(f"{'PASS' if ok else 'FAIL'}  {n}")
print(f"{sum(ok for _, ok in results)}/{len(results)} acceptance tests passed  (fresh DB: {TMP})")
sys.exit(0 if all(ok for _, ok in results) else 1)

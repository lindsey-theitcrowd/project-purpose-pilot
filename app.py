"""Project Purpose Phase One PILOT - local dashboard server (FAKE SAMPLE DATA ONLY)."""
import csv, io, json, os
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, PlainTextResponse, RedirectResponse
import hmac, tempfile
from pp.db import connect, DB_PATH
from pp import core, query, demo

if not os.path.exists(DB_PATH): demo.build(DB_PATH)
con = connect(DB_PATH)
app = FastAPI(title="Project Purpose Pilot (SAMPLE DATA)")
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, ".share_token")
SHARE_TOKEN = (os.environ.get("SHARE_TOKEN") or "").strip() or (open(TOKEN_FILE).read().strip() if os.path.exists(TOKEN_FILE) else None)
COOKIE = "pp_demo_k"

@app.middleware("http")
async def secret_link_gate(request: Request, call_next):
    """Private-link gate: valid ?k=<token> once -> HttpOnly cookie; anything else gets a plain 404."""
    if os.environ.get("PP_NO_GATE") == "1":
        return await call_next(request)
    if not SHARE_TOKEN:  # fail closed: no token configured -> nothing is served
        return PlainTextResponse("Not Found", status_code=404)
    qk = request.query_params.get("k")
    if qk and hmac.compare_digest(qk, SHARE_TOKEN):
        resp = RedirectResponse(url=request.url.path or "/", status_code=303)
        resp.set_cookie(COOKIE, SHARE_TOKEN, httponly=True, secure=True, samesite="lax", max_age=60 * 60 * 24 * 30)
        return resp
    ck = request.cookies.get(COOKIE)
    if ck and hmac.compare_digest(ck, SHARE_TOKEN):
        return await call_next(request)
    return PlainTextResponse("Not Found", status_code=404)

def filters_from(req: Request):
    qp = req.query_params; f = {}
    for k in ("state", "city", "industry", "priority", "source"):
        v = qp.getlist(k) or ([x for x in (qp.get(k) or "").split(",") if x])
        if v: f[k] = v
    for k in ("tier", "primary_tier"):
        if qp.get(k): f[k] = [int(x) for x in qp.get(k).split(",") if x]
    for k in ("founder_owner", "ran_business", "stale", "follow_up", "conflicts"):
        if qp.get(k) in ("1", "true", "yes"): f[k] = True
    if qp.get("company"): f["company"] = qp["company"]
    if qp.get("text"): f["text"] = qp["text"]
    if qp.get("role"): f["role_rx"] = [qp["role"]]
    if qp.get("industry_scope"): f["industry_scope"] = qp["industry_scope"]
    return f

def row(s):
    return {"id": s["id"], "name": s["name"], "title": s["title"]["value"], "title_prov": s["title"]["provenance"],
            "company": s["company"]["value"], "company_prov": s["company"]["provenance"], "industry": s["industry"]["value"],
            "city": s["city"]["value"], "state": s["state"]["value"], "sources": s["sources"], "tiers": s["tier_set"],
            "primary_tier": s["primary_tier"], "founder_owner": s["founder_owner"], "priority": s["owner_priority"],
            "follow_up": s["follow_up"], "stale": s["stale"], "conflicts": s["conflicts"], "last_checked": s["last_checked"]}

@app.get("/", response_class=HTMLResponse)
async def index(): return open(os.path.join(HERE, "static", "index.html")).read()

@app.get("/api/stats")
async def stats():
    rows = query.all_summaries(con)
    return {"people": len(rows), "source_records": con.execute("SELECT count(*) FROM source_record").fetchone()[0],
            "outlook_records": con.execute("SELECT count(*) FROM source_record WHERE source='outlook'").fetchone()[0],
            "linkedin_records": con.execute("SELECT count(*) FROM source_record WHERE source='linkedin'").fetchone()[0],
            "manual_records": con.execute("SELECT count(*) FROM source_record WHERE source='manual'").fetchone()[0],
            "pending_duplicates": con.execute("SELECT count(*) FROM match_candidate WHERE status='pending'").fetchone()[0],
            "auto_merged": con.execute("SELECT count(*) FROM match_candidate WHERE status='auto_merged'").fetchone()[0],
            "pending_corrections": con.execute("SELECT count(*) FROM change_proposal WHERE status='pending'").fetchone()[0],
            "stale": sum(1 for s in rows if s["stale"]), "follow_up": sum(1 for s in rows if s["follow_up"]),
            "conflicts": sum(1 for s in rows if s["conflicts"]),
            "tiers": {t: sum(1 for s in rows if s["primary_tier"] == t) for t in range(1, 6)},
            "stale_list": [row(s) for s in rows if s["stale"]][:8], "follow_list": [row(s) for s in rows if s["follow_up"]][:8],
            "llm": "none (rule-based parser + template summaries)"}

@app.get("/api/facets")
async def facets():
    rows = query.all_summaries(con)
    def vals(k): return sorted({s[k]["value"] for s in rows})
    return {"industry": vals("industry"), "state": vals("state"), "city": vals("city"), "company": vals("company"),
            "priority": core.PRIORITIES, "source": ["outlook", "linkedin", "manual"]}

@app.get("/api/people")
async def people(request: Request):
    f = filters_from(request); res, unknown = query.run_filters(con, f)
    return {"filters": f, "count": len(res), "excluded_unknown": unknown, "rows": [row(s) for s in res]}

@app.post("/api/ask")
async def ask(request: Request):
    q = (await request.json()).get("q", "")
    f, chips = query.parse_question(q); res, unknown = query.run_filters(con, f)
    return {"question": q, "parser": "rule-based (no LLM key configured)", "filters": f, "chips": chips, "count": len(res),
            "excluded_unknown": unknown, "rows": [row(s) for s in res]}

@app.get("/api/person/{pid}")
async def person(pid: int):
    s = core.summary(con, pid)
    if not s: raise HTTPException(404)
    s["history"] = [dict(r) for r in con.execute(
        "SELECT * FROM audit WHERE (entity='person' AND entity_id=?) OR (entity='change_proposal' AND entity_id IN (SELECT id FROM change_proposal WHERE person_id=?)) ORDER BY id DESC", (pid, pid))]
    s["duplicates"] = [dict(r) for r in con.execute("SELECT * FROM match_candidate WHERE person_a=? OR person_b=? ORDER BY id DESC", (pid, pid))]
    for d in s["duplicates"]:
        other = d["person_b"] if d["person_a"] == pid else d["person_a"]; o = core.summary(con, other, light=True)
        d["other"] = {"id": other, "name": o["name"], "company": o["company"]["value"], "title": o["title"]["value"]} if o else None
    s["proposals"] = [dict(r) for r in con.execute("SELECT * FROM change_proposal WHERE person_id=? ORDER BY id DESC", (pid,))]
    s["all_fields"] = [dict(r) for r in con.execute("SELECT field,value,provenance,source_label,source_url,as_of,confidence,is_current FROM field_value WHERE person_id=? ORDER BY field, is_current DESC, as_of DESC", (pid,))]
    for sr in s["source_records"]:
        sr["raw"] = json.loads(con.execute("SELECT raw_json FROM source_record WHERE id=?", (sr["id"],)).fetchone()[0])
    return s

@app.post("/api/person/{pid}/priority")
async def priority(pid: int, request: Request):
    b = await request.json(); core.set_priority(con, pid, b.get("priority"), b.get("follow_up")); return {"ok": True}

@app.post("/api/person/{pid}/note")
async def note(pid: int, request: Request):
    b = await request.json(); core.add_note(con, pid, b["text"]); return {"ok": True}

@app.post("/api/people")
async def add(request: Request):
    try: pid, dd = core.add_person(con, await request.json())
    except ValueError as e: raise HTTPException(400, str(e))
    return {"id": pid, "possible_duplicates": [dict(r) for r in con.execute("SELECT * FROM match_candidate WHERE (person_a=? OR person_b=?) AND status='pending'", (pid, pid))]}

@app.get("/api/review")
async def review():
    m = []
    for r in con.execute("SELECT * FROM match_candidate WHERE status='pending' ORDER BY score DESC, id"):
        d = dict(r); d["a"] = row(core.summary(con, r["person_a"], light=True)); d["b"] = row(core.summary(con, r["person_b"], light=True))
        for k in ("a", "b"):
            d[k]["source_ids"] = [x["source_id"] for x in core.summary(con, d[k]["id"], light=True)["source_records"]]
        m.append(d)
    c = []
    for r in con.execute("SELECT * FROM change_proposal WHERE status='pending' ORDER BY confidence DESC"):
        d = dict(r); s = core.summary(con, r["person_id"], light=True); d["person"] = s["name"]; d["has_outlook"] = "outlook" in s["sources"]; c.append(d)
    return {"duplicates": m, "corrections": c}

@app.post("/api/match/{mid}/{action}")
async def match(mid: int, action: str):
    try: core.decide_match(con, mid, action == "approve")
    except ValueError as e: raise HTTPException(400, str(e))
    return {"ok": True}

@app.post("/api/change/{cid}/{action}")
async def change(cid: int, action: str, request: Request):
    b = {}
    try: b = await request.json()
    except Exception: pass
    try: core.decide_change(con, cid, action == "approve", writeback=bool(b.get("writeback")), edited_value=b.get("value"))
    except ValueError as e: raise HTTPException(400, str(e))
    return {"ok": True}

@app.post("/api/monitor/run")
async def monitor(): return {"created": core.run_monitor(con, demo.load_updates())}

@app.post("/api/reset")
async def reset_demo():
    """Rebuild the fictional sample database from scratch (undoes everything a viewer did)."""
    global con
    tmp = DB_PATH + ".rebuild"
    c2, info = demo.build(tmp); demo.seed_activity(c2); c2.close()
    con.close(); os.replace(tmp, DB_PATH); con = connect(DB_PATH)
    return {"ok": True, "people": len(core.active_ids(con))}

@app.post("/api/dedupe/run")
async def dedupe(): return core.run_dedupe(con)

@app.get("/api/audit")
async def audit_log(limit: int = 200):
    return [dict(r) for r in con.execute("SELECT id,ts,actor,action,entity,entity_id,system,summary,reverted_by,reverts FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

@app.post("/api/audit/{aid}/revert")
async def revert(aid: int):
    try: return {"new_audit_id": core.revert(con, aid)}
    except ValueError as e: raise HTTPException(400, str(e))

@app.get("/api/outlook_stub/{contact_id}")
async def outlook_stub(contact_id: str):
    r = con.execute("SELECT data_json FROM outlook_stub WHERE contact_id=?", (contact_id,)).fetchone()
    if not r: raise HTTPException(404)
    return json.loads(r[0])

@app.post("/api/import/{source}")
async def do_import(source: str, file: UploadFile = File(...)):
    text = (await file.read()).decode("utf-8-sig")
    if source == "outlook": bid, n = core.import_outlook(con, text, file.filename)
    elif source == "linkedin": bid, n = core.import_linkedin(con, text, file.filename)
    else: raise HTTPException(400, "source must be outlook or linkedin")
    return {"batch": bid, "rows": n, "dedupe": core.run_dedupe(con)}

EXPORT_COLS = ["id", "name", "title", "title_provenance", "company", "company_provenance", "industry", "city", "state", "emails", "phones",
               "linkedin_url", "sources", "source_ids", "segments", "primary_segment", "founder_owner", "owner_priority", "follow_up",
               "relationship_origin", "last_checked", "stale", "bio_ai_summary", "data_note"]

@app.get("/api/export.csv")
async def export_csv(request: Request):
    f = filters_from(request); res, _ = query.run_filters(con, f)
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(EXPORT_COLS)
    for s0 in res:
        s = core.summary(con, s0["id"])
        w.writerow([s["id"], s["name"], s["title"]["value"], s["title"]["provenance"], s["company"]["value"], s["company"]["provenance"],
                    s["industry"]["value"], s["city"]["value"], s["state"]["value"], "; ".join(e["value"] for e in s["emails"]) or "Unknown",
                    "; ".join(p["value"] for p in s["phones"]) or "Unknown", s["linkedin_url"]["value"], ";".join(s["sources"]),
                    ";".join(x["source_id"] for x in s["source_records"]), ";".join(f"Tier {t}" for t in s["tier_set"]), f"Tier {s['primary_tier']}",
                    s["founder_owner"], s["owner_priority"], s["follow_up"], s["relationship_origin"], s["last_checked"], s["stale"],
                    s["bio"]["text"], "SAMPLE DATA - fictional"])
    core.audit(con, "owner (pilot)", "export", "export", None, f"Exported {len(res)} people to CSV (filters: {json.dumps(f)})"); con.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=project_purpose_export_SAMPLE.csv"})

@app.get("/api/export.json")
async def export_json():
    """Full portability export: master records, source records, field provenance, roles, decisions, audit."""
    out = {t: [dict(r) for r in con.execute(f"SELECT * FROM {t}")] for t in
           ("person", "source_record", "field_value", "role", "match_candidate", "change_proposal", "audit", "import_batch")}
    out["_note"] = "SAMPLE DATA - fictional"; return JSONResponse(out)

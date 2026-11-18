"""Core pilot logic: import, provenance, dedupe/merge, profiles/tiers, change detection, audit/undo.

All data handled here in the pilot is FAKE sample data.
"""
import csv, io, json, re, datetime
from rapidfuzz import fuzz
from .db import now, audit

PROV_RANK = {"User note": 0, "Verified": 1, "Participant-provided": 2, "AI summary": 3}
NICK = {"jim": "james", "jimmy": "james", "bob": "robert", "rob": "robert", "bobby": "robert", "mike": "michael",
        "bill": "william", "will": "william", "rick": "richard", "dick": "richard", "tom": "thomas", "chris": "christopher",
        "dan": "daniel", "danny": "daniel", "matt": "matthew", "tony": "anthony", "steve": "steven", "andy": "andrew",
        "drew": "andrew", "liz": "elizabeth", "beth": "elizabeth", "kate": "katherine", "katie": "katherine",
        "jen": "jennifer", "jenny": "jennifer", "becky": "rebecca", "greg": "gregory", "peggy": "margaret",
        "meg": "margaret", "josh": "joshua", "kev": "kevin", "dave": "david", "sue": "susan", "pat": "patricia"}
SERVICE_IND = {"Legal Services", "Accounting", "Consulting", "Marketing Services", "Insurance", "Banking", "Recruiting", "IT Services"}
STALE_DAYS = 365
TODAY = datetime.date.today()

# ---------------------------------------------------------------- helpers
def norm_first(s):
    s = re.sub(r"[^a-z]", "", (s or "").lower()); return NICK.get(s, s)

def norm_last(s): return re.sub(r"[^a-z]", "", (s or "").lower())

def norm_company_key(s):
    s = (s or "").lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(inc|llc|llp|lp|corp|corporation|co|company|ltd|group|n a|na)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def canonical_company(con, raw):
    raw = (raw or "").strip()
    if not raw: return ""
    key = norm_company_key(raw)
    for r in con.execute("SELECT name, alias FROM company_ref"):
        if key in (norm_company_key(r["name"]), norm_company_key(r["alias"])): return r["name"]
    return raw

def company_info(con, name):
    if not name: return None
    return con.execute("SELECT * FROM company_ref WHERE name=?", (name,)).fetchone()

def add_field(con, pid, field, value, prov, src_id, label, url=None, as_of=None, conf=None):
    value = (value or "").strip()
    if not value: return None
    return con.execute("INSERT INTO field_value(person_id,field,value,provenance,source_record_id,source_label,source_url,as_of,confidence,is_current,created_at)"
                       " VALUES(?,?,?,?,?,?,?,?,?,1,?)", (pid, field, value, prov, src_id, label, url, as_of, conf, now())).lastrowid

FOUNDER_RX = re.compile(r"\b(founder|co-founder|cofounder|owner|proprietor|principal|managing partner)\b", re.I)
RAN_RX = re.compile(r"(\bceo\b|chief executive|(?<!vice )\bpresident\b)", re.I)
CSUITE_RX = re.compile(r"(\bchief\b|\bcfo\b|\bcoo\b|\bcto\b|\bcio\b|\bcmo\b|\bceo\b)", re.I)

def add_role(con, pid, company, title, s, e, prov, label, url=None, src_id=None):
    t = title or ""
    return con.execute("INSERT INTO role(person_id,company,title,start_year,end_year,founder,owner,csuite,provenance,source_label,source_url,source_record_id,is_current)"
                       " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)",
                       (pid, company, title, s, e, int(bool(re.search(r"found", t, re.I))), int(bool(re.search(r"owner|proprietor|principal", t, re.I))),
                        int(bool(CSUITE_RX.search(t))), prov, label, url, src_id)).lastrowid

def new_person(con, name, origin=None):
    return con.execute("INSERT INTO person(display_name,created_at,relationship_origin) VALUES(?,?,?)", (name, now(), origin)).lastrowid

# ---------------------------------------------------------------- reference data + importers
def load_company_directory(con, path):
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            con.execute("INSERT OR REPLACE INTO company_ref VALUES(?,?,?,?,?,?,?)",
                        (r["Company"], r["Outlook Variant"], r["Domain"], r["Industry"], r["HQ City"], r["HQ State"], r["Source URL"]))
    con.commit()

def import_outlook(con, text, filename="outlook.csv", actor="owner (pilot)"):
    rows = list(csv.DictReader(io.StringIO(text)))
    bid = con.execute("INSERT INTO import_batch(source,filename,rows,imported_at) VALUES('outlook',?,?,?)", (filename, len(rows), now())).lastrowid
    for r in rows:
        cid = r.get("Contact ID (Graph stub)") or f"outlook-row-{bid}-{rows.index(r)}"
        origin = None
        m = re.search(r"(Met at [^.]+)\.", r.get("Notes", ""))
        if m: origin = m.group(1)
        pid = new_person(con, f"{r['First Name']} {r['Last Name']}".strip(), origin)
        sid = con.execute("INSERT INTO source_record(person_id,source,source_id,batch_id,raw_json,imported_at) VALUES(?,?,?,?,?,?)",
                          (pid, "outlook", cid, bid, json.dumps(r), now())).lastrowid
        con.execute("INSERT OR REPLACE INTO outlook_stub VALUES(?,?,?)", (cid, json.dumps(r), now()))
        L, asof = "Outlook contact (Jim's records)", r.get("Last Modified (stub)") or None
        for f, col in [("first_name", "First Name"), ("last_name", "Last Name"), ("title", "Job Title"),
                       ("city", "Business City"), ("state", "Business State"), ("email", "E-mail Address"),
                       ("email", "E-mail 2 Address"), ("phone", "Business Phone"), ("phone", "Mobile Phone")]:
            add_field(con, pid, f, r.get(col), "Verified", sid, L, None, asof)
        add_field(con, pid, "company", canonical_company(con, r.get("Company")), "Verified", sid, L, None, asof)
        cats = ";".join(c for c in (r.get("Categories") or "").split(";") if c and c != "SAMPLE")
        add_field(con, pid, "category", cats, "User note", sid, "Outlook category (set by Jim)", None, asof)
        add_field(con, pid, "note", r.get("Notes"), "User note", sid, "Outlook notes (private)", None, asof)
        for t, co, s, e in re.findall(r"Past: ([^,]+), (.+?) \((\d{4})-(\d{4})\)", r.get("Notes", "")):
            add_role(con, pid, canonical_company(con, co), t, int(s), int(e), "User note", "Outlook notes (Jim's records)", None, sid)
    audit(con, actor, "import", "import_batch", bid, f"Imported {len(rows)} Outlook contacts from {filename}", system="Outlook (stub)")
    con.commit(); return bid, len(rows)

def import_linkedin(con, text, filename="Connections.csv", actor="owner (pilot)", export_date=None):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("First Name,"))
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))
    export_date = export_date or TODAY.isoformat()
    bid = con.execute("INSERT INTO import_batch(source,filename,rows,imported_at) VALUES('linkedin',?,?,?)", (filename, len(rows), now())).lastrowid
    for r in rows:
        pid = new_person(con, f"{r['First Name']} {r['Last Name']}".strip())
        sid = con.execute("INSERT INTO source_record(person_id,source,source_id,batch_id,raw_json,imported_at) VALUES(?,?,?,?,?,?)",
                          (pid, "linkedin", r["URL"], bid, json.dumps(r), now())).lastrowid
        L = "LinkedIn Connections export"
        for f, col in [("first_name", "First Name"), ("last_name", "Last Name"), ("title", "Position"),
                       ("email", "Email Address"), ("linkedin_url", "URL"), ("connected_on", "Connected On")]:
            add_field(con, pid, f, r.get(col), "Participant-provided", sid, L, r["URL"] if f == "linkedin_url" else None, export_date)
        add_field(con, pid, "company", canonical_company(con, r.get("Company")), "Participant-provided", sid, L, None, export_date)
    audit(con, actor, "import", "import_batch", bid, f"Imported {len(rows)} LinkedIn connections from {filename}", system="LinkedIn export")
    con.commit(); return bid, len(rows)

# ---------------------------------------------------------------- person summary (provenance-aware)
def _best(vals):
    if not vals: return None
    vals = sorted(vals, key=lambda v: (v["as_of"] or "", -PROV_RANK.get(v["provenance"], 9)), reverse=True)
    b = dict(vals[0]); alts = []
    for v in vals[1:]:
        if v["value"].strip().lower() != b["value"].strip().lower() and v["value"] not in [a["value"] for a in alts]:
            alts.append(dict(v))
    b["alternatives"] = alts
    return b

UNKNOWN = {"value": "Unknown", "provenance": "Unknown", "source_label": None, "source_url": None, "as_of": None, "alternatives": []}

def summary(con, pid, light=False):
    p = con.execute("SELECT * FROM person WHERE id=?", (pid,)).fetchone()
    if not p: return None
    fv = [dict(r) for r in con.execute("SELECT * FROM field_value WHERE person_id=? AND is_current=1", (pid,))]
    by = {}
    for v in fv: by.setdefault(v["field"], []).append(v)
    best = {f: _best(v) for f, v in by.items()}
    g = lambda f: best.get(f) or dict(UNKNOWN)
    first, last = g("first_name"), g("last_name")
    name = f"{first['value'] if first['value'] != 'Unknown' else ''} {last['value'] if last['value'] != 'Unknown' else ''}".strip() or p["display_name"]
    company = g("company")
    ci = company_info(con, company["value"]) if company["value"] != "Unknown" else None
    if best.get("industry"): industry = best["industry"]
    elif ci: industry = {"value": ci["industry"], "provenance": "Verified", "source_label": "Public company directory (SAMPLE)",
                         "source_url": ci["source_url"], "as_of": "2026-11-01", "alternatives": []}
    else: industry = dict(UNKNOWN)
    roles = [dict(r) for r in con.execute("SELECT * FROM role WHERE person_id=? AND is_current=1 ORDER BY start_year", (pid,))]
    for r in roles:
        rc = company_info(con, r["company"]); r["industry"] = rc["industry"] if rc else None
    srcs = [dict(r) for r in con.execute("SELECT id,source,source_id,batch_id,imported_at FROM source_record WHERE person_id=?", (pid,))]
    title = g("title")
    t = title["value"] if title["value"] != "Unknown" else ""
    founder_cur = bool(FOUNDER_RX.search(t)); ran_cur = bool(RAN_RX.search(t))
    founder_past = [r for r in roles if r["founder"] or r["owner"] or FOUNDER_RX.search(r["title"] or "")]
    ran_past = [r for r in roles if RAN_RX.search(r["title"] or "")]
    founder_owner = founder_cur or bool(founder_past)
    cats = (g("category")["value"] if best.get("category") else "")
    # ---- tiers (evidence-based, multi-attribute, never a judgment of worth)
    def cite(v): return f"{v['source_label']}" + (f", as of {v['as_of']}" if v.get("as_of") else "")
    tiers = []
    if founder_cur or ran_cur: tiers.append({"tier": 1, "reason": f"Current title '{t}' ({cite(title)})"})
    for r in founder_past + [x for x in ran_past if x not in founder_past]:
        tiers.append({"tier": 1, "reason": f"Past role: {r['title']}, {r['company']} {r['start_year']}–{r['end_year']} ({r['source_label']})"})
    if re.search(r"(vice president|\bvp\b|\bsvp\b|\bevp\b|director|head of|general manager)", t, re.I):
        tiers.append({"tier": 2, "reason": f"Senior title '{t}' ({cite(title)})"})
    if industry["value"] in SERVICE_IND:
        tiers.append({"tier": 3, "reason": f"Professional-services firm: {company['value']} – {industry['value']} ({industry['source_label']})"})
    if re.search(r"\b(vendor|partner)\b", cats, re.I):
        tiers.append({"tier": 3, "reason": f"Tagged '{cats}' in Outlook categories (User note)"})
    if re.search(r"(chief (financial|operating|technology|information|marketing)|\bcfo\b|\bcoo\b|\bcto\b|controller|operations|plant manager|supply chain)", t, re.I):
        tiers.append({"tier": 4, "reason": f"Functional/operating title '{t}' ({cite(title)})"})
    if not tiers:
        tiers.append({"tier": 5, "reason": "Insufficient information to classify" + (f" (title '{t}')" if t else " (title Unknown)")})
    tier_set = sorted({x["tier"] for x in tiers})
    as_ofs = [v["as_of"] for v in fv if v["as_of"]]
    last_checked = max(as_ofs) if as_ofs else None
    stale = (not last_checked) or (datetime.date.fromisoformat(last_checked[:10]) < TODAY - datetime.timedelta(days=STALE_DAYS))
    emails = sorted({(v["value"].lower(), v["source_label"], v["provenance"]) for v in by.get("email", [])})
    phones = sorted({(v["value"], v["source_label"], v["provenance"]) for v in by.get("phone", [])})
    conflicts = [f for f in ("title", "company", "city", "state", "first_name") if best.get(f) and best[f]["alternatives"]]
    out = dict(id=p["id"], name=name, status=p["status"], merged_into=p["merged_into"], title=title, company=company, industry=industry,
               city=g("city"), state=g("state"), linkedin_url=g("linkedin_url"), connected_on=g("connected_on"),
               category=g("category"), emails=[{"value": e, "source": s, "provenance": pr} for e, s, pr in emails],
               phones=[{"value": e, "source": s, "provenance": pr} for e, s, pr in phones],
               sources=sorted({s["source"] for s in srcs}), source_records=srcs, roles=roles,
               founder_owner=founder_owner, ran_business=founder_owner or ran_cur or bool(ran_past),
               tiers=tiers, tier_set=tier_set, primary_tier=min(tier_set), owner_priority=p["owner_priority"],
               priority_set_by=p["priority_set_by"], priority_set_at=p["priority_set_at"], follow_up=bool(p["follow_up"]),
               relationship_origin=p["relationship_origin"] or "Unknown", last_checked=last_checked, stale=stale, conflicts=conflicts)
    if not light:
        out["notes"] = [dict(v) for v in by.get("note", [])]
        out["bio"] = make_bio(out)
    return out

def make_bio(s):
    """Deterministic factual 'template summary'. No LLM key is configured in the pilot, so the
    agent assembles the bio only from stored facts and cites each one; gaps read 'Unknown'."""
    cites, sents = [], []
    def c(v):
        if not v or v.get("provenance") == "Unknown": return ""
        key = (v.get("source_label"), v.get("source_url"))
        if key not in cites: cites.append(key)
        return f"[{cites.index(key) + 1}]"
    t, co = s["title"], s["company"]
    if t["value"] != "Unknown" and co["value"] != "Unknown": sents.append(f"{s['name']} is {t['value']} at {co['value']}{c(t)}{c(co) if co.get('source_label') != t.get('source_label') else ''}.")
    elif co["value"] != "Unknown": sents.append(f"{s['name']} is listed at {co['value']}{c(co)}; current title is Unknown.")
    elif t["value"] != "Unknown": sents.append(f"{s['name']}'s title is {t['value']}{c(t)}; current company is Unknown.")
    else: sents.append(f"{s['name']}: current role and company are Unknown.")
    if s["roles"]:
        parts = []
        for r in s["roles"]:
            parts.append(f"{r['title']} of {r['company']} ({r['start_year']}–{r['end_year']})" +
                         c({"source_label": r["source_label"], "source_url": r["source_url"], "provenance": r["provenance"]}))
        sents.append("Past experience: " + "; ".join(parts) + ".")
    else:
        sents.append("Past leadership or founder experience: Unknown.")
    loc = ", ".join(x["value"] for x in (s["city"], s["state"]) if x["value"] != "Unknown")
    sents.append(f"Sector: {s['industry']['value']}{c(s['industry'])}. Location: {loc + c(s['city'] if s['city']['value'] != 'Unknown' else s['state']) if loc else 'Unknown'}.")
    rel = []
    if s["category"]["value"] != "Unknown": rel.append(f"Outlook category '{s['category']['value']}'{c(s['category'])}")
    if s["connected_on"]["value"] != "Unknown": rel.append(f"LinkedIn connection since {s['connected_on']['value']}{c(s['connected_on'])}")
    if s["relationship_origin"] != "Unknown": rel.append(s["relationship_origin"])
    sents.append("Relationship context: " + ("; ".join(rel) if rel else "Unknown") + ".")
    return {"text": " ".join(sents), "sources": [{"n": i + 1, "label": l, "url": u} for i, (l, u) in enumerate(cites)],
            "provenance": "AI summary", "mode": "template (no LLM key configured; assembled only from stored facts)"}

def active_ids(con):
    return [r[0] for r in con.execute("SELECT id FROM person WHERE status='active' ORDER BY id")]

# ---------------------------------------------------------------- dedupe
def _keys(con, pid):
    rows = con.execute("SELECT field,value FROM field_value WHERE person_id=? AND is_current=1", (pid,)).fetchall()
    k = {"first": set(), "first_raw": set(), "last": set(), "email": set(), "li": set(), "company": set(), "full": set()}
    for r in rows:
        if r["field"] == "first_name": k["first"].add(norm_first(r["value"])); k["first_raw"].add(r["value"].lower())
        elif r["field"] == "last_name": k["last"].add(norm_last(r["value"]))
        elif r["field"] == "email": k["email"].add(r["value"].lower())
        elif r["field"] == "linkedin_url": k["li"].add(r["value"].lower())
        elif r["field"] == "company": k["company"].add(norm_company_key(r["value"]))
    k["full"] = {f"{f} {l}" for f in k["first"] for l in k["last"]}
    return k

def score_pair(a, b):
    if a["email"] & b["email"]: return 100, "Same email address: " + ", ".join(sorted(a["email"] & b["email"]))
    if a["li"] & b["li"]: return 100, "Same LinkedIn profile URL"
    same_co = bool(a["company"] & b["company"])
    if a["full"] & b["full"]:
        if same_co:
            if a["first_raw"] & b["first_raw"]: return 95, "Same full name and same company"
            return 85, f"Nickname match ({'/'.join(sorted(a['first_raw'] | b['first_raw']))}) at the same company"
        if not a["company"] or not b["company"]: return 55, "Same name; company is Unknown on one record"
        return 60, "Same name, different company: possible job change OR a different person"
    best = max((fuzz.token_sort_ratio(x, y) for x in a["full"] for y in b["full"]), default=0)
    if best >= 88:
        co = max((fuzz.ratio(x, y) for x in a["company"] for y in b["company"]), default=0)
        if co >= 85: return 75, f"Similar name ({best:.0f}% match) and similar company ({co:.0f}%)"
    return 0, ""

def resolve(con, pid):
    while True:
        r = con.execute("SELECT status, merged_into FROM person WHERE id=?", (pid,)).fetchone()
        if r and r["status"] == "merged" and r["merged_into"]: pid = r["merged_into"]
        else: return pid

def find_candidates(con):
    ids = active_ids(con); keys = {i: _keys(con, i) for i in ids}
    by_last, by_email = {}, {}
    for i, k in keys.items():
        for l in k["last"]: by_last.setdefault(l, []).append(i)
        for e in k["email"]: by_email.setdefault(e, []).append(i)
    pairs = set()
    for grp in list(by_last.values()) + list(by_email.values()):
        for x in grp:
            for y in grp:
                if x < y: pairs.add((x, y))
    out = []
    for a, b in sorted(pairs):
        s, why = score_pair(keys[a], keys[b])
        if s: out.append((a, b, s, why))
    return out

def run_dedupe(con, auto_threshold=95, actor="agent:reconcile"):
    auto = queued = 0
    for _ in range(5):
        merged_any = False
        for a, b, s, why in find_candidates(con):
            a, b = resolve(con, a), resolve(con, b)
            if a == b: continue
            seen = con.execute("SELECT status FROM match_candidate WHERE ((person_a=? AND person_b=?) OR (person_a=? AND person_b=?)) AND status IN ('pending','rejected')", (a, b, b, a)).fetchone()
            if seen: continue
            if s >= auto_threshold:
                mid = con.execute("INSERT INTO match_candidate(person_a,person_b,score,reasons,status,decided_by,decided_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
                                  (a, b, s, why, "auto_merged", actor, now(), now())).lastrowid
                merge(con, a, b, actor, mid, auto=True); auto += 1; merged_any = True
            else:
                con.execute("INSERT INTO match_candidate(person_a,person_b,score,reasons,status,created_at) VALUES(?,?,?,?,?,?)", (a, b, s, why, "pending", now()))
                queued += 1
        if not merged_any: break
    con.commit(); return {"auto_merged": auto, "queued_for_review": queued}

def merge(con, keep, drop, actor, candidate_id=None, auto=False):
    keep, drop = min(keep, drop), max(keep, drop)
    kp = dict(con.execute("SELECT * FROM person WHERE id=?", (keep,)).fetchone()); dp = dict(con.execute("SELECT * FROM person WHERE id=?", (drop,)).fetchone())
    moved = {t: [r[0] for r in con.execute(f"SELECT id FROM {t} WHERE person_id=?", (drop,))] for t in ("source_record", "field_value", "role")}
    for t in moved: con.execute(f"UPDATE {t} SET person_id=? WHERE person_id=?", (keep, drop))
    upd = {}
    if (kp["owner_priority"] in (None, "None")) and dp["owner_priority"] not in (None, "None"): upd["owner_priority"] = dp["owner_priority"]
    if not kp["relationship_origin"] and dp["relationship_origin"]: upd["relationship_origin"] = dp["relationship_origin"]
    if dp["follow_up"] and not kp["follow_up"]: upd["follow_up"] = 1
    for k, v in upd.items(): con.execute(f"UPDATE person SET {k}=? WHERE id=?", (v, keep))
    con.execute("UPDATE person SET status='merged', merged_into=? WHERE id=?", (keep, drop))
    # other pending candidates pointing at the dropped record now point at the master
    con.execute("UPDATE match_candidate SET person_a=? WHERE person_a=? AND status='pending'", (keep, drop))
    con.execute("UPDATE match_candidate SET person_b=? WHERE person_b=? AND status='pending'", (keep, drop))
    con.execute("DELETE FROM match_candidate WHERE status='pending' AND person_a=person_b")
    audit(con, actor, "auto_merge" if auto else "merge", "person", keep,
          f"{'Auto-merged' if auto else 'Merged'} #{drop} into #{keep} ({kp['display_name']}); source records kept",
          before={"keep": kp, "drop": dp, "moved": moved, "candidate_id": candidate_id}, after={"keep_updates": upd})

def decide_match(con, mid, approve, actor="owner (pilot)"):
    m = con.execute("SELECT * FROM match_candidate WHERE id=?", (mid,)).fetchone()
    if not m or m["status"] != "pending": raise ValueError("Not a pending match")
    if approve:
        con.execute("UPDATE match_candidate SET status='approved', decided_by=?, decided_at=? WHERE id=?", (actor, now(), mid))
        merge(con, m["person_a"], m["person_b"], actor, mid)
    else:
        con.execute("UPDATE match_candidate SET status='rejected', decided_by=?, decided_at=? WHERE id=?", (actor, now(), mid))
        audit(con, actor, "reject_match", "match_candidate", mid, f"Not the same person: #{m['person_a']} vs #{m['person_b']}",
              before={"status": "pending"}, after={"status": "rejected"})
    con.commit()

# ---------------------------------------------------------------- change detection (Monitor job)
OUTLOOK_COL = {"title": "Job Title", "company": "Company", "city": "Business City", "state": "Business State"}

def find_person_by(con, match):
    for f, key in (("email", "email"), ("linkedin_url", "linkedin_url")):
        if match.get(key):
            r = con.execute("SELECT person_id FROM field_value WHERE field=? AND lower(value)=lower(?)", (f, match[key])).fetchone()
            if r: return resolve(con, r[0])
    return None

def run_monitor(con, updates, actor="agent:monitor"):
    created = 0
    for u in updates:
        pid = find_person_by(con, u["match"])
        if not pid: continue
        s = summary(con, pid, light=True)
        old = s[u["field"]]["value"] if u["field"] in ("title", "company", "city", "state") else "(none)"
        if old == u["new_value"]: continue
        if con.execute("SELECT 1 FROM change_proposal WHERE person_id=? AND field=? AND new_value=?", (pid, u["field"], u["new_value"])).fetchone(): continue
        con.execute("INSERT INTO change_proposal(person_id,field,old_value,new_value,source_name,source_url,found_date,confidence,note,status,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,'pending',?)", (pid, u["field"], old, u["new_value"], u["source_name"], u["source_url"],
                                                              u["found_date"], u["confidence"], u.get("note"), now()))
        created += 1
    audit(con, actor, "monitor_run", "change_proposal", None, f"Public-source check (SAMPLE feed): {created} proposed corrections raised; nothing applied")
    con.commit(); return created

def get_setting(con, k, default=None):
    r = con.execute("SELECT value FROM setting WHERE key=?", (k,)).fetchone(); return r[0] if r else default

def decide_change(con, cid, approve, actor="owner (pilot)", writeback=False, edited_value=None):
    c = con.execute("SELECT * FROM change_proposal WHERE id=?", (cid,)).fetchone()
    if not c or c["status"] != "pending": raise ValueError("Not a pending proposal")
    if not approve:
        con.execute("UPDATE change_proposal SET status='rejected', decided_by=?, decided_at=? WHERE id=?", (actor, now(), cid))
        audit(con, actor, "reject_change", "change_proposal", cid, f"Rejected proposed {c['field']} '{c['new_value']}' for #{c['person_id']}",
              before={"status": "pending"}, after={"status": "rejected"})
        con.commit(); return
    pid, val = c["person_id"], edited_value or c["new_value"]
    before, after = {}, {}
    if c["field"] == "past_role":
        t, co, s, e = [x.strip() for x in val.split("|")]
        after["role_id"] = add_role(con, pid, co, t, int(s), int(e), "Verified", c["source_name"], c["source_url"])
    else:
        ids = [r[0] for r in con.execute("SELECT id FROM field_value WHERE person_id=? AND field=? AND is_current=1 AND provenance!='User note'", (pid, c["field"]))]
        con.executemany("UPDATE field_value SET is_current=0 WHERE id=?", [(i,) for i in ids])
        before["deactivated_field_ids"] = ids
        after["field_id"] = add_field(con, pid, c["field"], val, "Verified", None, c["source_name"], c["source_url"], c["found_date"], c["confidence"])
        if writeback and c["field"] in OUTLOOK_COL:
            src = con.execute("SELECT source_id FROM source_record WHERE person_id=? AND source='outlook' ORDER BY id LIMIT 1", (pid,)).fetchone()
            if src:
                row = con.execute("SELECT data_json FROM outlook_stub WHERE contact_id=?", (src[0],)).fetchone()
                data = json.loads(row[0]); col = OUTLOOK_COL[c["field"]]
                after["outlook_writeback"] = {"contact_id": src[0], "column": col, "before": data.get(col), "after": val}
                data[col] = val
                con.execute("UPDATE outlook_stub SET data_json=?, updated_at=? WHERE contact_id=?", (json.dumps(data), now(), src[0]))
    con.execute("UPDATE change_proposal SET status='approved', decided_by=?, decided_at=? WHERE id=?", (actor, now(), cid))
    audit(con, actor, "approve_change", "change_proposal", cid,
          f"Approved {c['field']}: '{c['old_value']}' → '{val}' for #{pid} (source: {c['source_name']}, {c['found_date']}, confidence {c['confidence']:.0%})"
          + (" + Outlook write-back (stub)" if after.get("outlook_writeback") else ""),
          before=before, after=after, system="master database" + (" + Outlook (stub)" if after.get("outlook_writeback") else ""))
    con.commit()

# ---------------------------------------------------------------- owner actions
PRIORITIES = ["High", "Medium", "Low", "None"]

def set_priority(con, pid, priority=None, follow_up=None, actor="owner (pilot)"):
    if actor.startswith("agent"): raise PermissionError("The AI agent may never set Owner Priority")
    p = con.execute("SELECT owner_priority, follow_up, priority_set_by, priority_set_at FROM person WHERE id=?", (pid,)).fetchone()
    before = dict(p); new_p = priority if priority is not None else p["owner_priority"]
    if new_p not in PRIORITIES: raise ValueError("bad priority")
    new_f = int(follow_up) if follow_up is not None else p["follow_up"]
    con.execute("UPDATE person SET owner_priority=?, follow_up=?, priority_set_by=?, priority_set_at=? WHERE id=?", (new_p, new_f, actor, now(), pid))
    audit(con, actor, "set_priority", "person", pid, f"#{pid} {con.execute('SELECT display_name FROM person WHERE id=?', (pid,)).fetchone()[0]}: Owner Priority {before['owner_priority']} → {new_p}; follow-up {bool(before['follow_up'])} → {bool(new_f)}",
          before=before, after={"owner_priority": new_p, "follow_up": new_f})
    con.commit()

def add_note(con, pid, text, actor="owner (pilot)"):
    fid = add_field(con, pid, "note", text, "User note", None, f"Private note by {actor}", None, TODAY.isoformat())
    audit(con, actor, "add_note", "person", pid, "Added private user note", after={"field_id": fid}); con.commit(); return fid

def add_person(con, d, actor="owner (pilot)"):
    name = f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()
    if not name: raise ValueError("Name required")
    pid = new_person(con, name, d.get("relationship_origin") or None)
    sid = con.execute("INSERT INTO source_record(person_id,source,source_id,batch_id,raw_json,imported_at) VALUES(?,?,?,?,?,?)",
                      (pid, "manual", f"MANUAL-{pid}", None, json.dumps(d), now())).lastrowid
    L = f"Added manually by {actor}"
    for f in ("first_name", "last_name", "title", "city", "state", "email", "phone", "linkedin_url", "industry"):
        add_field(con, pid, f, d.get(f), "User note", sid, L, None, TODAY.isoformat())
    add_field(con, pid, "company", canonical_company(con, d.get("company")), "User note", sid, L, None, TODAY.isoformat())
    if d.get("note"): add_field(con, pid, "note", d["note"], "User note", sid, "Private note (manual add)", None, TODAY.isoformat())
    pr = d.get("owner_priority") or "None"
    con.execute("UPDATE person SET owner_priority=?, priority_set_by=?, priority_set_at=? WHERE id=?", (pr, actor, now(), pid))
    audit(con, actor, "add_person", "person", pid, f"Added {name} manually (origin: {d.get('relationship_origin') or 'Unknown'})", after={"person_id": pid, "data": d})
    con.commit()
    dd = run_dedupe(con, auto_threshold=101)  # never auto-merge a manual add; just queue possible duplicates
    return pid, dd

# ---------------------------------------------------------------- audit revert
def revert(con, aid, actor="owner (pilot)"):
    a = con.execute("SELECT * FROM audit WHERE id=?", (aid,)).fetchone()
    if not a: raise ValueError("No such audit event")
    if a["reverted_by"]: raise ValueError("Already reverted")
    b = json.loads(a["before_json"] or "null"); af = json.loads(a["after_json"] or "null")
    act = a["action"]
    if act in ("merge", "auto_merge"):
        drop = b["drop"]["id"]; keep = b["keep"]["id"]
        for t, ids in b["moved"].items():
            con.executemany(f"UPDATE {t} SET person_id=? WHERE id=?", [(drop, i) for i in ids])
        con.execute("UPDATE person SET status='active', merged_into=NULL WHERE id=?", (drop,))
        for k in (af or {}).get("keep_updates", {}): con.execute(f"UPDATE person SET {k}=? WHERE id=?", (b["keep"][k], keep))
        if b.get("candidate_id"): con.execute("UPDATE match_candidate SET status='reverted' WHERE id=?", (b["candidate_id"],))
        summ = f"Reversed merge: #{drop} split back out from #{keep}"
    elif act == "approve_change":
        if af.get("role_id"): con.execute("UPDATE role SET is_current=0 WHERE id=?", (af["role_id"],))
        if af.get("field_id"): con.execute("UPDATE field_value SET is_current=0 WHERE id=?", (af["field_id"],))
        con.executemany("UPDATE field_value SET is_current=1 WHERE id=?", [(i,) for i in b.get("deactivated_field_ids", [])])
        wb = af.get("outlook_writeback")
        if wb:
            row = con.execute("SELECT data_json FROM outlook_stub WHERE contact_id=?", (wb["contact_id"],)).fetchone()
            data = json.loads(row[0]); data[wb["column"]] = wb["before"]
            con.execute("UPDATE outlook_stub SET data_json=?, updated_at=? WHERE contact_id=?", (json.dumps(data), now(), wb["contact_id"]))
        con.execute("UPDATE change_proposal SET status='reverted' WHERE id=?", (a["entity_id"],))
        summ = "Reversed approved correction" + (" and restored Outlook (stub) before-image" if wb else "")
    elif act == "set_priority":
        con.execute("UPDATE person SET owner_priority=?, follow_up=?, priority_set_by=?, priority_set_at=? WHERE id=?",
                    (b["owner_priority"], b["follow_up"], b["priority_set_by"], b["priority_set_at"], a["entity_id"]))
        summ = f"Restored Owner Priority to {b['owner_priority']}"
    elif act in ("reject_match", "reject_change"):
        t = "match_candidate" if act == "reject_match" else "change_proposal"
        con.execute(f"UPDATE {t} SET status='pending', decided_by=NULL, decided_at=NULL WHERE id=?", (a["entity_id"],))
        summ = "Reopened rejected item for review"
    elif act == "add_person":
        con.execute("UPDATE person SET status='removed' WHERE id=?", (a["entity_id"],)); summ = "Removed manually added person (record kept, hidden)"
    elif act == "add_note":
        con.execute("UPDATE field_value SET is_current=0 WHERE id=?", (af["field_id"],)); summ = "Hid private note"
    else:
        raise ValueError(f"'{act}' events are informational and cannot be reverted")
    new = audit(con, actor, "revert", a["entity"], a["entity_id"], f"{summ} (reverts audit #{aid})", reverts=aid, system=a["system"])
    con.execute("UPDATE audit SET reverted_by=? WHERE id=?", (new, aid)); con.commit(); return new

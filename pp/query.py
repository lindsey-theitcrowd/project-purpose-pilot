"""Filters + natural-language question parsing.

No LLM key is configured in the pilot, so questions go through a transparent rule-based parser
that turns the question into the same structured filters the filter panel uses. The applied
filters are always returned so the answer can be checked.
"""
import re
from .core import summary, active_ids

STATES = {"texas": "TX", "colorado": "CO", "illinois": "IL", "georgia": "GA", "tennessee": "TN", "arizona": "AZ",
          "new york": "NY", "oklahoma": "OK", "california": "CA", "florida": "FL"}
CITIES = ["dallas", "fort worth", "plano", "austin", "houston", "san antonio", "denver", "chicago", "atlanta",
          "nashville", "phoenix", "oklahoma city"]
INDUSTRY_WORDS = {
    "private equity": "Private Equity", " pe ": "Private Equity", "manufactur": "Manufacturing", "software": "Software",
    "tech": "Software", "real estate": "Commercial Real Estate", "bank": "Banking", "legal": "Legal Services",
    "law": "Legal Services", "account": "Accounting", "cpa": "Accounting", "consult": "Consulting", "energy": "Energy",
    "oil": "Energy", "logistic": "Logistics", "freight": "Logistics", "construct": "Construction", "health": "Healthcare Services",
    "marketing": "Marketing Services", "insur": "Insurance", "nonprofit": "Nonprofit", "venture": "Venture Capital",
    "recruit": "Recruiting", "it services": "IT Services"}
ROLE_WORDS = {"ceo": "ceo|chief executive", "cfo": "cfo|chief financial", "coo": "coo|chief operating", "cto": "cto|chief technology",
              "vice president": "vice president|\\bvp\\b|svp", "vp": "vice president|\\bvp\\b|svp", "director": "director",
              "controller": "controller", "partner": "partner", "president": "president"}
TIER_WORDS = {"1%er": 1, "1%ers": 1, "tier 1": 1, "tier 2": 2, "tier 3": 3, "tier 4": 4, "tier 5": 5, "vendor": 3, "senior manager": 2,
              "enterprise leader": 2, "operator": 4}

def parse_question(q):
    s = " " + q.lower().strip().rstrip("?") + " "
    f, chips = {}, []
    if re.search(r"found|owner|owned|ran |run |ran a|business owner|entrepreneur|built", s):
        if re.search(r"ran |run |ran a|led ", s): f["ran_business"] = True; chips.append("Founder/Owner OR CEO/President (current or past) = yes")
        else: f["founder_owner"] = True; chips.append("Founder/Owner experience (current or past) = yes")
    for name, ab in STATES.items():
        if re.search(rf"\b{name}\b", s) or re.search(rf"\bin {ab.lower()}\b", s):
            f.setdefault("state", []).append(ab); chips.append(f"Location state = {ab}")
    for c in CITIES:
        if re.search(rf"\b{c}\b", s) and not (c == "oklahoma city" and False):
            f.setdefault("city", []).append(c.title()); chips.append(f"Location city = {c.title()}")
    for w, ind in INDUSTRY_WORDS.items():
        if w in s and ind not in f.get("industry", []):
            f.setdefault("industry", []).append(ind)
    if f.get("industry"):
        f["industry_scope"] = "current_or_past"
        chips.append(f"Industry = {' OR '.join(f['industry'])} (current company or past role)")
    for w, rx in ROLE_WORDS.items():
        if not re.search(rf"\b{w}s?\b", s): continue
        if w == "president" and "vice president" in s: continue
        if w == "vp" and "vice president" in s: continue
        if rx in f.get("role_rx", []): continue
        f.setdefault("role_rx", []).append(rx); chips.append(f"Current title matches '{w.upper() if len(w) <= 3 else w}'")
    for w, t in TIER_WORDS.items():
        if w in s: f.setdefault("tier", []).append(t); chips.append(f"Segment includes Tier {t}")
    m = re.search(r"\b(high|medium|low)[ -]priority\b|priority (high|medium|low)", s)
    if m: p = (m.group(1) or m.group(2)).title(); f["priority"] = [p]; chips.append(f"Owner Priority = {p}")
    if "linkedin" in s: f["source"] = ["linkedin"]; chips.append("Source includes LinkedIn")
    if "outlook" in s: f["source"] = f.get("source", []) + ["outlook"]; chips.append("Source includes Outlook")
    if "stale" in s or "out of date" in s: f["stale"] = True; chips.append("Stale profile = yes")
    if "follow" in s: f["follow_up"] = True; chips.append("Flagged for follow-up = yes")
    m = re.search(r"\b(?:at|work(?:s|ing)? (?:at|for)) ([a-z0-9&' ]{3,})$", s.strip())
    if m and not f.get("city") and not f.get("state"): f["company"] = m.group(1).strip(); chips.append(f"Company contains '{m.group(1).strip()}'")
    if not f:
        f["text"] = q.strip(); chips.append(f"Text search = '{q.strip()}' (no structured filter recognized)")
    return f, chips

def _match(s, f, ignore=None):
    ig = ignore or set()
    if f.get("founder_owner") and not s["founder_owner"]: return False
    if f.get("ran_business") and not s["ran_business"]: return False
    if f.get("state") and "state" not in ig and s["state"]["value"] not in f["state"]: return False
    if f.get("city") and "city" not in ig and s["city"]["value"] not in f["city"]: return False
    if f.get("industry") and "industry" not in ig:
        inds = {s["industry"]["value"]}
        if f.get("industry_scope") == "current_or_past": inds |= {r["industry"] for r in s["roles"] if r.get("industry")}
        if not inds & set(f["industry"]): return False
    if f.get("role_rx"):
        if not any(re.search(rx, s["title"]["value"], re.I) for rx in f["role_rx"]) or s["title"]["value"] == "Unknown": return False
    if f.get("tier") and not set(f["tier"]) & set(s["tier_set"]): return False
    if f.get("primary_tier") and s["primary_tier"] not in f["primary_tier"]: return False
    if f.get("priority") and s["owner_priority"] not in f["priority"]: return False
    if f.get("source") and not set(f["source"]) & set(s["sources"]): return False
    if f.get("company") and f["company"].lower() not in s["company"]["value"].lower(): return False
    if f.get("stale") and not s["stale"]: return False
    if f.get("follow_up") and not s["follow_up"]: return False
    if f.get("conflicts") and not s["conflicts"]: return False
    if f.get("text"):
        t = f["text"].lower(); hay = " ".join([s["name"], s["title"]["value"], s["company"]["value"], s["industry"]["value"],
                                              s["city"]["value"], " ".join(e["value"] for e in s["emails"])]).lower()
        if not all(w in hay for w in t.split()): return False
    return True

def all_summaries(con):
    return [summary(con, i, light=True) for i in active_ids(con)]

def run_filters(con, f, rows=None):
    rows = rows if rows is not None else all_summaries(con)
    res = [s for s in rows if _match(s, f)]
    unknown = {}
    for fld in ("state", "city", "industry"):
        if f.get(fld):
            unknown[fld] = sum(1 for s in rows if s[fld]["value"] == "Unknown" and _match(s, f, ignore={fld}))
    return res, unknown

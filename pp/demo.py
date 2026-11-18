"""Build a fresh pilot database from the SAMPLE files."""
import os, json
from .db import connect
from . import core

HERE = os.path.dirname(os.path.dirname(__file__))
SD = os.path.join(HERE, "sample_data")

def build(path=None, monitor=True):
    if path and os.path.exists(path): os.remove(path)
    con = connect(path)
    core.load_company_directory(con, os.path.join(SD, "public_company_directory_SAMPLE.csv"))
    o = core.import_outlook(con, open(os.path.join(SD, "outlook_contacts_SAMPLE.csv")).read(), "outlook_contacts_SAMPLE.csv")
    l = core.import_linkedin(con, open(os.path.join(SD, "linkedin_Connections_SAMPLE.csv")).read(), "linkedin_Connections_SAMPLE.csv")
    d = core.run_dedupe(con)
    m = core.run_monitor(con, load_updates()) if monitor else 0
    return con, {"outlook": o, "linkedin": l, "dedupe": d, "monitor": m}

def load_updates():
    return json.load(open(os.path.join(SD, "public_updates_SAMPLE.json")))["updates"]


def seed_activity(con):
    """Optional: a few owner actions so the demo's 'Recent changes' isn't empty."""
    from . import core
    for pid in core.active_ids(con)[:40:8]: core.set_priority(con, pid, "High", True)
    for pid in core.active_ids(con)[3:20:9]: core.set_priority(con, pid, "Medium")
    m = con.execute("SELECT id FROM match_candidate WHERE status='pending' AND reasons LIKE 'Nickname%' ORDER BY id LIMIT 1").fetchone()
    if m: core.decide_match(con, m[0], True)
    c = con.execute("SELECT id FROM change_proposal WHERE status='pending' AND field='company'").fetchone()
    if c: core.decide_change(con, c[0], True, writeback=True)

if __name__ == "__main__":
    import sys
    from .db import DB_PATH
    con, info = build(DB_PATH)
    if "--seed" in sys.argv: seed_activity(con)
    print(info)

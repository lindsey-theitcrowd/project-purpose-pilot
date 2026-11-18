import sqlite3, os, json, datetime

DB_PATH = os.environ.get("PP_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pilot_SAMPLE.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS person(
  id INTEGER PRIMARY KEY, display_name TEXT, status TEXT DEFAULT 'active', merged_into INTEGER,
  owner_priority TEXT DEFAULT 'None', priority_set_by TEXT, priority_set_at TEXT, follow_up INTEGER DEFAULT 0,
  relationship_origin TEXT, created_at TEXT, is_sample INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS import_batch(id INTEGER PRIMARY KEY, source TEXT, filename TEXT, rows INTEGER, imported_at TEXT);
CREATE TABLE IF NOT EXISTS source_record(
  id INTEGER PRIMARY KEY, person_id INTEGER, source TEXT, source_id TEXT, batch_id INTEGER, raw_json TEXT, imported_at TEXT);
CREATE TABLE IF NOT EXISTS field_value(
  id INTEGER PRIMARY KEY, person_id INTEGER, field TEXT, value TEXT, provenance TEXT, source_record_id INTEGER,
  source_label TEXT, source_url TEXT, as_of TEXT, confidence REAL, is_current INTEGER DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS role(
  id INTEGER PRIMARY KEY, person_id INTEGER, company TEXT, title TEXT, start_year INTEGER, end_year INTEGER,
  founder INTEGER, owner INTEGER, csuite INTEGER, provenance TEXT, source_label TEXT, source_url TEXT,
  source_record_id INTEGER, is_current INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS company_ref(name TEXT PRIMARY KEY, alias TEXT, domain TEXT, industry TEXT, hq_city TEXT, hq_state TEXT, source_url TEXT);
CREATE TABLE IF NOT EXISTS match_candidate(
  id INTEGER PRIMARY KEY, person_a INTEGER, person_b INTEGER, score INTEGER, reasons TEXT, status TEXT,
  decided_by TEXT, decided_at TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS change_proposal(
  id INTEGER PRIMARY KEY, person_id INTEGER, field TEXT, old_value TEXT, new_value TEXT, source_name TEXT,
  source_url TEXT, found_date TEXT, confidence REAL, note TEXT, status TEXT, decided_by TEXT, decided_at TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, action TEXT, entity TEXT, entity_id INTEGER, system TEXT,
  summary TEXT, before_json TEXT, after_json TEXT, reverted_by INTEGER, reverts INTEGER);
CREATE TABLE IF NOT EXISTS outlook_stub(contact_id TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS setting(key TEXT PRIMARY KEY, value TEXT);
"""

def now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()

def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con

def audit(con, actor, action, entity, entity_id, summary, before=None, after=None, system="master database", reverts=None):
    cur = con.execute(
        "INSERT INTO audit(ts,actor,action,entity,entity_id,system,summary,before_json,after_json,reverts) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (now(), actor, action, entity, entity_id, system, summary,
         json.dumps(before) if before is not None else None, json.dumps(after) if after is not None else None, reverts))
    return cur.lastrowid

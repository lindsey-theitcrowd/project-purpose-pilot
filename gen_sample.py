"""Generate FAKE sample data for the Project Purpose pilot.

Every person, company, email, phone and URL here is fictional. Emails use the
reserved .example domain, phones use the 555-01xx fiction range, and every row
is tagged SAMPLE. Deterministic (seeded) so tests are repeatable.
"""
import csv, json, random, os

random.seed(42)
OUT = os.path.join(os.path.dirname(__file__), "sample_data")
os.makedirs(OUT, exist_ok=True)

FIRST = ["James","Robert","Michael","William","David","Richard","Thomas","Christopher","Daniel","Matthew",
         "Anthony","Steven","Andrew","Joshua","Kevin","Brian","Jason","Ryan","Eric","Gregory",
         "Mary","Patricia","Jennifer","Elizabeth","Katherine","Susan","Jessica","Sarah","Karen","Nancy",
         "Lisa","Margaret","Sandra","Ashley","Emily","Michelle","Amanda","Melissa","Rebecca","Laura",
         "Carlos","Luis","Priya","Wei","Aisha","Omar","Elena","Hiroshi","Fatima","Mateo"]
LAST = ["Abernathy","Bellweather","Castellano","Dunmore","Ellsworth","Fairchild","Galloway","Hargrove",
        "Ingram","Jessup","Kensington","Lockhart","Merriweather","Northcutt","Ostrander","Pemberton",
        "Quarles","Ravenscroft","Stallworth","Thistlewood","Underhill","Vandermeer","Whitlock","Yarborough",
        "Zimmerly","Ashcombe","Blackwood","Cartwright","Delacroix","Everly","Fenwick","Greenleaf",
        "Holloway","Ivanova","Juarez-Pell","Kowalczyk","Lindqvist","Montague","Nakamura-Reyes","Okonkwo-Hale"]
NICK = {"James":"Jim","Robert":"Bob","Michael":"Mike","William":"Bill","Richard":"Rick","Thomas":"Tom",
        "Christopher":"Chris","Daniel":"Dan","Matthew":"Matt","Anthony":"Tony","Steven":"Steve","Andrew":"Andy",
        "Elizabeth":"Liz","Katherine":"Kate","Jennifer":"Jen","Rebecca":"Becky","Gregory":"Greg","Margaret":"Peggy"}

# Fictional companies: (name, domain, industry, hq_city, hq_state, outlook_variant)
COMPANIES = [
 ("Lone Star Forge Works","lonestarforge.example","Manufacturing","Fort Worth","TX","Lone Star Forge"),
 ("Bluebonnet Capital Partners","bluebonnetcap.example","Private Equity","Dallas","TX","Bluebonnet Capital"),
 ("Trinity Ridge Equity","trinityridge.example","Private Equity","Dallas","TX","Trinity Ridge Equity LLC"),
 ("Pecos Valley Holdings","pecosvalley.example","Private Equity","Houston","TX","Pecos Valley Holdings, Inc."),
 ("Red Mesa Fabrication","redmesafab.example","Manufacturing","San Antonio","TX","Red Mesa Fab"),
 ("Cobalt Line Plastics","cobaltline.example","Manufacturing","Chicago","IL","Cobalt Line Plastics Inc"),
 ("Granite Peak Industrial","granitepeak.example","Manufacturing","Denver","CO","Granite Peak Industrial Corp"),
 ("Northwind Logic","northwindlogic.example","Software","Austin","TX","Northwind Logic Inc."),
 ("Copperleaf Analytics","copperleaf.example","Software","Plano","TX","Copperleaf Analytics LLC"),
 ("Harbor Signal Systems","harborsignal.example","Software","Atlanta","GA","Harbor Signal"),
 ("Prairie Gate Realty","prairiegate.example","Commercial Real Estate","Dallas","TX","Prairie Gate Realty Group"),
 ("Summit Arch Properties","summitarch.example","Commercial Real Estate","Phoenix","AZ","Summit Arch Properties"),
 ("First Cedar Bank","firstcedar.example","Banking","Dallas","TX","First Cedar Bank N.A."),
 ("Mesquite Trust Company","mesquitetrust.example","Banking","Houston","TX","Mesquite Trust Co."),
 ("Holloway & Pratt LLP","hollowaypratt.example","Legal Services","Dallas","TX","Holloway and Pratt"),
 ("Keystone Ledger CPAs","keystoneledger.example","Accounting","Plano","TX","Keystone Ledger"),
 ("Brightwater Advisory","brightwater.example","Consulting","Chicago","IL","Brightwater Advisory Group"),
 ("Sagebrush Energy Partners","sagebrushenergy.example","Energy","Houston","TX","Sagebrush Energy"),
 ("Caprock Midstream","caprock.example","Energy","Oklahoma City","OK","Caprock Midstream LLC"),
 ("Ironhorse Freight","ironhorsefreight.example","Logistics","Fort Worth","TX","Ironhorse Freight Inc"),
 ("Tidewater Logistics Group","tidewaterlog.example","Logistics","Nashville","TN","Tidewater Logistics"),
 ("Cornerstone Builders","cornerstonebld.example","Construction","Dallas","TX","Cornerstone Builders Inc."),
 ("Hill Country Health Partners","hillcountryhealth.example","Healthcare Services","Austin","TX","Hill Country Health"),
 ("Lantern Street Marketing","lanternstreet.example","Marketing Services","Dallas","TX","Lantern Street"),
 ("Bulwark Mutual Insurance","bulwarkmutual.example","Insurance","Denver","CO","Bulwark Mutual"),
 ("Open Range Foundation","openrange.example","Nonprofit","Austin","TX","Open Range Fdn"),
 ("Silverline Ventures","silverlinevc.example","Venture Capital","New York","NY","Silverline Ventures LP"),
 ("Magnolia Precision Parts","magnoliaprecision.example","Manufacturing","Houston","TX","Magnolia Precision"),
 ("Westfork Search Partners","westfork.example","Recruiting","Dallas","TX","Westfork Search"),
 ("Quarry Point IT Services","quarrypoint.example","IT Services","Plano","TX","Quarry Point IT"),
]
LOC = [("Dallas","TX"),("Fort Worth","TX"),("Plano","TX"),("Austin","TX"),("Houston","TX"),("San Antonio","TX"),
       ("Denver","CO"),("Chicago","IL"),("Atlanta","GA"),("Nashville","TN"),("Phoenix","AZ"),("New York","NY"),
       ("Oklahoma City","OK")]
T1 = ["Founder & CEO","Co-Founder","Owner","Principal","Managing Partner","President & Owner","Founder","CEO"]
T2 = ["Senior Vice President, Sales","Vice President of Strategy","Regional Director","Managing Director",
      "Senior Vice President","General Manager","Head of Partnerships","Vice President, Enterprise Accounts"]
T4 = ["Chief Financial Officer","Chief Operating Officer","Controller","VP Operations","Plant Manager",
      "Director of Operations","Chief Technology Officer","Director of Supply Chain"]
T3SVC = ["Partner","Senior Associate","Relationship Manager","Account Executive","Senior Consultant","Engagement Manager"]
T5 = ["Analyst","Coordinator","","Retired","Board Volunteer"]
SERVICE_IND = {"Legal Services","Accounting","Consulting","Marketing Services","Insurance","Banking","Recruiting","IT Services"}
CATS = ["Client","Vendor","Board","Friend","Partner","Investor","Alumni","Event contact"]

def pick_title(ind):
    r = random.random()
    if ind in SERVICE_IND and r < 0.5: return random.choice(T3SVC)
    if r < 0.30: return random.choice(T1)
    if r < 0.55: return random.choice(T2)
    if r < 0.85: return random.choice(T4)
    return random.choice(T5)

names, seen = [], set()
while len(names) < 150:
    f, l = random.choice(FIRST), random.choice(LAST)
    if (f, l) in seen: continue
    seen.add((f, l)); names.append((f, l))
# Homonyms: three different real-world (fictional) people sharing a name -> should be REJECTED in review
for a, b in [(60, 105), (61, 106), (62, 107)]:
    names[b] = names[a]

people = []
for i, (f, l) in enumerate(names):
    c = random.choice(COMPANIES)
    if i in (105, 106, 107):  # make sure homonyms are at a different company and city
        while c[0] == people[i - 45]["company"][0]: c = random.choice(COMPANIES)
    title = pick_title(c[2])
    city, st = (c[3], c[4]) if random.random() < 0.6 else random.choice(LOC)
    p = dict(idx=i, first=f, last=l, company=c, title=title, city=city, state=st,
             email=f"{f.lower()}.{l.lower().replace('-', '')}@{c[1]}",
             phone=f"(214) 555-01{i % 100:02d}", mobile=f"(469) 555-01{(i * 7) % 100:02d}",
             url=f"https://www.linkedin.com/in/sample-{f.lower()}-{l.lower()}-{1000 + i}",
             past=None, category=random.choice(CATS))
    if random.random() < 0.3:
        pc = random.choice(COMPANIES)
        sy = random.randint(1998, 2012)
        p["past"] = (random.choice(["Founder", "Co-Founder", "Owner", "President", "VP Operations", "Director of Sales"]),
                     pc[0], sy, sy + random.randint(3, 9))
    people.append(p)

def connected_on(i):
    m = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return f"{(i % 27) + 1:02d} {m[i % 12]} {2015 + i % 11}"

OUT_HDR = ["Contact ID (Graph stub)","First Name","Middle Name","Last Name","Title","Suffix","Company","Department",
           "Job Title","Business Street","Business City","Business State","Business Postal Code",
           "Business Country/Region","Business Phone","Mobile Phone","E-mail Address","E-mail 2 Address",
           "Notes","Categories","Last Modified (stub)"]
outlook, linkedin = [], []

def outlook_row(p, cid, first=None, company=None, title=None, email=None, email2="", modified=None):
    notes = "SAMPLE DATA - fictional person."
    if p["past"]:
        t, co, s, e = p["past"]
        notes += f" Past: {t}, {co} ({s}-{e})."
    if p["idx"] % 9 == 0: notes += " Met at the SAMPLE Dallas Founders Breakfast."
    return {"Contact ID (Graph stub)": cid, "First Name": first or p["first"], "Middle Name": "", "Last Name": p["last"],
            "Title": "", "Suffix": "", "Company": p["company"][5] if company is None else company, "Department": "",
            "Job Title": p["title"] if title is None else title, "Business Street": "",
            "Business City": "" if p["idx"] % 11 == 0 else p["city"],
            "Business State": "" if p["idx"] % 11 == 0 else p["state"], "Business Postal Code": "",
            "Business Country/Region": "United States", "Business Phone": "" if p["idx"] % 5 == 0 else p["phone"],
            "Mobile Phone": p["mobile"] if p["idx"] % 3 == 0 else "", "E-mail Address": p["email"] if email is None else email,
            "E-mail 2 Address": email2, "Notes": notes, "Categories": f"SAMPLE;{p['category']}",
            "Last Modified (stub)": modified or f"{2019 + p['idx'] % 7}-{(p['idx'] % 12) + 1:02d}-15"}

def li_row(p, email="", company=None, title=None):
    return {"First Name": p["first"], "Last Name": p["last"], "URL": p["url"], "Email Address": email,
            "Company": p["company"][0] if company is None else company,
            "Position": p["title"] if title is None else title, "Connected On": connected_on(p["idx"])}

expected = {"auto_email": [], "auto_name_company": [], "review_nickname": [], "review_job_change": [],
            "review_homonym": [], "title_conflict": [], "outlook_internal_dupe": []}
for p in people:
    i, cid = p["idx"], f"AAMk-SAMPLE-{p['idx']:04d}"
    if i < 60:  # in both sources
        if i < 25:
            outlook.append(outlook_row(p, cid)); linkedin.append(li_row(p, email=p["email"])); expected["auto_email"].append(i)
        elif i < 40:
            outlook.append(outlook_row(p, cid, email="" if i % 2 else None)); linkedin.append(li_row(p)); expected["auto_name_company"].append(i)
        elif i < 48:  # nickname + company spelling variant -> review
            nick = NICK.get(p["first"], p["first"][:-1])  # nickname, or a typo when no common nickname
            outlook.append(outlook_row(p, cid, first=nick, email=""))
            linkedin.append(li_row(p)); expected["review_nickname"].append(i)
        elif i < 54:  # job change: Outlook has OLD company/title (older), LinkedIn has new -> review
            old = COMPANIES[(COMPANIES.index(p["company"]) + 7) % len(COMPANIES)]
            outlook.append(outlook_row(p, cid, company=old[5], title=random.choice(T2), email="", modified="2021-03-02"))
            linkedin.append(li_row(p)); expected["review_job_change"].append(i)
        else:  # same email, conflicting titles -> auto merge, conflict shown on card
            outlook.append(outlook_row(p, cid, title=random.choice(T2)))
            linkedin.append(li_row(p, email=p["email"])); expected["title_conflict"].append(i)
    elif i < 105:
        outlook.append(outlook_row(p, cid))
        if i < 64:  # duplicate row inside Outlook itself (same email, extra detail)
            outlook.append(outlook_row(p, f"AAMk-SAMPLE-{i:04d}-DUP", email2=f"{p['first'].lower()}@personal-sample.example"))
            expected["outlook_internal_dupe"].append(i)
    else:
        linkedin.append(li_row(p, email=p["email"] if i % 4 == 0 else "",
                               company="" if i % 13 == 0 else None))
        if i in (105, 106, 107): expected["review_homonym"].append(i)

with open(os.path.join(OUT, "outlook_contacts_SAMPLE.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=OUT_HDR); w.writeheader(); w.writerows(outlook)
with open(os.path.join(OUT, "linkedin_Connections_SAMPLE.csv"), "w", newline="") as fh:
    fh.write("Notes:\n\"SAMPLE DATA - fictional connections generated for the Project Purpose pilot. "
             "Mirrors LinkedIn's Connections.csv export format.\"\n\n")
    w = csv.DictWriter(fh, fieldnames=["First Name","Last Name","URL","Email Address","Company","Position","Connected On"])
    w.writeheader(); w.writerows(linkedin)
with open(os.path.join(OUT, "public_company_directory_SAMPLE.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["Company","Outlook Variant","Domain","Industry","HQ City","HQ State","Source URL"])
    for c in COMPANIES: w.writerow([c[0], c[5], c[1], c[2], c[3], c[4], f"https://{c[1]}/about"])

# Simulated public-source monitor feed (company sites / press releases / filings), all fictional
def pp_(i): return people[i]
updates = [
 {"match": {"linkedin_url": pp_(3)["url"]}, "field": "title", "new_value": "Chief Executive Officer",
  "source_name": "Company leadership page (SAMPLE)", "source_url": f"https://{pp_(3)['company'][1]}/leadership",
  "found_date": "2026-11-12", "confidence": 0.92, "note": "Leadership page lists new title."},
 {"match": {"email": pp_(10)["email"]}, "field": "company", "new_value": "Silverline Ventures",
  "source_name": "Press release (SAMPLE)", "source_url": "https://silverlinevc.example/news/new-partner",
  "found_date": "2026-11-05", "confidence": 0.88, "note": "Announced as joining Silverline Ventures."},
 {"match": {"email": pp_(70)["email"]}, "field": "city", "new_value": "Austin",
  "source_name": "State business filing (SAMPLE)", "source_url": "https://sos-sample.example/filings/123",
  "found_date": "2026-10-28", "confidence": 0.65, "note": "Registered agent address moved to Austin."},
 {"match": {"linkedin_url": pp_(120)["url"]}, "field": "past_role",
  "new_value": "Founder | Open Range Foundation | 2010 | 2016",
  "source_name": "Foundation history page (SAMPLE)", "source_url": "https://openrange.example/history",
  "found_date": "2026-11-09", "confidence": 0.81, "note": "Named as founder in organization history."},
 {"match": {"email": pp_(80)["email"]}, "field": "title", "new_value": "President",
  "source_name": "News mention (SAMPLE)", "source_url": "https://news-sample.example/article/77",
  "found_date": "2026-11-14", "confidence": 0.42, "note": "Low confidence: article names a person with this name; could be someone else."},
]
with open(os.path.join(OUT, "public_updates_SAMPLE.json"), "w") as fh:
    json.dump({"_comment": "SAMPLE simulated public-source monitor results. Fictional.", "updates": updates}, fh, indent=2)
with open(os.path.join(OUT, "expected_SAMPLE.json"), "w") as fh:
    json.dump({"outlook_rows": len(outlook), "linkedin_rows": len(linkedin), "true_people": 150, **expected}, fh, indent=2)
print(f"outlook rows={len(outlook)} linkedin rows={len(linkedin)} people=150")

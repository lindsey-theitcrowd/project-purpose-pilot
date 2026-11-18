"""Capture screenshots of the main pilot screens from the running local server."""
import asyncio, sys
from playwright.async_api import async_playwright
B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
OUT = "screenshots"

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch()
        pg = await br.new_page(viewport={"width": 1440, "height": 1000})
        import os
        tf = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".share_token")
        if os.path.exists(tf): await pg.goto(B + "/?k=" + open(tf).read().strip())
        async def shot(name, full=True):
            await pg.wait_for_timeout(700); await pg.screenshot(path=f"{OUT}/{name}.png", full_page=full)
        await pg.goto(B + "/#home"); await shot("01_home_dashboard")
        await pg.goto(B + "/#people"); await pg.wait_for_selector("#q")
        for i, q in enumerate(["Show contacts who founded or ran businesses in Texas", "Which people are in private equity?", "Who is associated with manufacturing?"]):
            await pg.fill("#q", q); await pg.click(".ask button"); await pg.wait_for_selector(".chip"); await shot(f"0{2 + i}_ask_{['founders_texas', 'private_equity', 'manufacturing'][i]}")
        await pg.select_option("#f_industry", "Manufacturing"); await pg.select_option("#f_tier", "1"); await pg.select_option("#f_state", "TX")
        await pg.click("text=Apply filters"); await shot("05_filters_manufacturing_tx_tier1")
        await pg.goto(B + "/#people"); await pg.wait_for_selector("#res table")
        await pg.evaluate("openP(55)"); await pg.wait_for_selector("#drawer h2")
        await pg.wait_for_timeout(600)
        await pg.evaluate("document.querySelector('#drawer').style.position='absolute';document.querySelector('#drawer').style.height='auto'")
        await shot("06_person_card_conflict")
        await pg.evaluate("openP(11)"); await pg.wait_for_timeout(600); await shot("07_person_card_approved_change")
        await pg.goto(B + "/#review"); await pg.reload(); await shot("08_review_queue_corrections", full=False)
        await pg.evaluate("[...document.querySelectorAll('h2')].find(h=>h.textContent.startsWith('Possible duplicates')).scrollIntoView()"); await shot("08b_review_queue_duplicates", full=False)
        await pg.goto(B + "/#changes"); await pg.reload(); await shot("09_recent_changes_audit", full=False)
        await pg.goto(B + "/#add"); await pg.reload(); await pg.wait_for_selector("#a_first_name")
        await pg.fill("#a_first_name", "Jordan"); await pg.fill("#a_last_name", "Example-SAMPLE"); await pg.fill("#a_title", "Owner")
        await pg.fill("#a_company", "Sample Saddle Co"); await pg.fill("#a_city", "Fort Worth"); await pg.fill("#a_state", "TX")
        await pg.fill("#a_relationship_origin", "Met at SAMPLE chamber lunch, introduced by a board contact")
        await shot("10_add_person_form")
        await pg.goto(B + "/#import"); await pg.reload(); await shot("11_import")
        await br.close()
asyncio.run(main())

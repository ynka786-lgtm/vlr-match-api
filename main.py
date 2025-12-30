"""
VLR.gg Custom Backend - Production Ready
Scrapes ALL upcoming matches with proper date extraction
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup
import re
from datetime import datetime
from typing import List, Dict

app = FastAPI(title="VLR Custom Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

@app.get("/")
async def root():
    return {"status": "ok", "message": "VLR Custom Backend v1.0"}

def parse_date_header(date_text: str) -> str:
    """Parse 'Thu, January 8, 2026' to '2026-01-08'"""
    try:
        if ',' in date_text:
            parts = date_text.split(',')
            date_str = ','.join(parts[1:]).strip()
        else:
            date_str = date_text.strip()
        
        parsed = datetime.strptime(date_str, "%B %d, %Y").date()
        return parsed.isoformat()
    except:
        return None

@app.get("/matches")
async def get_all_matches():
    """Get all upcoming matches from VLR.gg/matches with proper dates"""
    url = "https://www.vlr.gg/matches"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    soup = BeautifulSoup(response.text, "lxml")
    matches = []
    current_date = "2026-01-08"
    
    # Find the main mod-dark container - all matches and dates are inside it
    main_container = soup.select_one(".mod-dark")
    if not main_container:
        raise HTTPException(status_code=500, detail="Could not find matches")
    
    # Find all div children - dates are in divs with month names
    # Then find match cards that follow
    for elem in main_container.find_all():
        # Check for date headers (they're divs with text like "Thu, January 8, 2026")
        if elem.name == 'div':
            elem_text = elem.get_text(strip=True)
            if any(month in elem_text for month in ['January', 'February', 'March', 'April', 'May', 'June',
                                                     'July', 'August', 'September', 'October', 'November', 'December']):
                if ',' in elem_text and re.search(r'\d{1,2}', elem_text):
                    parsed = parse_date_header(elem_text)
                    if parsed:
                        current_date = parsed
                        continue
        
        # Find match items in wf-card divs
        if elem.name == 'div' and 'wf-card' in elem.get('class', []):
            for item in elem.select(".match-item"):
                try:
                    href = item.get("href", "")
                    match_id = re.search(r'/(\d+)/', href)
                    if not match_id:
                        continue
                    match_id = match_id.group(1)
                    
                    teams = []
                    for team_el in item.select(".match-item-vs-team-name")[:2]:
                        team = team_el.get_text(strip=True)
                        if team:
                            teams.append(team)
                    
                    if len(teams) < 2:
                        continue
                    
                    event_el = item.select_one(".match-item-event")
                    event = event_el.get_text(strip=True) if event_el else "VCT"
                    
                    start_time = current_date
                    time_el = item.select_one(".match-item-time")
                    if time_el and time_el.get("data-utc-ts"):
                        try:
                            ts = int(time_el.get("data-utc-ts"))
                            start_time = datetime.utcfromtimestamp(ts).isoformat()
                        except:
                            pass
                    
                    matches.append({
                        "id": match_id,
                        "team1": teams[0],
                        "team2": teams[1],
                        "event": event,
                        "start_time": start_time
                    })
                except Exception as e:
                    print(f"Error: {e}")
                    continue
    
    return {"matches": matches}

@app.get("/match/{match_id}")
async def get_match(match_id: str):
    """Get detailed match info with player stats"""
    url = f"https://www.vlr.gg/{match_id}"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except:
            raise HTTPException(status_code=404, detail="Match not found")
    
    soup = BeautifulSoup(response.text, "lxml")
    
    # Teams
    teams = []
    team_els = soup.select(".match-header-link-name .wf-title-med")
    score_els = soup.select(".match-header-vs-score .js-spoiler span")
    
    for i, el in enumerate(team_els[:2]):
        score = score_els[i].get_text(strip=True) if i < len(score_els) else "0"
        teams.append({"name": el.get_text(strip=True), "score": score})
    
    # Check if upcoming
    is_upcoming = len(soup.select(".vm-stats-game")) == 0
    
    # Maps
    maps = []
    for map_container in soup.select(".vm-stats-game"):
        map_name_el = map_container.select_one(".map div:first-child")
        map_name = map_name_el.get_text(strip=True) if map_name_el else "Unknown"
        
        players = []
        for table_idx, table in enumerate(map_container.select("table.wf-table-inset")):
            for row in table.select("tbody tr"):
                try:
                    name_el = row.select_one(".text-of")
                    if not name_el:
                        continue
                    
                    stats = row.select("td.mod-stat span.mod-both")
                    rating = float((stats[0].get_text(strip=True) or "0")) if len(stats) > 0 else 0
                    kills = int((stats[2].get_text(strip=True) or "0")) if len(stats) > 2 else 0
                    deaths = int((stats[3].get_text(strip=True) or "0")) if len(stats) > 3 else 0
                    assists = int((stats[4].get_text(strip=True) or "0")) if len(stats) > 4 else 0
                    
                    players.append({
                        "name": name_el.get_text(strip=True),
                        "team": teams[table_idx]["name"] if table_idx < len(teams) else "Unknown",
                        "rating": rating,
                        "kills": kills,
                        "deaths": deaths,
                        "assists": assists
                    })
                except:
                    continue
        
        maps.append({"map": map_name, "players": players})
    
    return {
        "id": match_id,
        "teams": teams,
        "maps": maps,
        "is_upcoming": is_upcoming
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

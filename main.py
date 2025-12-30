"""
Fixed VLR.gg Scraper - Optimized for speed and reliability
This version fixes the /matches endpoint and adds better error handling
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
import asyncio

app = FastAPI(title="VLR Match API Fixed", version="3.0.0")

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
    return {
        "status": "ok",
        "message": "VLR.gg Scraper API v3.0 - Fixed",
        "endpoints": [
            "/matches - Fast, all upcoming matches with dates",
            "/match/{id} - Match details with player stats",
            "/live - Live match scores"
        ]
    }

def parse_relative_date(date_text: str) -> str:
    """Convert relative dates like 'Today', 'Tomorrow' to ISO format"""
    today = datetime.utcnow().date()
    date_lower = date_text.lower().strip()
    
    if date_lower == "today":
        return today.isoformat()
    elif date_lower == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    else:
        # Try parsing "Month Day" format
        try:
            # Add current year if not present
            if not any(char.isdigit() for word in date_text.split() for char in word if len(word) == 4):
                date_text = f"{date_text} {today.year}"
            parsed = datetime.strptime(date_text, "%B %d %Y")
            return parsed.date().isoformat()
        except:
            return today.isoformat()

@app.get("/matches")
async def get_all_matches():
    """Scrape all upcoming matches from VLR.gg main page - FAST"""
    url = "https://www.vlr.gg/matches"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch: {str(e)}")
    
    soup = BeautifulSoup(response.text, "lxml")
    matches = []
    
    # Find all date sections
    current_date = None
    for element in soup.select(".wf-card, .wf-label"):
        # Check if it's a date header
        if "wf-label" in element.get("class", []):
            date_text = element.get_text(strip=True)
            current_date = parse_relative_date(date_text)
            continue
        
        # Check if it's a match item
        match_items = element.select(".match-item")
        for item in match_items:
            try:
                # Match ID
                href = item.get("href", "")
                match_id = ""
                match_match = re.search(r'/(\d+)/', href)
                if match_match:
                    match_id = match_match.group(1)
                
                if not match_id:
                    continue
                
                # Teams
                teams = []
                team_items = item.select(".match-item-vs-team-name")
                for team_el in team_items[:2]:
                    team_name = team_el.get_text(strip=True)
                    if team_name:
                        teams.append(team_name)
                
                if len(teams) != 2:
                    continue
                
                # Event
                event_el = item.select_one(".match-item-event-series")
                event = event_el.get_text(strip=True) if event_el else ""
                
                # Try to get exact time from data attribute
                time_el = item.select_one(".match-item-time")
                start_time = current_date or datetime.utcnow().date().isoformat()
                
                if time_el:
                    ts = time_el.get("data-utc-ts", "")
                    if ts:
                        try:
                            dt = datetime.utcfromtimestamp(int(ts))
                            start_time = dt.isoformat()
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
                print(f"Error parsing match: {e}")
                continue
    
    return {"matches": matches}

@app.get("/match/{match_id}")
async def get_match(match_id: str):
    """Get detailed match data including player stats"""
    url = f"https://www.vlr.gg/{match_id}"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=404, detail=f"Match not found: {str(e)}")
    
    soup = BeautifulSoup(response.text, "lxml")
    
    # Teams
    teams = []
    team_elements = soup.select(".match-header-link-name .wf-title-med")
    score_elements = soup.select(".match-header-vs-score .js-spoiler span")
    logo_elements = soup.select(".match-header-link img")
    
    for i, team_el in enumerate(team_elements[:2]):
        team_name = team_el.get_text(strip=True)
        score = score_elements[i].get_text(strip=True) if i < len(score_elements) else "0"
        logo = logo_elements[i].get("src", "") if i < len(logo_elements) else ""
        if logo and not logo.startswith("http"):
            logo = f"https:{logo}" if logo.startswith("//") else f"https://www.vlr.gg{logo}"
        teams.append({"name": team_name, "score": score, "img": logo})
    
    # Event
    event_el = soup.select_one(".match-header-event")
    event = {
        "series": event_el.select_one("div:nth-child(1)").get_text(strip=True) if event_el else "",
        "stage": event_el.select_one("div:nth-child(2)").get_text(strip=True) if event_el else ""
    }
    
    # Check if upcoming (no stats)
    map_containers = soup.select(".vm-stats-game")
    is_upcoming = len(map_containers) == 0
    
    maps = []
    
    if not is_upcoming:
        # Parse completed match stats
        for map_container in map_containers:
            map_name_el = map_container.select_one(".map div:first-child")
            map_name = map_name_el.get_text(strip=True) if map_name_el else "Unknown"
            
            players = []
            tables = map_container.select("table.wf-table-inset")
            
            for table_index, table in enumerate(tables):
                player_rows = table.select("tbody tr")
                for row in player_rows:
                    try:
                        name_el = row.select_one(".text-of")
                        if not name_el:
                            continue
                        
                        player_name = name_el.get_text(strip=True)
                        team_name = teams[table_index]["name"] if table_index < len(teams) else "Unknown"
                        
                        # Get player image
                        player_img = ""
                        img_el = row.select_one("img")
                        if img_el:
                            player_img = img_el.get("src", "")
                            if player_img and not player_img.startswith("http"):
                                player_img = f"https:{player_img}" if player_img.startswith("//") else f"https://www.vlr.gg{player_img}"
                        
                        # Stats
                        stat_cells = row.select("td.mod-stat span.mod-both")
                        rating = 0.0
                        kills = 0
                        deaths = 0
                        assists = 0
                        
                        if len(stat_cells) >= 5:
                            try:
                                rating = float(stat_cells[0].get_text(strip=True) or "0")
                                kills = int(stat_cells[2].get_text(strip=True) or "0")
                                deaths = int(stat_cells[3].get_text(strip=True) or "0")
                                assists = int(stat_cells[4].get_text(strip=True) or "0")
                            except:
                                pass
                        
                        players.append({
                            "name": player_name,
                            "team": team_name,
                            "rating": rating,
                            "kills": kills,
                            "deaths": deaths,
                            "assists": assists,
                            "img": player_img
                        })
                    except:
                        continue
            
            maps.append({"map": map_name, "players": players})
    
    return {
        "teams": teams,
        "event": event,
        "maps": maps,
        "is_upcoming": is_upcoming
    }

@app.get("/live")
async def get_live_matches():
    """Get currently live matches"""
    url = "https://www.vlr.gg"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch: {str(e)}")
    
    soup = BeautifulSoup(response.text, "lxml")
    live_matches = []
    
    match_items = soup.select(".wf-module-item.match-item")
    
    for item in match_items:
        eta_el = item.select_one(".match-item-eta")
        is_live = eta_el and "live" in eta_el.get_text(strip=True).lower() if eta_el else False
        
        if not is_live:
            continue
        
        href = item.get("href", "")
        match_id = ""
        match_match = re.search(r'/(\d+)/', href)
        if match_match:
            match_id = match_match.group(1)
        
        teams = []
        team_items = item.select(".match-item-vs-team")
        for team_item in team_items:
            name_el = team_item.select_one(".match-item-vs-team-name")
            score_el = team_item.select_one(".match-item-vs-team-score")
            team_name = name_el.get_text(strip=True) if name_el else ""
            score = score_el.get_text(strip=True) if score_el else "0"
            teams.append({"name": team_name, "score": score})
        
        event_el = item.select_one(".match-item-event")
        event = event_el.get_text(strip=True) if event_el else ""
        
        if match_id and len(teams) == 2:
            live_matches.append({
                "id": match_id,
                "team1": teams[0],
                "team2": teams[1],
                "event": event,
                "status": "LIVE"
            })
    
    return {"live_matches": live_matches}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

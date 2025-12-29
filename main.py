"""
VLR.gg Scraper API - Enhanced version with team rosters, player history, and live scores

"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup
import re
from typing import Optional
import asyncio

app = FastAPI(title="VLR Match API", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "VLR.gg Scraper API v2.0",
        "endpoints": [
            "/match/{id} - Get match details with player stats",
            "/team/{id} - Get team roster",
            "/player/{id} - Get player profile and match history",
            "/live - Get live match scores"
        ]
    }

# ============== MATCH ENDPOINT ==============

@app.get("/match/{match_id}")
async def get_match(match_id: str):
    """Get detailed match data including player stats from VLR.gg"""
    url = f"https://www.vlr.gg/{match_id}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=404, detail=f"Match not found: {str(e)}")
    
    soup = BeautifulSoup(response.text, "lxml")
    
    # Parse teams
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
    
    # Parse event info
    event_el = soup.select_one(".match-header-event")
    event = {
        "series": event_el.select_one("div:nth-child(1)").get_text(strip=True) if event_el else "",
        "stage": event_el.select_one("div:nth-child(2)").get_text(strip=True) if event_el else "",
        "id": "",
        "img": None,
        "status": None
    }
    
    # Parse maps and player stats
    maps = []
    map_containers = soup.select(".vm-stats-game")
    
    for map_container in map_containers:
        map_name_el = map_container.select_one(".map div:first-child")
        map_name = map_name_el.get_text(strip=True) if map_name_el else "Unknown"
        
        if map_name.lower() == "all maps":
            map_name = "All Maps"
        
        # Get map scores
        map_teams = []
        score_els = map_container.select(".score")
        team_names = [t["name"] for t in teams]
        for i, score_el in enumerate(score_els[:2]):
            map_teams.append({
                "name": team_names[i] if i < len(team_names) else f"Team {i+1}",
                "score": score_el.get_text(strip=True)
            })
        
        # Parse player stats for this map
        players = []
        player_rows = map_container.select("table.wf-table-inset tbody tr")
        
        for row in player_rows:
            player_data = parse_player_row(row, teams)
            if player_data:
                players.append(player_data)
        
        maps.append({
            "map": map_name,
            "teams": map_teams,
            "players": players
        })
    
    return {
        "teams": teams,
        "event": event,
        "map_count": len([m for m in maps if m["map"] != "All Maps"]),
        "maps": maps
    }


def parse_player_row(row, teams):
    """Parse a single player row from the scoreboard"""
    try:
        name_el = row.select_one(".text-of")
        if not name_el:
            return None
        
        player_name = name_el.get_text(strip=True)
        team_name = teams[0]["name"] if teams else "Unknown"
        parent_table = row.find_parent("table")
        if parent_table:
            tables = row.find_parents()[0].find_all("table", class_="wf-table-inset")
            for i, table in enumerate(tables):
                if table == parent_table and i == 1 and len(teams) > 1:
                    team_name = teams[1]["name"]
                    break
        
        player_link = row.select_one("a")
        player_id = ""
        if player_link and player_link.get("href"):
            match = re.search(r'/player/(\d+)', player_link.get("href", ""))
            if match:
                player_id = match.group(1)
        
        agents = []
        agent_imgs = row.select(".mod-agent img")
        for img in agent_imgs:
            agent_title = img.get("title", "")
            if agent_title:
                agents.append({"title": agent_title, "img": img.get("src", "")})
        
        stat_cells = row.select("td.mod-stat span.mod-both")
        stats = {
            "rating": 0.0, "acs": 0, "kills": 0, "deaths": 0, "assists": 0,
            "kast": 0, "adr": 0, "headshot_percent": 0,
            "first_kills": 0, "first_deaths": 0, "first_kills_diff": 0
        }
        
        stat_keys = ["rating", "acs", "kills", "deaths", "assists", "kd_diff", "kast", "adr", "headshot_percent",

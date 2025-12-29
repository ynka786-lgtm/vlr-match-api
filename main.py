"""
VLR.gg Scraper API - Enhanced version with team rosters, player history, and live scores
Deploy to Render for use with VCT Companion iOS app
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
        
        stat_keys = ["rating", "acs", "kills", "deaths", "assists", "kd_diff", "kast", "adr", "headshot_percent", "first_kills", "first_deaths", "first_kills_diff"]
        
        for i, cell in enumerate(stat_cells):
            if i >= len(stat_keys):
                break
            text = cell.get_text(strip=True)
            key = stat_keys[i]
            if key == "kd_diff":
                continue
            try:
                text = text.replace("%", "").strip()
                if key == "rating":
                    stats[key] = float(text) if text else 0.0
                else:
                    stats[key] = int(float(text)) if text else 0
            except (ValueError, TypeError):
                pass
        
        return {"id": player_id, "name": player_name, "team": team_name, "agents": agents, **stats}
    except Exception as e:
        print(f"Error parsing player row: {e}")
        return None


# ============== TEAM ENDPOINT ==============

@app.get("/team/{team_id}")
async def get_team(team_id: str):
    """Get team roster and info from VLR.gg"""
    url = f"https://www.vlr.gg/team/{team_id}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=404, detail=f"Team not found: {str(e)}")
    
    soup = BeautifulSoup(response.text, "lxml")
    
    name_el = soup.select_one(".team-header-name h1")
    team_name = name_el.get_text(strip=True) if name_el else "Unknown"
    
    logo_el = soup.select_one(".team-header-logo img")
    logo = ""
    if logo_el:
        logo = logo_el.get("src", "")
        if logo and not logo.startswith("http"):
            logo = f"https:{logo}" if logo.startswith("//") else f"https://www.vlr.gg{logo}"
    
    region_el = soup.select_one(".team-header-country")
    region = region_el.get_text(strip=True) if region_el else ""
    
    roster = []
    player_items = soup.select(".team-roster-item")
    
    for item in player_items:
        player_link = item.select_one("a")
        if not player_link:
            continue
        
        href = player_link.get("href", "")
        player_id = ""
        id_match = re.search(r'/player/(\d+)', href)
        if id_match:
            player_id = id_match.group(1)
        
        name_el = item.select_one(".team-roster-item-name-alias")
        player_name = name_el.get_text(strip=True) if name_el else ""
        
        real_name_el = item.select_one(".team-roster-item-name-real")
        real_name = real_name_el.get_text(strip=True) if real_name_el else ""
        
        role_el = item.select_one(".team-roster-item-name-role")
        role = role_el.get_text(strip=True) if role_el else ""
        
        img_el = item.select_one("img")
        player_img = ""
        if img_el:
            player_img = img_el.get("src", "")
            if player_img and not player_img.startswith("http"):
                player_img = f"https:{player_img}" if player_img.startswith("//") else f"https://www.vlr.gg{player_img}"
        
        if player_name:
            roster.append({
                "id": player_id, "name": player_name, "real_name": real_name,
                "role": role, "img": player_img
            })
    
    return {"id": team_id, "name": team_name, "logo": logo, "region": region, "roster": roster}


# ============== TEAM SEARCH ENDPOINT ==============

@app.get("/team/search/{team_name}")
async def search_team(team_name: str):
    """Search for a team by name and return their ID and roster"""
    url = f"https://www.vlr.gg/search/?q={team_name}&type=teams"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    
    soup = BeautifulSoup(response.text, "lxml")
    results = []
    team_items = soup.select(".search-item")
    
    for item in team_items:
        link = item.select_one("a")
        if not link:
            continue
        href = link.get("href", "")
        if "/team/" not in href:
            continue
        team_id = ""
        id_match = re.search(r'/team/(\d+)', href)
        if id_match:
            team_id = id_match.group(1)
        name_el = item.select_one(".search-item-title")
        name = name_el.get_text(strip=True) if name_el else ""
        if team_id and name:
            results.append({"id": team_id, "name": name})
    
    if len(results) == 1:
        return await get_team(results[0]["id"])
    
    return {"results": results}


# ============== PLAYER ENDPOINT ==============

@app.get("/player/{player_id}")
async def get_player(player_id: str):
    """Get player profile from VLR.gg"""
    url = f"https://www.vlr.gg/player/{player_id}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=404, detail=f"Player not found: {str(e)}")
    
    soup = BeautifulSoup(response.text, "lxml")
    
    name_el = soup.select_one(".player-header h1")
    player_name = name_el.get_text(strip=True) if name_el else "Unknown"
    
    real_name_el = soup.select_one(".player-header h2")
    real_name = real_name_el.get_text(strip=True) if real_name_el else ""
    
    team_el = soup.select_one(".player-header-team a")
    team_name = team_el.get_text(strip=True) if team_el else ""
    
    img_el = soup.select_one(".player-header img")
    player_img = ""
    if img_el:
        player_img = img_el.get("src", "")
        if player_img and not player_img.startswith("http"):
            player_img = f"https:{player_img}" if player_img.startswith("//") else f"https://www.vlr.gg{player_img}"
    
    return {"id": player_id, "name": player_name, "real_name": real_name, "team": team_name, "img": player_img}


# ============== LIVE MATCHES ENDPOINT ==============

@app.get("/live")
async def get_live_matches():
    """Get currently live matches from VLR.gg"""
    url = "https://www.vlr.gg"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
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
                "id": match_id, "team1": teams[0], "team2": teams[1],
                "event": event, "status": "LIVE"
            })
    
    return {"live_matches": live_matches}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

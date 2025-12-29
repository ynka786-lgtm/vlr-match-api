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
    
    # Also get team IDs for roster lookup
    team_links = soup.select(".match-header-link")
    team_ids = []
    for link in team_links[:2]:
        href = link.get("href", "")
        match = re.search(r'/team/(\d+)', href)
        team_ids.append(match.group(1) if match else "")
    
    for i, team_el in enumerate(team_elements[:2]):
        team_name = team_el.get_text(strip=True)
        score = score_elements[i].get_text(strip=True) if i < len(score_elements) else "0"
        logo = logo_elements[i].get("src", "") if i < len(logo_elements) else ""
        if logo and not logo.startswith("http"):
            logo = f"https:{logo}" if logo.startswith("//") else f"https://www.vlr.gg{logo}"
        teams.append({
            "name": team_name, 
            "score": score, 
            "img": logo,
            "id": team_ids[i] if i < len(team_ids) else ""
        })
    
    # Parse event info
    event_el = soup.select_one(".match-header-event")
    event = {
        "series": event_el.select_one("div:nth-child(1)").get_text(strip=True) if event_el else "",
        "stage": event_el.select_one("div:nth-child(2)").get_text(strip=True) if event_el else "",
        "id": "",
        "img": None,
        "status": None
    }
    
    # Check if this is an upcoming match (no stats yet)
    map_containers = soup.select(".vm-stats-game")
    is_upcoming = len(map_containers) == 0
    
    # Parse maps and player stats
    maps = []
    
    if is_upcoming:
        # For upcoming matches, try to get expected lineups
        team1_roster = []
        team2_roster = []
        
        # Method 1: Look for roster sections on the match page
        roster_sections = soup.select(".match-streams-container")
        
        # Method 2: Look for player names in the match header/info section
        player_containers = soup.select(".match-header-vs-player")
        for i, container in enumerate(player_containers):
            player_name = container.get_text(strip=True)
            if player_name:
                if i % 2 == 0:
                    team1_roster.append({"name": player_name, "img": "", "id": ""})
                else:
                    team2_roster.append({"name": player_name, "img": "", "id": ""})
        
        # Method 3: If we have team IDs, fetch rosters directly (with images)
        if not team1_roster and len(team_ids) >= 1 and team_ids[0]:
            team1_roster = await fetch_team_roster(team_ids[0])
        if not team2_roster and len(team_ids) >= 2 and team_ids[1]:
            team2_roster = await fetch_team_roster(team_ids[1])
        
        # Create a placeholder map with roster info
        players = []
        for player_data in team1_roster[:5]:
            # Handle both dict and string formats for backwards compatibility
            if isinstance(player_data, dict):
                player_name = player_data.get("name", "")
                player_img = player_data.get("img", "")
                player_id = player_data.get("id", "")
            else:
                player_name = str(player_data)
                player_img = ""
                player_id = ""
            
            players.append({
                "id": player_id,
                "name": player_name,
                "team": teams[0]["name"] if teams else "Team 1",
                "agents": [],
                "rating": 0.0,
                "acs": 0,
                "kills": 0,
                "deaths": 0,
                "assists": 0,
                "kast": 0,
                "adr": 0,
                "headshot_percent": 0,
                "first_kills": 0,
                "first_deaths": 0,
                "first_kills_diff": 0,
                "img": player_img  # Add image URL
            })
        for player_data in team2_roster[:5]:
            # Handle both dict and string formats for backwards compatibility
            if isinstance(player_data, dict):
                player_name = player_data.get("name", "")
                player_img = player_data.get("img", "")
                player_id = player_data.get("id", "")
            else:
                player_name = str(player_data)
                player_img = ""
                player_id = ""
            
            players.append({
                "id": player_id,
                "name": player_name,
                "team": teams[1]["name"] if len(teams) > 1 else "Team 2",
                "agents": [],
                "rating": 0.0,
                "acs": 0,
                "kills": 0,
                "deaths": 0,
                "assists": 0,
                "kast": 0,
                "adr": 0,
                "headshot_percent": 0,
                "first_kills": 0,
                "first_deaths": 0,
                "first_kills_diff": 0,
                "img": player_img  # Add image URL
            })
        
        if players:
            maps.append({
                "map": "Roster",
                "teams": [{"name": t["name"], "score": "0"} for t in teams],
                "players": players
            })
    else:
        # Parse completed match stats
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
            # Get all tables - typically 2 tables, one per team
            tables = map_container.select("table.wf-table-inset")
            
            for table_index, table in enumerate(tables):
                player_rows = table.select("tbody tr")
                for row in player_rows:
                    player_data = parse_player_row(row, teams, table_index)
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
        "map_count": len([m for m in maps if m["map"] not in ["All Maps", "Roster"]]),
        "maps": maps,
        "is_upcoming": is_upcoming
    }


async def fetch_player_image(player_id: str) -> str:
    """Fetch player image from their profile page"""
    if not player_id:
        return ""
    
    url = f"https://www.vlr.gg/player/{player_id}"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            return ""
    
    soup = BeautifulSoup(response.text, "lxml")
    
    # Try multiple selectors for player image
    img_url = ""
    
    # Try 1: .player-header img
    img_el = soup.select_one(".player-header img")
    if img_el:
        img_url = img_el.get("src", "") or img_el.get("data-src", "") or img_el.get("data-lazy-src", "")
    
    # Try 2: Any img in player-header
    if not img_url:
        header_imgs = soup.select(".player-header img")
        for img in header_imgs:
            src = img.get("src", "") or img.get("data-src", "") or img.get("data-lazy-src", "")
            if src and src != "/img/base/ph/sil.png":  # Skip placeholder
                img_url = src
                break
    
    # Try 3: Look for img with player photo class
    if not img_url:
        photo_imgs = soup.select("img[class*='player'], img[class*='photo'], img[class*='avatar']")
        for img in photo_imgs:
            src = img.get("src", "") or img.get("data-src", "") or img.get("data-lazy-src", "")
            if src and src != "/img/base/ph/sil.png":
                img_url = src
                break
    
    # Fix URL if found
    if img_url:
        if img_url.startswith("//"):
            return f"https:{img_url}"
        elif img_url.startswith("/"):
            return f"https://www.vlr.gg{img_url}"
        elif img_url.startswith("http"):
            return img_url
    
    return ""


async def fetch_team_roster(team_id: str) -> list:
    """Helper to fetch team roster for upcoming matches - returns list of dicts with name and img"""
    url = f"https://www.vlr.gg/team/{team_id}"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            return []
    
    soup = BeautifulSoup(response.text, "lxml")
    
    roster = []
    player_items = soup.select(".team-roster-item")
    
    # First pass: collect all player data and IDs
    player_data_list = []
    for item in player_items[:5]:  # Max 5 players
        name_el = item.select_one(".team-roster-item-name-alias")
        if name_el:
            player_name = name_el.get_text(strip=True)
            if player_name:
                # Get player ID from link
                player_link = item.select_one("a")
                player_id = ""
                if player_link:
                    href = player_link.get("href", "")
                    id_match = re.search(r'/player/(\d+)', href)
                    if id_match:
                        player_id = id_match.group(1)
                
                # Get player image - try multiple selectors on team page
                player_img = ""
                
                # Try 1: Direct img tag in the item
                img_el = item.select_one("img")
                if img_el:
                    player_img = img_el.get("src", "") or img_el.get("data-src", "") or img_el.get("data-lazy-src", "")
                
                # Try 2: Look for img in the link
                if not player_img and player_link:
                    link_img = player_link.select_one("img")
                    if link_img:
                        player_img = link_img.get("src", "") or link_img.get("data-src", "") or link_img.get("data-lazy-src", "")
                
                # Try 3: Look for any img in the item (including nested)
                if not player_img:
                    all_imgs = item.select("img")
                    for img in all_imgs:
                        src = img.get("src", "") or img.get("data-src", "") or img.get("data-lazy-src", "")
                        if src and src != "/img/base/ph/sil.png":  # Skip placeholder images
                            player_img = src
                            break
                
                # Try 4: Look for background-image in style attribute
                if not player_img:
                    style_el = item.select_one("[style*='background-image']")
                    if style_el:
                        style = style_el.get("style", "")
                        bg_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', style)
                        if bg_match:
                            player_img = bg_match.group(1)
                
                # Fix URL if needed
                if player_img:
                    if player_img.startswith("//"):
                        player_img = f"https:{player_img}"
                    elif player_img.startswith("/"):
                        player_img = f"https://www.vlr.gg{player_img}"
                    elif not player_img.startswith("http"):
                        player_img = f"https://www.vlr.gg{player_img}"
                
                player_data_list.append({
                    "name": player_name,
                    "img": player_img,
                    "id": player_id
                })
    
    # Second pass: fetch images from player pages in parallel for players without images
    if player_data_list:
        # Collect tasks for players that need images
        tasks = []
        task_indices = []
        for i, player_data in enumerate(player_data_list):
            if not player_data["img"] and player_data["id"]:
                tasks.append(fetch_player_image(player_data["id"]))
                task_indices.append(i)
        
        # Execute all image fetches in parallel
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for idx, result in enumerate(results):
                if not isinstance(result, Exception) and result:
                    player_data_list[task_indices[idx]]["img"] = result
    
    return player_data_list


def parse_player_row(row, teams, table_index=0):
    """Parse a single player row from the scoreboard"""
    try:
        # Player name and team
        name_el = row.select_one(".text-of")
        if not name_el:
            return None
        
        player_name = name_el.get_text(strip=True)
        
        # Determine team from table index (0 = team 1, 1 = team 2)
        team_name = teams[table_index]["name"] if table_index < len(teams) else "Unknown"
        
        # Player ID and image
        player_link = row.select_one("a")
        player_id = ""
        player_img = ""
        if player_link:
            href = player_link.get("href", "")
            id_match = re.search(r'/player/(\d+)', href)
            if id_match:
                player_id = id_match.group(1)
            
            # Try to get player image from the row
            img_el = row.select_one("img")
            if img_el:
                player_img = img_el.get("src", "")
                if player_img and not player_img.startswith("http"):
                    player_img = f"https:{player_img}" if player_img.startswith("//") else f"https://www.vlr.gg{player_img}"
        
        # Agents
        agents = []
        agent_imgs = row.select(".mod-agent img")
        for img in agent_imgs:
            agent_title = img.get("title", "")
            if agent_title:
                agents.append({"title": agent_title, "img": img.get("src", "")})
        
        # Stats - get all stat cells
        stat_cells = row.select("td.mod-stat span.mod-both")
        
        # Default stats
        stats = {
            "rating": 0.0,
            "acs": 0,
            "kills": 0,
            "deaths": 0,
            "assists": 0,
            "kast": 0,
            "adr": 0,
            "headshot_percent": 0,
            "first_kills": 0,
            "first_deaths": 0,
            "first_kills_diff": 0
        }
        
        # Parse stats in order: Rating, ACS, K, D, A, +/-, KAST, ADR, HS%, FK, FD, FK Diff
        stat_keys = ["rating", "acs", "kills", "deaths", "assists", "kd_diff", "kast", "adr", "headshot_percent", "first_kills", "first_deaths", "first_kills_diff"]
        
        for i, cell in enumerate(stat_cells):
            if i >= len(stat_keys):
                break
            
            text = cell.get_text(strip=True)
            key = stat_keys[i]
            
            # Skip kd_diff, we don't need it
            if key == "kd_diff":
                continue
            
            # Parse value
            try:
                # Remove % signs
                text = text.replace("%", "").strip()
                if key == "rating":
                    stats[key] = float(text) if text else 0.0
                else:
                    stats[key] = int(float(text)) if text else 0
            except (ValueError, TypeError):
                pass
        
        return {
            "id": player_id,
            "name": player_name,
            "team": team_name,
            "agents": agents,
            "img": player_img,  # Add player image URL
            **stats
        }
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
    
    # Team name
    name_el = soup.select_one(".team-header-name h1")
    team_name = name_el.get_text(strip=True) if name_el else "Unknown"
    
    # Team logo
    logo_el = soup.select_one(".team-header-logo img")
    logo = ""
    if logo_el:
        logo = logo_el.get("src", "")
        if logo and not logo.startswith("http"):
            logo = f"https:{logo}" if logo.startswith("//") else f"https://www.vlr.gg{logo}"
    
    # Team region
    region_el = soup.select_one(".team-header-country")
    region = region_el.get_text(strip=True) if region_el else ""
    
    # Parse roster
    roster = []
    player_items = soup.select(".team-roster-item")
    
    for item in player_items:
        player_link = item.select_one("a")
        if not player_link:
            continue
        
        # Player ID from link
        href = player_link.get("href", "")
        player_id = ""
        id_match = re.search(r'/player/(\d+)', href)
        if id_match:
            player_id = id_match.group(1)
        
        # Player name (IGN)
        name_el = item.select_one(".team-roster-item-name-alias")
        player_name = name_el.get_text(strip=True) if name_el else ""
        
        # Real name
        real_name_el = item.select_one(".team-roster-item-name-real")
        real_name = real_name_el.get_text(strip=True) if real_name_el else ""
        
        # Role/Position
        role_el = item.select_one(".team-roster-item-name-role")
        role = role_el.get_text(strip=True) if role_el else ""
        
        # Player image
        img_el = item.select_one("img")
        player_img = ""
        if img_el:
            player_img = img_el.get("src", "")
            if player_img and not player_img.startswith("http"):
                player_img = f"https:{player_img}" if player_img.startswith("//") else f"https://www.vlr.gg{player_img}"
        
        if player_name:
            roster.append({
                "id": player_id,
                "name": player_name,
                "real_name": real_name,
                "role": role,
                "img": player_img
            })
    
    # Recent matches
    recent_matches = []
    match_items = soup.select(".mod-dark .wf-card")[:5]  # Last 5 matches
    
    for match_item in match_items:
        match_link = match_item.select_one("a")
        if not match_link:
            continue
        
        href = match_link.get("href", "")
        match_id = ""
        match_match = re.search(r'/(\d+)/', href)
        if match_match:
            match_id = match_match.group(1)
        
        # Opponent and score
        team_els = match_item.select(".m-item-team")
        if len(team_els) >= 2:
            opponent = ""
            score = ""
            result = ""
            
            for team_el in team_els:
                name = team_el.select_one(".m-item-team-name")
                sc = team_el.select_one(".m-item-result span")
                if name:
                    t_name = name.get_text(strip=True)
                    t_score = sc.get_text(strip=True) if sc else "0"
                    if t_name.lower() != team_name.lower():
                        opponent = t_name
                    else:
                        score = t_score
                        if "mod-win" in str(team_el.get("class", [])):
                            result = "W"
                        else:
                            result = "L"
            
            if opponent:
                recent_matches.append({
                    "id": match_id,
                    "opponent": opponent,
                    "score": score,
                    "result": result
                })
    
    return {
        "id": team_id,
        "name": team_name,
        "logo": logo,
        "region": region,
        "roster": roster,
        "recent_matches": recent_matches
    }


# ============== PLAYER ENDPOINT ==============

@app.get("/player/{player_id}")
async def get_player(player_id: str):
    """Get player profile and match history from VLR.gg"""
    url = f"https://www.vlr.gg/player/{player_id}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=404, detail=f"Player not found: {str(e)}")
    
    soup = BeautifulSoup(response.text, "lxml")
    
    # Player name
    name_el = soup.select_one(".player-header h1")
    player_name = name_el.get_text(strip=True) if name_el else "Unknown"
    
    # Real name
    real_name_el = soup.select_one(".player-header h2")
    real_name = real_name_el.get_text(strip=True) if real_name_el else ""
    
    # Team
    team_el = soup.select_one(".player-header-team a")
    team_name = team_el.get_text(strip=True) if team_el else ""
    team_id = ""
    if team_el:
        href = team_el.get("href", "")
        team_match = re.search(r'/team/(\d+)', href)
        if team_match:
            team_id = team_match.group(1)
    
    # Player image
    img_el = soup.select_one(".player-header img")
    player_img = ""
    if img_el:
        player_img = img_el.get("src", "")
        if player_img and not player_img.startswith("http"):
            player_img = f"https:{player_img}" if player_img.startswith("//") else f"https://www.vlr.gg{player_img}"
    
    # Career stats
    stats = {}
    stat_items = soup.select(".player-summary-container-1 .wf-card")
    for item in stat_items:
        label_el = item.select_one(".stat-type")
        value_el = item.select_one(".stat-value")
        if label_el and value_el:
            label = label_el.get_text(strip=True).lower().replace(" ", "_")
            value = value_el.get_text(strip=True)
            stats[label] = value
    
    # Recent matches with individual performance
    recent_matches = []
    match_rows = soup.select(".mod-dark tr.wf-card")[:10]  # Last 10 matches
    
    for row in match_rows:
        cells = row.select("td")
        if len(cells) < 5:
            continue
        
        # Match link and ID
        match_link = row.select_one("a")
        match_id = ""
        opponent = ""
        if match_link:
            href = match_link.get("href", "")
            match_match = re.search(r'/(\d+)/', href)
            if match_match:
                match_id = match_match.group(1)
            opponent_el = match_link.select_one(".m-item-team-name")
            if opponent_el:
                opponent = opponent_el.get_text(strip=True)
        
        # Result
        result_el = row.select_one(".m-item-result")
        result = ""
        score = ""
        if result_el:
            result = "W" if "mod-win" in str(result_el.get("class", [])) else "L"
            score_span = result_el.select_one("span")
            score = score_span.get_text(strip=True) if score_span else ""
        
        # Rating
        rating = 0.0
        for cell in cells:
            cell_text = cell.get_text(strip=True)
            try:
                potential_rating = float(cell_text)
                if 0 < potential_rating < 3:  # VLR rating range
                    rating = potential_rating
                    break
            except ValueError:
                continue
        
        # K/D/A
        kda_el = row.select_one(".mod-kda")
        kills, deaths, assists = 0, 0, 0
        if kda_el:
            kda_text = kda_el.get_text(strip=True)
            kda_parts = kda_text.split("/")
            if len(kda_parts) == 3:
                try:
                    kills = int(kda_parts[0])
                    deaths = int(kda_parts[1])
                    assists = int(kda_parts[2])
                except ValueError:
                    pass
        
        if match_id:
            recent_matches.append({
                "match_id": match_id,
                "opponent": opponent,
                "result": result,
                "score": score,
                "rating": rating,
                "kills": kills,
                "deaths": deaths,
                "assists": assists
            })
    
    return {
        "id": player_id,
        "name": player_name,
        "real_name": real_name,
        "team": team_name,
        "team_id": team_id,
        "img": player_img,
        "stats": stats,
        "recent_matches": recent_matches
    }


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
    
    # Find live match items (they have "LIVE" indicator)
    match_items = soup.select(".wf-module-item.match-item")
    
    for item in match_items:
        # Check if live
        eta_el = item.select_one(".match-item-eta")
        is_live = eta_el and "live" in eta_el.get_text(strip=True).lower() if eta_el else False
        
        if not is_live:
            continue
        
        # Match ID
        href = item.get("href", "")
        match_id = ""
        match_match = re.search(r'/(\d+)/', href)
        if match_match:
            match_id = match_match.group(1)
        
        # Teams and scores
        teams = []
        team_items = item.select(".match-item-vs-team")
        for team_item in team_items:
            name_el = team_item.select_one(".match-item-vs-team-name")
            score_el = team_item.select_one(".match-item-vs-team-score")
            
            team_name = name_el.get_text(strip=True) if name_el else ""
            score = score_el.get_text(strip=True) if score_el else "0"
            
            teams.append({"name": team_name, "score": score})
        
        # Event
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
    
    # Find team results
    results = []
    team_items = soup.select(".search-item")
    
    for item in team_items:
        link = item.select_one("a")
        if not link:
            continue
        
        href = link.get("href", "")
        if "/team/" not in href:
            continue
        
        # Team ID
        team_id = ""
        id_match = re.search(r'/team/(\d+)', href)
        if id_match:
            team_id = id_match.group(1)
        
        # Team name
        name_el = item.select_one(".search-item-title")
        name = name_el.get_text(strip=True) if name_el else ""
        
        if team_id and name:
            results.append({"id": team_id, "name": name})
    
    # If we found exactly one result, fetch full team info
    if len(results) == 1:
        return await get_team(results[0]["id"])
    
    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

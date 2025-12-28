"""
VLR Match API - A simple serverless API for fetching VLR.gg match details with player stats
Based on akhilnarang/vlrgg-scraper but simplified for serverless deployment
"""
import http
import re
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup, Tag

app = FastAPI(title="VLR Match API", version="1.0.0")

# Enable CORS for iOS app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
VLR_BASE_URL = "https://www.vlr.gg"
REQUEST_TIMEOUT = 30.0

# Pydantic Models
class Agent(BaseModel):
    title: str
    img: str

class PlayerStats(BaseModel):
    id: str
    name: str
    team: str
    agents: list[Agent]
    rating: float
    acs: int
    kills: int
    deaths: int
    assists: int
    kast: int
    adr: int
    headshot_percent: int
    first_kills: int
    first_deaths: int
    first_kills_diff: int

class MapTeam(BaseModel):
    name: str
    score: str

class MapData(BaseModel):
    map: str
    teams: list[MapTeam]
    players: list[PlayerStats]

class TeamInfo(BaseModel):
    name: str
    img: str
    score: Optional[str] = None
    id: Optional[str] = None

class EventInfo(BaseModel):
    id: str
    img: str
    series: str
    stage: str
    status: Optional[str] = None

class MatchDetails(BaseModel):
    teams: list[TeamInfo]
    event: EventInfo
    map_count: int
    maps: list[MapData]

# Helper functions
def clean_string(text: str) -> str:
    """Clean whitespace from string"""
    return " ".join(text.split())

def clean_number_string(text: str) -> float:
    """Convert string to number, handling various formats"""
    cleaned = clean_string(text).replace("%", "").replace("+", "").replace("−", "-")
    try:
        return float(cleaned) if "." in cleaned else int(cleaned)
    except (ValueError, TypeError):
        return 0

def get_image_url(src: str) -> str:
    """Convert relative image URL to absolute"""
    if src.startswith("//"):
        return f"https:{src}"
    elif src.startswith("/"):
        return f"{VLR_BASE_URL}{src}"
    return src

async def parse_scoreboard(tbody: Tag, team_name_mapping: dict) -> list[dict]:
    """Parse player stats from scoreboard"""
    players = []
    for player_row in tbody.find_all("tr"):
        player_data = player_row.find_all("td", class_="mod-player")
        if not player_data:
            continue
            
        player_data = player_data[0]
        stats = player_row.find_all("td", class_="mod-stat")
        
        # Get team name
        team_divs = player_data.find_all("div", class_="ge-text-light")
        team_name_short = clean_string(team_divs[-1].get_text()) if team_divs else ""
        
        # Get player ID
        player_id = ""
        if player_link := player_data.find("a"):
            href = player_link.get("href", "")
            parts = href.split("/")
            if len(parts) >= 3:
                player_id = parts[-2]
        
        # Get player name
        name_div = player_data.find("div", class_="text-of")
        player_name = clean_string(name_div.get_text()) if name_div else "Unknown"
        
        # Get agents
        agents = []
        agents_td = player_row.find("td", class_="mod-agents")
        if agents_td:
            for agent_img in agents_td.find_all("img"):
                agents.append({
                    "title": agent_img.get("title", ""),
                    "img": get_image_url(agent_img.get("src", ""))
                })
        
        # Parse stats - handle potential missing data gracefully
        def get_stat(index: int) -> float:
            try:
                td = stats[index]
                # Try multiple span patterns - VLR uses different classes
                stat_span = (
                    td.find("span", class_="side mod-side mod-both") or
                    td.find("span", class_="side mod-both") or
                    td.find("span", class_="mod-both") or
                    td.find("span", class_="mod-side")
                )
                if stat_span:
                    # Get direct text, ignoring nested elements
                    text = stat_span.get_text(strip=True)
                    if text:
                        return clean_number_string(text)
                # Fallback: get all text from td
                td_text = td.get_text(strip=True)
                if td_text:
                    # Extract first number from text
                    import re
                    numbers = re.findall(r'[\d.]+', td_text)
                    if numbers:
                        return clean_number_string(numbers[0])
            except (IndexError, AttributeError):
                pass
            return 0
        
        players.append({
            "id": player_id,
            "name": player_name,
            "team": team_name_mapping.get(team_name_short, team_name_short),
            "agents": agents,
            "rating": get_stat(0),
            "acs": int(get_stat(1)),
            "kills": int(get_stat(2)),
            "deaths": int(get_stat(3)),
            "assists": int(get_stat(4)),
            "kast": int(get_stat(6)),
            "adr": int(get_stat(7)),
            "headshot_percent": int(get_stat(8)),
            "first_kills": int(get_stat(9)),
            "first_deaths": int(get_stat(10)),
            "first_kills_diff": int(get_stat(11)),
        })
    
    return players

async def scrape_match(match_id: str) -> MatchDetails:
    """Scrape match details from VLR.gg"""
    url = f"{VLR_BASE_URL}/{match_id}"
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(url)
        if response.status_code != http.HTTPStatus.OK:
            raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
    
    soup = BeautifulSoup(response.content, "lxml")
    
    # Parse teams
    teams = []
    match_header = soup.find("div", class_="match-header-vs")
    if match_header:
        names = match_header.find_all("div", class_="wf-title-med")
        images = match_header.find_all("a", class_="match-header-link")
        
        # Get scores
        scores = [None, None]
        score_div = match_header.find("div", class_="match-header-vs-score")
        if score_div:
            score_spans = score_div.find_all("div", class_="js-spoiler")
            if score_spans:
                score_text = clean_string(score_spans[0].get_text())
                if ":" in score_text:
                    scores = score_text.split(":")
        
        for i in range(min(2, len(names))):
            team_info = {
                "name": clean_string(names[i].get_text()),
                "img": get_image_url(images[i].find("img")["src"]) if images[i].find("img") else "",
                "score": scores[i] if i < len(scores) else None
            }
            if href := images[i].get("href"):
                team_info["id"] = href.split("/")[2] if len(href.split("/")) > 2 else None
            teams.append(team_info)
    
    # Parse event
    event_data = soup.find("div", class_="match-header-super")
    event_info = {"id": "", "img": "", "series": "", "stage": "", "status": None}
    if event_data:
        event_link = event_data.find("a", class_="match-header-event")
        if event_link:
            if href := event_link.get("href"):
                event_info["id"] = href.split("/")[2] if len(href.split("/")) > 2 else ""
            if img := event_link.find("img"):
                event_info["img"] = get_image_url(img.get("src", ""))
            divs = event_link.find_all("div")
            if divs:
                event_info["series"] = clean_string(divs[0].get_text()) if divs else ""
            series_div = event_link.find("div", class_="match-header-event-series")
            if series_div:
                event_info["stage"] = clean_string(series_div.get_text())
    
    # Check status
    if soup.find("span", class_="match-header-vs-note mod-upcoming"):
        event_info["status"] = "upcoming"
    elif status_div := soup.find("div", class_="match-header-vs-note"):
        event_info["status"] = clean_string(status_div.get_text()).lower()
    
    # Parse map data
    maps = []
    stats_container = soup.find("div", class_="vm-stats")
    if stats_container:
        map_stats = stats_container.find_all("div", class_="vm-stats-game")
        
        # Get map names
        map_names = {}
        for map_nav in stats_container.find_all("div", class_="vm-stats-gamesnav-item"):
            game_id = map_nav.get("data-game-id")
            map_name = "".join(c for c in clean_string(map_nav.get_text()) if not c.isdigit())
            map_names[game_id] = map_name
        
        # If single map
        if not map_names:
            map_div = stats_container.find("div", class_="map")
            if map_div and (span := map_div.find("span")):
                map_names[stats_container.get("data-game-id", "0")] = span.get_text().strip()
        
        map_count = len([m for m in map_names.values() if m.lower() != "tbd"])
        
        for map_data in map_stats:
            game_id = map_data.get("data-game-id")
            if game_id == "all" or map_names.get(game_id, "").lower() == "tbd":
                continue
            
            # Get team scores for this map
            map_teams = []
            team_names_divs = map_data.find_all("div", class_="team-name")
            score_divs = map_data.find_all("div", class_="score")
            for i in range(min(2, len(team_names_divs))):
                map_teams.append({
                    "name": team_names_divs[i].get_text().strip(),
                    "score": score_divs[i].get_text().strip() if i < len(score_divs) else "0"
                })
            
            # Build team name mapping for player assignment
            team_short_names = []
            rounds_div = map_data.find("div", class_="vlr-rounds")
            if rounds_div:
                for team_div in rounds_div.find_all("div", class_="team"):
                    team_short_names.append(clean_string(team_div.get_text()))
            
            team_name_mapping = {}
            for short, full in zip(team_short_names, map_teams):
                team_name_mapping[short] = full["name"]
            
            # Parse player stats
            players = []
            for tbody in map_data.find_all("tbody"):
                players.extend(await parse_scoreboard(tbody, team_name_mapping))
            
            maps.append({
                "map": map_names.get(game_id, "Unknown"),
                "teams": map_teams,
                "players": players
            })
    else:
        map_count = 0
    
    return MatchDetails(
        teams=teams,
        event=event_info,
        map_count=map_count,
        maps=maps
    )

# API Routes
@app.get("/")
async def root():
    return {"message": "VLR Match API", "version": "1.0.0", "docs": "/docs"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/match/{match_id}", response_model=MatchDetails)
async def get_match(match_id: str):
    """
    Get detailed match information including per-map player stats.
    
    - **match_id**: The VLR.gg match ID (e.g., "593680" or "593680/team1-vs-team2")
    """
    # Clean match ID - extract just the number if full path provided
    clean_id = match_id.split("/")[0] if "/" in match_id else match_id
    
    try:
        return await scrape_match(clean_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scraping match: {str(e)}")

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


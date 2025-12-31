"""
VLR.gg VCT Tier 1 Backend
Returns only VCT Tier 1 matches (Americas, EMEA, APAC, CN)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup
import re
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="VCT Tier 1 Backend", version="2.0.0")

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

TIER1_EVENTS = ["VCT", "Americas", "EMEA", "APAC", "CN", "Pacific"]

@app.get("/")
async def root():
    return {"status": "ok", "message": "VCT Tier 1 Backend v2.0 - Tier 1 matches only"}

@app.get("/matches")
async def get_all_matches():
    """Get all VCT Tier 1 matches with proper dates from VLR.gg"""
    url = "https://www.vlr.gg/matches"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch VLR.gg: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch: {str(e)}")
    
    soup = BeautifulSoup(response.text, "lxml")
    matches = []
    current_date = "2026-01-08"
    
    try:
        # Get the main matches container
        main_container = soup.select_one(".mod-dark")
        if not main_container:
            raise HTTPException(status_code=500, detail="Could not find matches container")
        
        # Iterate through all elements in mod-dark
        for elem in main_container.find_all(recursive=True):
            if not elem.name:
                continue
            
            # Check for date headers (divs with month/date text)
            if elem.name == 'div':
                elem_text = elem.get_text(strip=True)
                
                # Check if this is a date header
                if any(month in elem_text for month in ['January', 'February', 'March', 'April', 'May', 'June',
                                                         'July', 'August', 'September', 'October', 'November', 'December']):
                    if re.search(r'\d{1,2}', elem_text) and ',' in elem_text:
                        try:
                            # Parse "Thu, January 8, 2026" format
                            parts = elem_text.split(',')
                            if len(parts) >= 2:
                                date_str = ','.join(parts[1:]).strip()
                                parsed = datetime.strptime(date_str, "%B %d, %Y").date()
                                current_date = parsed.isoformat()
                                logger.info(f"Found date: {current_date}")
                        except Exception as e:
                            logger.warning(f"Failed to parse date '{elem_text}': {e}")
        
        # Now find all match items with the current_date tracking
        all_match_items = soup.select(".match-item")
        logger.info(f"Found {len(all_match_items)} total match items")
        
        for item in all_match_items:
            try:
                # Get match ID
                href = item.get("href", "")
                match_id_match = re.search(r'/(\d+)/', href)
                if not match_id_match:
                    continue
                match_id = match_id_match.group(1)
                
                # Get teams
                teams = []
                for team_el in item.select(".match-item-vs-team-name")[:2]:
                    team_name = team_el.get_text(strip=True)
                    if team_name:
                        teams.append(team_name)
                
                if len(teams) < 2:
                    continue
                
                # Get event name
                event_el = item.select_one(".match-item-event")
                if not event_el:
                    event_el = item.select_one(".match-item-event-series")
                
                event_text = event_el.get_text(strip=True) if event_el else ""
                
                # FILTER: Only include Tier 1 VCT events
                is_tier1 = any(tier1 in event_text.upper() for tier1 in TIER1_EVENTS)
                
                if not is_tier1:
                    logger.info(f"Skipping non-Tier 1: {event_text}")
                    continue
                
                # Try to get exact timestamp
                time_el = item.select_one(".match-item-time")
                start_time = current_date
                
                if time_el and time_el.get("data-utc-ts"):
                    try:
                        ts = int(time_el.get("data-utc-ts"))
                        dt = datetime.utcfromtimestamp(ts)
                        start_time = dt.isoformat()
                    except:
                        pass
                
                matches.append({
                    "id": match_id,
                    "team1": teams[0],
                    "team2": teams[1],
                    "event": event_text,
                    "start_time": start_time
                })
                
                logger.info(f"Added match: {teams[0]} vs {teams[1]} - {event_text} on {start_time}")
                
            except Exception as e:
                logger.warning(f"Error parsing match item: {e}")
                continue
        
        if not matches:
            raise HTTPException(status_code=500, detail="Could not find matches")
        
        logger.info(f"Returning {len(matches)} Tier 1 matches")
        return {"matches": matches}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/match/{match_id}")
async def get_match(match_id: str):
    """Get match details from VLR.gg"""
    url = f"https://www.vlr.gg/{match_id}"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
        except:
            raise HTTPException(status_code=404, detail="Match not found")
    
    soup = BeautifulSoup(response.text, "lxml")
    
    return {
        "id": match_id,
        "status": "ok"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

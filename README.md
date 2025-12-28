# VLR Match API

A simple API for fetching per-match player statistics from VLR.gg.

## Features

- Real per-match player stats (K/D/A, rating, ACS, etc.)
- Per-map breakdown
- Team scores and event info
- CORS enabled for mobile apps

## API Endpoints

### GET /match/{match_id}

Returns detailed match info with player stats.

**Example:** `GET /match/593680`

**Response:**
```json
{
  "teams": [
    {"name": "Team A", "img": "...", "score": "2", "id": "123"},
    {"name": "Team B", "img": "...", "score": "1", "id": "456"}
  ],
  "event": {"id": "789", "series": "VCT Americas", "stage": "Playoffs"},
  "map_count": 3,
  "maps": [
    {
      "map": "Ascent",
      "teams": [{"name": "Team A", "score": "13"}, {"name": "Team B", "score": "11"}],
      "players": [
        {
          "id": "123",
          "name": "PlayerName",
          "team": "Team A",
          "agents": [{"title": "Jett", "img": "..."}],
          "rating": 1.45,
          "acs": 285,
          "kills": 25,
          "deaths": 18,
          "assists": 6,
          "kast": 78,
          "adr": 175,
          "headshot_percent": 32,
          "first_kills": 5,
          "first_deaths": 2,
          "first_kills_diff": 3
        }
      ]
    }
  ]
}
```

## Deploy to Render (Free)

1. Fork this repo to your GitHub
2. Go to [render.com](https://render.com) and sign up
3. Click "New" → "Web Service"
4. Connect your GitHub repo
5. Render will auto-detect settings from `render.yaml`
6. Click "Create Web Service"
7. Your API will be live at `https://your-app-name.onrender.com`

## Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.


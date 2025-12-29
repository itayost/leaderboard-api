# Leaderboard API

A RESTful API for managing game leaderboards, players, and scores.

## Features

- Multi-game support with API key authentication
- Player registration and management
- Multiple leaderboards per game
- Score submission and ranking
- Get player rank and nearby scores

## Tech Stack

- **Framework:** Flask (Python)
- **Database:** MongoDB Atlas
- **Documentation:** Flasgger (Swagger)
- **Hosting:** Vercel

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/leaderboard-api.git
cd leaderboard-api
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in your MongoDB credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```
PORT=8080
DB_CONNECTION_STRING=your-cluster.mongodb.net
DB_NAME=leaderboard_db
DB_USERNAME=your-username
DB_PASSWORD=your-password
```

### 5. Run the server

```bash
python app.py
```

The API will be available at `http://localhost:8080`

## API Documentation

Once the server is running, visit `http://localhost:8080/apidocs` for interactive Swagger documentation.

## API Endpoints

### Apps

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/apps` | Register a new app, receive API key |
| GET | `/apps/{app_id}` | Get app info |
| POST | `/apps/validate` | Validate an API key |

### Players

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/players` | Register a new player |
| GET | `/players` | Get all players |
| GET | `/players/{player_id}` | Get player info |
| PUT | `/players/{player_id}` | Update player info |

### Leaderboards

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/leaderboards` | Create a new leaderboard |
| GET | `/leaderboards` | Get all leaderboards |
| GET | `/leaderboards/{leaderboard_id}` | Get leaderboard info |
| DELETE | `/leaderboards/{leaderboard_id}` | Delete leaderboard |

### Scores

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/scores` | Submit a score |
| GET | `/scores/{leaderboard_id}` | Get top scores |
| GET | `/scores/{leaderboard_id}/player/{player_id}` | Get player rank & nearby |
| GET | `/scores/player/{player_id}` | Get all player scores |

## Authentication

All endpoints (except `/apps` POST and `/apps/validate`) require an API key in the header:

```
X-API-Key: your-api-key-here
```

## Deployment to Vercel

1. Push your code to GitHub
2. Import the repository to Vercel
3. Set environment variables in Vercel dashboard
4. Deploy!

## License

MIT License

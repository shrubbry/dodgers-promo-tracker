import requests
import datetime
import os
from utils import send_email  # assumes working Brevo integration

TODAY = datetime.date.today()
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"

TEAMS = {
    "Dodgers": 119,
    "Angels": 108,
}

PROMOS = {
    "Dodgers": [
        {"name": "Panda Express", "condition": lambda game: game['home'] and game['won']},
        {"name": "McDonald's (6+ runs)", "condition": lambda game: game['runs'] >= 6},
        {"name": "ampm", "condition": lambda game: game['home'] and game['steals'] > 0},
        {"name": "Jack in the Box", "condition": lambda game: game['strikeouts'] >= 7},
    ],
    "Angels": [
        {"name": "McDonald's (Fries)", "condition": lambda game: game['won']},
        {"name": "Del Taco", "condition": lambda game: game['home'] and game['runs'] >= 5},
    ],
}

def fetch_team_games(team_id):
    url = f"{MLB_API_BASE}/schedule?sportId=1&teamId={team_id}&date={TODAY}"
    return requests.get(url).json()

def fetch_boxscore(game_id):
    url = f"{MLB_API_BASE}/game/{game_id}/boxscore"
    return requests.get(url).json()

def evaluate_promos(team_name, team_id):
    schedule = fetch_team_games(team_id)
    games = schedule.get("dates", [])
    if not games:
        return [], f"{team_name}: No game or data unavailable"

    game_data = games[0]['games'][0]
    is_home = game_data['teams']['home']['team']['id'] == team_id
    team_info = game_data['teams']['home'] if is_home else game_data['teams']['away']
    opp_info = game_data['teams']['away'] if is_home else game_data['teams']['home']

    runs = team_info['score']
    won = team_info['isWinner']
    game_id = game_data['gamePk']

    boxscore = fetch_boxscore(game_id)
    players = boxscore['teams']['home' if is_home else 'away']['players']

    steals = sum(p.get('stats', {}).get('batting', {}).get('stolenBases', 0) for p in players.values())
    pitching = boxscore['teams']['home' if not is_home else 'away']['players']
    strikeouts = sum(p.get('stats', {}).get('pitching', {}).get('strikeOuts', 0) for p in pitching.values())

    summary = {
        'home': is_home,
        'runs': runs,
        'won': won,
        'steals': steals,
        'strikeouts': strikeouts,
    }

    active_promos = []
    for promo in PROMOS[team_name]:
        if promo['condition'](summary):
            active_promos.append(f"- {promo['name']}: ✅ Triggered")
        else:
            active_promos.append(f"- {promo['name']}: ❌ Not triggered")

    triggered = [p for p in active_promos if '✅' in p]
    return triggered, f"<b>{team_name}</b>\n" + "\n".join(active_promos)

def main():
    all_triggered = []
    all_sections = []
    for team, id in TEAMS.items():
        triggered, section = evaluate_promos(team, id)
        all_triggered.extend(triggered)
        all_sections.append(section)

    if not all_triggered:
        print("No triggered promos; no email sent.")
        return

    subject = f"{len(all_triggered)} food promos active today!"
    body = f"<b>{TODAY.strftime('%A, %B %d')}</b><br><br>" + "<br><br>".join(all_sections)
    send_email(subject, body)

if __name__ == "__main__":
    main()

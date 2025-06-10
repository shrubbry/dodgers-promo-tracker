import requests
import datetime
import os

# Get today's date for querying MLB API
TODAY = datetime.date.today()
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"

# Team IDs used by MLB API
TEAMS = {
    "Dodgers": 119,
    "Angels": 108,
}

# Promotion rules for each team, based on game outcomes and stats
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

# Sends email using Brevo's transactional email API
# Requires BREVO_API_KEY to be set in the environment
# Note: this is a single-recipient example; you'll extend for multiple subscribers later
def send_email(subject, html_content):
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise RuntimeError("Missing BREVO_API_KEY")

    payload = {
        "sender": {"name": "Dodgers Promo Tracker", "email": "your_email@example.com"},
        "to": [{"email": "your_subscriber@example.com"}],
        "subject": subject,
        "htmlContent": f"<html><body>{html_content}</body></html>",
    }

    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        json=payload,
    )

    if not response.ok:
        raise RuntimeError(f"Email failed: {response.status_code} - {response.text}")
    print("Email sent.")

# Query MLB schedule endpoint for today's game(s) for a given team
def fetch_team_games(team_id):
    url = f"{MLB_API_BASE}/schedule?sportId=1&teamId={team_id}&date={TODAY}"
    return requests.get(url).json()

# Query MLB boxscore endpoint for a given gamePk
def fetch_boxscore(game_id):
    url = f"{MLB_API_BASE}/game/{game_id}/boxscore"
    return requests.get(url).json()

# Evaluate which promos triggered for a specific team, based on schedule + boxscore
def evaluate_promos(team_name, team_id):
    schedule = fetch_team_games(team_id)
    games = schedule.get("dates", [])
    if not games:
        return [], f"{team_name}: No game or data unavailable"

    game_data = games[0]['games'][0]
    is_home = game_data['teams']['home']['team']['id'] == team_id
    team_info = game_data['teams']['home'] if is_home else game_data['teams']['away']
    opp_info = game_data['teams']['away'] if is_home else game_data['teams']['home']

    runs = team_info.get('score', 0)  # fallback in case 'score' is missing
    # Some MLB schedule responses omit 'isWinner' even after games end
    won = team_info.get('isWinner')
    if won is None:
        won = team_info.get('score', 0) > opp_info.get('score', 0)  # fallback comparison if 'isWinner' is missing
    game_id = game_data['gamePk']

    boxscore = fetch_boxscore(game_id)
    # Player stats used for steals and strikeouts
    boxscore_team_key = 'home' if boxscore['teams']['home']['team']['id'] == team_id else 'away'
    players = boxscore['teams'][boxscore_team_key]['players']
    steals = sum(p.get('stats', {}).get('batting', {}).get('stolenBases', 0) for p in players.values())

    # Team pitching stats used to total strikeouts (Jack in the Box promo)
    pitching = boxscore['teams'][boxscore_team_key]['players']
    strikeouts = sum(p.get('stats', {}).get('pitching', {}).get('strikeOuts', 0) for p in pitching.values())

    print(f"[DEBUG] {team_name} game summary: runs={runs}, steals={steals}, strikeouts={strikeouts}, won={won}, home={is_home}")

    summary = {
        'home': is_home,
        'runs': runs,
        'won': won,
        'steals': steals,
        'strikeouts': strikeouts,
    }

    # Evaluate all promo conditions for this team
    active_promos = []
    for promo in PROMOS[team_name]:
        if promo['condition'](summary):
            active_promos.append(f"- {promo['name']}: ✅ Triggered")
        else:
            active_promos.append(f"- {promo['name']}: ❌ Not triggered")

    triggered = [p for p in active_promos if '✅' in p]
    return triggered, f"<b>{team_name}</b>\n" + "\n".join(active_promos)

# Top-level script entrypoint: evaluate both teams and send email if needed
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

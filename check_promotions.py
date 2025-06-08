import datetime
import requests
import smtplib
import os
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Config ===
SPREADSHEET_ID = "1e9ujE14dzkqtiYgKuI6nZfMNXPDpLgFIfZ88dr-kp14"
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = os.environ["BREVO_EMAIL"]
SMTP_PASS = os.environ["BREVO_PASS"]
SMTP_SENDER = os.environ["BREVO_SENDER"]

# === Promo Definitions ===
TEAMS = {
    "Dodgers": {
        "id": 119,
        "promos": [
            {"name": "Panda Express (Win at Home)", "trigger": lambda g: g.get("is_winner") and g.get("home")},
            {"name": "McDonald’s (6+ runs)", "trigger": lambda g: g.get("team_score", 0) >= 6},
            {"name": "ampm (Steal a base at home)", "trigger": lambda g: g.get("stolen_bases", 0) >= 1 and g.get("home")},
            {"name": "Jack in the Box (7+ strikeouts)", "trigger": lambda g: g.get("pitcher_strikeouts", 0) >= 7},
        ]
    },
    "Angels": {
        "id": 108,
        "promos": [
            {"name": "McDonald’s (Win)", "trigger": lambda g: g.get("is_winner")},
            {"name": "Del Taco (Score 5+ runs at home)", "trigger": lambda g: g.get("team_score", 0) >= 5 and g.get("home")},
        ]
    }
}

# === Email Fetch ===
def fetch_emails():
    print("Fetching subscriber emails...")
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    return sheet.col_values(2)[1:]  # skip header row

# === Game Result Fetch ===
def fetch_team_result(team_id):
    date = datetime.date.today() - datetime.timedelta(days=1)
    date_str = date.strftime('%Y-%m-%d')
    r = requests.get(f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&teamId={team_id}')
    data = r.json()
    try:
        game = data['dates'][0]['games'][0]
        box = requests.get(f"https://statsapi.mlb.com/api/v1/game/{game['gamePk']}/boxscore").json()
    except (IndexError, KeyError):
        return None

    is_home = game['teams']['home']['team']['id'] == team_id
    team_side = 'home' if is_home else 'away'
    opp_side = 'away' if is_home else 'home'

    team_stats = box['teams'][team_side]['teamStats']['batting']
    pitching_stats = box['teams'][team_side]['teamStats']['pitching']
    score = game['teams'][team_side]['score']
    opp = game['teams'][opp_side]['team']['name']

    return {
        "team_score": score,
        "is_winner": game['teams'][team_side].get('isWinner', False),
        "opponent": opp,
        "home": is_home,
        "stolen_bases": team_stats.get('stolenBases', 0),
        "pitcher_strikeouts": pitching_stats.get('strikeOuts', 0)
    }

# === Email Sender ===
def send_emails(subject, body, recipients):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_SENDER
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_SENDER, recipients, msg.as_string())

# === Main Routine ===
def main():
    print("SCRIPT STARTING: top-level code is executing")
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    date_label = yesterday.strftime('%A, %B %d')

    email_lines = [f"Games played: {date_label}\n"]
    promos_triggered = []

    for team_name, team_info in TEAMS.items():
        print(f"Checking results for {team_name}...")
        result = fetch_team_result(team_info["id"])
        if not result:
            email_lines.append(f"{team_name} game was postponed or not played.\n")
            continue

        game_line = f"{team_name} {'won' if result['is_winner'] else 'lost'} vs. {result['opponent']} ({result['team_score']} runs)"
        email_lines.append(game_line)

        for promo in team_info["promos"]:
            active = promo["trigger"](result)
            status = "✅" if active else "✖️"
            line = f"  {status} {promo['name']}"
            email_lines.append(line)
            if active:
                promos_triggered.append(f"{team_name}: {promo['name']}")

        email_lines.append("")  # blank line between teams

    if promos_triggered:
        subject = f"Promo Alert – {len(promos_triggered)} Triggered!"
        email_body = "\n".join(email_lines)
        print("==== Email Content ====")
        print("Subject:", subject)
        print(email_body)
        emails = fetch_emails()
        send_emails(subject, email_body, emails)
        print(f"Email sent to {len(emails)} recipients.")
    else:
        print("No promos triggered – no email sent.")

if __name__ == "__main__":
    main()

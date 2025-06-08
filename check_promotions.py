import requests, datetime, smtplib, os
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials

print("SCRIPT STARTING: top-level code is executing")

TEAMS = {
    "Dodgers": {
        "id": 119,
        "promos": [
            {"name": "Panda Express: Win = Free Bowl", "trigger": lambda g: g.get("isWinner") is True},
            {"name": "Jack in the Box: Score 6+ runs = Free Tiny Tacos", "trigger": lambda g: g.get("score", 0) >= 6},
            {"name": "McDonald’s: Score in 1st inning = Free 6pc McNuggets", "trigger": lambda g: g.get("scored_by_inning", [0])[0] > 0},
            {"name": "AMPM: HR in 8th+ inning = Free Hot Dog", "trigger": lambda g: any(i >= 8 for i in g.get("homeRuns", []))}
        ]
    },
    "Angels": {
        "id": 108,
        "promos": [
            {"name": "McDonald’s: Win = Free Medium Fries", "trigger": lambda g: g.get("isWinner") is True},
            {"name": "Del Taco: Score 6+ runs = Free Tacos", "trigger": lambda g: g.get("score", 0) >= 6}
        ]
    }
}

SPREADSHEET_ID = '1e9ujE14dzkqtiYgKuI6nZfMNXPDpLgFIfZ88dr-kp14'

SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = os.environ["BREVO_EMAIL"]
SMTP_PASS = os.environ["BREVO_PASS"]
SMTP_SENDER = os.environ["BREVO_SENDER"]

def check_team_result(team_id):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&teamId={team_id}&expand=schedule.linescore'
    r = requests.get(url)
    data = r.json()

    try:
        game = data['dates'][0]['games'][0]
        linescore = game.get("linescore", {})
    except (IndexError, KeyError):
        return None

    team_home = game['teams']['home']['team']['id'] == team_id
    team_data = game['teams']['home'] if team_home else game['teams']['away']
    opponent_data = game['teams']['away'] if team_home else game['teams']['home']

    scored_by_inning = linescore.get('innings', [])
    runs_per_inning = [
        inning[('home' if team_home else 'away')].get('runs', 0)
        for inning in scored_by_inning
    ]
    home_run_innings = [
        i + 1 for i, inning in enumerate(runs_per_inning)
        if inning >= 1 and 'homeRuns' in linescore  # defensive
    ]

    return {
        "isWinner": team_data.get("isWinner", False),
        "score": team_data.get("score", 0),
        "opponent": opponent_data['team']['name'],
        "opponent_score": opponent_data.get("score", 0),
        "homeRuns": home_run_innings,
        "scored_by_inning": runs_per_inning
    }

def fetch_emails():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    return sheet.col_values(2)[1:]

def send_emails(subject, body, recipients):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_SENDER
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_SENDER, recipients, msg.as_string())

def main():
    date_played = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%A, %B %d")
    email_lines = [f"Games played: {date_played}", ""]

    any_promos = False
    for team_name, info in TEAMS.items():
        result = check_team_result(info["id"])
        if not result:
            email_lines.append(f"{team_name} game was postponed or unavailable.")
            continue

        line = f"{team_name} {'won' if result['isWinner'] else 'lost'} vs {result['opponent']} ({result['score']}–{result['opponent_score']})"
        email_lines.append(line)

        for promo in info["promos"]:
            if promo["trigger"](result):
                email_lines.append(f"  ✅ {promo['name']}")
                any_promos = True

    subject = ("Today's Promos!" if any_promos else "No Promos") + f" (Games played: {date_played})"
    recipients = fetch_emails()
    send_emails(subject, "\n".join(email_lines), recipients)
    print("==== Email Content ====")
    print("Subject:", subject)
    print("\n".join(email_lines))
    print(f"Email sent to {len(recipients)} recipients.")

if __name__ == "__main__":
    main()

import requests, datetime, smtplib, os
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Config ===
DODGERS_ID = 119
ANGELS_ID = 108

SPREADSHEET_ID = '1e9ujE14dzkqtiYgKuI6nZfMNXPDpLgFIfZ88dr-kp14'

SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = os.environ["BREVO_EMAIL"]
SMTP_PASS = os.environ["BREVO_PASS"]
SMTP_SENDER = os.environ["BREVO_SENDER"]

# === Team + Promo Definitions ===
TEAMS = {
    "Dodgers": {
        "id": DODGERS_ID,
        "promos": [
            {
                "name": "Panda Express: Win = Free Bowl",
                "trigger": lambda g: g.get("is_winner", False),
            },
            {
                "name": "AMPM: Score 7+ Runs = $1 Coffee",
                "trigger": lambda g: g.get("team_score", 0) >= 7,
            },
            {
                "name": "McDonald's: 10+ Strikeouts = Free 6pc McNuggets",
                "trigger": lambda g: g.get("pitcher_strikeouts", 0) >= 10,
            },
        ],
    },
    "Angels": {
        "id": ANGELS_ID,
        "promos": [
            {
                "name": "McDonald’s: Score in 1st inning = Free 6pc McNuggets",
                "trigger": lambda g: (g.get("scored_by_inning") or [0])[0] > 0,
            },
            {
                "name": "Del Taco: Win = Free Tacos",
                "trigger": lambda g: g.get("is_winner", False),
            },
        ],
    },
}

# === Result Fetching ===
def fetch_team_result(team_id):
    date = datetime.date.today() - datetime.timedelta(days=1)
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&teamId={team_id}&hydrate=team,linescore"
    r = requests.get(url)
    data = r.json()

    try:
        game = data["dates"][0]["games"][0]
        linescore = game.get("linescore", {})
        team_data = game["teams"]["home"] if game["teams"]["home"]["team"]["id"] == team_id else game["teams"]["away"]
        opp_data = game["teams"]["away"] if team_data == game["teams"]["home"] else game["teams"]["home"]

        innings = linescore.get("innings", [])
        scored_by_inning = [inning.get(team_data["team"]["name"].lower(), 0) for inning in innings]

        return {
            "team_score": team_data["score"],
            "opponent_score": opp_data["score"],
            "is_winner": team_data.get("isWinner", False),
            "opponent": opp_data["team"]["name"],
            "scored_by_inning": scored_by_inning,
            "pitcher_strikeouts": linescore.get("teams", {}).get("home" if team_data == game["teams"]["home"] else "away", {}).get("pitchers", [{}])[0].get("strikeOuts", 0)
        }
    except (IndexError, KeyError):
        return None

# === Email Handling ===
def fetch_emails():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    return sheet.col_values(2)[1:]  # skip header

def send_emails(subject, body, recipients):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_SENDER
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_SENDER, recipients, msg.as_string())

# === Main Flow ===
def main():
    print("SCRIPT STARTING: top-level code is executing")
    today = datetime.date.today()
    game_date = today - datetime.timedelta(days=1)
    game_date_str = game_date.strftime('%A, %B %d')

    email_lines = [f"Games played: {game_date_str}", ""]
    triggered_promos = []
    team_results = {}

    for team_name, team_data in TEAMS.items():
        result = fetch_team_result(team_data["id"])
        team_results[team_name] = result

        if not result:
            email_lines.append(f"{team_name} game was postponed or not played.")
            continue

        opponent = result.get("opponent", "Unknown")
        scoreline = f"{result.get('team_score', '?')}–{result.get('opponent_score', '?')}"
        outcome = "won" if result.get("is_winner") else "lost"
        email_lines.append(f"{team_name} {outcome} vs. {opponent} ({scoreline})")

        for promo in team_data["promos"]:
            try:
                active = promo["trigger"](result)
                email_lines.append(f"* {promo['name']}? {'Y' if active else 'N'}")
                if active:
                    triggered_promos.append(promo["name"])
            except Exception as e:
                email_lines.append(f"* {promo['name']}? Error evaluating promo")

        email_lines.append("")

    if not triggered_promos:
        print("No promotions triggered. Email will not be sent.")
        print("\n".join(email_lines))
        return

    subject_line = f"{len(triggered_promos)} Promos! (Games played: {game_date_str})"
    body = "\n".join([
        f"{len(triggered_promos)} promotion{'s' if len(triggered_promos) != 1 else ''} triggered!",
        *email_lines
    ])

    print("==== Email Content ====")
    print(f"Subject: {subject_line}")
    print(body)

    recipients = fetch_emails()
    send_emails(subject_line, body, recipients)
    print(f"Email sent to {len(recipients)} recipients.")

if __name__ == "__main__":
    main()

import requests, datetime, smtplib, os
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Constants
DODGERS_ID = 119
ANGELS_ID = 108

SPREADSHEET_ID = "1e9ujE14dzkqtiYgKuI6nZfMNXPDpLgFIfZ88dr-kp14"

SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = os.environ["BREVO_EMAIL"]
SMTP_PASS = os.environ["BREVO_PASS"]
SMTP_SENDER = os.environ["BREVO_SENDER"]

# Promotion logic
PROMOTIONS = {
    DODGERS_ID: [
        {"name": "Panda Express: Win", "trigger": lambda g: g.get("is_win", False)},
        {"name": "McDonald’s: Score in 1st", "trigger": lambda g: g.get("scored_by_inning", [0])[0] > 0},
        {"name": "Jack in the Box: Score 6+", "trigger": lambda g: g.get("runs", 0) >= 6},
        {"name": "ampm: 10+ Strikeouts", "trigger": lambda g: g.get("opponent_strikeouts", 0) >= 10}
    ],
    ANGELS_ID: [
        {"name": "McDonald’s: Score in 1st", "trigger": lambda g: g.get("scored_by_inning", [0])[0] > 0},
        {"name": "Del Taco: Win", "trigger": lambda g: g.get("is_win", False)},
    ]
}

# Fetch result from MLB API
def get_game_result(team_id):
    date = datetime.date.today() - datetime.timedelta(days=1)
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&teamId={team_id}"
    res = requests.get(url).json()

    try:
        game = res["dates"][0]["games"][0]
    except (IndexError, KeyError):
        return {"played": False}

    teams = game["teams"]
    side = "home" if teams["home"]["team"]["id"] == team_id else "away"
    opponent = "away" if side == "home" else "home"

    linescore = game.get("linescore", {})
    innings = linescore.get("innings", [])
    scored_by_inning = [
        inning.get(side, {}).get("runs", 0)
        for inning in innings
    ]

    return {
        "played": True,
        "opponent": teams[opponent]["team"]["name"],
        "is_win": teams[side].get("isWinner", False),
        "runs": teams[side]["score"],
        "scored_by_inning": scored_by_inning,
        "opponent_strikeouts": game.get("teams", {}).get(opponent, {}).get("pitchers", [{}])[0].get("stats", {}).get("strikeOuts", 0)
    }

# Fetch email addresses
def fetch_emails():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    return sheet.col_values(2)[1:]

# Send via Brevo
def send_emails(subject, message, recipients):
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = SMTP_SENDER
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_SENDER, recipients, msg.as_string())

# Build one-team summary
def build_summary(name, result, promos):
    if not result["played"]:
        return f"{name} game was postponed or not played."

    lines = [f"{name} {'won' if result['is_win'] else 'lost'} vs. {result['opponent']} ({result['runs']} runs)"]
    for promo in promos:
        try:
            triggered = promo["trigger"](result)
        except Exception:
            triggered = False
        lines.append(f"* {promo['name']}? {'Y' if triggered else 'N'}")
    return "\n".join(lines)

def main():
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    date_str = yesterday.strftime("%A, %B %d")

    team_names = {DODGERS_ID: "Dodgers", ANGELS_ID: "Angels"}

    triggered_any = False
    body_lines = [f"Games played: {date_str}", ""]
    for team_id, promos in PROMOTIONS.items():
        result = get_game_result(team_id)
        summary = build_summary(team_names[team_id], result, promos)
        body_lines.append(summary)
        body_lines.append("")

        for promo in promos:
            try:
                if promo["trigger"](result):
                    triggered_any = True
            except Exception:
                continue

    if triggered_any:
        recipients = fetch_emails()
        body = "\n".join(body_lines).strip()
        subject = f"Promo Alert for {date_str}"
        print("==== Email Content ====")
        print("Subject:", subject)
        print(body)
        send_emails(subject, body, recipients)
        print(f"Email sent to {len(recipients)} recipients.")
    else:
        print("No promos triggered. Email not sent.")

if __name__ == "__main__":
    print("SCRIPT STARTING: top-level code is executing")
    main()

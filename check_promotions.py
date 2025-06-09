import os, requests, smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials

TEAMS = {
    "Dodgers": {
        "id": 119,
        "promos": [
            {"name": "Panda Express: Win", "trigger": lambda g: g["win"]},
            {"name": "McDonald’s: Score in 1st", "trigger": lambda g: g["scored_by_inning"][0] > 0 if g["scored_by_inning"] else False},
            {"name": "Jack in the Box: Score 6+", "trigger": lambda g: g["runs_for"] >= 6},
            {"name": "ampm: 10+ Strikeouts", "trigger": lambda g: g["strikeouts"] >= 10}
        ]
    },
    "Angels": {
        "id": 108,
        "promos": [
            {"name": "McDonald’s: Score in 1st", "trigger": lambda g: g["scored_by_inning"][0] > 0 if g["scored_by_inning"] else False},
            {"name": "Del Taco: Win", "trigger": lambda g: g["win"]}
        ]
    }
}

SPREADSHEET_ID = '1e9ujE14dzkqtiYgKuI6nZfMNXPDpLgFIfZ88dr-kp14'
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = os.environ["BREVO_EMAIL"]
SMTP_PASS = os.environ["BREVO_PASS"]
SMTP_SENDER = os.environ["BREVO_SENDER"]

def fetch_emails():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    return sheet.col_values(2)[1:]  # Skip header

def send_email(subject, body, recipients):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = f"LA Sports Food <{SMTP_SENDER}>"
    msg["To"] = ", ".join(recipients)
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_SENDER, recipients, msg.as_string())

def check_game(team_id):
    date = datetime.now() - timedelta(days=1)
    date_str = date.strftime('%Y-%m-%d')
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&teamId={team_id}&hydrate=linescore'
    r = requests.get(url)
    data = r.json()

    try:
        game = data['dates'][0]['games'][0]
        linescore = game.get("linescore", {})
        team_side = 'home' if game['teams']['home']['team']['id'] == team_id else 'away'
        opponent = game['teams']['away']['team']['name'] if team_side == 'home' else game['teams']['home']['team']['name']
        runs_for = game['teams'][team_side]['score']
        runs_against = game['teams']['home' if team_side == 'away' else 'away']['score']
        innings = linescore.get("innings", [])
        scored_by_inning = [inning.get(team_side[0], 0) for inning in innings]
        strikeouts = game['teams'][team_side].get("strikeOuts", 0)
        win = game['teams'][team_side].get("isWinner", False)

        return {
            "opponent": opponent,
            "runs_for": runs_for,
            "runs_against": runs_against,
            "scored_by_inning": scored_by_inning,
            "strikeouts": strikeouts,
            "win": win
        }
    except (IndexError, KeyError):
        return None

def main():
    date_obj = datetime.now() - timedelta(days=1)
    date_str = date_obj.strftime('%A, %B %d')
    output = [f"**{date_str}**\n"]
    total_triggers = 0

    for team, info in TEAMS.items():
        result = check_game(info["id"])
        if not result:
            output.append(f"{team}: No game or data unavailable.\n")
            continue

        line = f"{team} vs. {result['opponent']}: {'Win' if result['win'] else 'Loss'} ({result['runs_for']}-{result['runs_against']})"
        output.append(line)

        for promo in info["promos"]:
            triggered = promo["trigger"](result)
            if triggered:
                total_triggers += 1
            output.append(f"• {promo['name']}? {'Y' if triggered else 'N'}")
        output.append("")

    if total_triggers == 0:
        print("No food promos triggered. Email will not be sent.")
        return

    subject = f"{total_triggers} food promo{'s' if total_triggers != 1 else ''} active today!"
    body = "\n".join(output)
    print("==== Email Content ====")
    print("Subject:", subject)
    print(body)

    recipients = fetch_emails()
    send_email(subject, body, recipients)
    print(f"Email sent to {len(recipients)} recipients.")

if __name__ == "__main__":
    main()

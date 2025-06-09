import requests
import datetime
import smtplib
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# === CONFIG ===
DODGERS_ID = 119
ANGELS_ID = 108

SPREADSHEET_ID = '1e9ujE14dzkqtiYgKuI6nZfMNXPDpLgFIfZ88dr-kp14'
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = os.environ["BREVO_EMAIL"]
SMTP_PASS = os.environ["BREVO_PASS"]
SMTP_SENDER = os.environ["BREVO_SENDER"]

# === HELPERS ===
def fetch_boxscore(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    r = requests.get(url)
    return r.json() if r.ok else None

def get_team_stats(box, team_id):
    if not box or "teams" not in box:
        return None, None
    side = "home" if box["teams"]["home"]["team"]['id'] == team_id else "away"
    team = box["teams"][side]
    pitching = team.get("teamStats", {}).get("pitching", {})
    players = team.get("players", {})

    steals = 0
    for pstats in players.values():
        try:
            steals += pstats["stats"]["batting"].get("stolenBases", 0)
        except (KeyError, TypeError):
            continue

    strikeouts = pitching.get("strikeOuts", 0)
    return strikeouts, steals

def check_team_result(team_id):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&teamId={team_id}'
    r = requests.get(url)
    data = r.json()

    try:
        game = data['dates'][0]['games'][0]
        game_pk = game['gamePk']
        opponent = game['teams']['away']['team']['name'] if game['teams']['home']['team']['id'] == team_id else game['teams']['home']['team']['name']
        runs_for = game['teams']['home']['score'] if game['teams']['home']['team']['id'] == team_id else game['teams']['away']['score']
        runs_against = game['teams']['away']['score'] if game['teams']['home']['team']['id'] == team_id else game['teams']['home']['score']
        result = 'Win' if game['teams']['home']['team']['id'] == team_id and game['teams']['home'].get('isWinner') else 'Loss'
        boxscore = fetch_boxscore(game_pk)
        strikeouts, steals = get_team_stats(boxscore, team_id)
        return {
            "played": True,
            "opponent": opponent,
            "result": result,
            "runs_for": runs_for,
            "runs_against": runs_against,
            "strikeouts": strikeouts,
            "steals": steals
        }
    except (IndexError, KeyError):
        return {"played": False}

def fetch_emails():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    return sheet.col_values(2)[1:]

def send_emails(subject, body, recipients):
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = f"LA Sports Food <{SMTP_SENDER}>"
    msg["To"] = ", ".join(recipients)
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_SENDER, recipients, msg.as_string())

# === PROMO LOGIC ===
TEAMS = {
    "Dodgers": {
        "id": DODGERS_ID,
        "promos": [
            {"name": "Panda Express: Win?", "trigger": lambda g: g["result"] == "Win"},
            {"name": "McDonald’s: Score in 1st?", "trigger": lambda g: g["played"] and g.get("runs_for", 0) >= 1},
            {"name": "Jack in the Box: Score 6+?", "trigger": lambda g: g["played"] and g.get("runs_for", 0) >= 6},
            {"name": "ampm: 10+ Strikeouts?", "trigger": lambda g: g["played"] and g.get("strikeouts", 0) >= 10},
        ]
    },
    "Angels": {
        "id": ANGELS_ID,
        "promos": [
            {"name": "McDonald’s: Score in 1st?", "trigger": lambda g: g["played"] and g.get("runs_for", 0) >= 1},
            {"name": "Del Taco: Win?", "trigger": lambda g: g["result"] == "Win"},
        ]
    }
}

def format_email(date_str, summaries):
    lines = [f"<b>{date_str}</b><br><br>"]
    total_promos = 0
    for team, data in summaries.items():
        if not data["played"]:
            lines.append(f"{team} did not play.<br>")
            continue
        line = f"{team} vs. {data['opponent']}: {data['result']} ({data['runs_for']}-{data['runs_against']})<br>"
        lines.append(line)
        for name, triggered in data["results"]:
            lines.append(f"&bull; {name} {'Y' if triggered else 'N'}<br>")
        lines.append("<br>")
        total_promos += sum(1 for _, v in data["results"] if v)
    subject = f"{total_promos} food promo{'s' if total_promos != 1 else ''} active today!"
    return subject, "".join(lines).strip()

def main():
    date_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime('%A, %B %d')
    summaries = {}
    total_triggered = 0
    for team, info in TEAMS.items():
        result = check_team_result(info["id"])
        if not result["played"]:
            summaries[team] = result
            continue
        result_summary = []
        for promo in info["promos"]:
            try:
                triggered = promo["trigger"](result)
            except Exception:
                triggered = False
            result_summary.append((promo["name"], triggered))
            if triggered:
                total_triggered += 1
        result["results"] = result_summary
        summaries[team] = result

    if total_triggered == 0:
        print("No food promos active today. No email sent.")
        return

    emails = fetch_emails()
    subject, body = format_email(date_str, summaries)
    print("==== Email Content ====")
    print("Subject:", subject)
    print(body)
    send_emails(subject, body, emails)
    print(f"Email sent to {len(emails)} recipients.")

if __name__ == "__main__":
    print("SCRIPT STARTING: top-level code is executing")
    main()

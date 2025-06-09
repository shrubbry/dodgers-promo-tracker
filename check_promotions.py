import requests, datetime, smtplib, os
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials

DODGERS_ID = 119
ANGELS_ID = 108

SPREADSHEET_ID = '1e9ujE14dzkqtiYgKuI6nZfMNXPDpLgFIfZ88dr-kp14'
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = os.environ["BREVO_EMAIL"]
SMTP_PASS = os.environ["BREVO_PASS"]
SMTP_SENDER = os.environ["BREVO_SENDER"]

TEAMS = {
    "Dodgers": {
        "id": DODGERS_ID,
        "opponent": None,
        "result": None,
        "score": None,
        "home_game": None,
        "steals": None,
        "strikeouts": None,
        "promos": [
            {"name": "Panda Express: Win?", "trigger": lambda g: g["win"] and g["home_game"]},
            {"name": "McDonald’s: 6+?", "trigger": lambda g: g["runs"] >= 6},
            {"name": "ampm: Stolen base?", "trigger": lambda g: g["home_game"] and g["steals"] > 0},
            {"name": "Jack in the Box: Strikeouts 7+?", "trigger": lambda g: g["strikeouts"] >= 7},
        ],
    },
    "Angels": {
        "id": ANGELS_ID,
        "opponent": None,
        "result": None,
        "score": None,
        "home_game": None,
        "steals": None,
        "strikeouts": None,
        "promos": [
            {"name": "McDonald’s: Win?", "trigger": lambda g: g["win"]},
            {"name": "Del Taco: 5+ at home?", "trigger": lambda g: g["home_game"] and g["runs"] >= 5},
        ],
    },
}

def fetch_game_data(team_id):
    date = datetime.date.today() - datetime.timedelta(days=1)
    date_str = date.strftime('%Y-%m-%d')
    r = requests.get(f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&teamId={team_id}')
    data = r.json()
    try:
        game = data['dates'][0]['games'][0]
        gamepk = game['gamePk']
        is_home = game['teams']['home']['team']['id'] == team_id
        win = game['teams']['home' if is_home else 'away']['isWinner']
        team_runs = game['teams']['home' if is_home else 'away']['score']
        opp_runs = game['teams']['away' if is_home else 'home']['score']
        opp_name = game['teams']['away' if is_home else 'home']['team']['name']

        # Get boxscore for advanced stats
        box = requests.get(f'https://statsapi.mlb.com/api/v1/game/{gamepk}/boxscore').json()
        pitching = box['teams']['home' if is_home else 'away']['pitchers']
        strikeouts = sum(box['players'][f'ID{pid}']['stats']['pitching'].get('strikeOuts', 0) for pid in pitching)
        batters = box['teams']['home' if is_home else 'away']['batters']
        steals = sum(box['players'][f'ID{bid}']['stats']['batting'].get('stolenBases', 0) for bid in batters)

        return {
            "win": win,
            "home_game": is_home,
            "runs": team_runs,
            "opp_runs": opp_runs,
            "opp_name": opp_name,
            "strikeouts": strikeouts,
            "steals": steals,
        }
    except (IndexError, KeyError):
        return None

def fetch_emails():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    return sheet.col_values(2)[1:]  # Skip header

def format_summary(date_label, results):
    lines = [f"<b>{date_label}</b>", ""]
    for team, result in results.items():
        if result is None:
            lines.append(f"{team}: No game or data unavailable")
            continue
        status = "Win" if result["win"] else "Loss"
        lines.append(f"{team} vs. {result['opp_name']}: {status} ({result['runs']}-{result['opp_runs']})")
        for promo in TEAMS[team]['promos']:
            triggered = promo['trigger'](result)
            lines.append(f"&bull; {promo['name']} {'Y' if triggered else 'N'}")
        lines.append("")
    return "<br>".join(lines)

def format_subject(count):
    return f"{count} food promo{'s' if count != 1 else ''} active today!"

def send_emails(subject, html_body, recipients):
    msg = MIMEText(html_body, 'html')
    msg["Subject"] = subject
    msg["From"] = SMTP_SENDER
    msg["To"] = ", ".join(recipients)
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_SENDER, recipients, msg.as_string())

def main():
    print("SCRIPT STARTING: top-level code is executing")
    date = datetime.date.today() - datetime.timedelta(days=1)
    date_label = date.strftime("%A, %B %d")
    results = {}
    total_triggers = 0

    for team, meta in TEAMS.items():
        data = fetch_game_data(meta['id'])
        results[team] = data
        if data:
            triggered = sum(1 for promo in meta['promos'] if promo['trigger'](data))
            total_triggers += triggered

    print("==== Email Content ====")
    subject = format_subject(total_triggers)
    print("Subject:", subject)
    html = format_summary(date_label, results)
    print(html.replace("<br>", "\n"))

    if total_triggers > 0:
        recipients = fetch_emails()
        send_emails(subject, html, recipients)
        print(f"Email sent to {len(recipients)} recipients.")
    else:
        print("No triggered promos; no email sent.")

if __name__ == "__main__":
    main()

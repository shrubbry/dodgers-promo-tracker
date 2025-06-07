print("SCRIPT STARTING: zzz_debug_marker.py is running")
print("SCRIPT STARTING: top-level code is executing")

import requests, datetime, smtplib
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# MLB team IDs
DODGERS_ID = 119
ANGELS_ID = 108

# Google Sheet setup
SHEET_NAME = 'Dodgers-Angels Promo Alerts (Responses)'  # Tab name
SPREADSHEET_ID = '1e9ujE14dzkqtiYgKuI6nZfMNXPDpLgFIfZ88dr-kp14'

# Email credentials (set via GitHub Secrets)
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = os.environ["BREVO_EMAIL"]
SMTP_PASS = os.environ["BREVO_PASS"]
SMTP_SENDER = os.environ["BREVO_SENDER"]

def check_team_result(team_id):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&teamId={team_id}'
    r = requests.get(url)
    data = r.json()

    try:
        game = data['dates'][0]['games'][0]
    except (IndexError, KeyError):
        return None

    team_side = 'home' if game['teams']['home']['team']['id'] == team_id else 'away'
    win = game['teams'][team_side].get('isWinner', False)
    return win

def fetch_emails():
    print("Running fetch_emails()...")

    print("Setting scope...")
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']

    print("Loading creds...")
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)

    print("Authorizing gspread...")
    gc = gspread.authorize(creds)

    print("Opening sheet...")
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

    print("Fetching col values...")
    result = sheet.col_values(2)[1:]

    print("Returning email list...")
    return result

def send_emails(message, recipients):
    msg = MIMEText(message)
    msg["Subject"] = "Dodgers/Angels Promotion Alert"
    msg["From"] = SMTP_SENDER
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, recipients, msg.as_string())

def main():
    dodgers_win = check_team_result(DODGERS_ID)
    angels_win = check_team_result(ANGELS_ID)

    promos = []
    if dodgers_win:
        promos.append("Dodgers Win! Panda Express promo active.")
    if angels_win:
        promos.append("Angels Win! McDonald's fries promo active.")

    if promos:
        emails = fetch_emails()
        print("Fetched emails:", emails)
        message = "\n".join(promos)
        send_emails(message, emails)
        print(f"Sent to {len(emails)} subscribers.")
    else:
        print("No promotions triggered.")

if __name__ == "__main__":
    print("Manual test: checking if creds.json exists...")
    print("creds.json exists?", os.path.exists("creds.json"))

    print("Manual test: calling fetch_emails() outside of promo block")
    try:
        emails = fetch_emails()
        print("Fetched emails (manual test):", emails)
    except Exception as e:
        print("ERROR during fetch_emails:", e)

    main()

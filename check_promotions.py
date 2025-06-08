import requests, datetime, smtplib, os
from email.mime.text import MIMEText
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === TEAM INFO ===
DODGERS_ID = 119
ANGELS_ID = 108
TEAM_NAMES = {
    DODGERS_ID: "Dodgers",
    ANGELS_ID: "Angels"
}

# === GOOGLE SHEET CONFIG ===
SPREADSHEET_ID = '1e9ujE14dzkqtiYgKuI6nZfMNXPDpLgFIfZ88dr-kp14'

# === EMAIL CONFIG (via GitHub Secrets) ===
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
smtp_user = os.environ["BREVO_EMAIL"]
smtp_pass = os.environ["BREVO_PASS"]
smtp_sender = os.environ["BREVO_SENDER"]

# === RESULT STRUCTURE ===
class GameResult:
    def __init__(self, team_name, opponent, team_score, opp_score, status, is_winner=None):
        self.team_name = team_name
        self.opponent = opponent
        self.team_score = team_score
        self.opp_score = opp_score
        self.status = status  # "F" (Final), "PPD" (Postponed), etc.
        self.is_winner = is_winner

    def summary(self):
        if self.status != "F":
            return f"{self.team_name} game was {self.status.lower()}."
        outcome = "won" if self.is_winner else "lost"
        return f"{self.team_name} {outcome} vs {self.opponent} ({self.team_score}–{self.opp_score})"

def get_game_result(team_id):
    date = datetime.date.today() - datetime.timedelta(days=1)
    date_str = date.strftime('%Y-%m-%d')
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&teamId={team_id}'
    r = requests.get(url)
    data = r.json()

    try:
        game = data['dates'][0]['games'][0]
    except (IndexError, KeyError):
        return None  # No game played

    teams = game['teams']
    status = game['status']['statusCode']
    is_home = teams['home']['team']['id'] == team_id
    team_side = 'home' if is_home else 'away'
    opp_side = 'away' if is_home else 'home'

    team_score = teams[team_side]['score']
    opp_score = teams[opp_side]['score']
    opponent = teams[opp_side]['team']['name']

    is_winner = teams[team_side].get('isWinner')

    return GameResult(
        team_name=TEAM_NAMES[team_id],
        opponent=opponent,
        team_score=team_score,
        opp_score=opp_score,
        status=status,
        is_winner=is_winner
    )

def fetch_emails():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    emails = sheet.col_values(2)[1:]
    return [e.strip() for e in emails if e.strip()]

def build_email(result_dodgers, result_angels):
    lines = []
    subject_tags = []

    if result_dodgers:
        lines.append(result_dodgers.summary())
        if result_dodgers.is_winner:
            lines.append("→ Panda Express promo active!")
            subject_tags.append("Dodgers Win")

    if result_angels:
        lines.append(result_angels.summary())
        if result_angels.is_winner:
            lines.append("→ McDonald's fries promo active!")
            subject_tags.append("Angels Win")

    date_line = f"Games played: {(datetime.date.today() - datetime.timedelta(days=1)).strftime('%A, %B %d')}"
    subject = f"{' + '.join(subject_tags) or 'No Promos'} ({date_line})"

    return subject, "\n".join([date_line, ""] + lines)

def send_emails(subject, message, recipients):
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = smtp_sender
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_sender, recipients, msg.as_string())

def main():
    result_dodgers = get_game_result(DODGERS_ID)
    result_angels = get_game_result(ANGELS_ID)

    if not result_dodgers and not result_angels:
        print("No games played yesterday.")
        return

    subject, body = build_email(result_dodgers, result_angels)
    print("==== Email Content ====")
    print(f"Subject: {subject}")
    print(body)

    recipients = fetch_emails()
    if not recipients:
        print("No subscribers found. Skipping email send.")
        return

    send_emails(subject, body, recipients)
    print(f"Email sent to {len(recipients)} recipients.")

if __name__ == "__main__":
    print("SCRIPT STARTING: top-level code is executing")
    main()


import requests
import datetime

# MLB team IDs
DODGERS_ID = 119
ANGELS_ID = 108

def check_team_result(team_id):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&teamId={team_id}'
    r = requests.get(url)
    data = r.json()

    try:
        game = data['dates'][0]['games'][0]
    except (IndexError, KeyError):
        print(f"No game found for team {team_id} on {date_str}")
        return None

    team_side = 'home' if game['teams']['home']['team']['id'] == team_id else 'away'
    win = game['teams'][team_side].get('isWinner', False)
    return win

def main():
    dodgers_win = check_team_result(DODGERS_ID)
    angels_win = check_team_result(ANGELS_ID)

    print("==== Promo Results ====")
    if dodgers_win:
        print("Dodgers Win! Panda Express promo active.")
    else:
        print("Dodgers lost or didn’t play.")

    if angels_win:
        print("Angels Win! McDonald's fries promo active.")
    else:
        print("Angels lost or didn’t play.")

if __name__ == "__main__":
    main()

import requests

player_id = 1
response = requests.get(f"https://fantasy.premierleague.com/api/element-summary/{player_id}/")
data = response.json()
history = data['history_past']

for season in history:
    print(season['season_name'])
    print("Influence:", season.get('influence'))
    print("Creativity:", season.get('creativity'))
    print("Threat:", season.get('threat'))
    print("ICT Index:", season.get('ict_index'))
    print("Value:", season.get('value'))
    print("-----")


player_id = 2  # Example player ID
response = requests.get(f"https://fantasy.premierleague.com/api/element-summary/{player_id}/")
data = response.json()
history = data['history_past']

for season in history:
    print(season.get('season_name'), ":", season.get('value'))

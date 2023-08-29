import os
import requests
from bs4 import BeautifulSoup
import sqlite3
import concurrent.futures

# Change the working directory to the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

UPDATE_PAST_PERFORMANCE = False

TEAM_NAME_MAPPING = {
    "Brighton": "Brighton & Hove Albion",
    "Luton": "Luton Town",
    "Man City": "Manchester City",
    "Man Utd": "Manchester United",
    "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest",
    "Sheffield Utd": "Sheffield United",
    "Spurs": "Tottenham Hotspur",
    "West Ham": "West Ham United",
    "Wolves": "Wolverhampton Wanderers"
}

BASE_FPL_URL = "https://fantasy.premierleague.com/api/"
IMAGE_BASE_URL = "https://resources.premierleague.com/premierleague/photos/players/110x140/"

def fetch_data_from_fpl(endpoint):
    try:
        response = requests.get(BASE_FPL_URL + endpoint)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None

def download_image(player):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    player_id, photo = player
    image_filename = photo.replace(".jpg", "")  # Remove the .jpg from the filename
    local_image_path = os.path.join('..\\assets\\player_images', image_filename + ".png")

    # Check if the image already exists
    if not os.path.exists(local_image_path):
        image_url = IMAGE_BASE_URL + "p" + image_filename + ".png"
        try:
            # Download the image
            image_response = requests.get(image_url, headers=headers, stream=True)
            image_response.raise_for_status()

            # Save the image to the local directory
            with open(local_image_path, 'wb') as file:
                for chunk in image_response.iter_content(chunk_size=8192):
                    file.write(chunk)

            return player_id, 'Downloaded'
        except requests.HTTPError:
            print(f"Failed to download image for player with ID {player_id} from URL: {image_url}")
            return player_id, 'Not Available'
    return player_id, 'Exists'  # If the image already exists

def fetch_player_images():
    # Create a directory to store the images if it doesn't exist
    if not os.path.exists('..\\assets\\player_images'):
        os.makedirs('..\\assets\\player_images')

    # Connect to SQLite database
    conn = sqlite3.connect(r'..\\data\\fpl_data.db')
    cursor = conn.cursor()

    # Fetch players with image_status 'Pending' or 'Not Available' from the database
    cursor.execute("SELECT player_id, photo FROM player_info WHERE image_status IN ('Pending', 'Not Available')")
    players = cursor.fetchall()

    # Use ThreadPoolExecutor to download images concurrently
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(download_image, players))

    # Update the database with the results
    for player_id, status in results:
        cursor.execute("UPDATE player_info SET image_status = ? WHERE player_id = ?", (status, player_id))

    # Commit changes and close connection
    conn.commit()
    conn.close()

    print("Player images download process completed!")

def fetch_performance_data(player_id, data_type):
    data = fetch_data_from_fpl(f"element-summary/{player_id}/")
    if data:
        return player_id, data[data_type]
    return player_id, None

def fetch_league_data(league_id):
    try:
        response = requests.get(f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None

def fetch_team_history(entry_id):
    """Fetch the team history data for a given entry ID."""
    try:
        response = requests.get(f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None

def scrape_stadium_and_manager():
    # URL for the Wikipedia page of the current Premier League season
    url = "https://en.wikipedia.org/wiki/2023%E2%80%9324_Premier_League"

    # Fetch the webpage content
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find all tables with the class 'wikitable'
    tables = soup.findAll('table', {'class': 'wikitable'})

    # Extract team names and stadium names from the first table
    stadium_data = {}
    for row in tables[0].findAll('tr')[1:]:  # Skip the header row
        columns = row.findAll('td')
        team_name = columns[0].find('a').text.strip() if columns[0].find('a') else columns[0].text.strip()
        stadium_name = columns[2].find('a').text.strip() if columns[2].find('a') else columns[2].text.strip()
        stadium_data[team_name] = stadium_name

    # Extract team names and manager names from the second table
    manager_data = {}
    for row in tables[1].findAll('tr')[1:]:  # Skip the header row
        columns = row.findAll('td')
        team_link = columns[0].find('a')
        team_name = team_link.text.strip() if team_link else columns[0].get_text(strip=True)
        
        manager_name = columns[1].get_text(strip=True)
                
        # Use the mapping to get the correct team name
        team_name_mapped = TEAM_NAME_MAPPING.get(team_name, team_name)
        manager_data[team_name_mapped] = manager_name

    print("Stadium Data:", stadium_data)
    print("Manager Data:", manager_data)

    # Connect to SQLite database and update the teams table
    conn = sqlite3.connect(r'..\\data\\fpl_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print(cursor.fetchall())
    for team in stadium_data:
        cursor.execute("""
            UPDATE teams
            SET stadium = ?, manager = ?
            WHERE team_name = ?
        """, (stadium_data[team], manager_data.get(team, "Unknown"), team))

    conn.commit()
    conn.close()

    print("Stadium and manager data updated successfully!")

def ingest_player_info():
    try:
        # Fetch data from FPL API
        print("Fetching player data from FPL API...")
        response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
        response.raise_for_status()  # Raise an exception for HTTP errors

        data = response.json()

        # Extract player data
        players = data['elements']

        # Connect to SQLite database
        print("Connecting to SQLite database...")
        conn = sqlite3.connect(r'..\\data\\fpl_data.db')
        cursor = conn.cursor()

        # Insert or update player data in the player_info table
        print("Inserting or updating player data into the database...")
        for player in players:
            
            # Insert the player if they don't exist
            cursor.execute("""
                INSERT OR IGNORE INTO player_info (
                    player_id, first_name, last_name, position, team_id, status, total_points, current_value, selected_by_percent, 
                    news, photo, chance_of_playing_next_round, chance_of_playing_this_round, code, cost_change_event, cost_change_event_fall,
                    cost_change_start, cost_change_start_fall, dreamteam_count, element_type, ep_next, ep_this, event_points, form,
                    in_dreamteam, news_added, points_per_game, squad_number, team_code, transfers_in, transfers_in_event, transfers_out,
                    transfers_out_event, value_form, value_season, web_name, minutes, goals_scored, assists, clean_sheets, goals_conceded,
                    own_goals, penalties_saved, penalties_missed, yellow_cards, red_cards, saves, bonus, bps, influence, creativity,
                    threat, ict_index, starts, expected_goals, expected_assists, expected_goal_involvements, expected_goals_conceded,
                    influence_rank, influence_rank_type, creativity_rank, creativity_rank_type, threat_rank, threat_rank_type,
                    ict_index_rank, ict_index_rank_type, corners_and_indirect_freekicks_order, corners_and_indirect_freekicks_text,
                    direct_freekicks_order, direct_freekicks_text, penalties_order, penalties_text, expected_goals_per_90, saves_per_90,
                    expected_assists_per_90, expected_goal_involvements_per_90, expected_goals_conceded_per_90, goals_conceded_per_90,
                    now_cost_rank, now_cost_rank_type, form_rank, form_rank_type, points_per_game_rank, points_per_game_rank_type,
                    selected_rank, selected_rank_type, starts_per_90, clean_sheets_per_90
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                player['id'], player['first_name'], player['second_name'], player['element_type'], player['team'], player['status'], 
                player['total_points'], player['now_cost'], player['selected_by_percent'], player['news'], player['photo'], 
                player.get('chance_of_playing_next_round', None), player.get('chance_of_playing_this_round', None), player['code'],
                player['cost_change_event'], player['cost_change_event_fall'], player['cost_change_start'], player['cost_change_start_fall'],
                player['dreamteam_count'], player['element_type'], player['ep_next'], player['ep_this'], player['event_points'], player['form'],
                player['in_dreamteam'], player.get('news_added', None), player['points_per_game'], player.get('squad_number', None), player['team_code'],
                player['transfers_in'], player['transfers_in_event'], player['transfers_out'], player['transfers_out_event'], player['value_form'],
                player['value_season'], player['web_name'], player['minutes'], player['goals_scored'], player['assists'], player['clean_sheets'],
                player['goals_conceded'], player['own_goals'], player['penalties_saved'], player['penalties_missed'], player['yellow_cards'],
                player['red_cards'], player['saves'], player['bonus'], player['bps'], player['influence'], player['creativity'], player['threat'],
                player['ict_index'], player['starts'], player['expected_goals'], player['expected_assists'], player['expected_goal_involvements'],
                player['expected_goals_conceded'], player['influence_rank'], player['influence_rank_type'], player['creativity_rank'],
                player['creativity_rank_type'], player['threat_rank'], player['threat_rank_type'], player['ict_index_rank'], player['ict_index_rank_type'],
                player.get('corners_and_indirect_freekicks_order', None), player.get('corners_and_indirect_freekicks_text', None),
                player.get('direct_freekicks_order', None), player.get('direct_freekicks_text', None), player.get('penalties_order', None),
                player.get('penalties_text', None), player['expected_goals_per_90'], player['saves_per_90'], player['expected_assists_per_90'],
                player['expected_goal_involvements_per_90'], player['expected_goals_conceded_per_90'], player['goals_conceded_per_90'],
                player['now_cost_rank'], player['now_cost_rank_type'], player['form_rank'], player['form_rank_type'], player['points_per_game_rank'],
                player['points_per_game_rank_type'], player['selected_rank'], player['selected_rank_type'], player['starts_per_90'], player['clean_sheets_per_90']
            ))

            # Update the player's details
            cursor.execute("""
                UPDATE player_info
                SET first_name = ?, last_name = ?, position = ?, team_id = ?, status = ?, total_points = ?, current_value = ?, selected_by_percent = ?, 
                news = ?, photo = ?, chance_of_playing_next_round = ?, chance_of_playing_this_round = ?, code = ?, cost_change_event = ?, 
                cost_change_event_fall = ?, cost_change_start = ?, cost_change_start_fall = ?, dreamteam_count = ?, element_type = ?, ep_next = ?, 
                ep_this = ?, event_points = ?, form = ?, in_dreamteam = ?, news_added = ?, points_per_game = ?, squad_number = ?, team_code = ?, 
                transfers_in = ?, transfers_in_event = ?, transfers_out = ?, transfers_out_event = ?, value_form = ?, value_season = ?, web_name = ?, 
                minutes = ?, goals_scored = ?, assists = ?, clean_sheets = ?, goals_conceded = ?, own_goals = ?, penalties_saved = ?, penalties_missed = ?, 
                yellow_cards = ?, red_cards = ?, saves = ?, bonus = ?, bps = ?, influence = ?, creativity = ?, threat = ?, ict_index = ?, starts = ?, 
                expected_goals = ?, expected_assists = ?, expected_goal_involvements = ?, expected_goals_conceded = ?, influence_rank = ?, 
                influence_rank_type = ?, creativity_rank = ?, creativity_rank_type = ?, threat_rank = ?, threat_rank_type = ?, ict_index_rank = ?, 
                ict_index_rank_type = ?, corners_and_indirect_freekicks_order = ?, corners_and_indirect_freekicks_text = ?, direct_freekicks_order = ?, 
                direct_freekicks_text = ?, penalties_order = ?, penalties_text = ?, expected_goals_per_90 = ?, saves_per_90 = ?, expected_assists_per_90 = ?, 
                expected_goal_involvements_per_90 = ?, expected_goals_conceded_per_90 = ?, goals_conceded_per_90 = ?, now_cost_rank = ?, 
                now_cost_rank_type = ?, form_rank = ?, form_rank_type = ?, points_per_game_rank = ?, points_per_game_rank_type = ?, selected_rank = ?, 
                selected_rank_type = ?, starts_per_90 = ?, clean_sheets_per_90 = ?
                WHERE player_id = ?
            """, (
                player['first_name'], player['second_name'], player['element_type'], player['team'], player['status'], player['total_points'], 
                player['now_cost'], player['selected_by_percent'], player['news'], player['photo'], player.get('chance_of_playing_next_round', None),
                player.get('chance_of_playing_this_round', None), player['code'], player['cost_change_event'], player['cost_change_event_fall'],
                player['cost_change_start'], player['cost_change_start_fall'], player['dreamteam_count'], player['element_type'], player['ep_next'],
                player['ep_this'], player['event_points'], player['form'], player['in_dreamteam'], player.get('news_added', None), player['points_per_game'],
                player.get('squad_number', None), player['team_code'], player['transfers_in'], player['transfers_in_event'], player['transfers_out'],
                player['transfers_out_event'], player['value_form'], player['value_season'], player['web_name'], player['minutes'], player['goals_scored'],
                player['assists'], player['clean_sheets'], player['goals_conceded'], player['own_goals'], player['penalties_saved'], player['penalties_missed'],
                player['yellow_cards'], player['red_cards'], player['saves'], player['bonus'], player['bps'], player['influence'], player['creativity'],
                player['threat'], player['ict_index'], player['starts'], player['expected_goals'], player['expected_assists'], player['expected_goal_involvements'],
                player['expected_goals_conceded'], player['influence_rank'], player['influence_rank_type'], player['creativity_rank'], player['creativity_rank_type'],
                player['threat_rank'], player['threat_rank_type'], player['ict_index_rank'], player['ict_index_rank_type'], player.get('corners_and_indirect_freekicks_order', None),
                player.get('corners_and_indirect_freekicks_text', None), player.get('direct_freekicks_order', None), player.get('direct_freekicks_text', None),
                player.get('penalties_order', None), player.get('penalties_text', None), player['expected_goals_per_90'], player['saves_per_90'], player['expected_assists_per_90'],
                player['expected_goal_involvements_per_90'], player['expected_goals_conceded_per_90'], player['goals_conceded_per_90'], player['now_cost_rank'],
                player['now_cost_rank_type'], player['form_rank'], player['form_rank_type'], player['points_per_game_rank'], player['points_per_game_rank_type'],
                player['selected_rank'], player['selected_rank_type'], player['starts_per_90'], player['clean_sheets_per_90'], player['id']
            ))

        # Commit changes and close connection
        conn.commit()
        print("Player data insertion or update complete!")
        conn.close()

    except requests.RequestException as e:
        print(f"Error fetching player data from FPL API: {e}")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def ingest_past_performance():
    try:
        # Connect to SQLite database
        print("Connecting to SQLite database...")
        conn = sqlite3.connect(r'..\\data\\fpl_data.db')
        cursor = conn.cursor()

        # Fetch all player IDs from the player_info table
        cursor.execute("SELECT player_id FROM player_info")
        player_ids = cursor.fetchall()

        # Use ThreadPoolExecutor to fetch data concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_id = {executor.submit(fetch_performance_data, player_id[0], 'history_past'): player_id[0] for player_id in player_ids}
            for future in concurrent.futures.as_completed(future_to_id):
                player_id = future_to_id[future]
                history = future.result()[1]
                if history:
                    for season in history:
                        influence = season.get('influence', 0)
                        creativity = season.get('creativity', 0)
                        threat = season.get('threat', 0)
                        ict_index = season.get('ict_index', 0)

                        # Check if the entry already exists
                        cursor.execute("""
                            SELECT season_id FROM past_performance WHERE player_id = ? AND season_name = ?
                        """, (player_id, season['season_name']))
                        existing_id = cursor.fetchone()

                        if existing_id:
                            season_id = existing_id[0]
                        else:
                            cursor.execute("SELECT MAX(season_id) FROM past_performance")
                            max_id = cursor.fetchone()[0]
                            season_id = (max_id or 0) + 1

                        cursor.execute("""
                            INSERT OR REPLACE INTO past_performance (season_id, player_id, season_name, total_points, minutes, goals_scored, assists, clean_sheets, goals_conceded, own_goals, penalties_saved, penalties_missed, yellow_cards, red_cards, saves, bonus, bps, influence, creativity, threat, ict_index)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (season_id, player_id, season['season_name'], season['total_points'], season['minutes'], season['goals_scored'], season['assists'], season['clean_sheets'], season['goals_conceded'], season['own_goals'], season['penalties_saved'], season['penalties_missed'], season['yellow_cards'], season['red_cards'], season['saves'], season['bonus'], season['bps'], influence, creativity, threat, ict_index))

        # Commit changes and close connection
        conn.commit()
        print("Past performance data insertion complete!")
        conn.close()

    except requests.RequestException as e:
        print(f"Error fetching data from FPL API: {e}")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def ingest_recent_performance():
    try:
        # Connect to SQLite database
        print("Connecting to SQLite database...")
        conn = sqlite3.connect(r'..\\data\\fpl_data.db')
        cursor = conn.cursor()

        # Fetch all player IDs from the player_info table
        cursor.execute("SELECT player_id FROM player_info")
        player_ids = cursor.fetchall()

        # Use ThreadPoolExecutor to fetch data concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_id = {executor.submit(fetch_performance_data, player_id[0], 'history'): player_id[0] for player_id in player_ids}
            for future in concurrent.futures.as_completed(future_to_id):
                player_id = future_to_id[future]
                history = future.result()[1]
                if history:
                    for match in history:
                        # Check if the entry already exists
                        cursor.execute("""
                            SELECT performance_id FROM recent_performance WHERE player_id = ? AND gameweek = ?
                        """, (player_id, match['round']))
                        existing_id = cursor.fetchone()

                        if existing_id:
                            performance_id = existing_id[0]
                        else:
                            cursor.execute("SELECT MAX(performance_id) FROM recent_performance")
                            max_id = cursor.fetchone()[0]
                            performance_id = (max_id or 0) + 1

                        cursor.execute("""
                            INSERT OR REPLACE INTO recent_performance (performance_id, player_id, gameweek, total_points, minutes, goals_scored, assists, bonus, saves, yellow_cards, red_cards, own_goals, penalties_missed, penalties_saved, opponent_team, was_home, clean_sheets, goals_conceded, bps, influence, creativity, threat, ict_index, value, transfers_balance)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (performance_id, player_id, match['round'], match['total_points'], match['minutes'], match['goals_scored'], match['assists'], match['bonus'], match['saves'], match['yellow_cards'], match['red_cards'], match['own_goals'], match['penalties_missed'], match['penalties_saved'], match['opponent_team'], match['was_home'], match['clean_sheets'], match['goals_conceded'], match['bps'], match['influence'], match['creativity'], match['threat'], match['ict_index'], match['value'], match['transfers_balance']))

        # Commit changes and close connection
        conn.commit()
        print("Recent performance data insertion complete!")
        conn.close()

    except requests.RequestException as e:
        print(f"Error fetching data from FPL API: {e}")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def ingest_upcoming_fixtures():
    try:
        # Fetch data from FPL API
        print("Fetching upcoming fixtures data from FPL API...")
        response = requests.get("https://fantasy.premierleague.com/api/fixtures/")
        response.raise_for_status()  # Raise an exception for HTTP errors

        fixtures = response.json()

        # Connect to SQLite database
        print("Connecting to SQLite database...")
        conn = sqlite3.connect(r'..\\data\\fpl_data.db')
        cursor = conn.cursor()

        # Insert upcoming fixtures data into the upcoming_fixtures table
        print("Inserting upcoming fixtures data into the database...")
        for fixture in fixtures:
            # Determine if the fixture is a home game for the team
            is_home = 1 if fixture['team_h'] == fixture['team_h'] else 0

            # Check if the row already exists in the database
            cursor.execute("""
                SELECT 1 FROM upcoming_fixtures WHERE fixture_id = ?
            """, (fixture['id'],))
            row_exists = cursor.fetchone()

            # If the row doesn't exist, insert it
            if not row_exists:
                cursor.execute("""
                    INSERT INTO upcoming_fixtures (fixture_id, team_id, opponent_team_id, gameweek, is_home, fixture_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (fixture['id'], fixture['team_h'], fixture['team_a'], fixture['event'], is_home, fixture['kickoff_time']))

        # Commit changes and close connection
        conn.commit()
        print("Upcoming fixtures data insertion complete!")
        conn.close()

    except requests.RequestException as e:
        print(f"Error fetching data from FPL API: {e}")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def ingest_team_info():   
    try:
        # Fetch data from FPL API
        print("Fetching data from FPL API...")
        response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
        response.raise_for_status()  # Raise an exception for HTTP errors

        data = response.json()

        # Extract team data
        teams = data['teams']

        # Connect to SQLite database
        print("Connecting to SQLite database...")
        conn = sqlite3.connect(r'..\\data\\fpl_data.db')
        cursor = conn.cursor()

        # Insert or update team data in the teams table
        print("Inserting or updating team data into the database...")
        for team in teams:
            # Use the mapping to get the correct team name
            team_name = TEAM_NAME_MAPPING.get(team['name'], team['name'])

            # Insert the team if it doesn't exist
            cursor.execute("""
                INSERT OR IGNORE INTO teams (team_name, short_name, strength)
                VALUES (?, ?, ?)
            """, (team_name, team['short_name'], team['strength']))

            # Update the team's details
            cursor.execute("""
                UPDATE teams
                SET short_name = ?, strength = ?
                WHERE team_name = ?
            """, (team['short_name'], team['strength'], team_name))

        # Commit changes and close connection
        conn.commit()
        print("Data insertion or update complete!")
        print(cursor.rowcount, "rows updated.")
        conn.close()

    except requests.RequestException as e:
        print(f"Error fetching data from FPL API: {e}")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def ingest_league_standings():
    league_ids = [9553, 1419663]  # Add more league IDs as needed

    # Connect to SQLite database
    print("Connecting to SQLite database...")
    conn = sqlite3.connect(r'..\\data\\fpl_data.db')
    cursor = conn.cursor()

    for league_id in league_ids:
        data = fetch_league_data(league_id)
        if data:
            standings = data['standings']['results']
            for team in standings:
                # Fetch the team history data to get the chips used and other metrics
                team_history = fetch_team_history(team['entry'])
                chips_used = team_history.get('chips', []) if team_history else []
                
                # Determine the chips used in the current gameweek
                current_gw_data = team_history['current'][-1] if team_history and 'current' in team_history else None
                recent_chip = [chip['name'] for chip in chips_used if chip['event'] == current_gw_data['event']] if current_gw_data else []

                # Extract other metrics from the current gameweek data
                gameweek_points = current_gw_data['points'] if current_gw_data else None
                previous_rank = current_gw_data['rank_sort'] if current_gw_data else None
                transfers_made = current_gw_data['event_transfers'] if current_gw_data else None
                bank_value = current_gw_data['bank'] / 10 if current_gw_data else None
                team_value = current_gw_data['value'] / 10 if current_gw_data else None

                # Insert or replace the data in the league_standings table
                cursor.execute("""
                    INSERT OR REPLACE INTO league_standings (player_id, league_id, team_name, player_name, total_points, rank, gameweek_points, previous_rank, transfers_made, bank_value, team_value, chips_used, recent_chip)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (team['entry'], league_id, team['entry_name'], team['player_name'], team['total'], team['rank'], gameweek_points, previous_rank, transfers_made, bank_value, team_value, ','.join([chip['name'] for chip in chips_used]), ','.join(recent_chip)))

                # Insert data into the player_gameweek_data table
                for gw_data in team_history['current']:
                    cursor.execute("""
                        INSERT OR REPLACE INTO player_gameweek_data (player_id, team_name, player_name, gameweek, points, rank, rank_sort, overall_rank, transfers_made, bank_value, team_value)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (team['entry'], team['entry_name'], team['player_name'], gw_data['event'], gw_data['points'], gw_data['rank'], gw_data['rank_sort'], gw_data['overall_rank'], gw_data['event_transfers'], gw_data['bank']/10, gw_data['value']/10))

    # Commit changes and close connection
    conn.commit()
    print("League standings and gameweek data insertion complete!")
    conn.close()

def main():

    # Check if the .db file exists at the expected path
    db_path = r'..\\data\\fpl_data.db'
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found in the current working directory: {os.getcwd()}")
        return  # Exit the main function early if the .db file is not found

    # Fetch and store team data
    ingest_team_info()

    # Scrape and store stadium and manager data
    scrape_stadium_and_manager()

    # Fetch and store player data
    ingest_player_info()

    # Call the function
    fetch_player_images()

    # Fetch and store past performance data if the flag is set
    if UPDATE_PAST_PERFORMANCE:
        ingest_past_performance()

    # Fetch and store recent performance data
    ingest_recent_performance()

    # Fetch and store upcoming fixtures
    ingest_upcoming_fixtures()

    # Fetch and store league standings data
    ingest_league_standings()

if __name__ == "__main__":
    main()
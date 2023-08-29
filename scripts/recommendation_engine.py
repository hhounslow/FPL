import sqlite3
import os
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load data from SQLite database into Pandas DataFrames
def load_data_from_db(database_path):
    tables = ['recent_performance', 'player_info', 'upcoming_fixtures', 'past_performance', 'teams']
    with sqlite3.connect(database_path) as conn:
        return {table: pd.read_sql_query(f"SELECT * FROM {table}", conn) for table in tables}

# Compute the refined recommendation score
def compute_refined_recommendation(data):

    # Merge player_info with teams data to get team names
    data['player_info'] = data['player_info'].merge(data['teams'], on='team_id', how='left')

    # 1. Player's Current Form
    data['player_info']['recent_form'] = data['recent_performance'].groupby('player_id')['total_points'].mean()

    # Extracting team_id for each player
    player_team_map = data['player_info'][['player_id', 'team_id']].set_index('player_id').to_dict()['team_id']
    data['recent_performance']['team_id'] = data['recent_performance']['player_id'].map(player_team_map)

    # 2. Team's Current Form
    team_form = data['recent_performance'].groupby('team_id')['total_points'].mean().reset_index(name='team_form')
    data['player_info'] = data['player_info'].merge(team_form, on='team_id', how='left')

    # 3. Player's Historical Performance (Reducing its influence)
    historical_performance = data['past_performance'].groupby('player_id')['total_points'].mean()
    data['player_info']['historical_form'] = data['player_info']['player_id'].map(historical_performance)
    
    # Computing set_piece_involvement
    data['player_info']['set_piece_involvement'] = (
        data['player_info']['corners_and_indirect_freekicks_order'].notna().astype(int) + 
        data['player_info']['direct_freekicks_order'].notna().astype(int) + 
        data['player_info']['penalties_order'].notna().astype(int)
    )

    # Calculate value_for_money
    data['player_info']['value_for_money'] = data['player_info']['total_points'] / data['player_info']['current_value']
    
    # Calculate goals_assists_per_90
    data['player_info']['goals_assists_per_90'] = (data['player_info']['goals_scored'] + data['player_info']['assists']) / data['player_info']['minutes'] * 90

    # Calculate ownership_differential
    data['player_info']['ownership_differential'] = 1 - data['player_info']['selected_by_percent'] / 100.0

    # Refining the scoring model based on the considerations
    data['player_info']['final_refined_score'] = (
        0.250 * data['player_info']['recent_form'] +
        0.225 * data['player_info']['team_form'] +
        0.05 * data['player_info']['historical_form'] +
        0.05 * data['player_info']['set_piece_involvement'] +
        0.15 * data['player_info']['bps'].astype(float) +
        0.05 * data['player_info']['value_for_money'] +   
        0.05 * data['player_info']['points_per_game'] +
        0.025 * data['player_info']['goals_assists_per_90'] +
        0.05 * data['player_info']['ownership_differential'] 
    )
    
    top_recommended_players = data['player_info'].sort_values(by='final_refined_score', ascending=False).head(25)
    
    return top_recommended_players

def print_score_breakdown(player_index, players_dataframe):
    player = players_dataframe.loc[player_index]

    print(f"Scoring Breakdown for {player['first_name']} {player['last_name']}:\n")

    breakdown_components = [
        ('Recent Form', 'recent_form', 0.250),
        ('Team Form', 'team_form', 0.225),
        ('Historical Form', 'historical_form', 0.0025),
        ('Set Piece Involvement', 'set_piece_involvement', 0.05),
        ('BPS', 'bps', 0.0015),
        ('Value for Money', 'value_for_money', 0.05),
        ('Points Per Game', 'points_per_game', 0.05),
        ('Goals & Assists Per 90', 'goals_assists_per_90', 0.025),
        ('Ownership Differential', 'ownership_differential', 0.05)
    ]

    for label, col_name, weight in breakdown_components:
        score_contribution = player[col_name] * weight
        print(f"{label}: {player[col_name]:.2f} * {weight} = {score_contribution:.2f}")

    print(f"\nTotal Refined Score: {player['final_refined_score']:.2f}")

DATABASE_PATH = os.path.join('..', 'data', 'fpl_data.db')
data = load_data_from_db(DATABASE_PATH)
top_players = compute_refined_recommendation(data)
top_players = top_players.reset_index(drop=True)
top_players.index = top_players.index + 1
print(top_players[['first_name', 'last_name', 'team_name', 'final_refined_score']])
player_index = int(input("\nEnter the index number of a player to see the scoring breakdown: "))

# Check if the entered index is valid
if player_index in top_players.index:
    print_score_breakdown(player_index, top_players)
else:
    print("Invalid index. Please enter a correct index number from the list.")
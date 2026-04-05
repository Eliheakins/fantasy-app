import duckdb

# Connect to the local shard
con = duckdb.connect()

# Mock a "Custom Formula" from a user
# Formula: Success Rate on 3rd Downs
custom_query = """
    SELECT
        passer_player_name,
        AVG(success) * 100 as custom_success_rate
    FROM 'nfl_pbp_2024.parquet'
    WHERE down = 3
    GROUP BY passer_player_name
    ORDER BY custom_success_rate DESC
    LIMIT 5
"""

print(con.execute(custom_query).df())

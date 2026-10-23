import numpy as np, polars as pl, nflreadpy as nfl
S="research/scratch"
frames=[]
for season in range(2018,2027):
    pbp=nfl.load_pbp(season)
    d=pbp.filter((pl.col("season_type")=="REG")&pl.col("epa").is_not_null()&pl.col("posteam").is_not_null()&((pl.col("pass")==1)|(pl.col("rush")==1)))
    g=d.group_by("season","week","posteam","defteam").agg(
        pl.col("epa").filter(pl.col("pass")==1).mean().alias("pass_epa"),
        pl.col("epa").filter(pl.col("rush")==1).mean().alias("rush_epa"),
        pl.col("sack").filter(pl.col("pass")==1).mean().alias("sack_rate"),
        (pl.col("pass")==1).mean().alias("pass_rate"),
        pl.len().alias("plays"))
    frames.append(g)
t=pl.concat(frames); t.write_parquet(f"{S}/team_game_epa.parquet"); print(t.height, t["season"].unique().sort().to_list())

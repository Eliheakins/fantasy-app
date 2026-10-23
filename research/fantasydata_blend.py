"""Does blending an outside weekly projection with ours help, on seasons with clean history?

Pulls the FantasyData weekly stat projections in the open `thecodeforest/fantasyfootball` repo
(2018 to 2021, one csv per week, about 300 players a week), scores them with Colgate's rules
(1 PPR, 4-point pass touchdown, -1 interception; no fumbles, which the projections lack), and
compares RMSE with our size-calibrated baseline for 2019 to 2021 and for blends between the two.
Names are matched to nflverse ids by name (85% match), so players it misses are left out.

Run from the repo root after `make refresh`: uv run python research/fantasydata_blend.py
"""

import urllib.request, io, csv, polars as pl, numpy as np
from fantasy import store
H={"User-Agent":"Mozilla/5.0"}
base="https://raw.githubusercontent.com/thecodeforest/fantasyfootball/main/examples/benchmarking_data/season/"
rows=[]
for yr in (2019,2020,2021):
    for wk in range(1,18):
        t=urllib.request.urlopen(urllib.request.Request(f"{base}{yr}/wk{wk}.csv",headers=H),timeout=60).read().decode()
        for r in csv.DictReader(io.StringIO(t)):
            r["season"]=yr; rows.append(r)
fd=pl.DataFrame(rows).with_columns([pl.col(c).cast(pl.Float64,strict=False) for c in rows[0] if c not in("name","team","position","opp","season","week")]+[pl.col("season").cast(pl.Int64),pl.col("week").cast(pl.Int64)])
# Colgate-like scoring: 1 PPR, 4 pt pass TD, -1 INT
fd=fd.with_columns((0.04*pl.col("passing_yds")+4*pl.col("passing_td")-1*pl.col("passing_int")+0.1*pl.col("rushing_yds")+6*pl.col("rushing_td")+0.1*pl.col("receiving_yds")+6*pl.col("receiving_td")+1.0*pl.col("receiving_rec")).alias("fd_proj"))
print("fantasydata rows",fd.height, fd.group_by("season").len().sort("season").to_dicts())
lid=store.read_table("leagues","raw").sort("league_key")["league_id"][0]  # colgate
ids=store.read_table("nfl_player_stats","raw").select(pl.col("player_id").alias("gsis_id"),pl.col("player_display_name").alias("name"),"season","week").unique()
pp=store.read_table("player_points").filter(pl.col("league_id")==lid).select("gsis_id","season","week","points")
from fantasy.stages.distributions import calibrated
pb=calibrated(store.read_table("proj_baseline").filter((pl.col("league_id")==lid)&~pl.col("is_future")&pl.col("has_history")).select("league_id","gsis_id","season","week","position","projection")).select("gsis_id","season","week","projection")
j=fd.join(ids,on=["name","season","week"],how="left")
print("matched names",j["gsis_id"].is_not_null().mean())
j=j.filter(pl.col("gsis_id").is_not_null()).join(pp,on=["gsis_id","season","week"],how="left").join(pb,on=["gsis_id","season","week"],how="left")
j=j.with_columns(played=pl.col("points").is_not_null(), points=pl.col("points").fill_null(0.0))
print("leak check: mean projected points, players with a points row vs without")
print(j.group_by("played").agg(pl.len().alias("n"),pl.col("fd_proj").mean().round(2).alias("fd_proj"),pl.col("projection").mean().round(2).alias("ours")))
b=j.filter(pl.col("played")&pl.col("projection").is_not_null()&(pl.col("fd_proj")>3))
for name,col in (("ours",pl.col("projection")),("fantasydata",pl.col("fd_proj")),("50/50",0.5*pl.col("projection")+0.5*pl.col("fd_proj"))):
    e=b.select(((col-pl.col("points"))**2).mean().sqrt().alias("rmse"),(col-pl.col("points")).abs().mean().alias("mae"))
    print(name, e.row(0), "n",b.height)
print("weight on fantasydata -> rmse (ours at 0, fantasydata at 1)")
for w in (0.0,0.25,0.5,0.75,0.9,1.0):
    col=(1-w)*pl.col("projection")+w*pl.col("fd_proj")
    print(w, round(float(b.select(((col-pl.col("points"))**2).mean().sqrt()).item()),3), "by season:", [round(float(b.filter(pl.col("season")==s).select(((col-pl.col("points"))**2).mean().sqrt()).item()),3) for s in (2019,2020,2021)])
print(b.group_by("position").agg(((pl.col("projection")-pl.col("points"))**2).mean().sqrt().round(2).alias("ours"),((pl.col("fd_proj")-pl.col("points"))**2).mean().sqrt().round(2).alias("fd")).sort("position"))

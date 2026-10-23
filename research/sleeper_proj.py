import json, time
import httpx, polars as pl, numpy as np
from fantasy import store

rows=[]
for wk in range(1,8):
    r=httpx.get(f"https://api.sleeper.com/projections/nfl/2026/{wk}",params={"season_type":"regular","position[]":["QB","RB","WR","TE","K"]},timeout=60)
    for d in r.json():
        rows.append({"week":wk,"sleeper_id":str(d["player_id"]),"stats":json.dumps(d["stats"]),"company":d.get("company"),"modified":d.get("last_modified")})
    time.sleep(0.3)
proj=pl.DataFrame(rows); print(proj.height, proj["company"].value_counts())
idm=store.read_table("id_map").select("sleeper_id","gsis_id")
pts=store.read_table("player_points"); base=store.read_table("proj_baseline").filter(~pl.col("is_future")&(pl.col("season")==2026))
out=[]
for lg in store.read_table("leagues","raw").iter_rows(named=True):
    sc=json.loads(lg["scoring_settings"]); lid=lg["league_id"]
    def score(s):
        d=json.loads(s); return sum(float(d.get(k,0))*w for k,w in sc.items() if w)
    p=proj.with_columns(pl.col("stats").map_elements(score,return_dtype=pl.Float64).alias("sleeper_proj")).join(idm,on="sleeper_id").drop_nulls("gsis_id")
    a=pts.filter((pl.col("league_id")==lid)&(pl.col("season")==2026)).select("gsis_id","week","position","points")
    b=base.filter(pl.col("league_id")==lid).select("gsis_id","week",pl.col("projection").alias("ours"))
    j=a.join(p.select("gsis_id","week","sleeper_proj"),on=["gsis_id","week"]).join(b,on=["gsis_id","week"],how="left")
    j=j.filter(pl.col("position")!="K").with_columns(pl.lit(lg["league_key"]).alias("lg"))
    out.append(j)
j=pl.concat(out)
j.write_parquet("research/scratch/sleeper_vs_ours.parquet")
print(j.height)

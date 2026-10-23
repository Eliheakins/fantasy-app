import json, numpy as np, polars as pl
from fantasy import store
from fantasy.stages.project import expected_frame, POSITIONS
leagues=store.read_table("leagues","raw"); lg=leagues.row(0,named=True); lid=lg["league_id"]
pp=store.read_table("player_points"); opp=store.read_table("nfl_ff_opportunity","raw")
exp=expected_frame(opp,pp,leagues.filter(pl.col("league_id")==lid))
base=store.read_table("proj_baseline").filter((pl.col("league_id")==lid)&~pl.col("is_future")&pl.col("has_history")).select("gsis_id","season","week","position","team","projection")
st=store.read_table("nfl_player_stats","raw").filter(pl.col("season_type")=="REG").select(pl.col("player_id").alias("gsis_id"),"season","week","carries","targets","target_share","air_yards_share","opponent_team")
ts=store.read_table("nfl_team_stats","raw").filter(pl.col("season_type")=="REG").select("team","season","week",pl.col("carries").alias("team_carries"))
first=st.group_by("gsis_id").agg(pl.col("season").min().alias("first_season"))
games=base.join(exp.select("gsis_id","season","week","exp_pts","points"),on=["gsis_id","season","week"],how="inner").join(st,on=["gsis_id","season","week"],how="left").join(ts,on=["team","season","week"],how="left").join(first,on="gsis_id",how="left")
games=games.with_columns((pl.col("carries")/pl.col("team_carries")).alias("carry_share"),(pl.col("points")-pl.col("projection")).alias("resid"),(pl.col("points")-pl.col("exp_pts")).alias("luck"),(pl.col("first_season")==pl.col("season")).alias("rookie")).sort("gsis_id","season","week")
# walk-forward player features using only prior games
def feats(g):
    luck=g["luck"].to_numpy(); ts_=g["target_share"].to_numpy(); cs=g["carry_share"].to_numpy(); season=g["season"].to_numpy()
    out_gap=np.full(len(g),np.nan); out_tt=np.full(len(g),np.nan); out_ct=np.full(len(g),np.nan)
    for i in range(len(g)):
        prior=slice(max(0,i-8),i)
        l=luck[prior]
        if len(l)>=3:
            w=0.5**(np.arange(len(l))[::-1]/4); out_gap[i]=(w*l).sum()/w.sum()
        same=season[:i]==season[i]
        t=ts_[:i][same]; c=cs[:i][same]
        if len(t)>=5 and np.isfinite(t[-3:]).all(): 
            r=np.nanmean(t[-3:]); e=np.nanmean(t[:-3]); out_tt[i]=r-e
        if len(c)>=5 and np.isfinite(c[-3:]).all():
            r=np.nanmean(c[-3:]); e=np.nanmean(c[:-3]); out_ct[i]=r-e
    return g.with_columns(pl.Series("gap",out_gap),pl.Series("tgt_trend",out_tt),pl.Series("carry_trend",out_ct))
parts=[feats(g) for _,g in games.group_by("gsis_id",maintain_order=True)]
panel=pl.concat(parts)
# opponent strength: walk-forward points allowed to position by opponent team, relative to league
allowed=panel.group_by("opponent_team","position","season","week").agg(pl.col("points").sum().alias("allowed")).sort("opponent_team","position","season","week")
league_mean=allowed.group_by("position","season","week").agg(pl.col("allowed").mean().alias("lm"))
allowed=allowed.join(league_mean,on=["position","season","week"]).with_columns((pl.col("allowed")-pl.col("lm")).alias("rel"))
allowed=allowed.with_columns(pl.col("rel").shift(1).ewm_mean(half_life=4,min_samples=3).over("opponent_team","position").alias("opp_rel"))
panel=panel.join(allowed.select("opponent_team","position","season","week","opp_rel"),on=["opponent_team","position","season","week"],how="left")
panel.write_parquet("research/scratch/outlook_panel.parquet")
print(panel.height); print(panel.select(pl.col("resid").mean(),pl.col("gap").mean(),pl.col("tgt_trend").std(),pl.col("opp_rel").std()))

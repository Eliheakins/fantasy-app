"""Does a learned model on lagged nflverse features beat the rolling baseline, and how far is it from FantasyData?

Part 1 trains a gradient-boosted regressor on 2019 to 2023 player-weeks (lagged exponentially
weighted points, expected points, targets, carries, attempts, snap share, target share and expected
touchdowns, games played, spread of recent points, implied total, home, position, week, practice
report flags) and scores 2024 to 2026 against our baseline with train-only calibration. Part 2
scores each of 2019 to 2021 with a model trained on the other seasons, on the FantasyData panel.

scikit-learn is not a project dependency. Run from the repo root after fd_panel.py:
    uv run --with scikit-learn python research/gbm_test.py
"""

import numpy as np, polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor
from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.stages.distributions import estimate_curves, residual_frame
lid=store.read_table("leagues","raw").sort("league_key")["league_id"][0]  # colgate
base=store.read_table("proj_baseline").filter((pl.col("league_id")==lid)&~pl.col("is_future")&pl.col("has_history"))
pp=store.read_table("player_points").filter(pl.col("league_id")==lid)
res=residual_frame(store.read_table("proj_baseline"),store.read_table("player_points"))
curves=estimate_curves(res.filter((pl.col("league_id")==lid)&(pl.col("season")<=2023)))
ours=apply_curves(base,curves).select("gsis_id","season","week","position",pl.col("projection").alias("ours"),"context")
games=pp.select("gsis_id","season","week","points","team_implied","total_line","is_home","opponent_team").sort("gsis_id","season","week")
opp=store.read_table("nfl_ff_opportunity","raw").select(pl.col("player_id").alias("gsis_id"),"season","week",pl.col("total_fantasy_points_exp").alias("exp_pts"),pl.col("rec_attempt").alias("tgt"),pl.col("rush_attempt").alias("car"),pl.col("pass_attempt").alias("att"),"rec_touchdown_exp","rush_touchdown_exp")
snaps=store.read_table("nfl_snaps","raw").filter(pl.col("gsis_id").is_not_null()).select("gsis_id","season","week",pl.col("offense_pct").alias("snap")).unique(["gsis_id","season","week"])
ts=store.read_table("nfl_player_stats","raw").filter(pl.col("season_type")=="REG").select(pl.col("player_id").alias("gsis_id"),"season","week","target_share","air_yards_share" if "air_yards_share" in store.read_table("nfl_player_stats","raw").columns else "target_share")
ts=ts.unique(["gsis_id","season","week"])
g=games.join(opp,on=["gsis_id","season","week"],how="left").join(snaps,on=["gsis_id","season","week"],how="left").join(ts.rename({"target_share":"tshare"}).select("gsis_id","season","week","tshare"),on=["gsis_id","season","week"],how="left").sort("gsis_id","season","week")
cols=["points","exp_pts","tgt","car","att","snap","tshare","rec_touchdown_exp","rush_touchdown_exp"]
exprs=[]
for c in cols:
    for hl in (2,4,8):
        exprs.append(pl.col(c).ewm_mean(half_life=hl).shift(1).over("gsis_id").alias(f"{c}_hl{hl}"))
    exprs.append(pl.col(c).shift(1).over("gsis_id").alias(f"{c}_last"))
exprs.append(pl.col("points").cum_count().over("gsis_id").alias("n_games"))
exprs.append(pl.col("points").rolling_std(8,min_samples=3).shift(1).over("gsis_id").alias("pts_sd8"))
g=g.with_columns(exprs)
inj=store.read_table("nfl_injuries","raw").filter(pl.col("game_type")=="REG").unique(["gsis_id","season","week"],keep="first").select("gsis_id","season","week",(pl.col("report_status")=="Questionable").fill_null(False).cast(pl.Float64).alias("inj_q"),(pl.col("report_status")=="Doubtful").fill_null(False).cast(pl.Float64).alias("inj_d"),pl.col("practice_status").str.contains("Did Not|DNP").fill_null(False).cast(pl.Float64).alias("prac_dnp"),pl.col("practice_status").str.contains("Limited").fill_null(False).cast(pl.Float64).alias("prac_lim"))
g=g.join(inj,on=["gsis_id","season","week"],how="left").with_columns(pl.col(["inj_q","inj_d","prac_dnp","prac_lim"]).fill_null(0.0))
d=g.join(ours,on=["gsis_id","season","week"],how="inner")
d=d.with_columns(pl.col("is_home").cast(pl.Float64),(pl.col("position")=="QB").cast(pl.Float64).alias("is_qb"),(pl.col("position")=="RB").cast(pl.Float64).alias("is_rb"),(pl.col("position")=="WR").cast(pl.Float64).alias("is_wr"),pl.col("context").alias("ctx"))
feat=[c for c in d.columns if any(c.startswith(x+"_") for x in cols)]+["n_games","pts_sd8","team_implied","total_line","is_home","is_qb","is_rb","is_wr","week","inj_q","inj_d","prac_dnp","prac_lim"]

# Part 1: train on 2019-2023, score 2024-2026 against the baseline
train=d.filter(pl.col("season")<=2023); test=d.filter((pl.col("season")>=2024)&(pl.col("ours")>3))
def fit(features, obj="regression"):
    m=HistGradientBoostingRegressor(loss="squared_error",max_iter=400,learning_rate=0.03,max_leaf_nodes=15,min_samples_leaf=80,l2_regularization=5.0,random_state=0)
    m.fit(train[features].to_numpy(),train["points"].to_numpy()); return m
def rm(a,b): return float(np.sqrt(((a-b)**2).mean()))
a=test["points"].to_numpy(); o=test["ours"].to_numpy()
print("test n",test.height,"RMSE ours (train-only calibration)",round(rm(a,o),4),"MAE",round(float(np.abs(a-o).mean()),4))
m1=fit(feat); p1=m1.predict(test[feat].to_numpy())
print("GBM without baseline feature  RMSE",round(rm(a,p1),4),"MAE",round(float(np.abs(a-p1).mean()),4))
feat2=feat+["ours"]; m2=fit(feat2); p2=m2.predict(test[feat2].to_numpy())
print("GBM with baseline as feature  RMSE",round(rm(a,p2),4),"MAE",round(float(np.abs(a-p2).mean()),4))
for s in (2024,2025,2026):
    mk=(test["season"]==s).to_numpy(); print(" ",s,"ours",round(rm(a[mk],o[mk]),3),"gbm",round(rm(a[mk],p1[mk]),3),"gbm+ours",round(rm(a[mk],p2[mk]),3),"n",int(mk.sum()))
bl=0.5*p1+0.5*o; print("50/50 gbm and ours RMSE",round(rm(a,bl),4))


# Part 2: leave one season out on the FantasyData panel
import sys; sys.path.insert(0,"research")
from fd_panel import SCRATCH
panel=pl.read_parquet(SCRATCH/"fd_panel.parquet").filter(pl.col("league_key")=="colgate")
ev=panel.filter(pl.col("played")&pl.col("ours").is_not_null()&pl.col("fd").is_not_null()).with_columns(((pl.col("ours")+pl.col("fd"))/2).alias("avg")).filter(pl.col("avg")>3).select("gsis_id","season","week","position","actual","ours","fd","avg")
def model():
    return HistGradientBoostingRegressor(loss="squared_error",max_iter=400,learning_rate=0.03,max_leaf_nodes=15,min_samples_leaf=80,l2_regularization=5.0,random_state=0)
preds=[]
for s in (2019,2020,2021):
    tr=d.filter((pl.col("season")!=s)&(pl.col("season")>=2019)); te=d.filter(pl.col("season")==s)
    m=model(); m.fit(tr[feat].to_numpy(),tr["points"].to_numpy())
    preds.append(te.select("gsis_id","season","week").with_columns(pl.Series("gbm",m.predict(te[feat].to_numpy()))))
x=ev.join(pl.concat(preds),on=["gsis_id","season","week"],how="inner")
a=x["actual"].to_numpy(); o=x["ours"].to_numpy(); f=x["fd"].to_numpy(); g=x["gbm"].to_numpy()
rm=lambda p: float(np.sqrt(((a-p)**2).mean()))
print("n",x.height)
print("RMSE ours %.3f  gbm %.3f  fd %.3f"%(rm(o),rm(g),rm(f)))
for w in (0.0,0.25,0.5,0.75,1.0):
    print("  gbm*(1-w)+fd*w  w=%.2f  RMSE %.3f"%(w,rm((1-w)*g+w*f)))
# optimal 3-way weights (no intercept) via least squares
X=np.column_stack([o,g,f]); b=np.linalg.lstsq(X,a,rcond=None)[0]; print("lstsq weights ours,gbm,fd:",np.round(b,3),"RMSE %.3f"%rm(X@b))
for s in (2019,2020,2021):
    mk=(x["season"]==s).to_numpy(); print(s,"ours %.3f gbm %.3f fd %.3f"%(np.sqrt(((a[mk]-o[mk])**2).mean()),np.sqrt(((a[mk]-g[mk])**2).mean()),np.sqrt(((a[mk]-f[mk])**2).mean())))

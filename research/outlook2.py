import numpy as np, polars as pl
from fantasy import store
S="research/scratch"
p=pl.read_parquet(f"{S}/outlook_panel.parquet").with_columns([pl.col(c).fill_nan(None) for c in ("gap","tgt_trend","carry_trend","opp_rel")])
st=store.read_table("nfl_player_stats","raw").filter(pl.col("season_type")=="REG").select(pl.col("player_id").alias("gsis_id"),"season","week","team","target_share","carries")
ts=store.read_table("nfl_team_stats","raw").filter(pl.col("season_type")=="REG").select("team","season","week",pl.col("carries").alias("tc"))
u=st.join(ts,on=["team","season","week"],how="left").with_columns((pl.col("carries")/pl.col("tc")).alias("cshare"),(pl.col("season")*100+pl.col("week")).alias("t")).sort("gsis_id","t")
u=u.with_columns(pl.col("target_share").fill_null(0.0),pl.col("cshare").fill_null(0.0))
u=u.with_columns(pl.col("target_share").ewm_mean(half_life=4).over("gsis_id").alias("ts_ewma"),pl.col("cshare").ewm_mean(half_life=4).over("gsis_id").alias("cs_ewma"))
usage=u.select("gsis_id","t","ts_ewma","cs_ewma").sort("t")
inj=store.read_table("nfl_injuries","raw").filter(pl.col("position").is_in(["QB","RB","WR","TE"])&(pl.col("game_type")=="REG")&pl.col("report_status").is_in(["Out","Doubtful"])).select("gsis_id","team","season","week").with_columns((pl.col("season")*100+pl.col("week")-1).alias("t_prior")).sort("t_prior")
# use usage as of the week before (t_prior)
out=inj.join_asof(usage.rename({"t":"t_prior"}),on="t_prior",by="gsis_id",strategy="backward")
out=out.drop_nulls("ts_ewma").filter((pl.col("ts_ewma")>0.04)|(pl.col("cs_ewma")>0.08))
vac=out.group_by("team","season","week").agg(pl.col("ts_ewma").sum().alias("vac_t"),pl.col("cs_ewma").sum().alias("vac_c"),pl.len().alias("n_out"))
p=p.join(vac,on=["team","season","week"],how="left").with_columns(pl.col("vac_t").fill_null(0.0),pl.col("vac_c").fill_null(0.0))
# games since return: look at gaps between consecutive appearances within a season (team games missed)
games=store.read_table("team_games").filter(pl.col("game_type")=="REG").select("team","season","week").sort("team","season","week").with_columns(pl.int_range(pl.len()).over("team","season").alias("g"))
p=p.join(games,on=["team","season","week"],how="left").sort("gsis_id","season","week")
p=p.with_columns((pl.col("g")-pl.col("g").shift(1).over("gsis_id","season")-1).alias("missed_before"))
p=p.with_columns(pl.when(pl.col("missed_before")>=1).then(pl.lit("first_back")).otherwise(pl.lit("regular")).alias("ret"))
print(p.group_by("ret").agg(pl.len().alias("n"),pl.col("resid").mean().round(2).alias("mean_resid"),pl.col("points").mean().round(1).alias("ppg"),pl.col("projection").mean().round(1).alias("proj")))
# second game back
p=p.with_columns(pl.col("ret").shift(1).over("gsis_id","season").alias("prev_ret"))
print(p.filter((pl.col("ret")=="regular")&(pl.col("prev_ret")=="first_back")).select(pl.len().alias("n"),pl.col("resid").mean().round(2)))
for pos in ("WR","TE","RB","QB"):
    d=p.filter((pl.col("position")==pos)&(pl.col("projection")>2))
    for f in ("vac_t","vac_c"):
        a=d[f].to_numpy(); r=d["resid"].to_numpy(); m=np.isfinite(a)
        print(pos,f,"corr %.3f"%np.corrcoef(a[m],r[m])[0,1], "slope %.2f"%np.polyfit(a[m],r[m],1)[0], "mean vac %.3f n=%d"%(a.mean(),m.sum()))
p.write_parquet(f"{S}/outlook_panel2.parquet")

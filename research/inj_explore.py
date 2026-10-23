import polars as pl, numpy as np
from fantasy import store
pl.Config.set_tbl_rows(60); pl.Config.set_fmt_str_lengths(30)
K=4
inj=store.read_table("nfl_injuries","raw").filter(pl.col("position").is_in(["QB","RB","WR","TE"])&(pl.col("game_type")=="REG")&(pl.col("season")<2026))
inj=inj.with_columns(pl.coalesce("report_primary_injury","practice_primary_injury").alias("body"))
st=store.read_table("nfl_player_stats","raw").filter(pl.col("season_type")=="REG")
st=st.with_columns((pl.col("attempts").fill_null(0)+pl.col("carries").fill_null(0)+pl.col("targets").fill_null(0)).alias("opp")).select(pl.col("player_id").alias("gsis_id"),"season","week","team","opp")
pts=store.read_table("player_points").filter(pl.col("league_id")==store.read_table("leagues","raw")["league_id"][0]).select("gsis_id","season","week","points")
base=store.read_table("proj_baseline").filter(~pl.col("is_future")&pl.col("has_history")).filter(pl.col("league_id")==store.read_table("leagues","raw")["league_id"][0]).select("gsis_id","season","week",pl.col("projection").alias("proj"))
games=store.read_table("team_games").filter(pl.col("game_type")=="REG").select("season","week","team")
# game index per team-season
games=games.sort("team","season","week").with_columns(pl.int_range(pl.len()).over("team","season").alias("g"))
# status weeks: injury row week -> team game index of that week
rows=inj.join(games,on=["season","week","team"])
rows=rows.filter(pl.col("report_status").is_in(["Out","Doubtful","Questionable"]))
# relevance: had opp>=5 in a prior game of the same season or last season's end (approx: any week before this one in season with opp>=5)
prior=st.filter(pl.col("opp")>=5).group_by("gsis_id","season").agg(pl.col("week").min().alias("first_rel"))
rows=rows.join(prior,on=["gsis_id","season"],how="inner").filter(pl.col("week")>pl.col("first_rel"))
out=[]
for k in range(K):
    nxt=games.select("season","team",(pl.col("g")-k).alias("g"),pl.col("week").alias(f"wk{k}"))
    rows=rows.join(nxt,on=["season","team","g"],how="left")
    played=st.select("gsis_id","season",pl.col("week").alias(f"wk{k}"),(pl.col("opp")>0).alias(f"p{k}"))
    rows=rows.join(played,on=["gsis_id","season",f"wk{k}"],how="left").with_columns(pl.col(f"p{k}").fill_null(False))
    rows=rows.with_columns(pl.when(pl.col(f"wk{k}").is_null()).then(None).otherwise(pl.col(f"p{k}")).alias(f"p{k}"))
rows=rows.join(pts.rename({"week":"wk0"}),on=["gsis_id","season","wk0"],how="left").join(base.rename({"week":"wk0"}),on=["gsis_id","season","wk0"],how="left")
rows=rows.with_columns((pl.col("points")/pl.col("proj")).alias("perf"))
rows.write_parquet(f"research/scratch/inj_panel.parquet")
print(rows.height)
g=rows.group_by("report_status").agg(pl.len().alias("n"),*[pl.col(f"p{k}").mean().round(3).alias(f"p{k}") for k in range(K)])
print(g)
top=["Hamstring","Ankle","Knee","Concussion","Shoulder","Foot","Groin","Hip","Calf","Quadricep","Back","Illness"]
q=rows.filter(pl.col("report_status")=="Questionable").filter(pl.col("body").is_in(top))
print(q.group_by("body").agg(pl.len().alias("n"),*[pl.col(f"p{k}").mean().round(3).alias(f"p{k}") for k in range(K)],pl.col("perf").filter(pl.col("p0")&pl.col("proj").is_not_null()&(pl.col("proj")>3)).mean().round(2).alias("perf_if_played")).sort("n",descending=True))
print(rows.filter(pl.col("report_status")=="Questionable").group_by("practice_status").agg(pl.len().alias("n"),*[pl.col(f"p{k}").mean().round(3).alias(f"p{k}") for k in range(K)]))
oo=rows.filter(pl.col("report_status").is_in(["Out","Doubtful"])).filter(pl.col("body").is_in(top))
print(oo.group_by("body").agg(pl.len().alias("n"),*[pl.col(f"p{k}").mean().round(3).alias(f"p{k}") for k in range(K)]).sort("n",descending=True))

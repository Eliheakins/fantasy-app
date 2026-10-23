import numpy as np, polars as pl
from fantasy import store
from fantasy.stages.crosswalk import normalize_name
S="research/scratch"
snaps=store.read_table("nfl_snaps","raw").filter(pl.col("game_id").is_not_null())
snaps=snaps.with_columns(pl.col("player").map_elements(normalize_name,return_dtype=pl.String).alias("nm"))
inj=store.read_table("nfl_injuries","raw").filter((pl.col("game_type")=="REG")&pl.col("report_status").is_in(["Out","Doubtful"])).with_columns(pl.col("full_name").map_elements(normalize_name,return_dtype=pl.String).alias("nm")).select("season","week","team","nm").unique().with_columns(pl.lit(True).alias("listed_out"))
GROUPS={"ol":(["T","G","C","OL","C/G"],"offense_snaps",5),"cb":(["CB"],"defense_snaps",2),"s":(["S","FS","SS"],"defense_snaps",2),"dl":(["DE","DT","NT","DL"],"defense_snaps",4),"lb":(["LB","ILB","OLB"],"defense_snaps",2)}
# need a game row per team-week with a game (use all snaps weeks)
weeks=snaps.select("season","week","team").unique()
frames=[]
for g,(pos,col,n) in GROUPS.items():
    d=snaps.filter(pl.col("position").is_in(pos)).select("season","week","team","nm","position",pl.col(col).fill_null(0.0).alias("sn"))
    d=d.sort("season","team","nm","week").with_columns(pl.col("sn").cum_sum().over("season","team","nm").alias("cum"))
    # prior cumulative snaps as of the week before (shift within player) and number of prior team games
    d=d.with_columns(pl.col("cum").shift(1).over("season","team","nm").fill_null(0.0).alias("prior"))
    # players listed this week (may have zero snaps and so no row): bring injuries onto prior-cum by (season,team,nm) at latest earlier week
    allp=d.group_by("season","team","nm").agg(pl.col("position").last())
    # cumulative prior at each week for every player of the team-season (including weeks with no row): build via asof
    wk=weeks.join(allp,on=["season","team"])
    w=wk.join(d.select("season","team","nm","week","cum"),on=["season","team","nm","week"],how="left").sort("season","team","nm","week").with_columns(pl.col("cum").forward_fill().over("season","team","nm").fill_null(0.0).alias("cum_now"))
    w=w.with_columns(pl.col("cum_now").shift(1).over("season","team","nm").fill_null(0.0).alias("prior"))
    w=w.with_columns(pl.col("prior").rank("ordinal",descending=True).over("season","team","week").alias("rk")).filter((pl.col("rk")<=n)&(pl.col("week")>=4))
    w=w.join(inj,on=["season","week","team","nm"],how="left").with_columns(pl.col("listed_out").fill_null(False))
    if g=="ol":
        agg=w.group_by("season","week","team").agg(pl.col("listed_out").sum().alias("ol_out"),(pl.col("listed_out")&pl.col("position").is_in(["T"])).sum().alias("ol_t_out"),(pl.col("listed_out")&pl.col("position").is_in(["G","C/G"])).sum().alias("ol_g_out"),(pl.col("listed_out")&pl.col("position").is_in(["C"])).sum().alias("ol_c_out"))
    else:
        agg=w.group_by("season","week","team").agg(pl.col("listed_out").sum().alias(f"{g}_out"))
    frames.append(agg)
out=frames[0]
for f in frames[1:]: out=out.join(f,on=["season","week","team"],how="full",coalesce=True)
out=out.fill_null(0)
out.write_parquet(f"{S}/team_avail.parquet")
print(out.height); print(out.select(pl.col("ol_out").mean(),pl.col("cb_out").mean(),pl.col("s_out").mean(),pl.col("dl_out").mean(),pl.col("lb_out").mean()))
for c in ("ol_out","cb_out","s_out","dl_out","lb_out"): print(c, out.group_by(c).len().sort(c).to_dicts())

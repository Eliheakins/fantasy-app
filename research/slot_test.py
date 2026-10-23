import numpy as np, polars as pl
from fantasy import store
from fantasy.stages.distributions import calibrated
from fantasy.stages.crosswalk import normalize_name
S="research/scratch"
# per-rank CB availability
snaps=store.read_table("nfl_snaps","raw").filter(pl.col("game_id").is_not_null())
snaps=snaps.with_columns(pl.col("player").map_elements(normalize_name,return_dtype=pl.String).alias("nm"))
inj=store.read_table("nfl_injuries","raw").filter((pl.col("game_type")=="REG")&pl.col("report_status").is_in(["Out","Doubtful"])).with_columns(pl.col("full_name").map_elements(normalize_name,return_dtype=pl.String).alias("nm")).select("season","week","team","nm").unique().with_columns(pl.lit(True).alias("out"))
weeks=snaps.select("season","week","team").unique()
d=snaps.filter(pl.col("position")=="CB").select("season","week","team","nm",pl.col("defense_snaps").fill_null(0.0).alias("sn")).sort("season","team","nm","week").with_columns(pl.col("sn").cum_sum().over("season","team","nm").alias("cum"))
allp=d.group_by("season","team","nm").agg(pl.len().alias("g")).select("season","team","nm")
w=weeks.join(allp,on=["season","team"]).join(d.select("season","team","nm","week","cum"),on=["season","team","nm","week"],how="left").sort("season","team","nm","week").with_columns(pl.col("cum").forward_fill().over("season","team","nm").fill_null(0.0).alias("c"))
w=w.with_columns(pl.col("c").shift(1).over("season","team","nm").fill_null(0.0).alias("prior"))
w=w.with_columns(pl.col("prior").rank("ordinal",descending=True).over("season","team","week").alias("rk")).filter((pl.col("rk")<=3)&(pl.col("week")>=4)).join(inj,on=["season","week","team","nm"],how="left").with_columns(pl.col("out").fill_null(False))
cb=w.group_by("season","week","team").agg(*[((pl.col("rk")==k)&pl.col("out")).sum().alias(f"cb{k}_out") for k in (1,2,3)])
# receiver depth proxy
st=store.read_table("nfl_player_stats","raw").filter(pl.col("season_type")=="REG").select(pl.col("player_id").alias("gsis_id"),"season","week","target_share","air_yards_share").sort("gsis_id","season","week")
st=st.with_columns(pl.col("target_share").fill_null(0.0),pl.col("air_yards_share").fill_null(0.0))
st=st.with_columns(pl.col("target_share").ewm_mean(half_life=6).over("gsis_id").shift(1).over("gsis_id").alias("ts"),pl.col("air_yards_share").ewm_mean(half_life=6).over("gsis_id").shift(1).over("gsis_id").alias("ays"))
st=st.with_columns((pl.col("ays")/pl.col("ts")).alias("depth"))
lid=store.read_table("leagues","raw")["league_id"][0]
p=pl.read_parquet(f"{S}/outlook_panel2.parquet").filter(pl.col("points").is_not_null()).join(st.select("gsis_id","season","week","depth","ts"),on=["gsis_id","season","week"],how="left")
p=calibrated(p.with_columns(pl.lit(lid).alias("league_id"))).with_columns((pl.col("points")-pl.col("projection")).alias("res")).filter(pl.col("projection")>2)
p=p.join(cb.rename({"team":"opponent_team"}),on=["season","week","opponent_team"],how="inner")
p=p.with_columns((pl.col("ret")=="first_back").cast(pl.Float64).alias("b1"),((pl.col("ret")=="regular")&(pl.col("prev_ret")=="first_back")).fill_null(False).cast(pl.Float64).alias("b2"),pl.col("vac_t").fill_null(0.0),pl.col("vac_c").fill_null(0.0))
wr=p.filter((pl.col("position")=="WR")&pl.col("depth").is_finite()&(pl.col("ts")>0.08))
med=float(wr["depth"].median()); print("WR rows",wr.height,"median depth proxy",round(med,2))
wr=wr.with_columns((pl.col("depth")<med).cast(pl.Float64).alias("shortarea"),(pl.col("depth")>=med).cast(pl.Float64).alias("deep"))
CTRL=["b1","b2","vac_t","vac_c"]
def design(d,cols): return np.column_stack([d[c].cast(pl.Float64).to_numpy() for c in cols]+[np.ones(d.height)])
def ols(d,cols):
    X=design(d,CTRL+cols); y=d["res"].to_numpy(); XtXi=np.linalg.inv(X.T@X); b=XtXi@X.T@y; e=y-X@b
    V=XtXi@(X.T*(e**2))@X@XtXi*(len(y)/(len(y)-X.shape[1])); k=len(CTRL); return b[k:k+len(cols)],np.sqrt(np.diag(V))[k:k+len(cols)]
for k in (1,2,3):
    wr=wr.with_columns((pl.col(f"cb{k}_out")*pl.col("shortarea")).alias(f"s{k}"),(pl.col(f"cb{k}_out")*pl.col("deep")).alias(f"d{k}"))
    b,se=ols(wr,[f"s{k}",f"d{k}"])
    tr,te=wr.filter(pl.col("season")<=2023),wr.filter(pl.col("season")>=2024)
    btr,_=ols(tr,[f"s{k}",f"d{k}"]); bte,_=ols(te,[f"s{k}",f"d{k}"])
    print("CB%d out: short-area WR %+.2f (t %+.1f, train %+.2f test %+.2f, n=%d) | deep WR %+.2f (t %+.1f, train %+.2f test %+.2f, n=%d)"%(k,b[0],b[0]/se[0],btr[0],bte[0],int((wr[f"s{k}"]>0).sum()),b[1],b[1]/se[1],btr[1],bte[1],int((wr[f"d{k}"]>0).sum())))
# all receivers (WR/TE) CB1/2/3
for pos in ("WR","TE","QB"):
    d=p.filter(pl.col("position")==pos)
    for k in (1,2,3):
        b,se=ols(d,[f"cb{k}_out"]); print(pos,"cb%d_out %+.2f (t %+.1f, n=%d)"%(k,b[0],b[0]/se[0],int((d[f'cb{k}_out']>0).sum())),end=" | ")
    print()

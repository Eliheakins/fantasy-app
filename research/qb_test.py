import numpy as np, polars as pl
from fantasy import store
from fantasy.stages.distributions import calibrated
S="research/scratch"
st=store.read_table("nfl_player_stats","raw").filter((pl.col("season_type")=="REG")&(pl.col("position")=="QB")).select(pl.col("player_id").alias("gsis_id"),"season","week","team",pl.col("attempts").fill_null(0.0).alias("att"))
# QB1 of a team before week w = most prior attempts that season (>= 3 prior team games)
tw=store.read_table("team_games").filter(pl.col("game_type")=="REG").select("season","week","team")
q=tw.join(st.select("gsis_id","season","team").unique(),on=["season","team"]).join(st.select("gsis_id","season","week","att"),on=["gsis_id","season","week"],how="left").with_columns(pl.col("att").fill_null(0.0)).sort("season","team","gsis_id","week")
q=q.with_columns(pl.col("att").cum_sum().over("season","team","gsis_id").alias("cum")).with_columns(pl.col("cum").shift(1).over("season","team","gsis_id").fill_null(0.0).alias("prior"))
q=q.with_columns(pl.col("prior").rank("ordinal",descending=True).over("season","team","week").alias("rk")).filter((pl.col("rk")==1)&(pl.col("week")>=4))
inj=store.read_table("nfl_injuries","raw").filter((pl.col("game_type")=="REG")&(pl.col("position")=="QB")&pl.col("report_status").is_in(["Out","Doubtful"])).select("season","week","gsis_id").unique().with_columns(pl.lit(True).alias("qb1_out"))
qb=q.join(inj,on=["season","week","gsis_id"],how="left").with_columns(pl.col("qb1_out").fill_null(False).cast(pl.Float64)).select("season","week","team","qb1_out")
print("team-games with QB1 listed out:",int(qb["qb1_out"].sum()),"of",qb.height)
lid=store.read_table("leagues","raw")["league_id"][0]
p=pl.read_parquet(f"{S}/outlook_panel2.parquet").filter(pl.col("points").is_not_null())
p=calibrated(p.with_columns(pl.lit(lid).alias("league_id"))).with_columns((pl.col("points")-pl.col("projection")).alias("res")).filter(pl.col("projection")>2)
p=p.join(qb,on=["season","week","team"],how="inner").with_columns((pl.col("ret")=="first_back").cast(pl.Float64).alias("b1"),((pl.col("ret")=="regular")&(pl.col("prev_ret")=="first_back")).fill_null(False).cast(pl.Float64).alias("b2"),pl.col("vac_t").fill_null(0.0),pl.col("vac_c").fill_null(0.0))
tr,te=p.filter(pl.col("season")<=2023),p.filter(pl.col("season")>=2024)
CTRL=["b1","b2","vac_t","vac_c"]
def design(d,cols): return np.column_stack([d[c].cast(pl.Float64).to_numpy() for c in cols]+[np.ones(d.height)])
def ols(d,cols):
    X=design(d,CTRL+cols); y=d["res"].to_numpy(); XtXi=np.linalg.inv(X.T@X); b=XtXi@X.T@y; e=y-X@b
    V=XtXi@(X.T*(e**2))@X@XtXi*(len(y)/(len(y)-X.shape[1])); k=len(CTRL); return b[k:k+len(cols)],np.sqrt(np.diag(V))[k:k+len(cols)]
for pos in ("RB","WR","TE"):
    d=p.filter(pl.col("position")==pos); b,se=ols(d,["qb1_out"]); btr,_=ols(tr.filter(pl.col("position")==pos),["qb1_out"]); bte,_=ols(te.filter(pl.col("position")==pos),["qb1_out"])
    print("%s: QB1 out %+.2f pts (t %+.1f)  train %+.2f test %+.2f  n=%d   mean projection %.1f"%(pos,b[0],b[0]/se[0],btr[0],bte[0],int((d["qb1_out"]>0).sum()),d["projection"].mean()))

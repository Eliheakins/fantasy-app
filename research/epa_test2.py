import numpy as np, polars as pl
from fantasy import store
from fantasy.stages.distributions import calibrated
S="research/scratch"
t=pl.read_parquet(f"{S}/team_game_epa.parquet").sort("posteam","season","week")
K=4.0
def prior_rating(df,key,col):
    x=df.sort(key,"season","week")
    def f(g):
        v=g[col].to_numpy(); n=len(v); out=np.zeros(n)
        for i in range(n):
            w=v[max(0,i-17):i]
            if len(w)==0: out[i]=0.0; continue
            wt=0.5**(np.arange(len(w))[::-1]/6); out[i]=(wt*w).sum()/(wt.sum()+K/ max(len(w),1)*0+K*0.0+0.0) if False else ((wt*w).sum())/(wt.sum()+ (K*0.25))
        return g.with_columns(pl.Series(f"{col}_prior",out))
    return pl.concat([f(g) for _,g in x.group_by(key,maintain_order=True)])
off=t.select("season","week",pl.col("posteam").alias("team"),"pass_epa","rush_epa","sack_rate","pass_rate")
off=pl.concat([prior_rating(off,"team",c).select("season","week","team",f"{c}_prior") if i==0 else prior_rating(off,"team",c).select(f"{c}_prior") for i,c in enumerate(["pass_epa","rush_epa","sack_rate","pass_rate"])],how="horizontal")
dfn=t.select("season","week",pl.col("defteam").alias("opponent_team"),pl.col("pass_epa").alias("dpass_epa"),pl.col("rush_epa").alias("drush_epa"))
dfn=pl.concat([prior_rating(dfn,"opponent_team",c).select("season","week","opponent_team",f"{c}_prior") if i==0 else prior_rating(dfn,"opponent_team",c).select(f"{c}_prior") for i,c in enumerate(["dpass_epa","drush_epa"])],how="horizontal")
p=pl.read_parquet(f"{S}/outlook_panel2.parquet").filter(pl.col("points").is_not_null())
lid0=store.read_table("leagues","raw")["league_id"][0]
ctx=store.read_table("proj_baseline").filter((pl.col("league_id")==lid0)&~pl.col("is_future")).select("gsis_id","season","week","context")
p=p.join(ctx,on=["gsis_id","season","week"],how="left")
lid=store.read_table("leagues","raw")["league_id"][0]
p=calibrated(p.with_columns(pl.lit(lid).alias("league_id"))).with_columns((pl.col("points")-pl.col("projection")).alias("res")).filter(pl.col("projection")>2)
p=p.join(off,on=["season","week","team"],how="left").join(dfn,on=["season","week","opponent_team"],how="left").drop_nulls(["pass_epa_prior","dpass_epa_prior","context"]).with_columns(pl.col("context").log().alias("lctx"))
p=p.with_columns((pl.col("ret")=="first_back").cast(pl.Float64).alias("b1"),((pl.col("ret")=="regular")&(pl.col("prev_ret")=="first_back")).fill_null(False).cast(pl.Float64).alias("b2"),pl.col("vac_t").fill_null(0.0),pl.col("vac_c").fill_null(0.0))
tr,te=p.filter(pl.col("season")<=2023),p.filter(pl.col("season")>=2024)
CTRL=["b1","b2","vac_t","vac_c"]
def design(d,cols): return np.column_stack([d[c].cast(pl.Float64).to_numpy() for c in cols]+[np.ones(d.height)])
def ols(d,cols):
    X=design(d,CTRL+cols); y=d["res"].to_numpy(); XtXi=np.linalg.inv(X.T@X); b=XtXi@X.T@y; e=y-X@b
    V=XtXi@(X.T*(e**2))@X@XtXi*(len(y)/(len(y)-X.shape[1])); k=len(CTRL); return b[k:k+len(cols)],np.sqrt(np.diag(V))[k:k+len(cols)]
CTRL=['b1','b2','vac_t','vac_c']

CTRL2=["b1","b2","vac_t","vac_c","lctx"]
def ols2(d,cols):
    X=np.column_stack([d[c].cast(pl.Float64).to_numpy() for c in CTRL2+cols]+[np.ones(d.height)]); y=d["res"].to_numpy(); XtXi=np.linalg.inv(X.T@X); b=XtXi@X.T@y; e=y-X@b
    V=XtXi@(X.T*(e**2))@X@XtXi*(len(y)/(len(y)-X.shape[1])); k=len(CTRL2); return b[k:k+len(cols)],np.sqrt(np.diag(V))[k:k+len(cols)]
print("controlling for log(context):")
for feat in ("pass_epa_prior","rush_epa_prior","sack_rate_prior"):
    sd=p[feat].std()
    for pos in ("QB","RB","WR","TE"):
        d=p.filter(pl.col("position")==pos); b,se=ols2(d,[feat]); print("%-16s %-3s per sd %+.2f (t %+.1f)"%(feat,pos,b[0]*sd,b[0]/se[0]),end=" | ")
    print()
print("corr(lctx, pass_epa_prior) = %.2f"%np.corrcoef(p["lctx"].to_numpy(),p["pass_epa_prior"].to_numpy())[0,1])

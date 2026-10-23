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
lid=store.read_table("leagues","raw")["league_id"][0]
p=calibrated(p.with_columns(pl.lit(lid).alias("league_id"))).with_columns((pl.col("points")-pl.col("projection")).alias("res")).filter(pl.col("projection")>2)
p=p.join(off,on=["season","week","team"],how="left").join(dfn,on=["season","week","opponent_team"],how="left").drop_nulls(["pass_epa_prior","dpass_epa_prior"])
p=p.with_columns((pl.col("ret")=="first_back").cast(pl.Float64).alias("b1"),((pl.col("ret")=="regular")&(pl.col("prev_ret")=="first_back")).fill_null(False).cast(pl.Float64).alias("b2"),pl.col("vac_t").fill_null(0.0),pl.col("vac_c").fill_null(0.0))
tr,te=p.filter(pl.col("season")<=2023),p.filter(pl.col("season")>=2024)
CTRL=["b1","b2","vac_t","vac_c"]
def design(d,cols): return np.column_stack([d[c].cast(pl.Float64).to_numpy() for c in cols]+[np.ones(d.height)])
def ols(d,cols):
    X=design(d,CTRL+cols); y=d["res"].to_numpy(); XtXi=np.linalg.inv(X.T@X); b=XtXi@X.T@y; e=y-X@b
    V=XtXi@(X.T*(e**2))@X@XtXi*(len(y)/(len(y)-X.shape[1])); k=len(CTRL); return b[k:k+len(cols)],np.sqrt(np.diag(V))[k:k+len(cols)]
print("rows",p.height)
for feat,desc in (("pass_epa_prior","own offense pass EPA"),("rush_epa_prior","own offense rush EPA"),("sack_rate_prior","own sack rate"),("pass_rate_prior","own pass rate"),("dpass_epa_prior","opp pass EPA allowed"),("drush_epa_prior","opp rush EPA allowed")):
    sd=p[feat].std()
    for pos in ("QB","RB","WR","TE"):
        d=p.filter(pl.col("position")==pos); b,se=ols(d,[feat]); btr,_=ols(tr.filter(pl.col("position")==pos),[feat]); bte,_=ols(te.filter(pl.col("position")==pos),[feat])
        print("%-22s %-3s per 1 sd: %+.2f pts (t %+.1f)  train %+.2f test %+.2f"%(desc,pos,b[0]*sd,b[0]/se[0],btr[0]*sd,bte[0]*sd))
# oos rmse with all four position-specific
def oos(cols,label):
    t0=t1=0.0;n=0
    for pos in ("QB","RB","WR","TE"):
        a=tr.filter(pl.col("position")==pos); b=te.filter(pl.col("position")==pos)
        Xa=design(a,CTRL); b0=np.linalg.solve(Xa.T@Xa+np.eye(Xa.shape[1]),Xa.T@a["res"].to_numpy())
        Xa2=design(a,CTRL+cols); b1=np.linalg.solve(Xa2.T@Xa2+np.eye(Xa2.shape[1]),Xa2.T@a["res"].to_numpy())
        e0=b["res"].to_numpy()-design(b,CTRL)@b0; e1=b["res"].to_numpy()-design(b,CTRL+cols)@b1
        t0+=(e0**2).sum();t1+=(e1**2).sum();n+=b.height
    print("%-40s rmse %.4f -> %.4f (%+.2f%%)"%(label,np.sqrt(t0/n),np.sqrt(t1/n),100*(np.sqrt(t1/t0)-1)))
oos(["pass_epa_prior","rush_epa_prior"],"own offense EPA")
oos(["dpass_epa_prior","drush_epa_prior"],"opponent EPA allowed")
oos(["pass_epa_prior","rush_epa_prior","dpass_epa_prior","drush_epa_prior"],"both")

import numpy as np, polars as pl
from fantasy import store
from fantasy.stages.distributions import calibrated
S="research/scratch"
p=pl.read_parquet(f"{S}/outlook_panel2.parquet").filter(pl.col("points").is_not_null())
lid=store.read_table("leagues","raw")["league_id"][0]
p=p.with_columns(pl.lit(lid).alias("league_id"))
p=calibrated(p).with_columns((pl.col("points")-pl.col("projection")).alias("res"))
p=p.filter(pl.col("projection")>2)
av=pl.read_parquet(f"{S}/team_avail.parquet")
off=av.select("season","week","team",*[c for c in av.columns if c.startswith("ol_")])
dfn=av.select("season","week",pl.col("team").alias("opponent_team"),*[c for c in av.columns if c in ("cb_out","s_out","dl_out","lb_out")])
p=p.join(off,on=["season","week","team"],how="left").join(dfn,on=["season","week","opponent_team"],how="left")
p=p.filter(pl.col("ol_out").is_not_null()&pl.col("cb_out").is_not_null())
p=p.with_columns((pl.col("ret")=="first_back").cast(pl.Float64).alias("b1"),((pl.col("ret")=="regular")&(pl.col("prev_ret")=="first_back")).fill_null(False).cast(pl.Float64).alias("b2"),pl.col("vac_t").fill_null(0.0),pl.col("vac_c").fill_null(0.0))
print("rows",p.height,"seasons",sorted(p["season"].unique().to_list()))
tr,te=p.filter(pl.col("season")<=2023),p.filter(pl.col("season")>=2024)
CTRL=["b1","b2","vac_t","vac_c"]
def design(d,cols): return np.column_stack([d[c].cast(pl.Float64).to_numpy() for c in cols]+[np.ones(d.height)])
def run(label,cols,positions,groupby=True):
    t0=t1=0.0;n=0;coef={}
    for pos in positions:
        a=tr.filter(pl.col("position")==pos); b=te.filter(pl.col("position")==pos)
        X=design(a,CTRL+cols); beta=np.linalg.solve(X.T@X+1.0*np.eye(X.shape[1]),X.T@a["res"].to_numpy())
        Xb=design(b,CTRL); base_b=np.linalg.solve(design(a,CTRL).T@design(a,CTRL)+np.eye(len(CTRL)+1),design(a,CTRL).T@a["res"].to_numpy())
        e0=b["res"].to_numpy()-Xb@base_b; e1=b["res"].to_numpy()-design(b,CTRL+cols)@beta
        t0+=(e0**2).sum(); t1+=(e1**2).sum(); n+=b.height; coef[pos]=dict(zip(cols,np.round(beta[len(CTRL):len(CTRL)+len(cols)],2)))
    print("%-34s rmse %.4f -> %.4f (%+.2f%%) coef %s"%(label,np.sqrt(t0/n),np.sqrt(t1/n),100*(np.sqrt(t1/t0)-1),coef))
OFF=["QB","RB","WR","TE"]
for lbl,cols,pos in (("OL out (all positions)",["ol_out"],OFF),("OL out, QB only",["ol_out"],["QB"]),("OL out, RB only",["ol_out"],["RB"]),("OL T/G/C split, all",["ol_t_out","ol_g_out","ol_c_out"],OFF),
    ("Opp CB out",["cb_out"],OFF),("Opp CB out, WR/TE",["cb_out"],["WR","TE"]),("Opp safety out",["s_out"],OFF),("Opp DL out",["dl_out"],OFF),("Opp LB out",["lb_out"],OFF),("All defense out",["cb_out","s_out","dl_out","lb_out"],OFF)):
    run(lbl,cols,pos)

print("\n=== coefficient, robust t-stat, and stability (train 2019-23 vs test 2024-26) ===")
def ols(d,cols):
    X=design(d,CTRL+cols); y=d["res"].to_numpy(); XtXi=np.linalg.inv(X.T@X); b=XtXi@X.T@y; e=y-X@b
    V=XtXi@(X.T*(e**2))@X@XtXi*(len(y)/(len(y)-X.shape[1])); k=len(CTRL)
    return b[k:k+len(cols)], np.sqrt(np.diag(V))[k:k+len(cols)]
for feat,posg in (("ol_out",["QB","RB","WR","TE"]),("cb_out",["QB","WR","TE","RB"]),("dl_out",["QB","WR","TE","RB"]),("s_out",["QB","WR","TE","RB"]),("lb_out",["QB","WR","TE","RB"])):
    for pos in posg:
        d=p.filter(pl.col("position")==pos); b,se=ols(d,[feat]); btr,_=ols(tr.filter(pl.col("position")==pos),[feat]); bte,_=ols(te.filter(pl.col("position")==pos),[feat])
        print("%-7s %-3s coef %+.2f  se %.2f  t %+.1f   train %+.2f  test %+.2f   n_affected %d"%(feat,pos,b[0],se[0],b[0]/se[0],btr[0],bte[0],int((d[feat]>0).sum())))

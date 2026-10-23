import numpy as np, polars as pl
from fantasy import store
from fantasy.stages.distributions import calibrated
S="research/scratch"
lid=store.read_table("leagues","raw")["league_id"][0]
base=store.read_table("proj_baseline").filter((pl.col("league_id")==lid)&~pl.col("is_future")&pl.col("has_history")).select("gsis_id","season","week","context")
p=pl.read_parquet(f"{S}/outlook_panel2.parquet").filter(pl.col("points").is_not_null()).join(base,on=["gsis_id","season","week"],how="left")
p=calibrated(p.with_columns(pl.lit(lid).alias("league_id"))).with_columns((pl.col("points")-pl.col("projection")).alias("res")).filter((pl.col("projection")>2)&pl.col("context").is_not_null())
print("context range",p["context"].quantile(0.05),p["context"].quantile(0.95))
tr,te=p.filter(pl.col("season")<=2023),p.filter(pl.col("season")>=2024)
# does the residual depend on context beyond what the exponent captures? regress res/projection on log(context)
for pos in ("QB","RB","WR","TE"):
    for nm,d in (("all",p),("train",tr),("test",te)):
        d=d.filter(pl.col("position")==pos); x=np.log(d["context"].to_numpy()); y=(d["res"]/d["projection"]).to_numpy()
        b=np.polyfit(x,y,1)[0]; print(pos,nm,"d(res/proj)/d(log context) = %+.2f"%b, end=" | ")
    print()
# oos: choose exponent adjustment factor delta: proj*context^delta
for pos in ("QB","RB","WR","TE"):
    a=tr.filter(pl.col("position")==pos); b=te.filter(pl.col("position")==pos)
    best=None
    for delta in np.linspace(-0.5,0.2,15):
        e=((a["points"]-a["projection"]*a["context"]**delta)**2).mean(); 
        if best is None or e<best[0]: best=(e,delta)
    d=best[1]; e0=((b["points"]-b["projection"])**2).mean(); e1=((b["points"]-b["projection"]*b["context"]**d)**2).mean()
    print(pos,"best extra exponent on train %.2f -> test rmse %.4f -> %.4f (%+.2f%%)"%(d,np.sqrt(e0),np.sqrt(e1),100*(np.sqrt(e1/e0)-1)))

print("\n=== re-tuning the context exponent (current 0.5), fit on train, scored on test ===")
for e in (0.0,0.1,0.2,0.3,0.4,0.5):
    t0=t1=a0=a1=0.0; n=0; row=[]
    for pos in ("QB","RB","WR","TE"):
        b=te.filter(pl.col("position")==pos); pred=(b["projection"]*b["context"]**(e-0.5)).to_numpy(); y=b["points"].to_numpy()
        t1+=((y-pred)**2).sum(); a1+=np.abs(y-pred).sum(); n+=b.height
        row.append("%s %.4f"%(pos,np.sqrt(((y-pred)**2).mean())))
    print("exponent %.1f: pooled RMSE %.4f  MAE %.4f   %s"%(e,np.sqrt(t1/n),a1/n," ".join(row)))
print("within train:")
for e in (0.0,0.1,0.2,0.3,0.5):
    t1=0.0;n=0
    for pos in ("QB","RB","WR","TE"):
        b=tr.filter(pl.col("position")==pos); pred=(b["projection"]*b["context"]**(e-0.5)).to_numpy(); y=b["points"].to_numpy(); t1+=((y-pred)**2).sum(); n+=b.height
    print("exponent %.1f: pooled RMSE %.4f"%(e,np.sqrt(t1/n)))

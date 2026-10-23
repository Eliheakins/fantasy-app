import numpy as np, polars as pl
from fantasy import store
from fantasy.stages.distributions import calibrated
S="research/scratch"
DIV={"AFC East":["BUF","MIA","NE","NYJ"],"AFC North":["BAL","CIN","CLE","PIT"],"AFC South":["HOU","IND","JAX","TEN"],"AFC West":["DEN","KC","LV","OAK","LAC","SD"],
"NFC East":["DAL","NYG","PHI","WAS"],"NFC North":["CHI","DET","GB","MIN"],"NFC South":["ATL","CAR","NO","TB"],"NFC West":["ARI","LA","SEA","SF","STL"]}
division={t:d for d,ts in DIV.items() for t in ts}
lid=store.read_table("leagues","raw")["league_id"][0]
p=pl.read_parquet(f"{S}/outlook_panel2.parquet").filter(pl.col("points").is_not_null())
p=calibrated(p.with_columns(pl.lit(lid).alias("league_id"))).with_columns((pl.col("points")-pl.col("projection")).alias("res")).filter(pl.col("projection")>2)
p=p.with_columns(pl.col("opponent_team").replace({"OAK":"LV","SD":"LAC","STL":"LA"}).alias("opp"),pl.col("team").replace({"OAK":"LV","SD":"LAC","STL":"LA"}).alias("tm"))
p=p.with_columns((pl.col("tm").replace_strict(division,default=None)==pl.col("opp").replace_strict(division,default=None)).alias("divisional")).drop_nulls("opp").sort("gsis_id","season","week")
print("rows",p.height,"divisional share",round(float(p["divisional"].mean()),3))
# prior residuals vs the same opponent within the last K seasons (including earlier weeks this season)
def feats(g,K):
    s=g["season"].to_numpy(); w=g["week"].to_numpy(); o=g["opp"].to_numpy(); r=g["res"].to_numpy(); rel=(g["res"]/g["projection"]).to_numpy()
    n=len(g); tot=np.zeros(n); cnt=np.zeros(n)
    for i in range(n):
        m=(o[:i]==o[i])&(s[:i]>=s[i]-K+1)
        # exclude future-of-season guard (rows sorted) ; earlier rows only
        if m.any(): tot[i]=rel[:i][m].sum(); cnt[i]=m.sum()
    return g.with_columns(pl.Series(f"sum{K}",tot),pl.Series(f"n{K}",cnt))
parts=[]
for _,g in p.group_by("gsis_id",maintain_order=True): 
    for K in (1,2,3): g=feats(g,K)
    parts.append(g)
p=pl.concat(parts); p.write_parquet(f"{S}/h2h_panel.parquet")
print(p.group_by("divisional").agg(pl.col("n2").mean().round(2).alias("avg prior games vs opp (2 seasons)"),(pl.col("n2")>0).mean().round(2).alias("share with any")))
tr,te=p.filter(pl.col("season")<=2023),p.filter(pl.col("season")>=2024)
K0=3.0
def design(d,cols): return np.column_stack([d[c].to_numpy().astype(float) for c in cols]+[np.ones(d.height)])
for K in (1,2,3):
    for lab,flt in (("divisional",pl.col("divisional")),("non-divisional",~pl.col("divisional"))):
        for who in ("all",):
            d=p.filter(flt&(pl.col(f"n{K}")>0)); 
            h=(d[f"sum{K}"]/(d[f"n{K}"]+K0)).to_numpy(); y=(d["res"]/d["projection"]).to_numpy()
            # regression of relative residual on h
            X=np.column_stack([h,np.ones(len(h))]); b=np.linalg.lstsq(X,y,rcond=None)[0]; e=y-X@b; se=np.sqrt((e**2).sum()/(len(y)-2)/((h-h.mean())**2).sum())
            dtr=tr.filter(flt&(pl.col(f"n{K}")>0)); hte=te.filter(flt&(pl.col(f"n{K}")>0))
            ftr=(dtr[f"sum{K}"]/(dtr[f"n{K}"]+K0)).to_numpy(); ytr=(dtr["res"]/dtr["projection"]).to_numpy()
            fte=(hte[f"sum{K}"]/(hte[f"n{K}"]+K0)).to_numpy(); yte=(hte["res"]/hte["projection"]).to_numpy()
            btr=np.polyfit(ftr,ytr,1)[0]; bte=np.polyfit(fte,yte,1)[0]
            print("last %d season(s), %-15s n=%6d  slope %.3f (t %.1f)  train %.3f test %.3f   corr %.3f"%(K,lab,len(y),b[0],b[0]/se,btr,bte,np.corrcoef(h,y)[0,1]))

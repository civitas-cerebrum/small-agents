#!/usr/bin/env python3
"""A/B analysis: exact tests, no scipy needed."""
import itertools, json, subprocess, sys
SP="/private/tmp/claude-501/-Users-sc-mac/9570bd18-0021-46e6-9f49-867862680f56/scratchpad"
reps=sys.argv[1:] or ["1","2","3","4"]
rows=[]
for arm in ("control","harness"):
    for r in reps:
        p=subprocess.run(["python3",f"{SP}/ab/grade.py",arm,r],capture_output=True,text=True)
        try: rows.append(json.loads(p.stdout))
        except Exception: print("grade failed:",arm,r,p.stdout[:100],p.stderr[:100])
C=[x for x in rows if x["arm"]=="control"]; H=[x for x in rows if x["arm"]=="harness"]
def fmt(x): return f'{x["arm"]:8} r{x["rep"]}  solved={int(x["solved"])} bash={x["bash"]} thrash={x["thrash"]} landed={int(x["landed"])} fix@={x["first_fix_cmd"]} timeout={int(x["timeout"])}'
for x in rows: print(fmt(x))

def fisher(a,b,c,d):
    """two-sided Fisher exact for [[a,b],[c,d]]"""
    from math import comb
    n=a+b+c+d; r1=a+b; c1=a+c
    def pmf(x): return comb(c1,x)*comb(n-c1,r1-x)/comb(n,r1)
    p0=pmf(a); return sum(pmf(x) for x in range(max(0,r1+c1-n),min(r1,c1)+1) if pmf(x)<=p0+1e-12)

def mw(u,v):
    """exact two-sided Mann-Whitney via permutation of the combined sample"""
    allv=u+v; n=len(u)
    obs=sum(1 for a in u for b in v if a<b)+0.5*sum(1 for a in u for b in v if a==b)
    cnt=0; tot=0
    for comb_ in itertools.combinations(range(len(allv)),n):
        uu=[allv[i] for i in comb_]; vv=[allv[i] for i in range(len(allv)) if i not in comb_]
        s=sum(1 for a in uu for b in vv if a<b)+0.5*sum(1 for a in uu for b in vv if a==b)
        tot+=1
        if abs(s-len(u)*len(v)/2)>=abs(obs-len(u)*len(v)/2)-1e-9: cnt+=1
    return cnt/tot

cs=sum(x["solved"] for x in C); hs=sum(x["solved"] for x in H)
print(f"\nsolved: control {cs}/{len(C)}  harness {hs}/{len(H)}  Fisher p={fisher(hs,len(H)-hs,cs,len(C)-cs):.4f}")
for k in ("bash","thrash","first_fix_cmd"):
    cu=[x[k] if x[k] is not None else 99 for x in C]; hu=[x[k] if x[k] is not None else 99 for x in H]
    print(f"{k:7}: control={cu} harness={hu}  MW p={mw(cu,hu):.4f}")

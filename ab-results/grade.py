#!/usr/bin/env python3
# grade.py <arm> <rep>  -> one JSON line of metrics (transcript-first; the
# result JSON is absent when the 25-min alarm killed the run)
import glob, json, os, re, subprocess, sys
SP="/private/tmp/claude-501/-Users-sc-mac/9570bd18-0021-46e6-9f49-867862680f56/scratchpad"
arm, rep = sys.argv[1], sys.argv[2]
ws=f"{SP}/ab/ws-{arm}-{rep}"
m={"arm":arm,"rep":int(rep),"solved":False,"bash":0,"thrash":0,"landed":False,
   "blocks":0,"hyp":0,"timeout":True,"first_fix_cmd":None}
try:
    r=subprocess.run(["python3",f"{SP}/hard/check.py",f"{ws}/zdot"],capture_output=True,text=True,timeout=60)
    m["solved"]="COMPLETES" in r.stdout and "WORKS" in r.stdout
except Exception: pass
out=f"{SP}/ab/out-{arm}-{rep}.json"
try:
    raw=open(out).read()
    if "{" in raw:
        d=json.loads(raw[raw.index("{"):]); m["timeout"]=False
except Exception: pass
trs=sorted(glob.glob(os.path.expanduser(f"~/.claude/projects/*ws-{arm}-{rep}/*.jsonl")),key=os.path.getmtime)
if trs:
    sys.path.insert(0,f"{SP}/small-agents/hooks"); import sa_state as S
    seen=[]; lastmsg=""
    for line in open(trs[-1]):
        try: e=json.loads(line)
        except: continue
        msg=e.get("message") or {}
        c=msg.get("content")
        if isinstance(c,list):
            txt="".join(b.get("text","") for b in c if isinstance(b,dict) and b.get("type")=="text")
            if txt.strip() and msg.get("role")=="assistant": lastmsg=txt
            for b in c:
                if isinstance(b,dict) and b.get("type")=="tool_use":
                    if b.get("name")=="Bash":
                        m["bash"]+=1; seen.append(S.tokenize(b["input"].get("command","")))
                    if b.get("name") in ("Edit","Write") and "setup.zsh" in str(b.get("input",{}).get("file_path","")) and m["first_fix_cmd"] is None:
                        m["first_fix_cmd"]=m["bash"]
                    if b.get("name")=="Bash" and b["input"].get("description","").upper().startswith("HYPOTHESIS:"):
                        m["hyp"]+=1
                if isinstance(b,dict) and b.get("type")=="tool_result":
                    t=b.get("content"); t=t if isinstance(t,str) else json.dumps(t)
                    if "BLOCKED by small-agents" in t: m["blocks"]+=1
    m["landed"]=bool(re.search(r"(root cause|because|caused by|the (problem|issue|bug) (is|was)|stuck|could not determine)",lastmsg,re.I)) and len(lastmsg)>150
    for i in range(len(seen)):
        for j in range(i+1,len(seen)):
            if seen[i] and seen[j] and S.similarity(seen[i],seen[j])>=0.55:
                m["thrash"]+=1; break
print(json.dumps(m))

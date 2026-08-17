import os,pty,time,re,select,sys
def clean(t): return re.sub(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[=>]','',t)
def idle(fd,i=1.2,m=8.0):
    o=b"";last=time.time();s=time.time()
    while time.time()-s<m:
        r,_,_=select.select([fd],[],[],0.2)
        if r:
            try:d=os.read(fd,65536)
            except OSError:break
            if d:o+=d;last=time.time()
        elif time.time()-last>i:break
    return clean(o.decode(errors='replace'))
pid,fd=pty.fork()
if pid==0:
    os.environ["ZDOTDIR"]=sys.argv[1];os.environ["TERM"]="xterm-256color"
    os.execvp("zsh",["zsh","-i"])
idle(fd,1.5,6)
os.write(fd,b"zzz-dep\t");r=idle(fd)
print("TAB  ->","COMPLETES" if "zzz-deploy" in r else "NO COMPLETION (BEL)" if "\x07" in r else repr(r))
os.write(fd,b"\x15zzz-deploy\n");r=idle(fd)
print("RUN  ->","WORKS" if "v1.2 ok" in r else "fails")
os.kill(pid,9)

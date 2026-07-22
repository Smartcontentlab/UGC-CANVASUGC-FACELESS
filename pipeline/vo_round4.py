#!/usr/bin/env python3
"""Round 4 (final): p4 no-compress + ad-lib excise; p5 take2-only; d05 simple remux."""
import subprocess, json, os, re
from faster_whisper import WhisperModel
W="/agent/workspace"; OUT=f"{W}/vo_batch/cuts"
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True)
def dur(p):
    r=sh(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{p}"')
    try: return float(r.stdout.strip())
    except: return -1
model=WhisperModel("small.en", device="cpu", compute_type="int8")
def wwords(path):
    segs,_=model.transcribe(path, word_timestamps=True, vad_filter=True)
    ws=[]
    for s in segs:
        for w in (s.words or []):
            t=re.sub(r"[^a-z0-9 ]","",w.word.lower().strip())
            if t: ws.append((t,float(w.start),float(w.end)))
    return ws
def stream(ws):
    txt=""; idx=[]
    for i,(t,a,b) in enumerate(ws):
        for _ in range(len(t)+1): idx.append(i)
        txt+=t+" "
    return txt,idx
def cutw(src,a,b,out,fi=0.03,fo=0.04):
    sh(f'ffmpeg -v error -i "{src}" -ss {max(0,a)} -to {b} -af "afade=t=in:st=0:d={fi},afade=t=out:st={max(0,b-a-fo)}:d={fo}" "{out}" -y')
def concat(files,out):
    lst=f"{OUT}/r4list.txt"
    with open(lst,"w") as f:
        for p in files: f.write(f"file '{p}'\n")
    sh(f'ffmpeg -v error -f concat -safe 0 -i "{lst}" "{out}" -y')
def finish(jid,voice,video,mode="replace",max_ext=4.0):
    vdur=dur(video); tdur=dur(voice); window=vdur-0.35
    at=1.0
    if tdur>window: at=min(1.10,tdur/window)
    fitted=voice
    if abs(at-1.0)>0.012:
        fitted=f"{OUT}/{jid}_r4fit.wav"; sh(f'ffmpeg -v error -i "{voice}" -af atempo={at:.4f} "{fitted}" -y')
    fdur=dur(fitted)
    vsrc=video; ext=0.0
    if fdur>vdur-0.35:
        ext=min(max_ext,fdur-(vdur-0.35)+0.5)
        vsrc=f"{OUT}/{jid}_r4ext.mp4"
        sh(f'ffmpeg -v error -i "{video}" -vf "tpad=stop_mode=clone:stop_duration={ext:.2f}" -an -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p "{vsrc}" -y')
        vdur=dur(vsrc)
    norm=f"{OUT}/{jid}_r4voice.wav"
    sh(f'ffmpeg -v error -i "{fitted}" -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 48000 "{norm}" -y')
    nd=dur(norm)
    outv=video.replace(".mp4","_realvo.mp4")
    if mode=="amix":
        sh(f'ffmpeg -v error -i "{video}" -i "{norm}" -filter_complex "[0:a]volume=0.25,apad[bed];[1:a]adelay=60|60,apad[vo];[bed][vo]amix=inputs=2:duration=first:normalize=0[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    else:
        sh(f'ffmpeg -v error -i "{vsrc}" -i "{norm}" -map 0:v -map 1:a -af apad -c:v copy -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    return {"voice":round(fdur,2),"norm":round(nd,2),"video":round(vdur,2),"at":round(at,3),"ext":round(ext,2),"out":outv,"outdur":round(dur(outv),2)}
R={}
# --- p4 ---
ws=wwords(f"{OUT}/p4_full.wav"); txt,idx=stream(ws)
def span(m,end=False):
    i=idx[min(m.end()-1 if end else m.start(),len(idx)-1)]
    return i
m0=re.search(r"setting up a budget",txt)
mcl=None
for m in re.finditer(r"whole set ?up",txt): mcl=m
t0=ws[span(m0)][1]; t1=ws[span(mcl,True)][2]
cuts=[]
# excise ad-lib "if not the whole weekend"
mal=re.search(r"if not the whole weekend",txt)
mns=re.search(r"no sorry",txt)
flub_i=None; ns_i=idx[mns.start()] if mns else None
if mns:
    for m in re.finditer(r"it tells you",txt):
        wi=idx[m.start()]
        if wi<ns_i: flub_i=wi
        else: break
segs=[]
cur=t0-0.08
if mal:
    a_i=idx[mal.start()]; b_i=idx[min(mal.end()-1,len(idx)-1)]
    segs.append((cur, ws[a_i][1]-0.05)); cur=ws[b_i][2]+0.02
if mns and flub_i is not None:
    after=ns_i
    while after<len(ws) and "sorry" not in ws[after][0]: after+=1
    after+=1
    segs.append((cur, ws[flub_i][1]-0.05)); cur=ws[after][1]-0.05
segs.append((cur, t1+0.15))
parts=[]
for k,(a,b) in enumerate(segs):
    if b-a<0.2: continue
    p=f"{OUT}/p4_r4_{k}.wav"; cutw(f"{OUT}/p4_full.wav",a,b,p); parts.append(p)
v=f"{OUT}/p4_r4.wav"; concat(parts,v)
R["p4"]=finish("p4",v,f"{W}/portfolio/piece4_penny-fintech-onboarding.mp4",max_ext=4.0)
# --- p5: LAST open -> its following close ---
ws=wwords(f"{OUT}/p5_full.wav"); txt,idx=stream(ws)
opens=[m for m in re.finditer(r"this texture is",txt)]
o=opens[-1]; oi=idx[o.start()]; t0=ws[oi][1]
mcl=None
for m in re.finditer(r"for us",txt):
    if idx[m.start()]>oi: mcl=m; break
if mcl:
    t1=ws[idx[min(mcl.end()-1,len(idx)-1)]][2]
    v=f"{OUT}/p5_r4.wav"; cutw(f"{OUT}/p5_full.wav",t0-0.08,min(t1+0.18,dur(f"{OUT}/p5_full.wav")),v)
    R["p5"]=finish("p5",v,f"{W}/portfolio/piece5_luma-serum-texture.mp4",max_ext=2.5)
else:
    R["p5"]={"err":"no close after last open","n_opens":len(opens),"txt_tail":txt[-160:]}
# --- d05 ---
ws=wwords(f"{OUT}/d05_full.wav"); txt,idx=stream(ws)
m0=re.search(r"(officially|i officially) stopped",txt)
mcl=None
for m in re.finditer(r"(in my comments|the comments|comments)",txt): mcl=m
t0=ws[idx[m0.start()]][1]; t1=ws[idx[min(mcl.end()-1,len(idx)-1)]][2]
v=f"{OUT}/d05_r4.wav"; cutw(f"{OUT}/d05_full.wav",t0-0.08,min(t1+0.18,dur(f"{OUT}/d05_full.wav")),v)
R["d05"]=finish("d05",v,f"{W}/posting_kit/videos/post05_d05_chatgpt-grocery.mp4",max_ext=3.5)
print(json.dumps(R,indent=1,default=lambda x:x.item() if hasattr(x,"item") else str(x)))

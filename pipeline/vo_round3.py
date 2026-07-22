#!/usr/bin/env python3
"""Round 3: p4 gap-compress, p5 small.en retry, p9 last-token close, d12 gap-compress."""
import subprocess, json, os, re
from faster_whisper import WhisperModel
W="/agent/workspace"; OUT=f"{W}/vo_batch/cuts"
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True)
def dur(p):
    r=sh(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{p}"')
    try: return float(r.stdout.strip())
    except: return -1

_models={}
def wwords(path, size="base.en"):
    if size not in _models: _models[size]=WhisperModel(size, device="cpu", compute_type="int8")
    segs,_=_models[size].transcribe(path, word_timestamps=True, vad_filter=True)
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
def cutwav(src,a,b,out):
    sh(f'ffmpeg -v error -i "{src}" -ss {max(0,a)} -to {b} -af "afade=t=in:st=0:d=0.03,afade=t=out:st={max(0,b-a-0.04)}:d=0.04" "{out}" -y')

def gap_compress(wav, out, keep=0.22, thresh="-38dB", mind=0.35):
    r=sh(f'ffmpeg -i "{wav}" -af silencedetect=noise={thresh}:d={mind} -f null - 2>&1')
    starts=[float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stdout+r.stderr)]
    ends=[float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stdout+r.stderr)]
    total=dur(wav)
    spans=[]; cur=0.0
    for s,e in zip(starts,ends+[total]):
        if s-cur>0.05: spans.append((cur,s))
        cur=e
    if total-cur>0.05: spans.append((cur,total))
    if not spans: sh(f'cp "{wav}" "{out}"'); return
    parts=[]
    for k,(a,b) in enumerate(spans):
        p=f"{OUT}/gc_{k}.wav"; sh(f'ffmpeg -v error -i "{wav}" -ss {a} -to {b} "{p}" -y'); parts.append(p)
    sil=f"{OUT}/gc_sil.wav"; sh(f'ffmpeg -v error -f lavfi -t {keep} -i anullsrc=r=48000:cl=mono "{sil}" -y')
    lst=f"{OUT}/gc_list.txt"
    with open(lst,"w") as f:
        for k,p in enumerate(parts):
            f.write(f"file '{p}'\n")
            if k<len(parts)-1: f.write(f"file '{sil}'\n")
    sh(f'ffmpeg -v error -f concat -safe 0 -i "{lst}" "{out}" -y')

def fit_and_mux(jid, voice, video, mode="replace", max_ext=3.5, compress_first=True):
    if compress_first:
        gc=f"{OUT}/{jid}_r3_gc.wav"; gap_compress(voice,gc); voice=gc
    vdur=dur(video); tdur=dur(voice); window=vdur-0.35
    at=1.0
    if tdur>window: at=min(1.10, tdur/window)
    fitted=voice
    if abs(at-1.0)>0.012:
        fitted=f"{OUT}/{jid}_r3_fit.wav"; sh(f'ffmpeg -v error -i "{voice}" -af atempo={at:.4f} "{fitted}" -y')
    fdur=dur(fitted)
    vsrc=video; ext=0.0
    if fdur>vdur-0.35:
        ext=min(max_ext, fdur-(vdur-0.35)+0.5)
        vsrc=f"{OUT}/{jid}_r3_ext.mp4"
        sh(f'ffmpeg -v error -i "{video}" -vf "tpad=stop_mode=clone:stop_duration={ext:.2f}" -an -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p "{vsrc}" -y')
        vdur=dur(vsrc)
    truncated = fdur > vdur-0.15
    norm=f"{OUT}/{jid}_r3_voice.wav"
    sh(f'ffmpeg -v error -i "{fitted}" -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 48000 "{norm}" -y')
    outv=video.replace(".mp4","_realvo.mp4")
    if mode=="amix":
        sh(f'ffmpeg -v error -i "{video}" -i "{norm}" -filter_complex "[0:a]volume=0.25,apad[bed];[1:a]adelay=60|60,apad[vo];[bed][vo]amix=inputs=2:duration=first:normalize=0[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    else:
        sh(f'ffmpeg -v error -i "{vsrc}" -i "{norm}" -map 0:v -map 1:a -af apad -c:v copy -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    return {"atempo":round(at,3),"voice":round(fdur,2),"video":round(vdur,2),"ext":round(ext,2),
            "truncated":bool(truncated),"out":outv,"outdur":round(dur(outv),2)}
R={}
# p4: re-splice (same as before) then gap-compress
ws=wwords(f"{OUT}/p4_full.wav"); txt,idx=stream(ws)
m0=re.search(r"setting up a budget",txt); mclose=None
for mc in re.finditer(r"(whole setup|whole set up)",txt): mclose=mc
mns=re.search(r"no sorry",txt)
t0=ws[idx[m0.start()]][1]; t1=ws[idx[min(mclose.end()-1,len(idx)-1)]][2]
ns_i=idx[mns.start()]; flub_i=None
for m in re.finditer(r"it tells you",txt):
    wi=idx[m.start()]
    if wi<ns_i: flub_i=wi
    else: break
after_i=ns_i
while after_i<len(ws) and "sorry" not in ws[after_i][0]: after_i+=1
after_i+=1
c1=f"{OUT}/p4_r3a.wav"; c2=f"{OUT}/p4_r3b.wav"; v=f"{OUT}/p4_r3.wav"
cutwav(f"{OUT}/p4_full.wav",t0-0.08,ws[flub_i][1]-0.05,c1)
cutwav(f"{OUT}/p4_full.wav",ws[after_i][1]-0.05,t1+0.15,c2)
sh(f'ffmpeg -v error -i "{c1}" -i "{c2}" -filter_complex "[0][1]concat=n=2:v=0:a=1" "{v}" -y')
R["p4"]=fit_and_mux("p4",v,f"{W}/portfolio/piece4_penny-fintech-onboarding.mp4",max_ext=4.0)
# p5: small.en
ws=wwords(f"{OUT}/p5_full.wav","small.en"); txt,idx=stream(ws)
opens=[m for m in re.finditer(r"(this texture is|texture is the whole)",txt)]
closes=[m for m in re.finditer(r"(this ones for us|ones for us|for us)",txt)]
cands=[]
for om in opens:
    t0=ws[idx[om.start()]][1]
    for cm in closes:
        t1=ws[idx[min(cm.end()-1,len(idx)-1)]][2]
        if t1>t0 and 8<=(t1-t0)<=30: cands.append((t0,t1)); break
if cands:
    t0,t1=cands[-1]
    v=f"{OUT}/p5_r3.wav"; cutwav(f"{OUT}/p5_full.wav",t0-0.08,t1+0.15,v)
    R["p5"]=fit_and_mux("p5",v,f"{W}/portfolio/piece5_luma-serum-texture.mp4",max_ext=2.0)
else: R["p5"]={"err":"nocand","n_open":len(opens),"n_close":len(closes),"txt":txt[:200]}
# p9: open -> LAST money token
ws=wwords(f"{OUT}/p9_full.wav"); txt,idx=stream(ws)
opens=[m for m in re.finditer(r"(fifteen|15).{0,16}target",txt)]
last=None
for m in re.finditer(r"\b(15|fifteen|dollars?)\b",txt): last=m
if opens and last:
    o=opens[-1] if len(opens)>1 else opens[0]
    t0=ws[idx[o.start()]][1]; t1=ws[idx[min(last.end()-1,len(idx)-1)]][2]
    v=f"{OUT}/p9_r3.wav"; cutwav(f"{OUT}/p9_full.wav",t0-0.08,min(t1+0.20,dur(f"{OUT}/p9_full.wav")),v)
    R["p9"]=fit_and_mux("p9",v,f"{W}/digicam_raw/piece9_digicam_clixshot.mp4",mode="amix",max_ext=0.0,compress_first=False)
else: R["p9"]={"err":"match","n_open":len(opens)}
# d12: body + tag splice then gap-compress, ext 3.5
ws=wwords(f"{OUT}/d12_full.wav"); txt,idx=stream(ws)
opens=[m for m in re.finditer(r"three free tools",txt)]
mbay=None
for m in re.finditer(r"edit bay",txt): mbay=m
sweats=[m for m in re.finditer(r"subscriptions are sweating",txt)]
o=opens[-1] if len(opens)>1 else opens[0]
t0=ws[idx[o.start()]][1]; tb=ws[idx[min(mbay.end()-1,len(idx)-1)]][2]
sm=sweats[-1]; si=idx[sm.start()]
s0=ws[max(0,si-1)][1]; s1=ws[idx[min(sm.end()-1,len(idx)-1)]][2]
c1=f"{OUT}/d12_r3a.wav"; c2=f"{OUT}/d12_r3b.wav"; v=f"{OUT}/d12_r3.wav"
cutwav(f"{OUT}/d12_full.wav",t0-0.08,tb+0.10,c1); cutwav(f"{OUT}/d12_full.wav",s0-0.06,s1+0.18,c2)
sh(f'ffmpeg -v error -i "{c1}" -i "{c2}" -filter_complex "[0][1]concat=n=2:v=0:a=1" "{v}" -y')
R["d12"]=fit_and_mux("d12",v,f"{W}/posting_kit/videos/post12_d12_free-tools.mp4",max_ext=3.5)
print(json.dumps(R,indent=1,default=lambda o:o.item() if hasattr(o,"item") else str(o)))
json.dump(R,open(f"{OUT}/round3_report.json","w"),indent=1,default=lambda o:o.item() if hasattr(o,"item") else str(o))

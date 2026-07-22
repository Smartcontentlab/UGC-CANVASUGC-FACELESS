#!/usr/bin/env python3
"""Targeted rebuilds: p2, p4, p5, p9, d05, d12 — whisper-word-driven cuts, no truncation, tail-extension allowed."""
import subprocess, json, os, re
from faster_whisper import WhisperModel

W="/agent/workspace"; OUT=f"{W}/vo_batch/cuts"
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True)
def dur(p):
    r=sh(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{p}"')
    try: return float(r.stdout.strip())
    except: return -1
model=WhisperModel("base.en", device="cpu", compute_type="int8")
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
def cutwav(src,a,b,out,fade=True):
    f=f'-af "afade=t=in:st=0:d=0.03,afade=t=out:st={max(0,b-a-0.04)}:d=0.04"' if fade else ""
    sh(f'ffmpeg -v error -i "{src}" -ss {max(0,a)} -to {b} {f} "{out}" -y')
def fit_and_mux(jid, voice, video, mode="replace", max_ext=3.5):
    vdur=dur(video); tdur=dur(voice)
    window=vdur-0.35
    at=1.0
    if tdur>window: at=min(1.10, tdur/window)
    fitted=voice
    if abs(at-1.0)>0.012:
        fitted=f"{OUT}/{jid}_rb_fit.wav"; sh(f'ffmpeg -v error -i "{voice}" -af atempo={at:.4f} "{fitted}" -y')
    fdur=dur(fitted)
    vsrc=video; ext=0.0
    if fdur>vdur-0.35:
        ext=min(max_ext, fdur-(vdur-0.35)+0.5)
        vsrc=f"{OUT}/{jid}_rb_ext.mp4"
        sh(f'ffmpeg -v error -i "{video}" -vf "tpad=stop_mode=clone:stop_duration={ext:.2f}" -an -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p "{vsrc}" -y')
        vdur=dur(vsrc)
    norm=f"{OUT}/{jid}_rb_voice.wav"
    sh(f'ffmpeg -v error -i "{fitted}" -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 48000 "{norm}" -y')
    outv=video.replace(".mp4","_realvo.mp4")
    if mode=="amix":
        base=video if vsrc==video else vsrc
        bedsrc=video  # bed comes from original (has audio); if extended, pad bed
        sh(f'ffmpeg -v error -i "{base}" -i "{video}" -i "{norm}" -filter_complex "[1:a]volume=0.25,apad[bed];[2:a]adelay=60|60,apad[vo];[bed][vo]amix=inputs=2:duration=first:normalize=0[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    else:
        sh(f'ffmpeg -v error -i "{vsrc}" -i "{norm}" -map 0:v -map 1:a -af apad -c:v copy -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    return {"atempo":round(at,3),"voice":round(fdur,2),"video":round(vdur,2),"ext":round(ext,2),"out":outv,"outdur":round(dur(outv),2)}

R={}
# ---- p2: full read after slate ----
ws=wwords(f"{OUT}/p2_full.wav"); txt,idx=stream(ws)
m0=re.search(r"my brain has (forty|40)",txt); m1=None
for m1c in re.finditer(r"(links? below|link is below|links below)",txt): m1=m1c
if m0 and m1:
    t0=ws[idx[m0.start()]][1]; t1=ws[idx[min(m1.end()-1,len(idx)-1)]][2]
    v=f"{OUT}/p2_rb.wav"; cutwav(f"{OUT}/p2_full.wav",t0-0.08,t1+0.15,v)
    R["p2"]=fit_and_mux("p2",v,f"{W}/portfolio/piece2_taskloop-saas-ad.mp4")
else: R["p2"]={"err":"match","txt":txt[:120]}
# ---- p4: take + flub excision ----
ws=wwords(f"{OUT}/p4_full.wav"); txt,idx=stream(ws)
m0=re.search(r"setting up a budget",txt)
mclose=None
for mc in re.finditer(r"(whole setup|the whole set up)",txt): mclose=mc
mns=re.search(r"no sorry",txt)
if m0 and mclose:
    t0=ws[idx[m0.start()]][1]; t1=ws[idx[min(mclose.end()-1,len(idx)-1)]][2]
    if mns:
        ns_i=idx[mns.start()]
        flub_i=None
        for m in re.finditer(r"it tells you",txt):
            wi=idx[m.start()]
            if wi<ns_i: flub_i=wi
            else: break
        after_i=ns_i
        while after_i<len(ws) and "sorry" not in ws[after_i][0]: after_i+=1
        after_i+=1
        c1=f"{OUT}/p4_rb1.wav"; c2=f"{OUT}/p4_rb2.wav"; v=f"{OUT}/p4_rb.wav"
        cutwav(f"{OUT}/p4_full.wav",t0-0.08,ws[flub_i][1]-0.05,c1)
        cutwav(f"{OUT}/p4_full.wav",ws[after_i][1]-0.05,t1+0.15,c2)
        sh(f'ffmpeg -v error -i "{c1}" -i "{c2}" -filter_complex "[0][1]concat=n=2:v=0:a=1" "{v}" -y')
    else:
        v=f"{OUT}/p4_rb.wav"; cutwav(f"{OUT}/p4_full.wav",t0-0.08,t1+0.15,v)
    R["p4"]=fit_and_mux("p4",v,f"{W}/portfolio/piece4_penny-fintech-onboarding.mp4")
else: R["p4"]={"err":"match","txt":txt[:120]}
# ---- p5: last complete take (open->first close after, <=1.6x target) ----
ws=wwords(f"{OUT}/p5_full.wav"); txt,idx=stream(ws)
opens=[m for m in re.finditer(r"this texture is",txt)]
closes=[m for m in re.finditer(r"for us",txt)]
cands=[]
for om in opens:
    t0=ws[idx[om.start()]][1]
    for cm in closes:
        t1=ws[idx[min(cm.end()-1,len(idx)-1)]][2]
        if t1>t0 and 9<= (t1-t0) <=29:
            cands.append((t0,t1)); break
if cands:
    t0,t1=cands[-1]
    v=f"{OUT}/p5_rb.wav"; cutwav(f"{OUT}/p5_full.wav",t0-0.08,t1+0.15,v)
    R["p5"]=fit_and_mux("p5",v,f"{W}/portfolio/piece5_luma-serum-texture.mp4")
else: R["p5"]={"err":"nocand","opens":len(opens),"closes":len(closes)}
# ---- p9: open->final dollars, amix bed ----
ws=wwords(f"{OUT}/p9_full.wav"); txt,idx=stream(ws)
m0=re.search(r"(fifteen|15).{0,14}target",txt)
last_dollar=None
for m in re.finditer(r"dollars?",txt): last_dollar=m
if m0 and last_dollar:
    t0=ws[idx[m0.start()]][1]; t1=ws[idx[min(last_dollar.end()-1,len(idx)-1)]][2]
    if t1-t0>21.5:  # two takes spanned; take the SECOND open if exists
        opens=[m for m in re.finditer(r"(fifteen|15).{0,14}target",txt)]
        if len(opens)>1: t0=ws[idx[opens[-1].start()]][1]
    v=f"{OUT}/p9_rb.wav"; cutwav(f"{OUT}/p9_full.wav",t0-0.08,min(t1+0.15,dur(f"{OUT}/p9_full.wav")),v)
    R["p9"]=fit_and_mux("p9",v,f"{W}/digicam_raw/piece9_digicam_clixshot.mp4",mode="amix",max_ext=0.0)
else: R["p9"]={"err":"match","txt":txt[:140]}
# ---- d05: full line incl 'in my comments', extend tail ----
ws=wwords(f"{OUT}/d05_full.wav"); txt,idx=stream(ws)
m0=re.search(r"i officially stopped",txt); m1=None
for mc in re.finditer(r"(in my comments|in the comments)",txt): m1=mc
if m0 and m1:
    t0=ws[idx[m0.start()]][1]; t1=ws[idx[min(m1.end()-1,len(idx)-1)]][2]
    v=f"{OUT}/d05_rb.wav"; cutwav(f"{OUT}/d05_full.wav",t0-0.08,t1+0.15,v)
    R["d05"]=fit_and_mux("d05",v,f"{W}/posting_kit/videos/post05_d05_chatgpt-grocery.mp4",max_ext=3.5)
else: R["d05"]={"err":"match","txt":txt[:120]}
# ---- d12: body (open#last -> 'edit bay') + clean 'subscriptions are sweating' tag ----
ws=wwords(f"{OUT}/d12_full.wav"); txt,idx=stream(ws)
opens=[m for m in re.finditer(r"three free tools",txt)]
mbay=None
for m in re.finditer(r"edit bay",txt): mbay=m
sweats=[m for m in re.finditer(r"subscriptions are sweating",txt)]
if opens and mbay and sweats:
    o=opens[-1] if len(opens)>1 else opens[0]
    t0=ws[idx[o.start()]][1]
    tb=ws[idx[min(mbay.end()-1,len(idx)-1)]][2]
    sm=sweats[-1]
    # back up to catch 'your'
    si=idx[sm.start()]
    s0=ws[max(0,si-1)][1]; s1=ws[idx[min(sm.end()-1,len(idx)-1)]][2]
    c1=f"{OUT}/d12_rb1.wav"; c2=f"{OUT}/d12_rb2.wav"; v=f"{OUT}/d12_rb.wav"
    cutwav(f"{OUT}/d12_full.wav",t0-0.08,tb+0.10,c1)
    cutwav(f"{OUT}/d12_full.wav",s0-0.06,s1+0.18,c2)
    sh(f'ffmpeg -v error -i "{c1}" -i "{c2}" -filter_complex "[0][1]concat=n=2:v=0:a=1" "{v}" -y')
    R["d12"]=fit_and_mux("d12",v,f"{W}/posting_kit/videos/post12_d12_free-tools.mp4",max_ext=3.0)
else: R["d12"]={"err":"match","opens":len(opens),"bay":bool(mbay),"sweats":len(sweats)}

print(json.dumps(R,indent=1,default=lambda o:o.item() if hasattr(o,"item") else str(o)))
json.dump(R,open(f"{OUT}/rebuild_report.json","w"),indent=1,default=lambda o:o.item() if hasattr(o,"item") else str(o))

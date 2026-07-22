#!/usr/bin/env python3
"""Authoritative portfolio VO verification + targeted rebuild."""
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
    segs,_=model.transcribe(path, word_timestamps=True, vad_filter=False)
    ws=[]
    for s in segs:
        for w in (s.words or []):
            t=re.sub(r"[^a-z0-9 ]","",w.word.lower().strip())
            if t: ws.append((t,w.start,w.end))
    return ws

CHECKS={
 "p1":(f"{W}/portfolio/piece1_ai-tools-listicle_realvo.mp4", r"three ai tools", r"(group chat|finds out)"),
 "p2":(f"{W}/portfolio/piece2_taskloop-saas-ad_realvo.mp4", r"my brain has", r"(link|below)"),
 "p3":(f"{W}/portfolio/piece3_aeris-unboxing_realvo.mp4", r"(okay|ok) the packaging", r"easy to recommend"),
 "p4":(f"{W}/portfolio/piece4_penny-fintech-onboarding_realvo.mp4", r"setting up a budget", r"whole setup"),
 "p5":(f"{W}/portfolio/piece5_luma-serum-texture_realvo.mp4", r"this texture is", r"(this ones for us|for us)"),
 "p7":(f"{W}/portfolio/piece7_evening-routine_realvo.mp4", r"my skin stopped", r"actually keep"),
 "p8":(f"{W}/portfolio/piece8_glowpod-device-demo_realvo.mp4", r"the spa charges", r"finally"),
 "p9":(f"{W}/digicam_raw/piece9_digicam_clixshot_realvo.mp4", r"(fifteen|15)", r"dollars?"),
}
report={}
for jid,(path,op,cp) in CHECKS.items():
    if not os.path.exists(path):
        report[jid]={"status":"MISSING_FILE"}; continue
    d=dur(path)
    aw=f"{OUT}/{jid}_check.wav"
    sh(f'ffmpeg -v error -i "{path}" -vn -ar 16000 -ac 1 "{aw}" -y')
    ws=wwords(aw)
    if not ws:
        report[jid]={"status":"NO_SPEECH","dur":d}; continue
    txt=" ".join(t for t,_,_ in ws)
    first_t=ws[0][1]; last_end=ws[-1][2]
    slate=bool(re.search(r"\b(vo ?p ?\d|vod ?\d|vop)\b",txt[:60]))
    has_open=bool(re.search(op,txt)); has_close=bool(re.search(cp,txt))
    trunc = (d-last_end) < 0.15 and not re.search(cp, txt[-80:]) if has_close==False else False
    hook_late = first_t>1.35
    ok = has_open and has_close and not slate and not hook_late and (d-last_end)>=0.10
    report[jid]={"status":"PASS" if ok else "FAIL","dur":round(d,2),"first_word_s":round(first_t,2),
                 "last_word_end":round(last_end,2),"open":has_open,"close":has_close,"slate":slate,
                 "hook_late":hook_late,"tail_room":round(d-last_end,2),"text":txt[:150]}
print(json.dumps(report,indent=1,default=lambda o: o.item() if hasattr(o,"item") else str(o)))
json.dump(report,open(f"{OUT}/verify_report.json","w"),indent=1,default=lambda o: o.item() if hasattr(o,"item") else str(o))

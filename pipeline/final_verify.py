#!/usr/bin/env python3
"""FINAL verification: all 15 real-voice files."""
import subprocess, json, os, re
from faster_whisper import WhisperModel
W="/agent/workspace"; OUT=f"{W}/vo_batch/cuts"
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True)
def dur(p):
    r=sh(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{p}"')
    try: return float(r.stdout.strip())
    except: return -1
model=WhisperModel("base.en", device="cpu", compute_type="int8")
C={
 "p1":(f"{W}/portfolio/piece1_ai-tools-listicle_realvo.mp4", r"(three|3) ai tools", r"(group chat|finds out)"),
 "p2":(f"{W}/portfolio/piece2_taskloop-saas-ad_realvo.mp4", r"my brain has", r"(link|below)"),
 "p3":(f"{W}/portfolio/piece3_aeris-unboxing_realvo.mp4", r"(okay|ok) the packaging", r"easy to recommend"),
 "p4":(f"{W}/portfolio/piece4_penny-fintech-onboarding_realvo.mp4", r"setting up a budget", r"whole set ?up"),
 "p5":(f"{W}/portfolio/piece5_luma-serum-texture_realvo.mp4", r"(this texture|texture is)", r"for us"),
 "p7":(f"{W}/portfolio/piece7_evening-routine_realvo.mp4", r"my skin stopped", r"actually keep"),
 "p8":(f"{W}/portfolio/piece8_glowpod-device-demo_realvo.mp4", r"the spa charges", r"finally"),
 "p9":(f"{W}/digicam_raw/piece9_digicam_clixshot_realvo.mp4", r"(fifteen|15)", r"(dollars?|\b15\b)"),
 "d03":(f"{W}/posting_kit/videos/post03_d03_removebg-tip_realvo.mp4", r"this free site", r"thank me later"),
 "d05":(f"{W}/posting_kit/videos/post05_d05_chatgpt-grocery_realvo.mp4", r"officially stopped", r"comments"),
 "d07":(f"{W}/posting_kit/videos/post07_d07_ai-broll-skeptic_realvo.mp4", r"skeptical about ai", r"shot ?lists?"),
 "d08":(f"{W}/posting_kit/videos/post08_d08_capcut-freevspro_realvo.mp4", r"honest difference", r"clients ask"),
 "d10":(f"{W}/posting_kit/videos/post10_d10_learn-with-ai_realvo.mp4", r"learn copywriting", r"real skill"),
 "d12":(f"{W}/posting_kit/videos/post12_d12_free-tools_realvo.mp4", r"(three|3) free tools", r"(edit bay|sweating)"),
 "d14":(f"{W}/posting_kit/videos/post14_d14_open-for-collabs_realvo.mp4", r"faceless ugc", r"(bio|collabs)"),
}
rep={}
fails=0
for jid,(path,op,cp) in C.items():
    if not os.path.exists(path): rep[jid]={"s":"MISSING"}; fails+=1; continue
    d=dur(path)
    aw=f"{OUT}/{jid}_fv.wav"
    sh(f'ffmpeg -v error -i "{path}" -vn -ar 16000 -ac 1 "{aw}" -y')
    segs,_=model.transcribe(aw, word_timestamps=True, vad_filter=False)
    ws=[]
    for s in segs:
        for w in (s.words or []):
            t=re.sub(r"[^a-z0-9 ]","",w.word.lower().strip())
            if t: ws.append((t,float(w.start),float(w.end)))
    if not ws: rep[jid]={"s":"NO_SPEECH","dur":round(d,2)}; fails+=1; continue
    txt=" ".join(t for t,_,_ in ws)
    first=ws[0][1]; lastend=ws[-1][2]
    slate=bool(re.search(r"\b(vo ?p|vod|vop)\b",txt[:40]))
    o=bool(re.search(op,txt)); c=bool(re.search(cp,txt))
    ok = o and c and not slate and first<=1.45 and (d-lastend)>=0.08
    if not ok: fails+=1
    rep[jid]={"s":"PASS" if ok else "FAIL","dur":round(d,2),"first":round(first,2),
              "tail":round(d-lastend,2),"o":o,"c":c,"slate":slate,"end_text":txt[-60:]}
print(json.dumps(rep,indent=0,default=lambda x:x.item() if hasattr(x,"item") else str(x)))
print("FAILS:",fails)

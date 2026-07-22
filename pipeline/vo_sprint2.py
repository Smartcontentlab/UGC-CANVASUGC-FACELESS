#!/usr/bin/env python3
"""VO sprint v2: whisper word-timestamps -> precise take cuts -> fit -> mux -> verify."""
import subprocess, json, os, re, sys
from faster_whisper import WhisperModel

SF="/agent/stored_files"; W="/agent/workspace"; OUT=f"{W}/vo_batch/cuts"
os.makedirs(OUT, exist_ok=True)
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True)
def dur(p):
    r=sh(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{p}"')
    try: return float(r.stdout.strip())
    except: return -1

# id, video, memo_wav(from v1), target, mode, open_pattern, close_pattern, special
J=[
 ("p1", f"{W}/portfolio/piece1_ai-tools-listicle.mp4", "p1", 24, "replace", r"three ai tools that honestly", r"group chat finds out", None),
 ("p2", f"{W}/portfolio/piece2_taskloop-saas-ad.mp4", "p2", 24, "replace", r"my brain has (forty|40) tabs", r"links? s?\s?below", None),
 ("p3", f"{W}/portfolio/piece3_aeris-unboxing.mp4", "p3", 22, "replace", r"okay the packaging alone", r"easy to recommend", None),
 ("p4", f"{W}/portfolio/piece4_penny-fintech-onboarding.mp4", "p4", 19, "replace", r"setting up a budget", r"thats the whole setup", "p4fix"),
 ("p5", f"{W}/portfolio/piece5_luma-serum-texture.mp4", "p5", 18, "replace", r"this texture is the whole personality", r"this ones for us", None),
 ("p7", f"{W}/portfolio/piece7_evening-routine.mp4", "p7", 18, "replace", r"my skin stopped fighting me", r"youll actually keep", None),
 ("p8", f"{W}/portfolio/piece8_glowpod-device-demo.mp4", "p8", 24, "replace", r"the spa charges", r"skincare tech finally", None),
 ("p9", f"{W}/digicam_raw/piece9_digicam_clixshot.mp4", "p9", 17, "amix", r"(fifteen|15) dollars at target", r"harder than my phones?", "p9tail"),
 ("d03", f"{W}/posting_kit/videos/post03_d03_removebg-tip.mp4", "d03", 13, "replace", r"this free site removes", r"thank me later", None),
 ("d05", f"{W}/posting_kit/videos/post05_d05_chatgpt-grocery.mp4", "d05", 12, "replace", r"i officially stopped writing grocery", r"in my comments", None),
 ("d07", f"{W}/posting_kit/videos/post07_d07_ai-broll-skeptic.mp4", "d07", 18, "replace", r"i was skeptical about ai b ?roll", r"replacing shot lists", None),
 ("d08", f"{W}/posting_kit/videos/post08_d08_capcut-freevspro.mp4", "d08", 15, "replace", r"the honest difference between free", r"when clients ask", None),
 ("d10", f"{W}/posting_kit/videos/post10_d10_learn-with-ai.mp4", "d10", 19, "replace", r"if i had to learn copywriting", r"real skill", None),
 ("d12", f"{W}/posting_kit/videos/post12_d12_free-tools.mp4", "d12", 14, "replace", r"three free tools quietly replacing", r"subscriptions are sweating", None),
 ("d14", f"{W}/posting_kit/videos/post14_d14_open-for-collabs.mp4", "d14", 12, "replace", r"i make faceless ugc", r"in bio", None),
]

model = WhisperModel("base.en", device="cpu", compute_type="int8")
def words_of(wav):
    segs,_ = model.transcribe(wav, word_timestamps=True, vad_filter=True)
    ws=[]
    for s in segs:
        for w in (s.words or []):
            t=re.sub(r"[^a-z0-9 ]","",w.word.lower().strip())
            if t: ws.append((t, w.start, w.end))
    return ws

def stream(ws):
    txt=""; idx=[]
    for i,(t,a,b) in enumerate(ws):
        for _ in range(len(t)+1): idx.append(i)
        txt+=t+" "
    return txt, idx

results=[]
for jid, video, wkey, target, mode, op, cp, special in J:
    row={"id":jid}
    wav=f"{OUT}/{wkey}_full.wav"
    if not (os.path.exists(video) and os.path.exists(wav)):
        row["status"]="MISSING"; results.append(row); continue
    vdur=dur(video)
    ws=words_of(wav)
    txt,idx=stream(ws)
    opens=[m for m in re.finditer(op,txt)]
    closes=[m for m in re.finditer(cp,txt)]
    if not opens or not closes:
        row["status"]="MATCH_FAIL"; row["txt_head"]=txt[:180]; results.append(row); continue
    # candidates: for each open, first close ending after it within duration bounds
    cands=[]
    for om in opens:
        oi=idx[min(om.start(),len(idx)-1)]; t0=ws[oi][1]
        for cm in closes:
            ci=idx[min(cm.end()-1,len(idx)-1)]; t1=ws[ci][2]
            if t1>t0 and 0.5*target <= (t1-t0) <= 2.4*target:
                cands.append((t0,t1,oi,ci)); break
    if not cands:
        row["status"]="NO_CAND"; row["opens"]=len(opens); row["closes"]=len(closes); results.append(row); continue
    t0,t1,oi,ci=cands[-1]
    # p9: extend to trailing "dollars" after closer
    if special=="p9tail":
        for j in range(ci+1, min(ci+12,len(ws))):
            if "dollar" in ws[j][0] or ws[j][0]=="15": t1=ws[j][2]; ci=j
    seg=f"{OUT}/{jid}_v2take.wav"
    a=max(0,t0-0.12); b=min(dur(wav), t1+0.18)
    # p4: excise flub inside [a,b]
    if special=="p4fix":
        m_ns=re.search(r"no sorry",txt)
        if m_ns:
            ns_i=idx[m_ns.start()]
            # find start of the flubbed clause: last "it tells you" before "no sorry"
            flub_start_i=None
            for m in re.finditer(r"it tells you",txt):
                wi=idx[m.start()]
                if wi<ns_i: flub_start_i=wi
                else: break
            after_i=ns_i
            while after_i<len(ws) and "sorry" not in ws[after_i][0]: after_i+=1
            after_i+=1
            if flub_start_i and after_i<len(ws):
                c1=f"{OUT}/{jid}_pt1.wav"; c2=f"{OUT}/{jid}_pt2.wav"
                cut1_end=ws[flub_start_i][1]-0.06; cut2_start=ws[after_i][1]-0.05
                sh(f'ffmpeg -v error -i "{wav}" -ss {a} -to {cut1_end} -af "afade=t=out:st={cut1_end-a-0.04}:d=0.04" "{c1}" -y')
                sh(f'ffmpeg -v error -i "{wav}" -ss {cut2_start} -to {b} -af "afade=t=in:st=0:d=0.04" "{c2}" -y')
                sh(f'ffmpeg -v error -i "{c1}" -i "{c2}" -filter_complex "[0][1]concat=n=2:v=0:a=1" "{seg}" -y')
            else:
                sh(f'ffmpeg -v error -i "{wav}" -ss {a} -to {b} "{seg}" -y')
        else:
            sh(f'ffmpeg -v error -i "{wav}" -ss {a} -to {b} "{seg}" -y')
    else:
        sh(f'ffmpeg -v error -i "{wav}" -ss {a} -to {b} "{seg}" -y')
    tdur=dur(seg)
    window=vdur-0.35
    at=1.0; fitted=seg
    if tdur>window: at=min(1.10, tdur/window)
    elif tdur<window*0.75: at=max(0.96, tdur/(window*0.88))
    if abs(at-1.0)>0.015:
        fitted=f"{OUT}/{jid}_v2fit.wav"
        sh(f'ffmpeg -v error -i "{seg}" -af atempo={at:.4f} "{fitted}" -y')
    fdur=dur(fitted)
    extend=0.0; vsrc=video; reenc=False
    if fdur>window:
        extend=min(2.5, fdur-window+0.45)
        vsrc=f"{OUT}/{jid}_ext.mp4"; reenc=True
        sh(f'ffmpeg -v error -i "{video}" -vf "tpad=stop_mode=clone:stop_duration={extend:.2f}" -an -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p "{vsrc}" -y')
        vdur=dur(vsrc)
    norm=f"{OUT}/{jid}_v2voice.wav"
    sh(f'ffmpeg -v error -i "{fitted}" -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 48000 "{norm}" -y')
    outv=video.replace(".mp4","_realvo.mp4")
    if mode=="amix":
        sh(f'ffmpeg -v error -i "{video}" -i "{norm}" -filter_complex "[0:a]volume=0.25[bed];[1:a]adelay=100|100,apad[vo];[bed][vo]amix=inputs=2:duration=first:normalize=0[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    else:
        amap = f'-i "{norm}" -map 0:v -map 1:a'
        sh(f'ffmpeg -v error -i "{vsrc}" {amap} -af apad -c:v {"copy" if not reenc else "copy"} -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    od=dur(outv)
    ok = od>0 and abs(od-vdur)<0.4
    row.update({"status":"OK" if ok else "MUX_FAIL","take":[round(t0,2),round(t1,2)],"take_dur":round(tdur,2),
                "atempo":round(at,3),"fit":round(fdur,2),"video":round(vdur,2),"extended":round(extend,2),"out":outv})
    results.append(row)

json.dump(results, open(f"{OUT}/manifest2.json","w"), indent=1)
for r in results:
    print(r.get("id"), r.get("status"), "take=",r.get("take"), "at=",r.get("atempo"), "fit=",r.get("fit"), "vid=",r.get("video"), "ext=",r.get("extended"), r.get("txt_head","")[:80])

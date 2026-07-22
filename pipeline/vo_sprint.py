#!/usr/bin/env python3
"""VO swap sprint: cut best take from each memo, fit, loudnorm, mux onto video."""
import subprocess, json, glob, os, sys, re

SF = "/agent/stored_files"
W = "/agent/workspace"
OUT = f"{W}/vo_batch/cuts"
os.makedirs(OUT, exist_ok=True)

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def dur(path):
    r = sh(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"')
    return float(r.stdout.strip())

def find(pattern):
    g = sorted(glob.glob(pattern))
    g = [x for x in g if "_realvo" not in x and "thumb" not in x]
    return g[0] if g else None

# jobs: (id, video, memo, target_s, mode)
jobs = [
    ("p1", find(f"{W}/portfolio/piece1*.mp4"), f"{SF}/cmrwat1760kzj07ad6nrn1jgx_Larkin St.m4a", 24, "replace"),
    ("p2", find(f"{W}/portfolio/piece2*.mp4"), f"{SF}/cmrwat18n0kzl07adirj2dpon_Larkin St 2.m4a", 24, "replace"),
    ("p3", find(f"{W}/portfolio/piece3*.mp4"), f"{SF}/cmrwat17e0kzk07addrgd14e1_Larkin St 3.m4a", 22, "replace"),
    ("p4", find(f"{W}/portfolio/piece4*.mp4"), f"{SF}/cmrwatkbi0l0307ad1liopb3t_Larkin St 4.m4a", 19, "pending"),
    ("p5", find(f"{W}/portfolio/piece5*.mp4"), f"{SF}/cmrwatkci0l0407adh8sn6gai_Larkin St 5.m4a", 18, "replace"),
    ("p7", find(f"{W}/portfolio/piece7*.mp4"), f"{SF}/cmrwatpkp0ki706ad5qs5mzt7_Larkin St 7.m4a", 18, "replace"),
    ("p8", find(f"{W}/portfolio/piece8*.mp4"), f"{SF}/cmrwatplt0ki806ad50jjx81p_Larkin St 8.m4a", 24, "replace"),
    ("p9", f"{W}/digicam_raw/piece9_digicam_clixshot.mp4", f"{SF}/cmrwatpn90ki906adcyvgf27g_Larkin St 9.m4a", 17, "amix"),
    ("d03", f"{W}/posting_kit/videos/post03_d03_removebg-tip.mp4", f"{SF}/cmrwavpq20kok06adtejnv1bu_Larkin St 10.m4a", 13, "replace"),
    ("d05", f"{W}/posting_kit/videos/post05_d05_chatgpt-grocery.mp4", f"{SF}/cmrwavpqe0kol06adkpsd95dn_Larkin St 11.m4a", 12, "replace"),
    ("d07", f"{W}/posting_kit/videos/post07_d07_ai-broll-skeptic.mp4", f"{SF}/cmrwavpsm0kop06ad81bis3h0_Larkin St 12.m4a", 18, "replace"),
    ("d08", f"{W}/posting_kit/videos/post08_d08_capcut-freevspro.mp4", f"{SF}/cmrwavpqu0kon06adpv8eiizi_Larkin St 13.m4a", 15, "replace"),
    ("d10", f"{W}/posting_kit/videos/post10_d10_learn-with-ai.mp4", f"{SF}/cmrwavpoz0koi06adt5xsugou_Larkin St 14.m4a", 19, "replace"),
    ("d12", f"{W}/posting_kit/videos/post12_d12_free-tools.mp4", f"{SF}/cmrwavppm0koj06adm2vbaicg_Larkin St 15.m4a", 14, "pending"),
    ("d14", f"{W}/posting_kit/videos/post14_d14_open-for-collabs.mp4", f"{SF}/cmrwavpqo0kom06adycpqfria_Larkin St 16.m4a", 12, "replace"),
]

def voiced_regions(wav, total, noise="-32dB", mindur=0.55):
    r = sh(f'ffmpeg -i "{wav}" -af silencedetect=noise={noise}:d={mindur} -f null - 2>&1')
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stdout + r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stdout + r.stderr)]
    # build voiced spans
    spans, cur = [], 0.0
    for s, e in zip(starts, ends + [total]):
        if s - cur > 0.35: spans.append((cur, s))
        cur = e
    if total - cur > 0.35: spans.append((cur, total))
    return spans

manifest = []
for jid, video, memo, target, mode in jobs:
    row = {"id": jid, "video": video, "mode": mode}
    if not video or not os.path.exists(str(video)) or not os.path.exists(memo):
        row["status"] = "MISSING_INPUT"; manifest.append(row); continue
    vdur = dur(video)
    wav = f"{OUT}/{jid}_full.wav"
    sh(f'ffmpeg -v error -i "{memo}" -ar 48000 -ac 1 "{wav}" -y')
    mdur = dur(wav)
    spans = voiced_regions(wav, mdur)
    row["video_dur"] = round(vdur, 2); row["memo_dur"] = round(mdur, 2)
    row["spans"] = [(round(a,2), round(b,2)) for a, b in spans]
    if mode == "pending":
        # cut every span >3s as candidate for manual splice
        cands = []
        for k, (a, b) in enumerate(spans):
            if b - a >= 3.0:
                c = f"{OUT}/{jid}_cand{k}.wav"
                sh(f'ffmpeg -v error -i "{wav}" -ss {a} -to {b} "{c}" -y')
                cands.append({"file": c, "span": (round(a,2), round(b,2)), "dur": round(b-a,2)})
        row["candidates"] = cands; row["status"] = "PENDING_SPLICE"
        manifest.append(row); continue
    # take selection: last span within 0.55x..1.7x of target, skipping first span if it's short (slate)
    cands = [(a, b) for a, b in spans if 0.55*target <= (b-a) <= 1.7*target]
    # never pick a candidate that starts before 1.0s (slate fused) unless it's the only one
    pref = [c for c in cands if c[0] >= 1.0] or cands
    if not pref:
        row["status"] = "NO_TAKE_FOUND"; manifest.append(row); continue
    a, b = pref[-1]
    take = f"{OUT}/{jid}_take.wav"
    sh(f'ffmpeg -v error -i "{wav}" -ss {max(0,a-0.05)} -to {min(mdur,b+0.10)} "{take}" -y')
    tdur = dur(take)
    # fit: voice should end ~0.4s before video end
    window = vdur - 0.4
    at = 1.0
    if tdur > window:
        at = min(1.10, tdur / window)
    elif tdur < window * 0.80:
        at = max(0.95, tdur / (window * 0.90))
    fitted = take
    if abs(at - 1.0) > 0.015:
        fitted = f"{OUT}/{jid}_fit.wav"
        sh(f'ffmpeg -v error -i "{take}" -af atempo={at:.4f} "{fitted}" -y')
    fdur = dur(fitted)
    norm = f"{OUT}/{jid}_voice.wav"
    sh(f'ffmpeg -v error -i "{fitted}" -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 48000 "{norm}" -y')
    outv = video.replace(".mp4", "_realvo.mp4")
    if mode == "amix":
        r = sh(f'ffmpeg -v error -i "{video}" -i "{norm}" -filter_complex "[0:a]volume=0.25[bed];[1:a]adelay=100|100,apad[vo];[bed][vo]amix=inputs=2:duration=first:normalize=0[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    else:
        r = sh(f'ffmpeg -v error -i "{video}" -i "{norm}" -map 0:v -map 1:a -af apad -c:v copy -c:a aac -b:a 128k -t {vdur:.3f} "{outv}" -y')
    ok = os.path.exists(outv) and abs(dur(outv) - vdur) < 0.35
    row.update({"take_span": (round(a,2), round(b,2)), "take_dur": round(tdur,2), "atempo": round(at,3),
                "fitted_dur": round(fdur,2), "out": outv, "status": "OK" if ok else "MUX_FAIL",
                "err": (r.stderr or "")[-200:] if not ok else ""})
    manifest.append(row)

print(json.dumps(manifest, indent=1))
with open(f"{OUT}/manifest.json", "w") as f: json.dump(manifest, f, indent=1)

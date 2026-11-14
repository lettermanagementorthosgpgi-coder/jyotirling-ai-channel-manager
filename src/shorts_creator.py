"""Approval-first Shorts preparation from a user-authorized public vertical video."""
import argparse,json,os,re,shutil,subprocess,sys,zipfile
from pathlib import Path
from src.ai_providers import generate
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/"shorts_work"
def run(args,cwd=None):
 p=subprocess.run(args,cwd=str(cwd) if cwd else None,text=True,capture_output=True,timeout=1800)
 if p.returncode: raise RuntimeError((p.stderr or p.stdout)[-2000:])
 return p.stdout.strip()
def get_id(url):
 m=re.search(r"youtu\.be/([A-Za-z0-9_-]{11})|youtube\.com/(?:watch\?.*v=|shorts/|embed/)([A-Za-z0-9_-]{11})",url)
 if not m: raise ValueError("Valid public YouTube URL required.")
 return next(x for x in m.groups() if x)
def download(url):
 folder=WORK/"source"; folder.mkdir(parents=True)
 info=json.loads(run([sys.executable,"-m","yt_dlp","--no-playlist","--dump-single-json",url]))
 if info.get("is_live") or info.get("live_status") in ("is_live","is_upcoming"): raise ValueError("Completed videos only.")
 run([sys.executable,"-m","yt_dlp","--no-playlist","-f","bv*[height<=1080]+ba/b[height<=1080]","--merge-output-format","mp4","-o",str(folder/"source.%(ext)s"),url])
 files=[p for p in folder.glob("source.*") if p.suffix.lower() in (".mp4",".mkv",".webm",".mov")]
 if not files: raise RuntimeError("Downloader did not produce a video file.")
 src=files[0]
 if src.suffix.lower()!=".mp4":
  dst=folder/"source.mp4"; run(["ffmpeg","-y","-i",str(src),"-c","copy",str(dst)]); src=dst
 return src,info
def get_transcript(vid):
 from youtube_transcript_api import YouTubeTranscriptApi
 data=YouTubeTranscriptApi().fetch(vid,languages=["hi","sa","ur","bn","en"])
 rows=[]
 for x in getattr(data,"snippets",data):
  text=x.get("text","") if isinstance(x,dict) else getattr(x,"text","")
  start=x.get("start",0) if isinstance(x,dict) else getattr(x,"start",0)
  dur=x.get("duration",0) if isinstance(x,dict) else getattr(x,"duration",0)
  text=re.sub(r"\s+"," ",str(text)).strip()
  if text: rows.append({"start":float(start),"duration":float(dur),"text":text})
 if not rows: raise RuntimeError("No public timed transcript/captions found.")
 return rows
def select(rows,count,mn,mx):
 transcript="\n".join(f"[{x['start']:.2f}s] {x['text']}" for x in rows)[:65000]
 prompt=f"""Choose up to {count} distinct, complete and compelling moments from this Hindi devotional transcript. Each must be {mn}-{mx} seconds. Do not invent speech. Return ONLY JSON: {{"clips":[{{"start_seconds":1.0,"end_seconds":44.0,"hook":"Hindi hook","title":"Hindi title","description":"Hindi description","hashtags":["#..."],"tags":["..."],"reason":"Hindi reason"}}]}}. Use Hindi for all text fields. Timestamps are seconds from source start:\n{transcript}"""
 errors=[]
 for provider,key in (("openai","OPENAI_API_KEY"),("gemini","GEMINI_API_KEY")):
  if not os.getenv(key): continue
  try:
   raw,model=generate(provider,prompt)
   fence=chr(96)*3
   raw=raw.strip()
   if raw.startswith(fence): raw="\n".join(raw.splitlines()[1:-1])
   try: obj=json.loads(raw)
   except json.JSONDecodeError:
    a,b=raw.find("{"),raw.rfind("}"); obj=json.loads(raw[a:b+1])
   if isinstance(obj,dict) and isinstance(obj.get("clips"),list): return obj,provider,model
  except Exception as e: errors.append(provider+": "+str(e)[:250])
 raise RuntimeError("No AI provider returned valid clip selections. "+"; ".join(errors))
def timecode(t):
 ms=int(round(t*1000)); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000)
 return f"{h:02}:{m:02}:{s:02},{ms:03}"
def create(url,count,mn,mx):
 vid=get_id(url)
 if not 1<=count<=10 or not 15<=mn<=mx<=60: raise ValueError("Count 1–10; duration 15–60 seconds.")
 if WORK.exists(): shutil.rmtree(WORK)
 WORK.mkdir(parents=True)
 source,info=download(url); rows=get_transcript(vid)
 duration=float(info.get("duration") or run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(source)]))
 obj,provider,model=select(rows,count,mn,mx)
 clips=[]
 for x in obj["clips"]:
  try: start,end=float(x["start_seconds"]),float(x["end_seconds"])
  except (KeyError,TypeError,ValueError): continue
  if start<0 or end>duration or not mn<=end-start<=mx or not x.get("title") or not x.get("hook"): continue
  clips.append({"start_seconds":round(start,2),"end_seconds":round(end,2),"duration_seconds":round(end-start,2),
   "hook":str(x["hook"])[:180],"title":str(x["title"])[:100],"description":str(x.get("description",""))[:1600],
   "hashtags":x.get("hashtags",[])[:15],"tags":x.get("tags",[])[:30],"reason":str(x.get("reason",""))[:400]})
  if len(clips)>=count: break
 if not clips: raise RuntimeError("AI returned no valid timestamp selections.")
 out=WORK/"shorts"; out.mkdir()
 probe=json.loads(run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","json",str(source)]))
 stream=probe.get("streams",[{}])[0]
 if int(stream.get("height",0))<=int(stream.get("width",0)): raise ValueError("Source is not vertical; no crop/reframing was applied.")
 for i,c in enumerate(clips,1):
  srt=out/f"short_{i:02}.srt"; cues=[]
  for row in rows:
   a=max(c["start_seconds"],row["start"]); b=min(c["end_seconds"],row["start"]+max(row["duration"],1.2))
   if b>a: cues.append(f"{len(cues)+1}\n{timecode(a-c['start_seconds'])} --> {timecode(b-c['start_seconds'])}\n{row['text']}\n")
  if not cues: raise RuntimeError("No captions overlap selected clip.")
  srt.write_text("\n".join(cues),encoding="utf-8-sig")
  vf=f"subtitles={srt.name}:force_style='FontName=Noto Sans Devanagari,FontSize=20,Outline=2,Shadow=1,Alignment=2,MarginV=55'"
  run(["ffmpeg","-y","-ss",str(c["start_seconds"]),"-i",str(source),"-t",str(c["duration_seconds"]),"-vf",vf,
   "-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","128k","-movflags","+faststart",str(out/f"short_{i:02}.mp4")],cwd=out)
  c.update({"source_video_url":url,"review_status":"Pending Approval"})
 report={"status":"success","source_video_id":vid,"source_video_url":url,"source_title":info.get("title",""),
  "source_duration_seconds":duration,"framing":"Original vertical framing preserved","ai_provider":provider,"ai_model":model,
  "shorts":clips,"publishing":"Not uploaded; each Short requires separate user approval.",
  "rights_notice":"Use only videos you own or are authorized to download and edit."}
 (out/"shorts_metadata.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 with zipfile.ZipFile(WORK/"jyotirling_shorts_review.zip","w",zipfile.ZIP_DEFLATED) as z:
  for p in out.iterdir():
   if p.is_file(): z.write(p,p.name)
 return WORK/"jyotirling_shorts_review.zip"
def main():
 p=argparse.ArgumentParser(); p.add_argument("--url",required=True); p.add_argument("--count",type=int,default=5)
 p.add_argument("--min-seconds",type=int,default=30); p.add_argument("--max-seconds",type=int,default=60)
 a=p.parse_args(); print("SHORTS PACKAGE:",create(a.url,a.count,a.min_seconds,a.max_seconds))
 print("No YouTube upload, metadata change, or publication was performed.")
if __name__=="__main__": main()

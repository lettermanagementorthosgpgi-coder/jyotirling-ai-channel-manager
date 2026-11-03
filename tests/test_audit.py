"""Tests for supported Analytics activity and Reporting reach metrics."""
import unittest
from src.audit import (_analytics_by_video,_daily_analytics_by_video,_parse_reach_csv,
                       _unique_playlist_video_ids,_unique_video_details)

class Req:
    def __init__(self,data=None,error=None): self.data,self.error=data or {},error
    def execute(self):
        if self.error: raise self.error
        return self.data
class Reports:
    def __init__(self,pages,fail_at=None): self.pages,self.fail_at,self.calls=pages,fail_at,[]
    def query(self,**kw):
        self.calls.append(kw); n=len(self.calls)
        if n==self.fail_at: return Req(error=RuntimeError("simulated"))
        return Req(self.pages[n-1])
class Analytics:
    def __init__(self,reports): self.r=reports
    def reports(self): return self
    def query(self,**kw): return self.r.query(**kw)

class Tests(unittest.TestCase):
    def test_playlist_dedup(self):
        ids,dupes=_unique_playlist_video_ids([
            {"id":"p1","contentDetails":{"videoId":"A"}},
            {"id":"p2","contentDetails":{"videoId":"A"}}])
        self.assertEqual(ids,["A"]); self.assertEqual(dupes[0]["playlist_item_id"],"p2")
    def test_video_dedup(self):
        vids,dupes=_unique_video_details([{"id":"A"},{"id":"A"}])
        self.assertEqual(len(vids),1); self.assertEqual(dupes,["A"])
    def test_analytics_uses_supported_metrics_only(self):
        h=[{"name":"video"},{"name":"views"}]
        f=Reports([{"columnHeaders":h,"rows":[["A",5]]}])
        r=_analytics_by_video(Analytics(f),"2026-10-01","2026-11-01")
        self.assertTrue(r["available"]); self.assertEqual(r["by_video"]["A"]["views"],5)
        self.assertNotIn("impressions",f.calls[0]["metrics"])
        self.assertNotIn("impressionClickThroughRate",f.calls[0]["metrics"])
    def test_daily_analytics(self):
        h=[{"name":"day"},{"name":"views"}]
        f=Reports([{"columnHeaders":h,"rows":[["2026-11-01",9]]}])
        r=_daily_analytics_by_video(Analytics(f),"2026-10-01","2026-11-01")
        self.assertEqual(r["by_day"]["2026-11-01"]["views"],9)
        self.assertEqual(f.calls[0]["dimensions"],"day")
        self.assertEqual(r["scope"],"channel")
    def test_reach_csv(self):
        s=("date,channel_id,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
           "2026-10-31,C,A,1500,0.042\n2026-10-30,C,A,800,0.03\n")
        r=_parse_reach_csv(s,"2026-10-31")
        self.assertEqual(r["A"],[{"date":"2026-10-31","thumbnail_impressions":1500,
                                  "thumbnail_impressions_ctr":0.042}])
    def test_pagination(self):
        h=[{"name":"video"},{"name":"views"}]
        f=Reports([{"columnHeaders":h,"rows":[[f"v{i}",i] for i in range(200)]},
                   {"columnHeaders":h,"rows":[["v200",200]]}])
        r=_analytics_by_video(Analytics(f),"2026-10-01","2026-11-01")
        self.assertEqual(r["pages_fetched"],2); self.assertEqual(len(r["by_video"]),201)
    def test_failure_is_reported(self):
        f=Reports([{"columnHeaders":[{"name":"video"}],"rows":[]}],fail_at=1)
        r=_daily_analytics_by_video(Analytics(f),"2026-10-01","2026-11-01")
        self.assertFalse(r["available"])

if __name__ == "__main__": unittest.main()

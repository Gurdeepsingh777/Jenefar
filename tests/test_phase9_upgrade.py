from pathlib import Path

from jenefar.core.autonomous import AutonomousTaskEngine
from jenefar.memory.lifecycle import MemoryLifecycle
from jenefar.voice.interaction import VoiceInteractionController
from jenefar.avatar.viseme import text_to_visemes
from jenefar.vision.agent_loop import VisionAgentLoop
from jenefar.research.citations import Citation, attach_citations
from jenefar.security.engagement import SecurityEngagement
from jenefar.robotics.unified import UnifiedRobotController


def test_autonomous_loop_replans():
    calls=[]
    plans=[[{"id":"a"},{"id":"b"}],[{"id":"b"}]]
    def planner(_): return plans.pop(0)
    def execute(step): calls.append(step["id"]); return step["id"]
    def verify(step,result): return step["id"]!="a" or len(calls)>1
    run=AutonomousTaskEngine(planner=planner,executor=execute,verifier=verify).run("task")
    assert run.status=="completed" and run.replans==1


def test_memory_lifecycle_tracks_contradiction(tmp_path: Path):
    m=MemoryLifecycle(tmp_path/"m.db")
    m.remember("preference","Python",source="user")
    m.remember("preference","C++",source="user")
    facts=m.contradictions("preference")
    assert len(facts)==2 and any(f.active and f.value=="C++" for f in facts)


def test_voice_barge_in():
    c=VoiceInteractionController(); turn=c.begin_listening(); c.begin_speaking(); c.interrupt()
    assert c.should_stop_speech(turn) and c.snapshot()["listening"]


def test_viseme_generation():
    frames=text_to_visemes("hello")
    assert frames and frames[0].timestamp_ms==0


class FakeVision:
    def locate_and_click(self,q,verify=None): return {"verification":{"screen_changed":True},"query":q}
    def locate_and_type(self,q,text,verify=None): return {"verification":{"screen_changed":True},"query":q,"text":text}
    def analyze(self,q): return {"summary":q}


def test_vision_agent_loop():
    out=VisionAgentLoop(FakeVision()).run("task",[{"type":"click","query":"button"},{"type":"observe"}])
    assert len(out)==2 and all(item.verified for item in out)


def test_citations():
    out=attach_citations(["claim"],[Citation("source","title","page 2")])
    assert out[0]["citations"][0]["locator"]=="page 2"


def test_security_engagement(tmp_path: Path):
    e=SecurityEngagement(tmp_path/"eng.json"); e.start("lab",["lab.example.com"])
    e.add_finding("test","high","lab.example.com","evidence","fix")
    assert e.report()["findings"][0]["severity"]=="high"


def test_robot_unified():
    class A:
        def command(self,c,a): return (c,a)
    r=UnifiedRobotController(serial=A())
    assert r.command("stop")==("stop","")

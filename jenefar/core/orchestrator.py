from __future__ import annotations
from jenefar.agents.bugbounty.bugbounty import BugBountyAgent
from jenefar.agents.coding.python import PythonAgent
from jenefar.agents.cybersecurity.cyber import CybersecurityAgent
from jenefar.agents.research.research import ResearchAgent
from jenefar.agents.robotics.robotics import RoboticsAgent
from jenefar.core.config import load_config
from jenefar.core.planner import Planner
from jenefar.core.router import AgentRouter
from jenefar.core.session import Session
from jenefar.core.state import JenefarState
from jenefar.critic.verifier import Verifier
from jenefar.voice.wakeword import WakeWord

class JenefarOrchestrator:
    def __init__(self):
        self.config=load_config()
        self.state=JenefarState.SLEEPING
        self.session=Session()
        self.planner=Planner()
        self.router=AgentRouter([PythonAgent(),CybersecurityAgent(),BugBountyAgent(),RoboticsAgent(),ResearchAgent()])
        self.verifier=Verifier()
        self.wakeword=WakeWord(self.config.wake_phrases)

    def run(self):
        print(f"[JENEFAR] {self.config.name} is running.")
        print("[JENEFAR] Sleeping. Say/type 'Hi Jenefar' or 'Hello Jenefar' to wake me.")
        print("[JENEFAR] Type 'exit' to quit.")
        while True:
            try: raw=input("You > ").strip()
            except (EOFError,KeyboardInterrupt):
                print("\n[JENEFAR] Shutting down."); return
            if raw.lower()=="exit":
                print("[JENEFAR] Goodbye."); return
            if self.state==JenefarState.SLEEPING:
                if not self.wakeword.detect(raw):
                    print("[JENEFAR] (sleeping)"); continue
                self.state=JenefarState.AWAKE
                command=self.wakeword.remove_wake_phrase(raw)
                if not command:
                    print("[JENEFAR] Yes, I'm listening."); continue
                print(f"Jenefar > {self.handle(command)}"); continue
            if raw: print(f"Jenefar > {self.handle(raw)}")

    def handle(self,text:str)->str:
        self.state=JenefarState.THINKING
        self.session.add("user",text)
        plan=self.planner.plan(text)
        result=self.router.dispatch(text,metadata={
            "session_id":self.session.session_id,
            "intent":plan.intent,
            "planner_reason":plan.reason,
        })
        output=self.verifier.verify(text,result.content)
        self.session.add("assistant",output)
        self.state=JenefarState.SLEEPING if self.config.single_turn_sleep else JenefarState.AWAKE
        return output

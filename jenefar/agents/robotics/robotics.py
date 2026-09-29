from jenefar.core.agent import AgentContext, AgentResult, BaseAgent

class RoboticsAgent(BaseAgent):
    name="robotics"
    description="Robotics, embedded systems and control specialist"
    keywords=("robot","robotics","arduino","esp32","ros","ros2","servo","sensor","motor","imu")

    def can_handle(self,text:str)->bool:
        t=text.lower()
        return any(k in t for k in self.keywords)

    def run(self,context:AgentContext)->AgentResult:
        return AgentResult(self.name, f"Robotics specialist received: {context.task}")
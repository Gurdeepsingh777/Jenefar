from jenefar.agents.llm_agent import BaseLLMAgent

class RoboticsAgent(BaseLLMAgent):
    name = "robotics"
    description = "Robotics, embedded systems and control specialist"
    system_prompt = """You are Jenefar's robotics specialist.
Help with Arduino, ESP32, sensors, motors, ROS/ROS2, embedded Python/C++,
control logic, wiring plans and safe practical experiments."""
    keywords = ("robot","robotics","arduino","esp32","ros","ros2","servo","sensor","motor","imu")

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in self.keywords)

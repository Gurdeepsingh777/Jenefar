from __future__ import annotations
class UnifiedRobotController:
    """Common bounded interface over serial, MQTT and ROS2 adapters."""
    def __init__(self,*,serial=None,mqtt=None,ros2=None): self.serial=serial; self.mqtt=mqtt; self.ros2=ros2
    def status(self): return {"serial":self.serial is not None,"mqtt":self.mqtt is not None,"ros2":self.ros2 is not None}
    def command(self,command,*,transport="auto",argument=""):
        selected=transport
        if selected=="auto": selected="serial" if self.serial is not None else "mqtt" if self.mqtt is not None else "ros2"
        adapter={"serial":self.serial,"mqtt":self.mqtt,"ros2":self.ros2}.get(selected)
        if adapter is None: raise RuntimeError(f"Robot transport '{selected}' is unavailable.")
        if selected=="serial": return adapter.command(command,argument)
        if selected=="mqtt": return adapter.publish_command(command if not argument else f"{command}:{argument}")
        raise ValueError("ROS2 unified command requires an explicit adapter-specific message.")

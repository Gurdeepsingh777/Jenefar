from dataclasses import dataclass
from typing import Callable

@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str,ToolSpec] = {}

    def register(self,spec:ToolSpec)->None:
        self._tools[spec.name]=spec

    def get(self,name:str)->ToolSpec:
        return self._tools[name]

    def list(self)->list[ToolSpec]:
        return list(self._tools.values())
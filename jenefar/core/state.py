from enum import Enum


class JenefarState(str, Enum):
    SLEEPING = "sleeping"
    AWAKE = "awake"
    THINKING = "thinking"
    RESPONDING = "responding"

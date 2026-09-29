from enum import Enum

class JenefarState(str, Enum):
    SLEEPING = "sleeping"
    AWAKE = "awake"
    THINKING = "thinking"
    WAITING_APPROVAL = "waiting_approval"
    RESPONDING = "responding"

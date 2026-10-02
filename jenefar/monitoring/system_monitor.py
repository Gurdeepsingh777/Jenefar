from __future__ import annotations

import psutil
import time


def get_cpu():
    return round(
        psutil.cpu_percent(interval=0.2),
        1
    )


def get_ram():

    memory = psutil.virtual_memory()

    return {
        "percent": round(memory.percent,1),
        "used_gb": round(
            memory.used /1024**3,
            2
        ),
        "total_gb": round(
            memory.total /1024**3,
            2
        )
    }



def get_gpu():

    result = {
        "available":False,
        "usage":0,
        "memory":0,
    }


    try:

        from pynvml import (
            nvmlInit,
            nvmlDeviceGetHandleByIndex,
            nvmlDeviceGetUtilizationRates,
            nvmlDeviceGetMemoryInfo
        )


        nvmlInit()

        handle = nvmlDeviceGetHandleByIndex(0)


        util = nvmlDeviceGetUtilizationRates(
            handle
        )

        mem = nvmlDeviceGetMemoryInfo(
            handle
        )


        result.update(
            {
                "available":True,
                "usage":round(util.gpu,1),
                "memory_used_gb":
                    round(
                    mem.used/1024**3,
                    2
                    ),
                "memory_total_gb":
                    round(
                    mem.total/1024**3,
                    2
                    )
            }
        )


    except Exception:

        pass


    return result




def get_system_stats():

    return {

        "timestamp":time.time(),

        "cpu":
            get_cpu(),

        "ram":
            get_ram(),

        "gpu":
            get_gpu()

    }

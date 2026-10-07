from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class VisemeFrame:
    timestamp_ms:int; viseme:str; weight:float
GROUPS={"a":"aa","e":"ee","i":"ee","o":"oh","u":"ou","m":"closed","b":"closed","p":"closed","f":"fv","v":"fv","s":"s","z":"s"}
def text_to_visemes(text:str,*,ms_per_char:int=55)->list[VisemeFrame]:
    out=[]; t=0
    for ch in str(text).lower():
        if ch.isspace(): t+=ms_per_char; continue
        out.append(VisemeFrame(t,GROUPS.get(ch,"neutral"),.85)); t+=ms_per_char
    return out

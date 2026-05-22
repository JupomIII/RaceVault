from __future__ import annotations
import re
from typing import Optional, Dict


def parse_time_to_seconds(time_str: str) -> Optional[float]:
    if not time_str:
        return None
    try:
        parts = str(time_str).strip().split(":")
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        if len(parts) == 3:
            h, m, s = parts
            return int(h)*3600 + int(m)*60 + float(s)
    except:
        return None
    return None


def parse_event_details(event_name: str) -> Dict[str, str]:
    name = event_name.upper()
    boat = None
    distance = None
    category = None

    for bt in ["K1","K2","K4","C1","C2","C4"]:
        if bt in name:
            boat = bt
            break

    return {"boat_type": boat, "distance": distance, "category": category}

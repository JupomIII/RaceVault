from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import os


@dataclass
class Config:
    input_dir: str = "input"
    output_dir: str = "output"
    supported_extensions: List[str] = field(default_factory=lambda: [".pdf"])
    known_athletes_file: Optional[str] = None
    min_confidence_threshold: float = 0.5
    max_workers: int = 1

    def ensure_dirs(self) -> None:
        for d in [self.input_dir, self.output_dir]:
            os.makedirs(d, exist_ok=True)
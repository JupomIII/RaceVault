from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import os


@dataclass
class Config:
    input_dir: str = "input"
    output_dir: str = "output"
    failed_dir: str = "failed"
    parsed_dir: str = "parsed"
    debug_dir: str = "debug"
    logs_dir: str = "logs"
    supported_extensions: List[str] = field(default_factory=lambda: [".pdf"])
    known_athletes_file: Optional[str] = None
    min_confidence_threshold: float = 0.5
    max_workers: int = 1

    def ensure_dirs(self) -> None:
        for d in [self.input_dir, self.output_dir, self.failed_dir, self.parsed_dir, self.debug_dir, self.logs_dir]:
            os.makedirs(d, exist_ok=True)
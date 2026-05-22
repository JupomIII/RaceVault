from __future__ import annotations
from typing import Dict, Type

from .base_parser import BaseParser
from .layout_a import LayoutAParser
from .layout_b import LayoutBParser
from .layout_c import LayoutCParser
from .layout_d import LayoutDParser

PARSER_REGISTRY: Dict[str, Type[BaseParser]] = {
    "layout_a": LayoutAParser,
    "layout_b": LayoutBParser,
    "layout_c": LayoutCParser,
    "layout_d": LayoutDParser,
}


def get_parser(layout_type: str) -> BaseParser:
    parser_cls = PARSER_REGISTRY.get(layout_type)
    if not parser_cls:
        raise ValueError(f"No parser registered for layout: {layout_type}")
    return parser_cls()
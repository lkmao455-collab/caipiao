"""八卦占卜模块.

提供八卦基础、六十四卦、起卦引擎等功能。
"""

from .bagua import BAGUA, get_trigram_by_name, get_trigram_by_number, get_trigram_by_yao
from .yijing import HEXAGRAMS, get_hexagram, get_hexagram_by_name
from .divination_engine import (
    time_divination,
    random_divination,
    manual_divination,
    DivinationResult,
)

__all__ = [
    "BAGUA",
    "get_trigram_by_name",
    "get_trigram_by_number",
    "get_trigram_by_yao",
    "HEXAGRAMS",
    "get_hexagram",
    "get_hexagram_by_name",
    "time_divination",
    "random_divination",
    "manual_divination",
    "DivinationResult",
]

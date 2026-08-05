"""八卦占卜模块.

提供八卦基础、六十四卦、起卦引擎等功能。
"""

from .bagua import BAGUA, get_trigram_by_name, get_trigram_by_number, get_trigram_by_yao
from .divination_engine import (
    DivinationResult,
    batch_time_divination,
    manual_divination,
    random_divination,
    time_divination,
)
from .yijing import HEXAGRAMS, get_hexagram, get_hexagram_by_name

__all__ = [
    "BAGUA",
    "HEXAGRAMS",
    "DivinationResult",
    "batch_time_divination",
    "get_hexagram",
    "get_hexagram_by_name",
    "get_trigram_by_name",
    "get_trigram_by_number",
    "get_trigram_by_yao",
    "manual_divination",
    "random_divination",
    "time_divination",
]

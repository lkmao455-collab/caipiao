"""八卦占卜策略.

基于易经卦象与天干地支的号码生成策略，可应用于所有彩种。
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...profile import LotteryProfile, get_profile
from ...strategy import GenerationStrategy, StrategyMetadata
from ...ticket import Ticket
from ....calendar.heavenly_earthly import (
    get_ganzhi_year,
    get_ganzhi_month,
    get_ganzhi_day,
    get_ganzhi_hour,
    get_shichen,
    HEAVENLY_STEMS,
    EARTHLY_BRANCHES,
)
from ....divination.bagua import get_yao_from_number, get_trigram_by_yao
from ....divination.yijing import get_hexagram, get_changed_hexagram, HEXAGRAMS
from ....divination.divination_engine import time_divination, random_divination


class BaguaStrategy(GenerationStrategy):
    """基于八卦卦象的号码生成策略.

    原理：
    1. 根据当前时间或随机数起卦
    2. 提取卦象数字信息
    3. 通过数学映射生成号码
    4. 结合天干地支五行属性调整

    特点：
    - 支持所有彩种
    - 每次生成基于不同时间点，自然产生变化
    - 可选固定种子保持可重复性
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="bagua",
            name="八卦占卜",
            description="基于易经卦象与天干地支生成号码，融合传统智慧。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "method": {
                "type": "choice",
                "label": "起卦方式",
                "default": "time",
                "choices": [
                    ("time", "时间起卦（梅花易数）"),
                    ("random", "随机起卦"),
                ],
                "tooltip": "时间起卦：依当前年、月、日、时成卦；随机起卦：系统随机掷出六爻。",
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
                "tooltip": "固定随机种子可使每次生成的号码相同，便于重复实验。留空则完全随机。",
            },
            "use_ganzhi": {
                "type": "bool",
                "label": "结合天干地支",
                "default": True,
                "tooltip": "是否结合当前日期的天干地支五行属性调整号码生成。",
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        method = options.get("method", "time")
        if method not in ("time", "random"):
            raise ValueError(f"不支持的起卦方式: {method}")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)

        method = options.get("method", "time")
        seed = options.get("seed")
        use_ganzhi = options.get("use_ganzhi", True)

        # 创建随机数生成器
        rng = random.Random(seed)

        # 生成号码
        tickets: List[Ticket] = []
        for _ in range(count):
            # 起卦
            if method == "time":
                result = time_divination()
            else:
                result = random_divination(seed=seed)

            # 获取当前彩种信息（通过参数传递）
            # 由于策略需要知道目标彩种，我们使用一个默认的映射
            # 实际使用时，UI会传递profile_key
            profile_key = options.get("profile_key", "ssq")
            profile = get_profile(profile_key)

            # 基于卦象生成号码
            numbers = self._generate_numbers_from_hexagram(
                result, profile, use_ganzhi, rng
            )

            # 构建投注单
            ticket = self._build_ticket(profile, numbers, result, options)
            tickets.append(ticket)

        return tickets

    def _generate_numbers_from_hexagram(
        self,
        result,
        profile: LotteryProfile,
        use_ganzhi: bool,
        rng: random.Random,
    ) -> Dict[str, List[int]]:
        """从卦象生成号码."""
        numbers = {}

        # 获取卦象信息
        hexagram = result.hexagram
        yao = result.yao
        upper = result.upper_trigram
        lower = result.lower_trigram

        # 先天八卦数
        xiantian_num = {"乾": 1, "兑": 2, "离": 3, "震": 4, "巽": 5, "坎": 6, "艮": 7, "坤": 8}

        # 计算基础数字
        upper_num = xiantian_num.get(upper.name, 1)
        lower_num = xiantian_num.get(lower.name, 1)

        # 爻象数字
        yao_numbers = []
        for y in yao:
            if y in (1, 2):
                yao_numbers.append(1)
            else:
                yao_numbers.append(0)

        # 基于卦象的数学运算生成数字池
        base_numbers = set()

        # 上下卦数字组合
        base_numbers.add((upper_num + lower_num) % 10)
        base_numbers.add((upper_num * lower_num) % 10)
        base_numbers.add(abs(upper_num - lower_num))
        base_numbers.add(upper_num)
        base_numbers.add(lower_num)

        # 爻象组合
        yao_sum = sum(yao_numbers)
        base_numbers.add(yao_sum % 10)
        base_numbers.add((yao_sum * 3) % 10)

        # 动爻位置
        for i, y in enumerate(yao):
            if y in (2, 3):
                base_numbers.add(i + 1)
                base_numbers.add((i + 1) * 2 % 10)

        # 天干地支影响
        if use_ganzhi:
            now = datetime.now()
            day_gz = get_ganzhi_day(now.year, now.month, now.day)
            day_stem = day_gz[0]
            day_branch = day_gz[1]

            stem_index = HEAVENLY_STEMS.index(day_stem)
            branch_index = EARTHLY_BRANCHES.index(day_branch)

            base_numbers.add(stem_index % 10)
            base_numbers.add(branch_index % 10)
            base_numbers.add((stem_index + branch_index) % 10)

        # 为每个号码组生成号码
        for group in profile.pick_groups:
            lo = group.lo
            hi = group.hi
            pool_size = hi - lo + 1
            count = group.count

            # 使用不同的算法为每个组生成号码
            group_numbers = set()

            # 从基础数字映射
            for n in base_numbers:
                mapped = (n * 7 + upper_num * 3 + lower_num * 5) % pool_size + lo
                if lo <= mapped <= hi:
                    group_numbers.add(mapped)

            # 添加随机补充
            while len(group_numbers) < count:
                if group.positional:
                    # 按位组：每位独立
                    n = rng.randint(lo, hi)
                    group_numbers.add(n)
                else:
                    n = rng.randint(lo, hi)
                    if not group.allow_repeat:
                        if n not in group_numbers:
                            group_numbers.add(n)
                    else:
                        group_numbers.add(n)

            # 截取需要的数量
            sorted_nums = sorted(group_numbers)[:count]
            numbers[group.key] = sorted_nums

        return numbers

    def _build_ticket(
        self,
        profile: LotteryProfile,
        numbers: Dict[str, List[int]],
        result,
        options: Dict[str, Any],
    ) -> Ticket:
        """构建投注单."""
        # 生成说明文本
        basis = (
            f"八卦占卜策略：{result.method}，"
            f"本卦{result.hexagram.full_name}"
        )
        if result.changed_hexagram:
            basis += f"→{result.changed_hexagram.full_name}"
        basis += f"。{result.hexagram.description}"

        # 详情信息
        details = {
            "hexagram": result.hexagram.full_name,
            "method": result.method,
            "time": result.time_str,
            "upper_trigram": result.upper_trigram.name,
            "lower_trigram": result.lower_trigram.name,
            "nature": result.hexagram.nature,
            "description": result.hexagram.description,
        }

        return Ticket(
            profile=profile,
            groups=numbers,
            strategy_name=self.metadata.name,
            basis=basis,
            details=details,
        )

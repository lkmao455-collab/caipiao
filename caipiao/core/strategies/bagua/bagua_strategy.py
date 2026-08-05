"""八卦占卜策略.

基于易经卦象与天干地支的号码生成策略，可应用于所有彩种。
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from ....calendar.almanac import get_lucky_hours
from ....calendar.heavenly_earthly import (
    EARTHLY_BRANCHES,
    HEAVENLY_STEMS,
    get_ganzhi_day,
)
from ....divination.divination_engine import (
    batch_time_divination,
    random_divination,
    time_divination,
)
from ...profile import LotteryProfile, get_profile
from ...strategy import GenerationStrategy, StrategyMetadata
from ...ticket import Ticket


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

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "method": {
                "type": "choice",
                "label": "起卦方式",
                "default": "time",
                "choices": [
                    ("time", "时间起卦（梅花易数）"),
                    ("time_batch", "时间起卦（批量，按时辰）"),
                    ("time_lucky", "时间起卦（自动吉时）"),
                    ("random", "随机起卦"),
                ],
                "tooltip": "时间起卦：依当前年、月、日、时成卦；批量按时辰：每个选中时辰生成一卦；自动吉时：根据日干支自动选择吉时；随机起卦：系统随机掷出六爻。",
            },
            "time_mode": {
                "type": "choice",
                "label": "时间选择模式",
                "default": "shichen",
                "choices": [
                    ("hour", "按小时选择（24小时）"),
                    ("shichen", "按时辰选择（12时辰）"),
                ],
                "tooltip": "选择小时模式或时辰模式来指定起卦时间。",
            },
            "selected_hours": {
                "type": "str",
                "label": "选择的小时",
                "default": "",
                "tooltip": "逗号分隔的小时列表（24小时制），如 0,1,2 或 23,0,1。仅在批量时间起卦时生效。",
            },
            "selected_shichen": {
                "type": "str",
                "label": "选择的时辰",
                "default": "",
                "tooltip": "逗号分隔的时辰地支，如 子,丑,寅。仅在批量时间起卦按时辰模式时生效。",
            },
            "lucky_min_score": {
                "type": "int",
                "label": "吉时最低分数",
                "default": 60,
                "min": 50,
                "max": 100,
                "tooltip": "自动吉时模式下，低于此分数的时辰不选。分数越高，选择的时辰越吉利。",
            },
            "lucky_max_count": {
                "type": "int",
                "label": "最多选择吉时数",
                "default": 6,
                "min": 1,
                "max": 12,
                "tooltip": "自动吉时模式下，最多选择几个吉时。",
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

    def validate_options(self, options: dict[str, Any]) -> None:
        method = options.get("method", "time")
        if method not in ("time", "time_batch", "time_lucky", "random"):
            raise ValueError(f"不支持的起卦方式: {method}")

    def _parse_selected_hours(self, options: dict[str, Any]) -> list[int]:
        """解析选中的小时列表."""
        time_mode = options.get("time_mode", "shichen")

        if time_mode == "hour":
            selected_str = options.get("selected_hours", "")
            if not selected_str:
                return []
            return [int(h.strip()) for h in selected_str.split(",") if h.strip()]
        else:
            # 时辰模式
            selected_str = options.get("selected_shichen", "")
            if not selected_str:
                return []

            shichen_hours = {
                "子": [23, 0], "丑": [1, 2], "寅": [3, 4], "卯": [5, 6],
                "辰": [7, 8], "巳": [9, 10], "午": [11, 12], "未": [13, 14],
                "申": [15, 16], "酉": [17, 18], "戌": [19, 20], "亥": [21, 22],
            }

            hours = []
            for branch in selected_str.split(","):
                branch = branch.strip()
                if branch in shichen_hours:
                    hours.extend(shichen_hours[branch])
            return sorted(set(hours))

    def _get_lucky_hours(self, options: dict[str, Any]) -> list[int]:
        """获取自动吉时的小时列表."""
        now = datetime.now(timezone.utc).astimezone()
        min_score = options.get("lucky_min_score", 60)
        max_count = options.get("lucky_max_count", 6)

        lucky_info = get_lucky_hours(
            year=now.year, month=now.month, day=now.day,
            min_score=min_score
        )

        # 取前max_count个吉时
        lucky_hours = []
        for item in lucky_info[:max_count]:
            lucky_hours.extend(item["hours"])

        return sorted(set(lucky_hours))

    def generate(
        self, count: int = 1, options: dict[str, Any] | None = None
    ) -> list[Ticket]:
        """生成号码.

        对于时间起卦（time_batch/time_lucky），注数由选中的时间数量决定，
        count参数被忽略。对于随机起卦（random），使用count参数。
        """
        options = options or {}
        self.validate_options(options)

        method = options.get("method", "time")
        seed = options.get("seed")
        use_ganzhi = options.get("use_ganzhi", True)

        # 创建随机数生成器
        rng = random.Random(seed)

        # 生成号码
        tickets: list[Ticket] = []

        if method in ("time_batch", "time_lucky"):
            # 批量时间起卦：根据选中的小时/时辰生成，注数=选中时间数量
            if method == "time_batch":
                selected_hours = self._parse_selected_hours(options)
            else:
                # 自动吉时模式
                selected_hours = self._get_lucky_hours(options)

            if not selected_hours:
                # 没有选中时间，使用当前小时
                now = datetime.now(timezone.utc).astimezone()
                selected_hours = [now.hour]

            now = datetime.now(timezone.utc).astimezone()
            results = batch_time_divination(
                year=now.year, month=now.month, day=now.day,
                hours=selected_hours
            )

            profile_key = options.get("profile_key", "ssq")
            profile = get_profile(profile_key)

            for result in results:
                numbers = self._generate_numbers_from_hexagram(
                    result, profile, use_ganzhi, rng
                )
                ticket = self._build_ticket(profile, numbers, result, options)
                tickets.append(ticket)

        else:
            # 时间起卦（单次）或随机起卦
            for i in range(count):
                if method == "time":
                    now = datetime.now(timezone.utc).astimezone()
                    result = time_divination(hour=(now.hour + i) % 24)
                else:
                    effective_seed = (seed + i) if seed is not None else None
                    result = random_divination(seed=effective_seed)

                profile_key = options.get("profile_key", "ssq")
                profile = get_profile(profile_key)

                numbers = self._generate_numbers_from_hexagram(
                    result, profile, use_ganzhi, rng
                )

                ticket = self._build_ticket(profile, numbers, result, options)
                tickets.append(ticket)

        return tickets

    def _generate_numbers_from_hexagram(
        self,
        result,
        profile: LotteryProfile,
        use_ganzhi: bool,
        rng: random.Random,
    ) -> dict[str, list[int]]:
        """从卦象生成号码."""
        numbers = {}

        # 获取卦象信息
        _hexagram = result.hexagram
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
            now = datetime.now(timezone.utc).astimezone()
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
            # 选号个数：固定彩种用开奖个数 group.count；
            # 可变选号彩种（如快乐8）玩家选 1-10 个，而非开奖的 20 个。
            if group.variable_pick:
                count = rng.randint(group.effective_pick_min, group.effective_pick_max)
            else:
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
        numbers: dict[str, list[int]],
        result,
        options: dict[str, Any],
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

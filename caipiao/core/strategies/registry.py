"""策略注册表：按彩种管理所有生成策略类。"""

from __future__ import annotations

from typing import Dict, List, Type

from .lotteries.ssq import balanced as ssq_balanced
from .lotteries.ssq import smart_hot_cold as ssq_smart_hot_cold
from .lotteries.fc3d import balanced as fc3d_balanced
from .lotteries.fc3d import smart_hot_cold as fc3d_smart_hot_cold
from .lotteries.dlt import balanced as dlt_balanced
from .lotteries.dlt import smart_hot_cold as dlt_smart_hot_cold
from .lotteries.kl8 import balanced as kl8_balanced
from .lotteries.kl8 import smart_hot_cold as kl8_smart_hot_cold
from .lotteries.pl3 import balanced as pl3_balanced
from .lotteries.pl3 import smart_hot_cold as pl3_smart_hot_cold
from .lotteries.pl5 import balanced as pl5_balanced
from .lotteries.pl5 import smart_hot_cold as pl5_smart_hot_cold
from .lotteries.qlc import balanced as qlc_balanced
from .lotteries.qlc import smart_hot_cold as qlc_smart_hot_cold
from .lotteries.qxc import balanced as qxc_balanced
from .lotteries.qxc import smart_hot_cold as qxc_smart_hot_cold
from ..strategy import GenerationStrategy

STRATEGY_REGISTRY: Dict[str, List[Type[GenerationStrategy]]] = {
    "ssq": [
        ssq_smart_hot_cold.SSQSmartHotColdStrategy,
        ssq_balanced.SSQBalancedStrategy,
    ],
    "3d": [
        fc3d_smart_hot_cold.FC3DSmartHotColdStrategy,
        fc3d_balanced.FC3DBalancedStrategy,
    ],
    "qlc": [
        qlc_smart_hot_cold.QLCSmartHotColdStrategy,
        qlc_balanced.QLCBalancedStrategy,
    ],
    "kl8": [
        kl8_smart_hot_cold.KL8SmartHotColdStrategy,
        kl8_balanced.KL8BalancedStrategy,
    ],
    "dlt": [
        dlt_smart_hot_cold.DLTSmartHotColdStrategy,
        dlt_balanced.DLTBalancedStrategy,
    ],
    "pl3": [
        pl3_smart_hot_cold.PL3SmartHotColdStrategy,
        pl3_balanced.PL3BalancedStrategy,
    ],
    "pl5": [
        pl5_smart_hot_cold.PL5SmartHotColdStrategy,
        pl5_balanced.PL5BalancedStrategy,
    ],
    "qxc": [
        qxc_smart_hot_cold.QXCSmartHotColdStrategy,
        qxc_balanced.QXCBalancedStrategy,
    ],
}

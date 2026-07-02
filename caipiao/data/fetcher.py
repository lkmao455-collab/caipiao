"""历史数据获取器（多彩种统一）.

``LotteryDataFetcher`` 现在按彩种档案（LotteryProfile）解析数据，
复用统一的网络请求重试逻辑。

数据源统一采用 17500.cn 的纯文本 ``*_asc.txt`` 文件，格式固定：
    期号 日期 号码... 统计尾列...
每种彩种只需实现行解析器（``_parse_*``）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, List, Optional

import requests

from ..core.profile import LotteryProfile
from .models import DrawRecord

logger = logging.getLogger(__name__)


class LotteryDataFetcher:
    """按指定彩种从网上抓取历史开奖数据."""

    def __init__(
        self,
        profile: LotteryProfile | None = None,
        timeout: int = 60,
        max_retries: int = 3,
    ) -> None:
        from ..core.profile import SSQ

        self.profile = profile or SSQ
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        self._parser: Callable[[List[str], str], Optional[DrawRecord]] = {
            "ssq": self._parse_ssq,
            "3d": self._parse_3d,
            "qlc": self._parse_qlc,
            "kl8": self._parse_kl8,
        }.get(self.profile.parser_key, self._parse_ssq)

    # ------------------------------------------------------------------ #
    # 行解析器
    # ------------------------------------------------------------------ #
    def _parse_ssq(self, parts: List[str], line: str) -> Optional[DrawRecord]:
        if len(parts) < 9:
            return None
        issue = parts[0]
        draw_date = datetime.strptime(parts[1], "%Y-%m-%d")
        red_balls = sorted(int(parts[i]) for i in range(2, 8))
        blue_ball = int(parts[8])
        return DrawRecord(
            issue=issue,
            draw_date=draw_date,
            red_balls=red_balls,
            blue_ball=blue_ball,
        )

    def _parse_3d(self, parts: List[str], line: str) -> Optional[DrawRecord]:
        if len(parts) < 5:
            return None
        issue = parts[0]
        draw_date = datetime.strptime(parts[1], "%Y-%m-%d")
        digits = [int(parts[i]) for i in range(2, 5)]
        return DrawRecord(
            issue=issue,
            draw_date=draw_date,
            profile="3d",
            groups={"pos": digits},
        )

    def _parse_qlc(self, parts: List[str], line: str) -> Optional[DrawRecord]:
        if len(parts) < 10:
            return None
        issue = parts[0]
        draw_date = datetime.strptime(parts[1], "%Y-%m-%d")
        basic = sorted(int(parts[i]) for i in range(2, 9))
        special = [int(parts[9])]
        return DrawRecord(
            issue=issue,
            draw_date=draw_date,
            profile="qlc",
            groups={"basic": basic, "special": special},
        )

    def _parse_kl8(self, parts: List[str], line: str) -> Optional[DrawRecord]:
        if len(parts) < 22:
            return None
        issue = parts[0]
        draw_date = datetime.strptime(parts[1], "%Y-%m-%d")
        nums = sorted(int(parts[i]) for i in range(2, 22))
        return DrawRecord(
            issue=issue,
            draw_date=draw_date,
            profile="kl8",
            groups={"main": nums},
        )

    # ------------------------------------------------------------------ #
    # 网络请求
    # ------------------------------------------------------------------ #
    def _get_with_retry(self, url: str):
        import time

        last_exc = None
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    url, headers=self.headers, timeout=self.timeout
                )
                if response.status_code == 200:
                    return response
                last_exc = Exception(f"HTTP {response.status_code}")
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)
        raise last_exc or RuntimeError("请求失败")

    # ------------------------------------------------------------------ #
    # 编码处理
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode_response(response) -> str:
        """尝试多种编码解码响应体，避免中文乱码或解码异常。"""
        content = response.content
        for enc in (response.apparent_encoding, "utf-8", "gb18030", "gbk"):
            if not enc:
                continue
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------ #
    # 公共接口
    # ------------------------------------------------------------------ #
    def fetch_all(self) -> List[DrawRecord]:
        """获取全部历史记录."""
        logger.info("Fetching data from %s", self.profile.data_url)
        response = self._get_with_retry(self.profile.data_url)
        text = self._decode_response(response)

        records: List[DrawRecord] = []
        for line in text.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) < 3:
                continue
            try:
                rec = self._parser(parts, line)
                if rec is not None:
                    records.append(rec)
            except (ValueError, IndexError) as exc:
                logger.debug("解析行失败: %s (%s)", parts, exc)
                continue

        if not records:
            raise ValueError("未解析到任何记录")
        logger.info("成功获取 %d 条 %s 记录", len(records), self.profile.name)
        return records

    def fetch_latest(self) -> Optional[DrawRecord]:
        """获取最新一期开奖记录."""
        try:
            response = self._get_with_retry(self.profile.data_url)
            text = self._decode_response(response)
            lines = text.strip().split("\n")
            if lines:
                parts = lines[-1].strip().split()
                if len(parts) >= 3:
                    return self._parser(parts, lines[-1])
        except Exception as exc:  # noqa: BLE001
            logger.debug("获取 %s 最新一期失败: %s", self.profile.name, exc)
        return None

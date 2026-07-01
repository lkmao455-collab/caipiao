"""历史数据获取器."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from .models import DrawRecord

logger = logging.getLogger(__name__)


class LotteryDataFetcher:
    """从网上抓取双色球历史开奖数据."""

    # getssq 使用的数据源：17500.cn 纯文本全量数据
    GETSSQ_URL = "http://data.17500.cn/ssq_asc.txt"
    # 500.com 全量数据（HTML 表格）
    URL_500 = (
        "https://datachart.500.com/ssq/history/inc/history.php"
        "?start=00001&end=99999"
    )
    # 中彩网分页数据
    URL_ZHCW_TEMPLATE = "https://kaijiang.zhcw.com/zhcw/html/ssq/list_{page}.html"

    def __init__(self, timeout: int = 60, max_retries: int = 3) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def fetch_all(self) -> List[DrawRecord]:
        """按优先级尝试多个数据源获取全部历史记录."""
        sources = [
            ("getssq/17500.cn", self._fetch_from_getssq),
            ("500.com", self._fetch_from_500),
            ("中彩网", self._fetch_from_zhcw),
        ]
        for name, func in sources:
            try:
                logger.info("尝试从 %s 获取数据", name)
                return func()
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s 获取失败: %s", name, exc)
                continue
        raise RuntimeError("所有数据源均获取失败")

    def _fetch_from_getssq(self) -> List[DrawRecord]:
        """从 getssq 使用的 17500.cn 数据源获取完整历史数据.

        数据格式为每行一条记录，空格分隔：
        期号 日期 红球1-6 蓝球 出球顺序1-6 投注额 奖池 各奖项注数/金额...
        """
        logger.info("Fetching data from %s", self.GETSSQ_URL)
        response = self._get_with_retry(self.GETSSQ_URL)
        response.encoding = "utf-8"
        response.raise_for_status()

        records: List[DrawRecord] = []
        for line in response.text.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) < 9:
                continue
            try:
                issue = parts[0]
                draw_date = datetime.strptime(parts[1], "%Y-%m-%d")
                red_balls = sorted(int(parts[i]) for i in range(2, 8))
                blue_ball = int(parts[8])
                records.append(
                    DrawRecord(
                        issue=issue,
                        draw_date=draw_date,
                        red_balls=red_balls,
                        blue_ball=blue_ball,
                    )
                )
            except (ValueError, IndexError) as exc:
                logger.debug("解析行失败: %s (%s)", parts, exc)
                continue

        if not records:
            raise ValueError("未解析到任何记录")
        logger.info("成功获取 %d 条记录", len(records))
        return records

    def _fetch_from_500(self) -> List[DrawRecord]:
        """从 500.com 获取完整历史数据."""
        logger.info("Fetching data from %s", self.URL_500)
        response = self._get_with_retry(self.URL_500)
        # gb18030 是 gb2312 的超集，能更好地处理生僻字
        response.encoding = "gb18030"
        response.raise_for_status()

        # 使用 html.parser 避免 lxml/libxml2 的编码警告
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", id="tablelist")
        if table is None:
            raise ValueError("未找到数据表格")

        tbody = table.find("tbody", id="tdata") or table
        rows = tbody.find_all("tr")
        records: List[DrawRecord] = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 16:
                continue
            texts = [c.get_text(strip=True) for c in cols]
            try:
                issue = texts[0]
                red_balls = sorted(int(texts[i]) for i in range(1, 7))
                blue_ball = int(texts[7])
                draw_date = datetime.strptime(texts[15], "%Y-%m-%d")
                records.append(
                    DrawRecord(
                        issue=issue,
                        draw_date=draw_date,
                        red_balls=red_balls,
                        blue_ball=blue_ball,
                    )
                )
            except (ValueError, IndexError) as exc:
                logger.debug("解析行失败: %s (%s)", texts, exc)
                continue

        if not records:
            raise ValueError("未解析到任何记录")
        logger.info("成功获取 %d 条记录", len(records))
        return records

    def _get_with_retry(self, url: str):
        """带重试的 GET 请求."""
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

    def _fetch_from_zhcw(self, max_pages: int = 200) -> List[DrawRecord]:
        """从中彩网分页获取历史数据."""
        records: List[DrawRecord] = []
        for page in range(1, max_pages + 1):
            url = self.URL_ZHCW_TEMPLATE.format(page=page)
            logger.info("Fetching page %d from %s", page, url)
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.encoding = "utf-8"
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", class_="wqhgt")
            if table is None:
                break

            rows = table.find_all("tr")[2:]  # 跳过表头
            page_records = 0
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue
                texts = [c.get_text(strip=True) for c in cols]
                try:
                    draw_date = datetime.strptime(texts[0], "%Y-%m-%d")
                    issue = texts[1]
                    numbers = texts[2]
                    if len(numbers) != 14:
                        continue
                    red_balls = sorted(int(numbers[i : i + 2]) for i in range(0, 12, 2))
                    blue_ball = int(numbers[12:14])
                    records.append(
                        DrawRecord(
                            issue=issue,
                            draw_date=draw_date,
                            red_balls=red_balls,
                            blue_ball=blue_ball,
                        )
                    )
                    page_records += 1
                except (ValueError, IndexError) as exc:
                    logger.debug("解析行失败: %s (%s)", texts, exc)
                    continue

            if page_records == 0:
                break

        if not records:
            raise ValueError("备选数据源未获取到任何记录")
        logger.info("备选源成功获取 %d 条记录", len(records))
        return records

    def fetch_latest(self) -> Optional[DrawRecord]:
        """获取最新一期开奖记录（优先使用轻量数据源）."""
        # 优先从 17500.cn 取最后一行
        try:
            response = self._get_with_retry(self.GETSSQ_URL)
            response.encoding = "utf-8"
            lines = response.text.strip().split("\n")
            if lines:
                parts = lines[-1].strip().split()
                if len(parts) >= 9:
                    return DrawRecord(
                        issue=parts[0],
                        draw_date=datetime.strptime(parts[1], "%Y-%m-%d"),
                        red_balls=sorted(int(parts[i]) for i in range(2, 8)),
                        blue_ball=int(parts[8]),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("从 17500.cn 获取最新一期失败: %s", exc)

        # 备选：从中彩网第一页取最新一行
        try:
            url = self.URL_ZHCW_TEMPLATE.format(page=1)
            response = self._get_with_retry(url)
            response.encoding = "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", class_="wqhgt")
            if table:
                rows = table.find_all("tr")[2:]
                if rows:
                    cols = rows[0].find_all("td")
                    texts = [c.get_text(strip=True) for c in cols]
                    draw_date = datetime.strptime(texts[0], "%Y-%m-%d")
                    issue = texts[1]
                    numbers = texts[2]
                    if len(numbers) == 14:
                        return DrawRecord(
                            issue=issue,
                            draw_date=draw_date,
                            red_balls=sorted(
                                int(numbers[i : i + 2]) for i in range(0, 12, 2)
                            ),
                            blue_ball=int(numbers[12:14]),
                        )
        except Exception as exc:  # noqa: BLE001
            logger.debug("从中彩网获取最新一期失败: %s", exc)

        return None

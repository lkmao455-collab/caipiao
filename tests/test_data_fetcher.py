"""数据获取器测试."""

import pytest

from caipiao.core.profile import SSQ, FC3D, QLC
from caipiao.data.fetcher import LotteryDataFetcher


class TestLotteryDataFetcher:
    """LotteryDataFetcher 测试."""

    def test_initialization_ssq(self):
        fetcher = LotteryDataFetcher(profile=SSQ)
        assert fetcher.profile.key == "ssq"
        assert fetcher.timeout == 60

    def test_initialization_3d(self):
        fetcher = LotteryDataFetcher(profile=FC3D)
        assert fetcher.profile.key == "3d"

    def test_custom_timeout(self):
        fetcher = LotteryDataFetcher(profile=SSQ, timeout=30)
        assert fetcher.timeout == 30

    def test_custom_retries(self):
        fetcher = LotteryDataFetcher(profile=SSQ, max_retries=5)
        assert fetcher.max_retries == 5

    def test_invalid_retries(self):
        with pytest.raises(ValueError, match="max_retries"):
            LotteryDataFetcher(profile=SSQ, max_retries=0)

    def test_parser_key_ssq(self):
        fetcher = LotteryDataFetcher(profile=SSQ)
        assert fetcher.profile.parser_key == "ssq"

    def test_parser_key_3d(self):
        fetcher = LotteryDataFetcher(profile=FC3D)
        assert fetcher.profile.parser_key == "3d"

    def test_headers_set(self):
        fetcher = LotteryDataFetcher(profile=SSQ)
        assert "User-Agent" in fetcher.headers

    def test_decode_response(self):
        # 测试解码逻辑
        class MockResponse:
            content = "test".encode("utf-8")
            apparent_encoding = "utf-8"

        result = LotteryDataFetcher._decode_response(MockResponse())
        assert result == "test"

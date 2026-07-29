"""AppSettings 持久化与边界异常处理单元测试.

使用隔离的 QSettings 命名空间（TestCaipiao/TestGenerator），不污染真实用户配置。
覆盖：整型越界钳制/非法输入回退、字典属性不可序列化/None 回退、布尔属性往返与
QSettings 自动布尔转换、损坏整型值读取回退、按彩种维度方法、current_lottery 原始键，
以及全部可读写属性的保存/恢复往返。
"""

import pytest

from caipiao.persistence.settings import AppSettings

ORG, APP = "TestCaipiao", "TestGenerator"


@pytest.fixture
def settings():
    s = AppSettings(ORG, APP)
    for key in list(s._settings.allKeys()):
        s._settings.remove(key)
    s.sync()
    yield s
    for key in list(s._settings.allKeys()):
        s._settings.remove(key)
    s.sync()


# --------------------------------------------------------------------------- #
# 整型 setter：越界钳制与非法输入回退
# --------------------------------------------------------------------------- #
def test_default_count_clamp_and_fallback(settings):
    settings.default_count = 9999
    assert settings.default_count == 1000
    settings.default_count = -100
    assert settings.default_count == 1
    settings.default_count = "abc"          # 非法 -> 回退 1
    assert settings.default_count == 1
    settings.default_count = 2.7            # float -> 2
    assert settings.default_count == 2
    settings.default_count = None           # None -> 回退 1
    assert settings.default_count == 1


def test_last_backtest_count_clamp_and_fallback(settings):
    settings.last_backtest_count = 0
    assert settings.last_backtest_count == 1
    settings.last_backtest_count = "bad"
    assert settings.last_backtest_count == 5


# --------------------------------------------------------------------------- #
# 字典属性：不可序列化 / None 回退
# --------------------------------------------------------------------------- #
def test_last_strategy_options_fallback(settings):
    settings.last_strategy_options = {"method": "random"}
    assert settings.last_strategy_options == {"method": "random"}

    class Bad:
        pass

    settings.last_strategy_options = {"x": Bad()}   # 不可序列化 -> 回退 {}
    assert settings.last_strategy_options == {}

    settings.last_strategy_options = None           # None -> 回退 {}
    assert settings.last_strategy_options == {}


# --------------------------------------------------------------------------- #
# 布尔属性：往返与 QSettings 自动布尔转换
# --------------------------------------------------------------------------- #
def test_bool_roundtrip_and_autobool(settings):
    settings.dark_theme = True
    assert settings.dark_theme is True
    settings.dark_theme = False
    assert settings.dark_theme is False
    # QSettings 自动把 yes/no/on/off/1/0 转成 bool
    settings.set("dark_theme", "yes")
    assert settings.dark_theme is True
    settings.set("dark_theme", "off")
    assert settings.dark_theme is False
    settings.set("dark_theme", "no")
    assert settings.dark_theme is False


# --------------------------------------------------------------------------- #
# 损坏整型值的读取健壮性（修复前 default_count getter 会抛 ValueError）
# --------------------------------------------------------------------------- #
def test_corrupt_int_getter_falls_back(settings):
    guarded = {
        "default_count": 1,
        "auto_update_interval_days": 1,
        "draw_analysis_max_gap": 1,
        "draw_analysis_filter_threshold": 1,
        "last_backtest_count": 5,
    }
    for k in guarded:
        settings.set(k, "garbage_not_a_number")
    settings.sync()
    for k, default in guarded.items():
        assert getattr(settings, k) == default, f"{k} 未回退到默认值"


# --------------------------------------------------------------------------- #
# 按彩种维度方法
# --------------------------------------------------------------------------- #
def test_per_profile_methods(settings):
    settings.set_draw_analysis_max_gap("ssq", 12)
    settings.set_batch_backtest_count("ssq", 33)
    settings.sync()
    assert settings.get_draw_analysis_max_gap("ssq") == 12
    assert settings.get_batch_backtest_count("ssq") == 33
    # 未设置的彩种回退默认值
    assert settings.get_draw_analysis_max_gap("nonexistent") == 1
    assert settings.get_batch_backtest_count("nonexistent") == 5


# --------------------------------------------------------------------------- #
# 设置页原始键 current_lottery
# --------------------------------------------------------------------------- #
def test_current_lottery_raw_key(settings):
    settings.set("current_lottery", "ssq")
    settings.sync()
    assert settings.get("current_lottery", "") == "ssq"


# --------------------------------------------------------------------------- #
# 全部可读写属性保存/恢复往返
# --------------------------------------------------------------------------- #
def _writable_props():
    return [
        name
        for name in dir(AppSettings)
        if not name.startswith("_")
        and isinstance(getattr(AppSettings, name, None), property)
        and getattr(AppSettings, name).fget
        and getattr(AppSettings, name).fset
    ]


def _sample_for(current):
    if isinstance(current, bool):
        return not current
    if isinstance(current, int):
        return 2  # 处于所有整型属性的合法区间内
    if isinstance(current, str):
        return "tv_xyz"
    if isinstance(current, dict):
        return {"_t": 1, "m": "随机"}
    return None


def test_all_writable_props_roundtrip(settings):
    props = _writable_props()
    samples = {}
    for name in props:
        val = _sample_for(getattr(settings, name))
        if val is None:
            continue
        setattr(settings, name, val)
        samples[name] = val
    settings.sync()
    for name, expected in samples.items():
        assert getattr(settings, name) == expected, name
    assert len(samples) >= 50  # 确保覆盖了绝大多数属性

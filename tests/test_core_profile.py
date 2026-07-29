"""Core Profile 模块单元测试."""

import pytest

from caipiao.core.profile import (
    SSQ, FC3D, KL8, DLT, PL3, PL5, QXC,
    NumberGroup, LotteryProfile,
    get_profile, list_profiles, profile_keys,
    list_profiles_by_category, category_label,
    LOTTERY_CATEGORY_WELFARE, LOTTERY_CATEGORY_SPORTS,
)


class TestNumberGroup:
    """NumberGroup 测试."""

    def test_size(self):
        g = NumberGroup("red", "红球", 1, 33, 6)
        assert g.size == 33

    def test_values(self):
        g = NumberGroup("red", "红球", 1, 5, 3)
        assert g.values == [1, 2, 3, 4, 5]

    def test_effective_pick_min_default(self):
        g = NumberGroup("red", "红球", 1, 33, 6)
        assert g.effective_pick_min == 6

    def test_effective_pick_min_custom(self):
        g = NumberGroup("main", "号码", 1, 80, 20, pick_min=1)
        assert g.effective_pick_min == 1

    def test_effective_pick_max_default(self):
        g = NumberGroup("red", "红球", 1, 33, 6)
        assert g.effective_pick_max == 6

    def test_effective_pick_max_custom(self):
        g = NumberGroup("main", "号码", 1, 80, 20, pick_max=10)
        assert g.effective_pick_max == 10

    def test_variable_pick_true(self):
        g = NumberGroup("main", "号码", 1, 80, 20, pick_min=1, pick_max=10)
        assert g.variable_pick is True

    def test_variable_pick_false(self):
        g = NumberGroup("red", "红球", 1, 33, 6)
        assert g.variable_pick is False

    def test_high_low_border(self):
        g = NumberGroup("red", "红球", 1, 33, 6)
        assert g.high_low_border == 17

    def test_validate_numbers_ok(self):
        g = NumberGroup("red", "红球", 1, 33, 6)
        g.validate_numbers([1, 2, 3, 4, 5, 6])

    def test_validate_numbers_out_of_range(self):
        g = NumberGroup("red", "红球", 1, 33, 6)
        with pytest.raises(ValueError, match="必须在"):
            g.validate_numbers([0, 2, 3, 4, 5, 6])

    def test_validate_numbers_duplicate(self):
        g = NumberGroup("red", "红球", 1, 33, 6)
        with pytest.raises(ValueError, match="不能重复"):
            g.validate_numbers([1, 1, 3, 4, 5, 6])

    def test_validate_numbers_allow_repeat(self):
        g = NumberGroup("pos", "号码", 0, 9, 3, allow_repeat=True)
        g.validate_numbers([1, 1, 1])

    def test_frozen(self):
        g = NumberGroup("red", "红球", 1, 33, 6)
        with pytest.raises(AttributeError):
            g.key = "blue"


class TestLotteryProfile:
    """LotteryProfile 测试."""

    def test_group_found(self):
        g = SSQ.group("red")
        assert g.key == "red"

    def test_group_not_found(self):
        with pytest.raises(KeyError, match="不存在"):
            SSQ.group("nonexistent")

    def test_group_keys(self):
        assert "red" in SSQ.group_keys
        assert "blue" in SSQ.group_keys

    def test_pick_groups(self):
        picks = SSQ.pick_groups
        assert all(not g.draw_only for g in picks)

    def test_primary_group_ssq(self):
        assert SSQ.primary_group.key == "red"

    def test_primary_group_fc3d(self):
        assert FC3D.primary_group.key == "pos"

    def test_is_daily_fc3d(self):
        assert FC3D.is_daily is True

    def test_is_daily_ssq(self):
        assert SSQ.is_daily is False

    def test_xgboost_prefix_ssq(self):
        assert SSQ.xgboost_prefix() == "xgboost"

    def test_xgboost_prefix_fc3d(self):
        assert FC3D.xgboost_prefix() == "3d_xgboost"

    def test_lightgbm_prefix_ssq(self):
        assert SSQ.lightgbm_prefix() == "lightgbm"

    def test_lightgbm_prefix_fc3d(self):
        assert FC3D.lightgbm_prefix() == "3d_lightgbm"

    def test_catboost_prefix_ssq(self):
        assert SSQ.catboost_prefix() == "catboost"

    def test_catboost_prefix_fc3d(self):
        assert FC3D.catboost_prefix() == "3d_catboost"

    def test_frozen(self):
        with pytest.raises(AttributeError):
            SSQ.key = "test"


class TestProfiles:
    """全局 Profile 注册测试."""

    def test_get_profile_ssq(self):
        assert get_profile("ssq").key == "ssq"

    def test_get_profile_unknown_returns_ssq(self):
        assert get_profile("unknown").key == "ssq"

    def test_list_profiles_count(self):
        # 当前共 7 个支持彩种（双色球/福彩3D/快乐8/大乐透/排列3/排列5/七星彩）。
        profiles = list_profiles()
        assert len(profiles) == 7

    def test_profile_keys(self):
        keys = profile_keys()
        assert "ssq" in keys
        assert "3d" in keys
        assert "dlt" in keys

    def test_list_profiles_by_category(self):
        by_cat = list_profiles_by_category()
        assert LOTTERY_CATEGORY_WELFARE in by_cat
        assert LOTTERY_CATEGORY_SPORTS in by_cat

    def test_category_label(self):
        assert category_label(LOTTERY_CATEGORY_WELFARE) == "福利彩票"
        assert category_label(LOTTERY_CATEGORY_SPORTS) == "体育彩票"

    def test_category_label_unknown(self):
        assert category_label("unknown") == "unknown"

    def test_all_profiles_have_groups(self):
        for p in list_profiles():
            assert len(p.groups) > 0

    def test_all_profiles_have_data_url(self):
        for p in list_profiles():
            assert isinstance(p.data_url, str)

    def test_all_profiles_have_parser_key(self):
        for p in list_profiles():
            assert isinstance(p.parser_key, str)

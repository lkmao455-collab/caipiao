# Delete test files that reference deleted strategy modules

$tests_to_delete = @(
    "tests/test_ssq_strategies.py",
    "tests/test_ssq_advanced_strategies.py",
    "tests/test_ssq_consensus_constraint.py",
    "tests/test_ssq_ml_strategies.py",
    "tests/test_fc3d_strategies.py",
    "tests/test_fc3d_dispersed_random.py",
    "tests/test_fc3d_ensemble_v2.py",
    "tests/test_fc3d_ml_strategies.py",
    "tests/test_fc3d_stability.py",
    "tests/test_fc3d_bet_mode.py",
    "tests/test_fc3d_utils.py",
    "tests/test_other_lottery_strategies.py",
    "tests/test_other_lottery_advanced_strategies.py",
    "tests/test_other_lottery_ml_strategies.py",
    "tests/test_batch_backtest_integration.py",
    "tests/test_batch_backtest_summary_browser.py",
    "tests/test_core.py",
    "tests/test_optimal_period_scan.py",
    "tests/test_optimal_strategy_scan.py",
    "tests/test_strategy_factory.py",
    "tests/test_strategy_common.py",
    "tests/test_stability_validator.py",
    "tests/test_lottery_unified.py",
    "tests/test_kl8_smart_hot_cold.py",
    "tests/test_fc3d_smart_hot_cold.py",
    "tests/test_qlc_experience_filter.py",
    "tests/test_ml.py",
    "tests/test_data.py",
)

foreach ($f in $tests_to_delete) {
    $path = "E:\caipiao\$f"
    if (Test-Path $path) {
        Remove-Item $path -Force
        Write-Host "Deleted: $f"
    }
}

Write-Host "`n=== Test cleanup complete ==="

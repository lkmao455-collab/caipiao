# Cleanup strategies: keep only smart_hot_cold.py and balanced.py for each lottery type

$lotteries = @("ssq", "fc3d", "dlt", "kl8", "pl3", "pl5", "qlc", "qxc")
$keep_files = @("smart_hot_cold.py", "balanced.py", "__init__.py", "_base.py", "stability.py", "analyzer.py", "utils.py")
$lottery_dir = "E:\caipiao\caipiao\core\strategies\lotteries"

# Delete entire advanced directory
$advanced_dir = "E:\caipiao\caipiao\core\strategies\advanced"
if (Test-Path $advanced_dir) {
    Remove-Item $advanced_dir -Recurse -Force
    Write-Host "Deleted: $advanced_dir"
}

# Process each lottery type
foreach ($lottery in $lotteries) {
    $dir = Join-Path $lottery_dir $lottery
    if (-not (Test-Path $dir)) { continue }

    Write-Host "`n=== Processing $lottery ==="

    # Get all .py files
    $all_files = Get-ChildItem -Path $dir -Filter "*.py" -File

    foreach ($f in $all_files) {
        $name = $f.Name
        # Skip __init__.py and _base.py (always keep)
        if ($name -eq "__init__.py" -or $name -eq "_base.py" -or $name -eq "stability.py" -or $name -eq "analyzer.py" -or $name -eq "utils.py") {
            Write-Host "  KEEP: $name (utility)"
            continue
        }

        if ($name -eq "smart_hot_cold.py" -or $name -eq "balanced.py") {
            Write-Host "  KEEP: $name"
            continue
        }

        # Delete everything else
        Remove-Item $f.FullName -Force
        Write-Host "  DELETE: $name"
    }

    # Delete ml subdirectory
    $ml_dir = Join-Path $dir "ml"
    if (Test-Path $ml_dir) {
        Remove-Item $ml_dir -Recurse -Force
        Write-Host "  DELETE: ml/"
    }

    # Delete __pycache__
    $cache_dir = Join-Path $dir "__pycache__"
    if (Test-Path $cache_dir) {
        Remove-Item $cache_dir -Recurse -Force
        Write-Host "  DELETE: __pycache__/"
    }
}

Write-Host "`n=== Cleanup complete ==="

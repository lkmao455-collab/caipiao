# Task 5 Report: Conflict Relaxation and Deterministic Sampling

## Status

DONE

## Summary

Implemented the full `generate()` method for `SSQConsensusConstraintStrategy`, including conflict relaxation, deterministic sampling, and the minor fixes requested for Task 4.

## Changes Made

### Modified Files

- `caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py`
- `tests/test_ssq_consensus_constraint.py`

### Implementation Details

1. **`generate()` method**
   - Uses a single `seed` for all randomness via `random.Random(seed)`.
   - Orchestrates the six stages: statistical prior → candidate generation → hard constraints (with relaxation) → scoring → deterministic sampling → ticket construction.
   - Records any relaxed constraints and the seed in the final `basis` string.

2. **Conflict relaxation (`_apply_hard_constraints_with_relaxation`)**
   - Supports `relaxation_order="strict"` to disable relaxation and fail fast.
   - Default `"reverse"` mode tries, in order:
     1. Apply constraints as-is.
     2. Expand the balanced sum range (up to 10 iterations, floor 21, cap 183).
     3. Relax `odd_count` by ±1, ±2, ±3.
     4. Reduce `exclude_red` one ball at a time.
     5. Disable all hard constraints as a last resort.
   - Raises `ValueError("无法生成任何候选组合，请检查参数设置")` if still empty.

3. **Deterministic sampling (`_sample_deterministically`)**
   - Sorts scored candidates by descending score.
   - Builds a high-quality pool from the top 50% (or `count`, whichever is larger).
   - Uses `rng.sample` to pick `count` indices deterministically.
   - Same seed + same options + same history produces identical output.

4. **Task 4 minor fixes**
   - Added guard in `_score_candidates` to avoid `ZeroDivisionError` when all enabled model weights are 0.
   - Implemented `blue_sampling_mode` schema option in `_generate_candidates`:
     - `"uniform"`: sample blue balls uniformly.
     - `"weighted"` (default): sample by the fused blue probability vector.

## Tests Added

- `test_generate_is_deterministic`
- `test_conflict_relaxation`
- `test_score_candidates_no_zero_division_when_all_weights_zero`
- `test_blue_sampling_mode_uniform`
- `test_blue_sampling_mode_weighted`

## Verification

```bash
pytest tests/test_ssq_consensus_constraint.py -v
```

Result:

```
12 passed in 4.42s
```

## Commits

- `4a32d84` feat(ssq): conflict relaxation and deterministic sampling

## Concerns

None. All specified requirements are implemented and verified.

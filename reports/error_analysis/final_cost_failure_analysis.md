# Failure Analysis -- final_cost (Section 47)

Held-out **test split** (752 rows across 41 projects). Champion is `DeterministicEacBaseline` (`BAC / CPI`, ADR-0006), so there is no SHAP/permutation explanation to attach here -- the formula itself is the explanation.

## Largest errors

- PRJ-0278 @ 2023-06-30: actual $68,852,421, predicted $45,569,146 (error $-23,283,275, lifecycle=early, project_type=residential)
- PRJ-0278 @ 2023-07-31: actual $68,852,421, predicted $47,576,807 (error $-21,275,614, lifecycle=early, project_type=residential)
- PRJ-0213 @ 2023-09-30: actual $80,060,955, predicted $62,499,244 (error $-17,561,711, lifecycle=early, project_type=infrastructure)
- PRJ-0278 @ 2023-09-30: actual $68,852,421, predicted $51,317,945 (error $-17,534,476, lifecycle=early, project_type=residential)
- PRJ-0278 @ 2023-08-31: actual $68,852,421, predicted $52,322,525 (error $-16,529,896, lifecycle=early, project_type=residential)

## Systematic bias by subgroup (positive bias = model overpredicts final cost)

**Project size:**
  - large (n=244): MAE=$2,730,938, bias=-661,852
  - medium (n=250): MAE=$1,361,652, bias=+397,732
  - small (n=258): MAE=$783,330, bias=+159,007

**Lifecycle stage:**
  - early (n=249): MAE=$2,029,492, bias=-1,210,985
  - late (n=272): MAE=$1,521,535, bias=+1,224,168
  - mid (n=231): MAE=$1,253,940, bias=-227,157

**Inflation regime:**
  - low_inflation (n=254): MAE=$2,076,511, bias=-1,202,563
  - high_inflation (n=222): MAE=$1,604,683, bias=+1,469,157
  - mid_inflation (n=276): MAE=$1,178,216, bias=-151,220

## Uncertainty interval

- 76 of 752 test rows (10.1%) fall outside their own conformal prediction interval.
- Out-of-distribution rows (at least one numeric feature outside the train split's range): 3 of 752 (0.4%).

## What a human reviewer should check

- The largest-error projects listed above, especially any where the actual cost fell outside the reported prediction interval.
- Subgroups with the largest MAE/bias above -- a consistent sign on `bias` means the model is systematically over- or under-predicting for that subgroup, not just noisy.
- Out-of-distribution rows, where `BAC / CPI` is being applied to a CPI value the model's calibration split never observed.
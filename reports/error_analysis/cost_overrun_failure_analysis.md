# Failure Analysis -- cost_overrun (Section 47)

Held-out **test split** (752 rows across 41 projects). Threshold=0.080 (Section 17, optimized on the calibration split, never on test).

## Where the model fails

- False negatives (missed a real overrun/delay): 7 of 266 actual positives (2.6%).
- False positives (false alarm): 211 of 486 actual negatives (43.4%).
- Near-threshold predictions (within +-0.05 of the decision boundary): 80 rows -- these are the cases most sensitive to model noise and the ones a human reviewer gains the most from double-checking.
- Out-of-distribution rows (at least one numeric feature outside the train split's observed range): 3 of 752 (0.4%). The model extrapolates for these; treat its probability as less trustworthy.

## Worst false negatives (model most confident, and most wrong)

- PRJ-0064 @ 2023-11-30: predicted 0.021, actual positive (cpi=1.016, lifecycle=mid)
- PRJ-0021 @ 2023-04-30: predicted 0.079, actual positive (cpi=1.030, lifecycle=early)
- PRJ-0064 @ 2023-07-31: predicted 0.079, actual positive (cpi=1.091, lifecycle=early)
- PRJ-0034 @ 2024-08-31: predicted 0.079, actual positive (cpi=1.091, lifecycle=early)
- PRJ-0064 @ 2023-08-31: predicted 0.079, actual positive (cpi=1.060, lifecycle=early)

Top SHAP drivers for the single worst false negative (PRJ-0064 @ 2023-11-30):
  - `numeric__operational_variance`: SHAP=-0.1702
  - `numeric__cost_variance`: SHAP=-0.1002
  - `numeric__cpi`: SHAP=-0.0840
  - `numeric__gross_floor_area_m2`: SHAP=+0.0121
  - `numeric__inflation_component`: SHAP=+0.0119

## Worst false positives (model most confident, and most wrong)

- PRJ-0230 @ 2024-08-31: predicted 1.000, actual negative (cpi=0.810, lifecycle=early)
- PRJ-0230 @ 2024-05-31: predicted 0.965, actual negative (cpi=0.780, lifecycle=early)
- PRJ-0230 @ 2024-06-30: predicted 0.965, actual negative (cpi=0.805, lifecycle=early)
- PRJ-0230 @ 2024-10-31: predicted 0.965, actual negative (cpi=0.835, lifecycle=mid)
- PRJ-0230 @ 2025-02-28: predicted 0.965, actual negative (cpi=0.802, lifecycle=mid)

Top SHAP drivers for the single worst false positive (PRJ-0230 @ 2024-08-31):
  - `numeric__cpi`: SHAP=+0.1963
  - `numeric__operational_variance`: SHAP=+0.1740
  - `numeric__cost_variance`: SHAP=+0.0652
  - `numeric__lifecycle_fraction`: SHAP=+0.0235
  - `numeric__inflation_component`: SHAP=+0.0154

## Hardest subgroups (lowest AUC per dimension)

**Project type:**
  - commercial (n=191): AUC=0.900
  - residential (n=291): AUC=0.957
  - infrastructure (n=87): AUC=0.980

**Lifecycle stage:**
  - early (n=249): AUC=0.850
  - mid (n=231): AUC=0.966
  - late (n=272): AUC=0.996

**Geography (state):**
  - ES (n=76): AUC=0.597
  - BA (n=58): AUC=0.855
  - DF (n=46): AUC=0.976

**Inflation regime:**
  - low_inflation (n=254): AUC=0.832
  - mid_inflation (n=276): AUC=0.982
  - high_inflation (n=222): AUC=0.998

## Global drivers

Top 5 features by mean |SHAP value| (encoded feature space):
  - `numeric__operational_variance`: 0.1289
  - `numeric__cpi`: 0.1073
  - `numeric__cost_variance`: 0.0542
  - `numeric__lifecycle_fraction`: 0.0248
  - `numeric__inflation_component`: 0.0213

Top 5 features by permutation importance (original feature space, ROC-AUC drop):
  - `cpi`: 0.1088
  - `operational_variance`: 0.0865
  - `cost_variance`: 0.0103
  - `inflation_component`: 0.0061
  - `gross_floor_area_m2`: 0.0045

## What a human reviewer should check

- Any prediction within +-0.05 of the 0.080 threshold -- the model's decision there is close to a coin flip between the two sides of the boundary.
- Any prediction flagged out-of-distribution above -- the model is extrapolating, not interpolating within data it was trained on.
- Predictions for the subgroups listed under "Hardest subgroups" above, where the model's discriminative power is weakest even though the global metric looks strong.
- False negatives specifically: at this threshold the model trades a higher false-positive rate for a lower false-negative rate (Section 17's cost matrix makes a missed overrun far more expensive than a false alarm) -- but the 7 false negatives above are the cases that slipped through anyway and deserve manual follow-up.
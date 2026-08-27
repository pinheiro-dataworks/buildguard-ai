# Failure Analysis -- schedule_delay (Section 47)

Held-out **test split** (752 rows across 41 projects). Threshold=0.140 (Section 17, optimized on the calibration split, never on test).

## Where the model fails

- False negatives (missed a real overrun/delay): 28 of 395 actual positives (7.1%).
- False positives (false alarm): 139 of 357 actual negatives (38.9%).
- Near-threshold predictions (within +-0.05 of the decision boundary): 45 rows -- these are the cases most sensitive to model noise and the ones a human reviewer gains the most from double-checking.
- Out-of-distribution rows (at least one numeric feature outside the train split's observed range): 3 of 752 (0.4%). The model extrapolates for these; treat its probability as less trustworthy.

## Worst false negatives (model most confident, and most wrong)

- PRJ-0064 @ 2024-07-31: predicted 0.000, actual positive (cpi=0.844, lifecycle=late)
- PRJ-0064 @ 2024-08-31: predicted 0.000, actual positive (cpi=0.831, lifecycle=late)
- PRJ-0099 @ 2024-07-31: predicted 0.000, actual positive (cpi=0.918, lifecycle=mid)
- PRJ-0099 @ 2024-08-31: predicted 0.000, actual positive (cpi=0.921, lifecycle=mid)
- PRJ-0099 @ 2024-05-31: predicted 0.000, actual positive (cpi=0.900, lifecycle=mid)

Top SHAP drivers for the single worst false negative (PRJ-0064 @ 2024-07-31):
  - `numeric__lifecycle_fraction`: SHAP=-0.3360
  - `numeric__spi`: SHAP=-0.0645
  - `numeric__schedule_variance`: SHAP=+0.0481
  - `numeric__months_to_planned_completion`: SHAP=-0.0297
  - `numeric__change_order_amount_to_date`: SHAP=-0.0281

## Worst false positives (model most confident, and most wrong)

- PRJ-0053 @ 2024-03-31: predicted 0.996, actual negative (cpi=0.802, lifecycle=mid)
- PRJ-0053 @ 2024-05-31: predicted 0.996, actual negative (cpi=0.817, lifecycle=late)
- PRJ-0372 @ 2024-07-31: predicted 0.996, actual negative (cpi=0.921, lifecycle=late)
- PRJ-0277 @ 2024-01-31: predicted 0.996, actual negative (cpi=0.992, lifecycle=mid)
- PRJ-0277 @ 2024-02-29: predicted 0.996, actual negative (cpi=1.012, lifecycle=mid)

Top SHAP drivers for the single worst false positive (PRJ-0053 @ 2024-03-31):
  - `numeric__spi`: SHAP=+0.4452
  - `numeric__lifecycle_fraction`: SHAP=-0.0918
  - `numeric__schedule_variance`: SHAP=+0.0344
  - `numeric__months_to_planned_completion`: SHAP=-0.0049
  - `numeric__gross_floor_area_m2`: SHAP=-0.0026

## Hardest subgroups (lowest AUC per dimension)

**Project type:**
  - commercial (n=191): AUC=0.872
  - residential (n=291): AUC=0.880
  - industrial (n=122): AUC=0.917

**Lifecycle stage:**
  - early (n=249): AUC=0.761
  - late (n=272): AUC=0.929
  - mid (n=231): AUC=0.931

**Geography (state):**
  - BA (n=58): AUC=0.838
  - SC (n=83): AUC=0.861
  - GO (n=53): AUC=0.943

**Inflation regime:**
  - low_inflation (n=254): AUC=0.771
  - high_inflation (n=222): AUC=0.924
  - mid_inflation (n=276): AUC=0.940

## Global drivers

Top 5 features by mean |SHAP value| (encoded feature space):
  - `numeric__spi`: 0.2038
  - `numeric__lifecycle_fraction`: 0.1645
  - `numeric__schedule_variance`: 0.0585
  - `numeric__months_to_planned_completion`: 0.0360
  - `numeric__inflation_component`: 0.0129

Top 5 features by permutation importance (original feature space, ROC-AUC drop):
  - `spi`: 0.3230
  - `lifecycle_fraction`: 0.1271
  - `months_to_planned_completion`: 0.0342
  - `schedule_variance`: 0.0246
  - `number_of_units`: 0.0019

## What a human reviewer should check

- Any prediction within +-0.05 of the 0.140 threshold -- the model's decision there is close to a coin flip between the two sides of the boundary.
- Any prediction flagged out-of-distribution above -- the model is extrapolating, not interpolating within data it was trained on.
- Predictions for the subgroups listed under "Hardest subgroups" above, where the model's discriminative power is weakest even though the global metric looks strong.
- False negatives specifically: at this threshold the model trades a higher false-positive rate for a lower false-negative rate (Section 17's cost matrix makes a missed overrun far more expensive than a false alarm) -- but the 28 false negatives above are the cases that slipped through anyway and deserve manual follow-up.
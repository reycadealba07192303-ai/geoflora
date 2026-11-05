# 21-class + 3-class cascade check (2026-11-05)

Script: `cascade_eval_21cls_3cls.py` (run from ml-lab with its venv: `python reports/cascade/cascade_eval_21cls_3cls.py .`).
Models: `geoflora-mnv2-21cls-v1` (threshold 0.686) and `geoflora-mnv2-3cls-v2` (threshold 0.968).
Data: 21-class test set (931 images, 152 of them target species) + `dataset/nissap/unknown_test` (408 images).
Leakage check: 0 of the 931 test images are in the 3-class train or val sets.

| Strategy | Targets correct | Precision when it says TARGET | False target alarms (779 non-target + 408 unknown) |
|---|---|---|---|
| 21-class alone (threshold) | 90/152 (59%) | 92.8% | 5 + 2 = 7 |
| 21 says target, 3cls must agree | 90/152 | 92.8% | 7 (no change: 3cls always agreed) |
| 21 says target, 3cls must agree and be confident | 81/152 (53%) | 95.3% | 4 + 0 = 4 |
| **21 first; if its top-1 is a target but below threshold, accept only when 3cls agrees and is confident** | **115/152 (76%)** | 85.8% | 12 + 7 = 19 |

Per target (correct/n), 21 alone vs. cascade+rescue: Chromolaena 23/57 vs 36/57, Lantana 39/52 vs 45/52, Pontederia crassipes 28/43 vs 34/43.
3-class alone (from its own evaluation): 33% false acceptance of non-target plants with threshold (1,710 unknown test images). Do not serve it alone.

Remaining images are "uncertain" and should go to the app's review queue. Single test set, used once for this comparison. Do not tune further on it.

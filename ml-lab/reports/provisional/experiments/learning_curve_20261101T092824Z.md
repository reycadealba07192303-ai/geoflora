# Experiment: learning_curve (20261101T092824Z)

> **PROVISIONAL PILOT - NOT A RESEARCH RESULT.** Trained on unreviewed source identifications; do not report these figures as GeoFlora model performance.

Dataset version: ds-20261101-c9f7f87fef

Accuracy CI: exact binomial 95%. Macro F1 CI: observation-group bootstrap 95%.

| Config | Train imgs | Test imgs | Accuracy (CI) | Macro F1 (CI) | Unknown FAR |
|---|---|---|---|---|---|
| fraction=0.25 | 43 | 36 | 0.694 (0.519-0.837) | 0.691 (0.526-0.837) | 0.467 |
| fraction=0.5 | 84 | 36 | 1.000 (0.903-1.000) | 1.000 (1.000-1.000) | 0.117 |
| fraction=1.0 | 165 | 36 | 1.000 (0.903-1.000) | 1.000 (1.000-1.000) | 0.311 |

Each row is an independent training run; class-expansion rows are evaluated only on their own classes.

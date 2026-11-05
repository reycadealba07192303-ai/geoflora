# Experiment: learning_curve (20261104T104000Z)

Dataset version: ds-20261104-8b1b716af8

Accuracy CI: exact binomial 95%. Macro F1 CI: observation-group bootstrap 95%.

| Config | Train imgs | Test imgs | Accuracy (CI) | Macro F1 (CI) | Unknown FAR |
|---|---|---|---|---|---|
| fraction=0.25 | 78 | 66 | 0.909 (0.813-0.966) | 0.906 (0.826-0.969) | 0.610 |
| fraction=0.5 | 152 | 66 | 0.955 (0.873-0.991) | 0.953 (0.901-1.000) | 0.253 |
| fraction=1.0 | 302 | 66 | 0.970 (0.895-0.996) | 0.969 (0.925-1.000) | 0.187 |

Each row is an independent training run; class-expansion rows are evaluated only on their own classes.

# Experiment: class_expansion (20261104T103307Z)

Dataset version: ds-20261104-00998fdf5b

Accuracy CI: exact binomial 95%. Macro F1 CI: observation-group bootstrap 95%.

| Config | Train imgs | Test imgs | Accuracy (CI) | Macro F1 (CI) | Unknown FAR |
|---|---|---|---|---|---|
| classes=2 | 207 | 45 | 1.000 (0.921-1.000) | 1.000 (1.000-1.000) | 0.386 |
| classes=3 | 302 | 66 | 0.955 (0.873-0.991) | 0.953 (0.901-1.000) | 0.246 |
| classes=4 | 401 | 88 | 0.830 (0.734-0.901) | 0.824 (0.726-0.897) | 0.351 |
| classes=5 | 499 | 109 | 0.789 (0.700-0.861) | 0.787 (0.713-0.855) | 0.368 |
| classes=6 | 597 | 130 | 0.785 (0.704-0.852) | 0.778 (0.699-0.846) | 0.175 |
| classes=7 | 695 | 151 | 0.775 (0.700-0.839) | 0.769 (0.695-0.830) | 0.158 |
| classes=8 | 790 | 172 | 0.762 (0.691-0.823) | 0.758 (0.687-0.811) | 0.088 |
| classes=9 | 888 | 193 | 0.751 (0.684-0.811) | 0.752 (0.686-0.804) | 0.140 |
| classes=10 | 986 | 215 | 0.753 (0.690-0.810) | 0.751 (0.686-0.805) | 0.105 |

Each row is an independent training run; class-expansion rows are evaluated only on their own classes.

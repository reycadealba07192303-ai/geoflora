# V1 and V2 validation after owner approval

Labels are approved from owner attestation. This validation does not establish independent botanical or Philippine geographic verification.

| Manifest | Rows | Unapproved | Path/checksum errors | Cross-split near-duplicate groups | Training-ready |
|---|---:|---:|---:|---:|---|
| storage\datasets\curated\v1\manifest.csv | 78 | 0 | 0 | 1 | No |
| storage\datasets\curated\v2\manifest.csv | 243 | 0 | 0 | 39 | No |

Both historical files are intact and their labels now have owner approval. Their existing splits still contain near-duplicate leakage, so neither is confirmed for training/final evaluation. Approval events do not change split assignments. Preserve these versions and create a new grouped version after geographic eligibility is resolved.

Evidence: baseline-evidence.json. This validation refreshes the earlier Part 1 snapshot; its report describes the state before owner approval.

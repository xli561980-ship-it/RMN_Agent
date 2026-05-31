# Query Anchor Ablation

- Analyzer: `heuristic only`
- Reranker: `none` (default pipeline)
- Forced gold source mode is **diagnostic only** and not used in production.

## Summary

| question_id | mode | scope_source | recall@5 | recall@10 | recall@20 | in_pool |
| --- | --- | --- | --- | --- | --- | --- |
| hybrid_replicate_safety | no_anchor | - | 0.0 | 0.0 | 0.0 | False |
| hybrid_replicate_safety | analyzer_anchor | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf | 1.0 | 1.0 | 1.0 | True |
| hybrid_replicate_safety | forced_gold_source_anchor | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf | 1.0 | 1.0 | 1.0 | True |
| missing_evidence | no_anchor | - | 0.0 | 0.0 | 0.0 | False |
| missing_evidence | analyzer_anchor | - | 0.0 | 0.0 | 0.0 | False |
| missing_evidence | forced_gold_source_anchor | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf | 1.0 | 1.0 | 1.0 | True |

## Focus questions

### `hybrid_replicate_safety`

#### gold_hit_rank delta (analyzer vs no_anchor)
| section | no_anchor | analyzer_anchor | forced_gold |
| --- | --- | --- | --- |
| Microfluidic fabrication | None | 1 | 1 |
| Safety Instructions | None | 1 | 1 |

#### `no_anchor` top-20 sources

| rank | source |
| --- | --- |
| 1 | d2lc00203e1.pdf |
| 2 | General Lab Rules MRBL-2.pdf |
| 3 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 4 | General Lab Rules MRBL-2.pdf |
| 5 | indenting-at-the-microscale-guidelines-for-robust-mechanical-characterization-of-alginate-microgels.pdf |
| 6 | BioelectronicsLab-S1-SafetyBriefing.pdf |
| 7 | Advanced Materials - 2025 - Harder - A Soft Microrobot for Single‐Cell Transport  Spheroid Assembly  and Dual‐Mode Drug.pdf |
| 8 | General Lab Rules MRBL-2.pdf |
| 9 | indenting-at-the-microscale-guidelines-for-robust-mechanical-characterization-of-alginate-microgels.pdf |
| 10 | Phosphate-buffered_saline_(PBS__1X_MTR_CLP1_EN.pdf |
| 11 | pnas.1819415116.sapp.pdf |
| 12 | pH meter 30046976_SevenExcellence_UserManual_EN_FR_ES_PL_I.pdf |
| 13 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 14 | BioelectronicsLab-S1-SafetyBriefing.pdf |
| 15 | Adv Materials Inter - 2024 - Özkale - Why Biopolymer Microgels with Dynamically Switchable Properties Would be a Great.pdf |
| 16 | General Lab Rules MRBL-2.pdf |
| 17 | indenting-at-the-microscale-guidelines-for-robust-mechanical-characterization-of-alginate-microgels.pdf |
| 18 | BA Magnetic stirrer_eng.pdf |
| 19 | indenting-at-the-microscale-guidelines-for-robust-mechanical-characterization-of-alginate-microgels.pdf |
| 20 | General Lab Rules MRBL-2.pdf |

#### `analyzer_anchor` top-20 sources

| rank | source |
| --- | --- |
| 1 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 2 | General Lab Rules MRBL-2.pdf |
| 3 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 4 | General Lab Rules MRBL-2.pdf |
| 5 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 6 | BioelectronicsLab-S1-SafetyBriefing.pdf |
| 7 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 8 | General Lab Rules MRBL-2.pdf |
| 9 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 10 | Phosphate-buffered_saline_(PBS__1X_MTR_CLP1_EN.pdf |
| 11 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 12 | pH meter 30046976_SevenExcellence_UserManual_EN_FR_ES_PL_I.pdf |
| 13 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 14 | BioelectronicsLab-S1-SafetyBriefing.pdf |
| 15 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 16 | General Lab Rules MRBL-2.pdf |
| 17 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 18 | BA Magnetic stirrer_eng.pdf |
| 19 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 20 | General Lab Rules MRBL-2.pdf |

#### `forced_gold_source_anchor` top-20 sources

| rank | source |
| --- | --- |
| 1 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 2 | General Lab Rules MRBL-2.pdf |
| 3 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 4 | General Lab Rules MRBL-2.pdf |
| 5 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 6 | BioelectronicsLab-S1-SafetyBriefing.pdf |
| 7 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 8 | General Lab Rules MRBL-2.pdf |
| 9 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 10 | Phosphate-buffered_saline_(PBS__1X_MTR_CLP1_EN.pdf |
| 11 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 12 | pH meter 30046976_SevenExcellence_UserManual_EN_FR_ES_PL_I.pdf |
| 13 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 14 | BioelectronicsLab-S1-SafetyBriefing.pdf |
| 15 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 16 | General Lab Rules MRBL-2.pdf |
| 17 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 18 | BA Magnetic stirrer_eng.pdf |
| 19 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 20 | General Lab Rules MRBL-2.pdf |

### `missing_evidence`

#### gold_hit_rank delta (analyzer vs no_anchor)
| section | no_anchor | analyzer_anchor | forced_gold |
| --- | --- | --- | --- |
| Introduction | None | None | 1 |

#### `no_anchor` top-20 sources

| rank | source |
| --- | --- |
| 1 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 2 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 3 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 4 | indenting-at-the-microscale-guidelines-for-robust-mechanical-characterization-of-alginate-microgels.pdf |
| 5 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 6 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 7 | Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic Differentiation of Single Stem Cells in 3D (1).pdf |
| 8 | Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic Differentiation of Single Stem Cells in 3D (1).pdf |
| 9 | Adv Materials Inter - 2024 - Özkale - Why Biopolymer Microgels with Dynamically Switchable Properties Would be a Great.pdf |
| 10 | Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic Differentiation of Single Stem Cells in 3D (1).pdf |
| 11 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 12 | Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic Differentiation of Single Stem Cells in 3D (1).pdf |
| 13 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |

#### `analyzer_anchor` top-20 sources

| rank | source |
| --- | --- |
| 1 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 2 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 3 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 4 | indenting-at-the-microscale-guidelines-for-robust-mechanical-characterization-of-alginate-microgels.pdf |
| 5 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 6 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 7 | Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic Differentiation of Single Stem Cells in 3D (1).pdf |
| 8 | Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic Differentiation of Single Stem Cells in 3D (1).pdf |
| 9 | Adv Materials Inter - 2024 - Özkale - Why Biopolymer Microgels with Dynamically Switchable Properties Would be a Great.pdf |
| 10 | Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic Differentiation of Single Stem Cells in 3D (1).pdf |
| 11 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |
| 12 | Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic Differentiation of Single Stem Cells in 3D (1).pdf |
| 13 | Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf |

#### `forced_gold_source_anchor` top-20 sources

| rank | source |
| --- | --- |
| 1 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 2 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 3 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 4 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 5 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 6 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 7 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 8 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 9 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 10 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 11 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 12 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 13 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |
| 14 | Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf |

## Notes

- `forced_gold_source_anchor` injects `gold_sources[0]` into analysis for upper-bound diagnosis.
- Production should rely on UI anchor + analyzer hints, not forced gold injection.

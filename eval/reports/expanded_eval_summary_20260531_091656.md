# Expanded Retrieval Eval Summary

- Timestamp: `20260531_091656`
- Questions: **31**
- Gold evidence rows: **69**

## 1. 评估集规模

### Question type 分布

| category | count |
| --- | --- |
| ambiguous_anchor | 5 |
| hybrid | 5 |
| missing_evidence | 5 |
| paper_comparison | 5 |
| paper_only | 5 |
| sop_only | 6 |

### Route 分布

| expected_route | count |
| --- | --- |
| HYBRID | 9 |
| PAPER_ONLY | 16 |
| SOP_ONLY | 6 |

- Paper / SOP / hybrid（按 route）：{'SOP_ONLY': 6, 'PAPER_ONLY': 16, 'HYBRID': 9}

## 2. 总体指标

| metric | value |
| --- | --- |
| recall@5 | 0.9355 |
| recall@10 | 0.9355 |
| recall@20 | 0.9677 |
| precision@5 | 0.7613 |
| mrr | 0.8437 |
| ndcg@5 | 0.9963 |
| doc_type_accuracy | 0.9871 |
| sop_boundary_accuracy | 0.9677 |
| paper_to_sop_confusion_rate | 0.0129 |

## 3. 各类型指标

| category | n | recall@5 | recall@10 | recall@20 | mrr |
| --- | --- | --- | --- | --- | --- |
| ambiguous_anchor | 5 | 1.0 | 1.0 | 1.0 | 0.8 |
| hybrid | 5 | 1.0 | 1.0 | 1.0 | 0.767 |
| missing_evidence | 5 | 1.0 | 1.0 | 1.0 | 0.85 |
| paper_comparison | 5 | 1.0 | 1.0 | 1.0 | 1.0 |
| paper_only | 5 | 0.6 | 0.6 | 0.8 | 0.614 |
| sop_only | 6 | 1.0 | 1.0 | 1.0 | 1.0 |

## 4. Failure analysis 汇总

| issue_type | count |
| --- | --- |
| ranking_issue | 4 |
| recall_issue | 1 |

## 5. Top failure cases

| question_id | category | expected_route | predicted_route | recall@5 | possible_cause |
| --- | --- | --- | --- | --- | --- |
| paper_protocol_microgel | paper_only | PAPER_ONLY | HYBRID | 1.0 | route_or_ranking |
| paper_ozkale_toolbox | paper_only | PAPER_ONLY | PAPER_ONLY | 0.0 | route_or_ranking |
| paper_d2lc_actuated | paper_only | PAPER_ONLY | PAPER_ONLY | 0.0 | route_or_ranking |
| hybrid_fume_hood_solvents | hybrid | HYBRID | SOP_ONLY | 1.0 | route_or_ranking |
| missing_microgel_platform_generalization | missing_evidence | PAPER_ONLY | PAPER_ONLY | 1.0 | route_or_ranking |
| anchor_corpus_literature | ambiguous_anchor | PAPER_ONLY | PAPER_ONLY | 1.0 | route_or_ranking |

### `paper_protocol_microgel`
- Question: Photothermally powered 3D microgels 这篇论文的完整制备/刺激流程中，当前上下文能支持哪些关键步骤和参数？
- Gold sources: `['papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf']`
- Top retrieved: `['papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'manuals/Litesizer 500 Instruction Manual .pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'manuals/Litesizer 500 Instruction Manual .pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf']`
- Issues: `[]`

### `paper_ozkale_toolbox`
- Question: Özkale 2024 perspective 论文如何描述 biopolymer microgels 作为 stem cell cultivation tool-box 的价值？
- Gold sources: `['papers/Adv Materials Inter - 2024 - Özkale - Why Biopolymer Microgels with Dynamically Switchable Properties Would be a Great.pdf']`
- Top retrieved: `['papers/1-s2.0-S0142961220307432-main.pdf', 'papers/1-s2.0-S0142961220307432-main.pdf', 'papers/1-s2.0-S0142961220307432-main.pdf', 'papers/1-s2.0-S0142961220307432-main.pdf', 'papers/1-s2.0-S0142961220307432-main.pdf']`
- Issues: `[]`

### `paper_d2lc_actuated`
- Question: Actuated 3D microgels for single cell mechanobiology 这篇论文的核心研究对象和应用场景是什么？
- Gold sources: `['papers/d2lc00203e1.pdf']`
- Top retrieved: `['papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf']`
- Issues: `[]`

### `hybrid_fume_hood_solvents`
- Question: 复现 microgel 制备中涉及 acetic acid、oil phase 或有机溶剂步骤时，BA Fume hood SOP 有哪些操作限制？
- Gold sources: `['papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'manuals/BA Fume hood_eng.pdf']`
- Top retrieved: `['manuals/General Lab Rules MRBL-2.pdf', 'manuals/FreeZone Console Freeze Dryers (7343200 Rev F).pdf', 'manuals/BA Fume hood_eng.pdf', 'manuals/General Lab Rules MRBL-2.pdf', 'manuals/BA Fume hood_eng.pdf']`
- Issues: `[]`

### `missing_microgel_platform_generalization`
- Question: 这些研究是否足以支持将 photothermal microgel 平台推广到所有 alginate microgel 体系？
- Gold sources: `['papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Adv Materials Inter - 2024 - Özkale - Why Biopolymer Microgels with Dynamically Switchable Properties Would be a Great.pdf', 'papers/d2lc00203e1.pdf']`
- Top retrieved: `['papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf']`
- Issues: `[]`

### `anchor_corpus_literature`
- Question: 这些研究是否支持 microgel mechanobiology 在所有 cell type 和 stimulation modality 上都成立？
- Gold sources: `['papers/Advanced Materials - 2025 - Wang - Photothermally Powered 3D Microgels Mechanically Regulate Mesenchymal Stem Cells Under (2).pdf', 'papers/Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf', 'papers/Small Science - 2025 - İyisan - Hydrostatic Pressure Induces Osteogenic Differentiation of Single Stem Cells in 3D (1).pdf', 'papers/Adv Materials Inter - 2024 - Özkale - Why Biopolymer Microgels with Dynamically Switchable Properties Would be a Great.pdf']`
- Top retrieved: `['papers/d2lc00203e1.pdf', 'papers/Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf', 'papers/smtd202400272-sup-0001-suppmat.docx', 'papers/Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf', 'papers/Small Methods - 2024 - İyisan - Mechanoactivation of Single Stem Cells in Microgels Using a 3D‐Printed Stimulation Device.pdf']`
- Issues: `[]`

## 6. 下一步建议

- 扩展集整体可接受；下一步继续增加 hard negatives 与 generation/citation eval，而非围绕当前集过拟合。
- 若 chunking_boundary_issue 频繁出现：考虑 header-aware / parent-child 对比实验。
- 若 gold_label_mismatch 出现：用 eval-gold-check 修正标签，而非改 retrieval 逻辑刷分。

## Artifacts

- Retrieval eval JSON: `/Users/xds_mac/Library/CloudStorage/OneDrive-TUM/cursorgitrmn/RMN_Agent/eval/reports/retrieval_eval_20260531_090008.json`
- Gold alignment: ``

# PPT Dataset Summary

## 1. 数据集构建

本阶段工作的核心目标，是把多源、异构、粒度不一致的智能家居公开数据，统一整理成可用于“中枢节点决策”的 episode 级监督样本。具体来说，我们将 Home Assistant、SmartSense、CASAS、EdgeWisePersona 与中文家居命令数据统一接入，并构建了从 Raw、Staging、Canonical 到 Episode 的四层数据仓库。

当前仓库已经完成：
- 原始文件登记 47,176 条
- 状态快照 `fact_state_snapshot` 3,351,343 条
- 任务 `fact_task` 412,353 条
- 动作集合 `fact_action_set` 381,431 条
- 最终 episode 样本 `episodes.parquet` 381,427 条

统一后的监督样本以“一轮中枢决策”为单位，字段包括 `state_id`、`task_id`、`action_set_id`、候选设备集合、目标动作集合以及可选的 `synthetic_discussion`，从而使不同数据源能够进入同一条训练和评估流程。

推荐配图：
- [dataset_pipeline_overview.svg](/Users/fengdefan/Code/GitHub/homekgmas/outputs/figures/ppt/dataset_pipeline_overview.svg)
- [dataset_table_scale.svg](/Users/fengdefan/Code/GitHub/homekgmas/outputs/figures/ppt/dataset_table_scale.svg)

## 2. 验证方法

我们对数据构建流程采用了“结构完整性 + 映射覆盖率 + 切分安全性”三类验证方法。

第一，检查结构完整性：
- 时间戳解析率在核心表上达到 100%
- 去重统计在 staging / canonical / bridge 主要表上均为 0
- `episodes` 表空值比例为 0

第二，检查标准化质量：
- 设备域映射覆盖率为 67.48%
- 动作映射覆盖率为 99.98%
- 对不能恢复强标签的数据源显式保留 `weak` 或 `medium` 标记，不伪造强监督

第三，检查切分泄漏：
- `home_multi_split_count = 4`
- `user_multi_split_count = 2`

这说明当前数据仓库已经具备可复现实验基础，但后续还需要进一步压低跨 split 的 home / user 泄漏数量。

推荐配图：
- [dataset_validation_snapshot.svg](/Users/fengdefan/Code/GitHub/homekgmas/outputs/figures/ppt/dataset_validation_snapshot.svg)

## 3. 当前结果

从最终样本规模来看，当前已经构建出 381,427 条 episode。其中：
- `train` 集 306,621 条
- `valid` 集 37,423 条
- `test` 集 37,383 条

从标签质量看：
- `strong` = 373,512
- `medium` = 7,118
- `weak` = 797

从样本来源看，当前以 SmartSense 的历史动作监督为主，同时由中文命令和 Home Assistant 提供显式任务与目标动作对齐样本：
- source_dataset
smartsense                 373379
zh_commands                  7118
home_assistant_datasets       133

从任务类型看，当前最主要的学习目标是“基于历史上下文预测下一步动作”，其次是“用户自然语言到动作”的映射，以及“routine 驱动的设备建议”：
- task_source
inferred      373379
routine        21719
user_nl        17251
automation         4

从动作域看，已覆盖 `media_player`、`light`、`cover`、`climate`、`fan`、`switch`、`lock` 等多类设备：
- device_domain
media_player    238520
other            68700
light            33242
cover            18010
climate          13203
fan               5246
appliance         3473
switch            2365

推荐配图：
- [dataset_result_breakdown.svg](/Users/fengdefan/Code/GitHub/homekgmas/outputs/figures/ppt/dataset_result_breakdown.svg)

## 4. 汇报中可直接使用的一段总结

目前我们已经把多源智能家居公开数据统一构造成了可用于中枢节点训练的 episode 级数据集。该数据集不再只是孤立的命令识别、环境感知或 routine 预测任务，而是被统一映射为“给定状态与任务，预测最终设备动作集合”的监督形式。当前共形成 381,427 条样本，其中强监督样本占主导，能够支撑我们对中枢决策流程、候选设备召回、动作生成以及合成多 agent proposal 机制开展系统性实验。

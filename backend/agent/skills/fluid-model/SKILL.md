---
name: fluid-model
description: 获得预测管网的调度能力。在 Windows 环境下按算例(001-264,默认001)修改控制CSV(Boundary等)、就地patch批量job-config、运行 real_predict 并汇总/对比输出。
dependencies:
  - python>=3.9
---

# 最关键的两个绝对路径前缀-请务必记住！！重要
[PROJECT-PATH-PREFIX]: "D:/ml_pro_master/chroes/fluid_model" 
比如python -m real_predict.main ... 整个流体模型项目的代码都是在这个项目路径下面，后续的都是相对路径，如果你使用 WorkspaceTools 的 `run_command`：**real_predict 必须传 `cwd=<项目根目录绝对路径>`，但是scripts是属于SKILL里面的路径，就是之前的项目路径，可以不用cwd。只有real_predict或者mock_data需要到fluid_model的根目录下面去执行。当遇到路径的脚本不存在的时候反复思考是不是路径写错了，再结束对话。**

[SKILL-PATH-PREFIX]: "D:/ml_pro_master/gis_pipeline_llm/backend/agent/skills/fluid-model" 这个是关于这个预制SKILL的脚本的代码都放在这里。也支持自定义脚本在 `[SKILL-PATH-PREFIX]/temporary_scripts` 目录下创建。

# real_predict 批量预测工作流

这个 Skill 专注于一个可重复的流程：  
**选算例 →（按场景）修改控制 CSV → patch job-config → 执行 `python -m real_predict.main ...` → 阅读输出 →（可选）对比“修改前/后”差异。**

# 关键
请务必执行完全部的步骤，进行一轮闭环之后再进行返回

---

## 强制规则（必须照做）

### 0) 预测算例选择规则（001–264）
- **允许范围**：第001个算例 ～ 第264个算例 ；对应`[PROJECT-PATH-PREFIX]/data/dataset/mock_test` 下面的测试样例
- **默认**：用户没说 / 说错 / 超范围 → **默认使用第001个算例**

### 1) 路径与工作目录规则
- **所有关键路径都建议使用绝对路径**


### B. 完整批量预测工作流（1→4，可反复迭代）


#### Step 1：修改 csv
按照用户的要求修改控制 CSV（Boundary等），这里CSV有非常几千列，建议你读取的时候只读取对应的告诉你的控制变量的列。

#### Step 2：修改json文件
`[PROJECT-PATH-PREFIX]/real_predict/examples/batch_jobs_for_skill_1.json`
`[PROJECT-PATH-PREFIX]/real_predict/examples/batch_jobs_for_skill_2.json`
batch_jobs_for_skill_x.json 这个文件是准备好模型的文件，你可以直接修改，不用另外创建后修改，然后如果修改炸了，可以查看`[PROJECT-PATH-PREFIX]/real_predict/examples/batch_jobs_for_skill_base.json`，这个是正确的格式。
batch_jobs_for_skill.json这个文件里面"sample_dir","name"可能需要修改成这次执行的样子
"ensemble_config"对应的`[PROJECT-PATH-PREFIX]/real_predict/examples/static_pipeline_six_subgraphs_value_projection.json`这个json文件里面有提前设置好的模型和分图的流程，你不需要改变,只需要理解。
"output" 你固定死就是这个real_predict/examples/static_pipeline_six_subgraphs_for_skill_x,不用提前清空这个文件夹，执行的时候会覆盖的。生成后也不用清空。这里real_predict/examples/static_pipeline_six_subgraphs_for_skill_1和real_predict/examples/static_pipeline_six_subgraphs_for_skill_2 已经帮你创建好了。
"sample_dir"请指向 data/dataset/mock_test/ 里面的文件夹。每次你担心修改csv文件对吧，直接使用下面的指令

robocopy "data\dataset\mock_test\第xxx个算例" "data\dataset\mock_test\第xxx个算例-缓存" /MIR
然后可以任意修改里面的csv文件，不用生成backup，因为这个文件夹最后会删掉。/MIR确保完全复制内容，因为这里是缓存文件夹。


#### Step 3：执行预测（严格按要求）
```bash
python -m real_predict.main --job-config "real_predict/examples/batch_jobs_for_skill_1.json"
cwd=[PROJECT-PATH-PREFIX]
```
或者改成其他的序号json
```bash
python -m real_predict.main --job-config "real_predict/examples/batch_jobs_for_skill_2.json"
cwd=[PROJECT-PATH-PREFIX]
```

#### Step 4: 查看输出
分析输出，分析前后执行获得的csv的不同之处，得出结论
```


---
- 如果需要临时定义Scripts自定义修改的模式，可以在 `[SKILL-PATH-PREFIX]/temporary_scripts` 目录下创建脚本。


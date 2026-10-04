# 可执行的工作流数据样例

这是数据预检演示，不是可玩 Godot 工程。资源路径都是契约示例，本仓库尚未包含这些模型。预检不检查资源文件是否存在、不创建场景、不验证画面或性能。

## 用户要求示例

“用现有的工业园资源做一个鼠标模拟光枪的短关卡。镜头自动沿轨道走，在三个驻点交战。左键开火，R 装填，手枪 8 发。先教玩家打普通敌人，再练习远程优先级，最后打有弱点窗口的精英。敌人攻击前要有声音和动作提示，所有敌人解决后再走，死亡可以重试。交付 Windows 与 Android 版本。”

这些是样例要求，不是用户已经确定要开发的游戏题材。约 90 秒是设计参考，必须由实际试玩校准。

## 产物对应关系

- `game_spec.json`：平台、输入、武器和硬门槛初值。
- `asset_manifest.json`：建筑、普通敌人、远程敌人、精英的语义能力；明确标注 metadata_only。
- `level_ir.json`：三个驻点、刷怪条目、镜头和关卡出口。
- `validate_workflow.py`：Python 标准库预检与故障注入自检，无第三方依赖。

运行（`python` 不在 PATH 时替换为本机 Python 绝对路径）：

```powershell
python docs/ai-workflow/examples/validate_workflow.py
python docs/ai-workflow/examples/validate_workflow.py --self-test
python docs/ai-workflow/examples/validate_workflow.py --report <report-path.json>
```

退出码 0 为该预检覆盖项通过，1 为数据检查失败，2 为文件读取/JSON 格式/未受支持结构错误。`--self-test` 验证正常样例并注入典型坏数据；仅证明预检器有用，不证明游戏通过测试。

2026-10-04 已执行：正常样例通过，12 类故障注入均被拒绝。结果保存在 [preflight-report.json](preflight-report.json) 与 [self-test-report.json](self-test-report.json)。

## 预检覆盖

版本匹配；鼠标配置；武器与门槛正数；资产/驻点/锚点/刷怪 ID 唯一；资源与路径引用；相机位置/FOV 数据；落位宽限；入场声音先行；可射击时间不晚于前摇；反应窗下限；保守敌人数量；闸门终态；超时策略；从入口可达与最终可结束；首版禁止循环；精英具备弱点能力。

数量上限使用“本驻点所有刷怪合计”，属于保守静态近似，会拒绝某些实际分波后合法的关卡；正式编译器必须根据活动时段和事件依赖计算同时在场数。这里只采用单波驻点避免混淆。

不覆盖：完整 schema、所有字段严格类型、建筑拼装、碰撞/遮挡、实际动画/声音、BOSS 周期可打窗口、资源文件、seed determinism、真实输入、自动试玩、导出和平台性能。这些对应工作流后续实施任务。

## 初始字段约定

`schema_version=0.1`。位置单位米，时间字段后缀 `_ms`，入场/前摇/攻击时间相对落位完成；settle 时间是单独阶段。`next` 为下一个驻点 ID；末点为 null。`resolved` 定义为 dead、escaped、disarmed 之一。watchdog 默认 fail，不允许假装通关。

样例中逻辑“elite”只表示资源具备弱点语义，完整 BOSS 状态机和窗口测试尚未实现。正式实现需要增加版本化 JSON Schema、事件依赖图、需求追踪与证据格式。

# 参考标准映射

本文件说明 Skill 如何综合 ASD-STE100 Issue 9 与 Google developer documentation
style guide。需要解释规则来源、处理差异或审查覆盖范围时读取本文件。

## 规则映射

| 主题 | ASD-STE100 提供的约束 | Google 指南提供的约束 | 本 Skill 的处理 |
| --- | --- | --- | --- |
| 术语 | 受控词典、批准词义与词性、技术名词一致性 | 项目术语优先、用词一致、避免行话 | 通用任务采用项目术语；严格 STE 追加词典核对 |
| 句子 | 短句、有限动词形式、主动语态 | 主动语态优先，执行者无关时允许被动语态 | 默认主动语态并明确主体；严格 STE 使用更窄条件 |
| 程序 | 祈使句、一个主要指令、20 词限制 | 前置条件、位置、目标、操作、结果和可选标签 | 按读者执行顺序组合，并仅对严格 STE 应用词数限制 |
| 描述 | 信息逐步展开、25 词、单主题段落、最多 6 句 | 面向任务组织、描述性标题、清晰导航 | 采用渐进结构和单主题段落；英语限制按合规要求启用 |
| 安全 | 等级、命令或条件、潜在结果 | 在操作前提供清晰提示并使用准确通知类型 | 采用领域等级，不自行判定风险级别 |
| 全球读者 | 避免区域词、俚语和行话 | 避免习语、幽默和文化特定表达，保持可翻译性 | 采用稳定术语、标准语序和明确日期单位 |
| 无障碍 | 主要关注语言清晰度 | 替代文本、等效正文、描述链接和非视觉定位 | 将 Google 无障碍规则作为通用要求 |
| 代码和命令 | 不属于主要软件文档格式规范 | 可执行示例、占位符、输入输出和代码格式 | 使用 Google 原则并服从项目代码规范 |

## 差异处理

按以下优先级处理差异：

1. 法规、合同、领域安全标准和用户明确指定的合规目标；
2. 项目规范、产品术语表、接口定义和发布平台要求；
3. 严格 STE 任务使用 Issue 9 全部规则及词典；
4. 其他技术文档使用核心写作标准。

需要记录的常见差异包括：

- 缩写式：严格 STE 禁止；其他英文按项目风格和全球读者要求决定。
- 被动语态：Google 允许有限使用；严格 STE 仅按 Issue 9 条件使用。
- 短语动词：严格 STE 有明确限制；通用文档避免含义不透明或难翻译的用法。
- 拼写：严格 STE 默认美式拼写；其他文档服从项目和目标读者约定。
- 句长：严格 STE 使用 20/25 词限制；其他语言和普通英文按一个主要陈述或操作拆分。
- 语气：Google 鼓励直接、友好的表达；中文专项规则可以要求更正式的书面语。

## 官方来源

- [ASD-STE100 Simplified Technical English, Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf)
- [Google developer documentation style guide](https://developers.google.com/style)
- [Google active voice](https://developers.google.com/style/voice)
- [Google procedures](https://developers.google.com/style/procedures)
- [Google headings and titles](https://developers.google.com/style/headings)
- [Google write for a global audience](https://developers.google.com/style/translation)
- [Google accessible documentation](https://developers.google.com/style/accessibility)
- [Google code samples](https://developers.google.com/style/code-samples)
- [Google command-line syntax](https://developers.google.com/style/code-syntax)

Google 指南持续更新。规则判断依赖当前版本时重新核对官方页面，并在结果中记录核对
日期。ASD-STE100 合规任务固定使用用户或合同指定的 Issue。

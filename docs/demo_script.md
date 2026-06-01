# 演示脚本

这份脚本用于准备面试、课程展示或作品集讲解。实际演示时，请使用本地非敏感文档，并根据 `data/papers/` 和 `data/manuals/` 中的具体内容调整问题。

## 30 秒介绍

RMN Agent 是一个面向科研文档和实验室 SOP / 手册的双路 RAG 助手。它不是把所有 PDF 都丢进一个向量库后直接聊天，而是在入库和检索阶段区分两类来源：论文提供研究证据，SOP 和设备手册提供操作规范与安全约束。

当前 Demo 可以展示完整路径：放入论文和手册，执行入库，在 Streamlit 界面提问，系统先做 query analysis，再按 paper、SOP 或 hybrid 路径检索，最后生成带引用线索的回答，并在 debug 面板里展示路由和 citation validation 结果。

## 2 分钟讲解流程

1. 介绍场景：

   “实验室或 R&D 团队经常同时使用论文、补充材料、设备手册和内部 SOP。论文里有方法和参数，但不一定代表本地批准的操作流程；SOP 和手册才更接近设备使用、安全要求和执行约束。”

2. 展示知识库结构：

   “这个仓库把文档放在两个目录：`data/papers/` 存论文和补充材料，`data/manuals/` 存 SOP、设备手册和操作说明。入库时系统会写入 `doc_type=paper` 或 `doc_type=sop`。”

3. 说明入库流程：

   “`ingest.py` 支持 `.pdf` 和 `.docx`。它会解析文本、切分 chunk、生成 embedding、写入本地 Chroma，并记录哪些文件已经处理过。论文和 SOP 的 chunk 大小也不同，论文偏参数检索，SOP 尽量保留操作步骤。”

4. 打开应用：

   “Streamlit 界面是这个项目的演示入口。侧边栏可以看到论文和手册列表，可以触发入库，也可以锁定某一篇论文，减少跨论文混淆。”

5. 提问论文型问题：

   示例：`这篇 microgel 论文里的关键制备步骤和参数是什么？`

   “这类问题会偏向 paper path。系统检索论文片段，回答时保留 `[Source: ...]` 形式的引用线索。”

6. 提问 SOP / 手册型问题：

   示例：`设备手册中对启动、校准或安全注意事项有什么要求？`

   “这类问题应主要走 SOP path，因为用户问的是可执行操作或设备约束。”

7. 提问混合型问题：

   示例：`如果我要参考论文复现实验，哪些步骤必须再核对本实验室 SOP？`

   “这个问题能体现项目的核心设计：论文参数可以提供研究参考，但真正执行前要回到 SOP / 手册确认安全和本地流程。”

8. 展示 debug 与校验：

   “界面会展示 query analysis、检索 chunk 数量、引用列表和 citation validation。debug 面板让用户能看到系统为什么走这条检索路径，以及回答中的引用是否属于本轮检索结果。”

9. 总结：

   “这个项目当前是本地 Demo，不是生产系统。它的重点是展示 RAG 架构设计、来源类型分离、证据约束回答和现场可演示的原型能力。”

## 技术架构讲解

可以把 RMN Agent 拆成七层说明：

- 输入层：`app.py` 中的 Streamlit chat input，以及侧边栏的 paper scope selector。
- 问题分析层：`query_analyzer.py` 判断问题属于 `SOP_ONLY`、`PAPER_ONLY` 还是 `HYBRID`，并选择回答模式。
- 检索层：`rag_core.py` 基于 Chroma 检索 paper chunk 和 SOP chunk，支持 metadata filter 与可选混合召回。
- 范围控制层：`fusion_scope.py` 处理单篇论文锁定、project_id 过滤和标题软重排。
- Prompt 编排层：`fusion_prompts.py` 根据 scholarly、operational、hybrid 场景构造系统 Prompt。
- 模型层：通过 LangChain 调用 Google Gemini 进行 query analysis 和回答生成，embedding provider 可通过环境变量配置。
- 输出与校验层：Streamlit 流式展示回答和引用，`citation_validator.py` 标记未知引用或缺少引用的数字型声明。

## 演示时可以强调的技术点

- 论文和 SOP 不是同一种证据，系统用 `doc_type` 在入库和检索阶段区分它们。
- query analysis 不只是分类标签，它会影响检索 query、回答模式和可选论文范围。
- Prompt 要求回答基于检索上下文，缺证据时直接说明，不补造实验参数。
- citation validation 当前是轻量检查，能发现引用不属于本轮检索或数字声明缺引用等问题，但不能替代完整事实验证。
- Streamlit UI 的作用是让系统可以被现场讲清楚，包括“系统做了什么”和“为什么这样回答”。

## 可能被问到的问题

**问：这是生产系统吗？**

答：不是。当前是本地 Demo，用于展示架构和可行性。生产使用还需要认证、权限控制、部署、日志、监控、更强评估和安全审查。

**问：它和普通 RAG 聊天机器人有什么区别？**

答：关键区别是来源类型分离和问题路由。论文和 SOP 在入库、检索和回答解释时都被区分，避免把论文中的探索性参数直接当成本地批准流程。

**问：如果 LLM query analyzer 失败怎么办？**

答：`query_analyzer.py` 有规则 fallback，会根据关键词、仪器提示、显式文件名和 UI paper anchor 做基础路由和范围判断。

**问：系统如何降低幻觉？**

答：系统要求回答基于检索上下文，并保留引用线索；生成后还会做轻量 citation validation。这不能证明回答完全正确，但能捕捉一部分常见问题。

**问：仓库里包含什么数据？**

答：仓库只包含 `data/` 下的占位目录。真实演示需要自己放入本地非敏感 `.pdf` 或 `.docx` 文件，不应提交客户数据或密钥。

**问：如果要继续完善，优先改哪里？**

答：优先增加更完整的 UI 或 API、结构化输出模板、权限控制、日志监控、Docker 部署，以及更系统的评估集。

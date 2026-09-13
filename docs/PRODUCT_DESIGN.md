# 轻量级 AI 长篇创作平台产品与技术设计

> 文档版本：v0.4  
> 修订日期：2026-09-13  
> 对比基准：OpenFic 仓库（<https://github.com/syrizelink/OpenFic>，以评审日期可见内容为准，发布前重新核对）。  
> 目标：在保持 Windows 轻量部署的前提下，形成比 OpenFic 更强的结构化创作、可解释 AI、批量审稿、版本安全和数据迁移能力。

## 1. 产品定位

本项目是一款本地优先、可自托管、首发只支持 Windows 10/11 x64 的长篇小说创作工作台。它把编辑器、作品资料库、AI 助手、检索、版本控制和创作分析放在同一个项目空间中。浏览器/PWA 只作为开发调试和后续交付形态，不进入 Windows 首发验收。

核心原则：

- **人主导创作**：AI 提供建议、草稿、检查和执行能力，所有写入正文的动作可预览、可撤销。
- **轻量运行**：默认只启动 Tauri 窗口进程和一个 Python Sidecar 服务进程，数据使用 SQLite；不要求 Redis、Postgres、消息队列或独立向量数据库。
- **本地优先**：正文、设定、密钥和历史版本默认保存在本地；云端只承担用户主动配置的模型调用。
- **结构化长上下文**：作品资料不是一堆聊天记录，而是可引用、可追踪、可更新的知识对象。
- **可迁移**：项目可以完整导出为 Markdown/JSON/ZIP，不绑定某个模型或数据库。

## 2. 用户与场景

### 2.1 目标用户

1. 个人长篇作者：需要管理章节、角色、世界观、伏笔和版本。
2. 网文作者：需要快速续写、改写、批量检查和章节节奏分析。
3. 剧本/互动小说作者：需要角色关系、分支剧情和场景卡片。
4. AI 写作爱好者：需要自定义模型、Prompt、工作流和工具。
5. 小型创作团队：作为后续 Web/协作版本的目标用户；Windows 首发先按单用户本地工作区设计。

### 2.2 关键任务

- 从灵感建立作品结构和大纲。
- 根据设定生成章节计划、场景卡和写作草稿。
- 在编辑器中对选中文本执行续写、改写、压缩、扩写和风格转换。
- 检查人物性格、时间线、设定冲突、伏笔回收和重复表达。
- 面向 10 万字发布基线，并对百万字项目做性能验证，检索相关章节和设定。
- 回看 AI 做过的每次修改，比较差异并恢复任意版本。
- 将作品导出为 Markdown、JSON；DOCX/EPUB 在 1.0 提供。

## 3. 相对 OpenFic 的设计取舍

| 领域 | 本项目策略 |
|---|---|
| 部署 | 默认 Tauri + 一个 Python Sidecar + SQLite + 本地文件；不强制 LanceDB、Redis、消息队列 |
| Agent | 一个主 Agent + 可配置专家角色；专家默认以工作流节点运行，避免复杂多代理生命周期 |
| 检索 | SQLite FTS5 作为必选；向量检索为可插拔模块，可用本地 embedding 或远程 API |
| 前端 | React + Tiptap；Windows 首发以 Tauri 2 桌面端为交付形态，PWA 仅作为开发/后续形态，使用系统 WebView |
| 上下文 | 规则化上下文包、引用来源和 token 预算可视化，避免黑盒拼接 |
| 数据 | SQLite 表 + 文件附件；所有写入带 revision 和 operation 记录 |
| 实时性 | SSE 用于单向流式输出；多人协作和 Socket.IO 不进入 Windows 首发 |
| 扩展 | Provider、工具、工作流和导入导出都有稳定接口 |
| 领先能力 | 故事图谱、约束引擎、伏笔闭环、证据引用、批量审稿、Prompt 评测、可恢复离线草稿、受限插件隔离；复杂模型路由、跨设备合并和 OS 级沙箱属于 1.x |

## 4. 功能范围

### 4.1 MVP（0.1～0.2）必须功能

- 项目、卷、章节树。
- Tiptap 富文本编辑器和 Markdown 双向导入导出。
- 基础资料卡：角色、地点、组织、物品和规则；故事图谱关系与来源追踪在 1.0 提供。
- 章节大纲和基础场景卡。
- AI 操作预览、逐条审批、冲突保护和可撤销事务。
- 系统提示词编辑、最终 Prompt 预览和版本回放。
- AI 对话、选区操作、章节续写。
- 一个自定义 OpenAI-compatible Provider。
- 多级系统提示词：全局、项目、Agent、工作流、会话临时提示词。
- SQLite FTS5 检索和引用片段展示。
- 版本历史、差异比较、撤销和恢复。
- 一键 ZIP 导出与 JSON 备份。
- Windows 本地 API Key 加密；应用密码作为可选增强。

### 4.2 Windows 1.0 功能（在 MVP 之上）

- 可选混合检索：FTS5 + 向量 + 可选重排；无向量依赖时 FTS5 仍是完整默认方案。
- 工作流编排：节点、条件、审批、重试、输出变量。
- 时间线和事件关系图。
- 伏笔状态管理：埋设、发展、回收、废弃。
- AI 连贯性审查和引用证据。
- 批量章节审稿、摘要、标签和质量评分。
- 角色关系图和剧情分支基础视图；场景地图列入 1.x。
- CLI 和受限插件工具；Webhook、公开插件市场和完整插件沙箱属于 1.x。
- DOCX/EPUB 导出。
- 质量评测和基础备用模型配置；复杂模型路由与成本策略属于 1.x。
- 本地离线草稿恢复、可验证项目包和创作分析指标；跨设备操作队列与三方合并属于 1.x。
- 插件权限白名单、独立进程和 JSON-RPC 隔离；OS 级沙箱属于 1.x。

以下能力属于后续版本，不阻塞 Windows 1.0：多人实时协作、公开 Web/PWA 托管、跨设备离线同步与三方合并、Socket.IO、复杂模型路由、Webhook、公开插件市场和完整 OS 级插件沙箱。

### 4.3 暂不做

- 多租户计费平台。
- 自建大模型训练和 GPU 推理集群。
- 默认支持十几家 Provider 的专用协议。
- 复杂的实时协同光标系统。
- 自动生成整本小说的无人值守模式。

### 4.4 功能领先蓝图

本项目不通过堆叠更多 Provider 或更复杂的 Agent 数量来竞争，而是把创作过程中最容易失控的部分做成一等能力。

| 能力 | OpenFic 侧重点 | 本项目的增强设计 | 用户收益 |
|---|---|---|---|
| 故事知识 | World Info、章节摘要和 RAG | 角色/地点/组织/事件/伏笔组成可追踪故事图谱，实体有状态和来源 | 修改设定时能知道会影响哪些章节 |
| 连贯性 | Agent 审查和上下文检索 | 时间线约束、实体状态约束、伏笔生命周期和证据级问题列表 | 少靠模型记忆，多靠规则发现矛盾 |
| AI 写入 | 工具调用、审批、Revision | 操作事务、old_hash 乐观锁、批量预览、逐条接受/拒绝/重排 | 防止 AI 覆盖新内容 |
| 上下文 | 分层上下文、压缩和检索 | ContextPackage 可视化、来源引用、预算模拟、调用前预览 | 用户知道模型为什么这样回答 |
| Prompt | Prompt Chain、Agent、Skill、Rule 分散配置 | 五级提示词、变量白名单、版本、回放和离线评测集 | 可复现、可比较、可持续优化 |
| 审稿 | 单次 Agent 检查 | 规则检查 + LLM 检查 + 批量报告 + 证据跳转 | 一次检查全书并定位问题 |
| 创作分析 | 写作统计和 Dashboard | 节奏、视角、角色出场、对话比例、重复度、伏笔回收率 | 看到作品结构而非只有字数 |
| 模型使用 | 多 Provider 接入 | 模型路由、故障转移、成本/质量策略和本地模型优先 | 更稳定、更省钱 |
| 离线与迁移 | 本地持久化和导出 | 离线操作队列、冲突合并、可验证 ZIP、schema 迁移 | 换设备和断网创作更安全 |
| 扩展 | Agent 工具和 Skill | 版本化插件清单、权限沙箱、输入输出 schema | 扩展不会污染核心数据 |

### 4.5 领先功能的边界

- **故事图谱**只保存可验证的事实和来源，不让模型自动把猜测写成设定。
- **约束引擎**先运行确定性检查，再调用 LLM 解释和提出修复建议。
- **批量审稿**生成问题报告和证据，不自动修改正文。
- **模型路由**根据任务类型选择模型，不把 API Key 或请求正文暴露给路由器。
- **插件隔离**只能通过声明式工具 API 访问项目数据，禁止直接读写数据库文件；1.0 使用权限白名单、独立进程和 JSON-RPC 边界。这不是 OS 级安全沙箱，后者作为后续增强。

## 5. 系统架构

```text
Tauri Windows 桌面壳（开发阶段可由浏览器访问）
        |
        | REST + SSE
        v
应用服务（FastAPI）
  ├── 项目与内容服务
  ├── AI 编排服务
  ├── 上下文构建器
  ├── 检索服务
  ├── 版本与操作日志
  ├── 导入导出服务
  └── 设置与认证
        |
        ├── SQLite + FTS5
        ├── 本地附件目录
        ├── 可选向量索引（`sqlite-vec` 首选，LanceDB 可选）
        └── 外部 LLM/Embedding/Rerank API
```

### 5.1 推荐技术栈

- 后端：Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、SQLite。
- 前端：React 19、TypeScript、Vite、Tiptap、TanStack Query、Zustand、CSS Modules；不引入 Tailwind 运行时依赖。
- 流式：SSE；断线后使用事件 ID 恢复。
- 检索：SQLite FTS5；中文分词器使用可选 jieba，未安装时使用字符 n-gram；向量模块通过协议隔离。
- 任务：短任务可用 `asyncio`；摘要、索引、批量审稿和导出使用 SQLite jobs 表，支持重启恢复。
- 测试：pytest、pytest-asyncio、Vitest、Playwright。
- 打包：Docker、uv build；Windows 桌面端使用 Tauri 2 + WebView2 + PyInstaller one-dir Python Sidecar，避免 one-file 启动解压延迟。

### 5.2 桌面端方案：Tauri 2

桌面端不使用 Electron。首发只支持 Windows，Tauri 2 使用 Windows WebView2，前端复用同一套静态 Web 构建产物；PWA 交付仍属于后续形态。

桌面端职责保持最小：

- 启动和停止本地 Python 服务；
- 分配随机本地端口并通过 localhost 通信；
- 管理数据目录和单实例锁；
- 提供系统托盘、开机启动和文件选择器；
- 调用系统通知和安全存储；
- 不在 Rust 层实现业务逻辑。

预期收益：安装包显著小于 Electron，内存占用更低，启动更快。Windows 首发可以减少跨平台 WebView 差异和打包维护成本，后续再评估其他平台。

### 5.3 轻量边界

默认安装应满足：

- 一个 Tauri 窗口进程和一个 Python Sidecar 服务进程（不含系统 WebView2 进程）。
- 一个 SQLite 数据库。
- 一个数据目录。
- 不要求 Redis、Postgres、Node 运行时、Chromium 或独立向量数据库。Windows 桌面用户无需单独安装 Python。

## 6. 核心领域模型

### 6.1 主要表

- `projects`：作品基本信息、语言、状态、统计。
- `volumes`：卷/篇章层级。
- `chapters`：章节标题、顺序、状态、正文、字数。
- `scenes`：场景目标、冲突、出场角色、地点、预期结果。
- `entities`：统一资料对象，`kind` 区分角色、地点、组织、物品、规则。
- `entity_relations`：实体关系和证据。
- `entity_states`：实体在不同章节/事件节点上的状态快照。
- `story_constraints`：时间、年龄、地点、因果和设定约束。
- `story_facts`：经用户确认的事实、来源和置信级别。
- `timeline_events`：事件时间、顺序、参与实体和章节来源。
- `story_branches`：分支名称、父分支、触发条件、关联章节和状态。
- `foreshadows`：伏笔状态、埋设章节、回收章节、描述。
- `foreshadow_links`：伏笔与章节、事件、实体之间的证据链接。
- `notes`：自由笔记和标签。
- `ai_sessions` / `ai_messages`：AI 会话和消息。
- `operations`：每次 AI 或用户写入的操作记录。
- `revisions`：内容快照、父版本、作者和来源。
- `providers` / `models`：模型配置，密钥只存密文。
- `prompt_templates`：系统提示词、Agent 提示词和工作流提示词。
- `prompt_versions`：提示词版本、变量定义、适用范围和变更记录。
- `jobs`：摘要、索引、批量审查等后台任务。
- `workflow_runs` / `workflow_nodes`：工作流运行、节点状态、输入快照和输出。
- `evaluation_cases` / `evaluation_runs`：Prompt 和模型评测样例、评分和回归结果。
- `offline_operations`：离线编辑队列、客户端版本和冲突状态。
- `settings`：用户和项目级设置。

### 6.2 内容版本策略

所有正文修改都转化为 operation：

```json
{
  "type": "replace_range",
  "target": "chapter:abc",
  "from": 1024,
  "to": 1450,
  "old_hash": "...",
  "new_text": "...",
  "source": "ai",
  "session_id": "..."
}
```

服务端校验 `old_hash`，避免 AI 结果覆盖用户刚刚修改的内容。成功后生成 revision，并保留前后文本哈希和 diff。

操作坐标统一使用 Unicode code point 的半开区间 `[from, to)`；前端编辑器不得把 UTF-16 偏移直接提交给后端。正文哈希按规范化前的原始文本计算，服务端只在内容哈希实际变化时创建 revision，并用幂等键合并重复提交。

## 7. AI 与工作流设计

### 7.1 Provider 抽象

统一接口：

```python
class ChatProvider(Protocol):
    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]: ...
    async def count_tokens(self, messages: list[Message]) -> int | None: ...
```

Windows 首发只实现 OpenAI-compatible；Anthropic-compatible、Gemini 和本地模型在后续版本通过适配器增加，不污染核心领域代码。

### 7.2 系统提示词系统

系统提示词不是写死在代码里的常量，而是可管理、可预览、可版本化的配置对象。

支持五个层级：

1. **全局提示词**：默认语言、基本写作原则、输出格式和安全边界。
2. **项目提示词**：作品题材、叙事视角、时代背景、禁用内容和总体文风。
3. **Agent 提示词**：写作、策划、审稿、资料整理等角色的职责和行为规范。
4. **工作流提示词**：某个工作流节点的具体任务、输入格式和输出 schema。
5. **会话临时提示词**：只对当前任务生效的额外要求。

合并顺序为：

```text
全局 → 项目 → Agent → 工作流 → 会话临时
``` 

越靠后的层级优先级越高，但不能绕过工具权限、隐私和写入审批规则。系统提示词编辑器必须提供：

- Markdown 编辑和变量插入；
- 可用变量列表，例如 `{{project.name}}`、`{{chapter.content}}`、`{{selected_text}}`；
- 启用/禁用和适用范围；
- 版本历史、差异比较和恢复；
- “查看本次实际提示词”预览；
- token 估算和超预算提示；
- 导入、导出和模板复制。

提示词中禁止保存 API Key、密码和未经用户确认的外部指令。每次 AI 调用保存提示词版本 ID 和最终渲染摘要，便于复现和审计。

### 7.3 上下文包

每次调用生成可审计的 `ContextPackage`：

- 系统规则和写作风格。
- 当前章节、选区和邻近段落。
- 项目摘要、卷摘要、章节摘要。
- 相关角色/世界观实体。
- 时间线和伏笔证据。
- 检索结果及其来源 ID。
- 当前计划和用户指令。
- token 预算、截断原因和优先级。

前端可以展开查看“AI 看到了什么”，解决长上下文黑盒问题。

### 7.4 确定性创作引擎

在调用 LLM 之前运行轻量规则引擎：

- 时间线顺序和日期冲突；
- 角色年龄、地点和出场状态；
- 已确认事实与新文本的矛盾；
- 伏笔是否有埋设、发展和回收证据；
- 章节编号、标题和引用完整性。

规则引擎输出结构化问题，LLM 负责解释、排序和提出修复方案。这样可以减少把所有判断交给模型造成的不稳定。

### 7.5 批量审稿与创作分析

用户可以选择章节范围，生成异步审稿任务。报告包含问题等级、证据片段、涉及实体、建议方案和一键跳转位置。审稿任务不直接修改正文。

创作分析至少提供：节奏曲线、章节字数、场景数量、角色出场、对话比例、视角切换、重复短语、伏笔回收率和未解决问题数量。

### 7.6 模型评测与后续路由

Windows 1.0 为任务声明上下文需求，支持主模型和备用模型失败转移；每次调用保存模型、Prompt 版本、上下文摘要、token、耗时和用户采纳结果。基于质量、速度和成本的自动模型路由，以及本地模型优先策略，列入 1.x。

评测集由用户自有片段组成，支持固定样例回放和人工评分，避免 Prompt 修改后质量退化。

### 7.7 Agent 能力分层

- **写作助手**：续写、改写、扩写、压缩、润色。
- **策划助手**：大纲、场景卡、节奏和冲突设计。
- **资料助手**：检索、摘要、实体提取、时间线整理。
- **审稿助手**：连贯性、设定冲突、人物一致性、重复度检查。
- **执行器**：在审批后写入章节、实体、伏笔和计划。

默认只运行一个主会话。专家助手作为可复用工作流节点调用，输出结构化结果后回到主会话，降低并发和恢复复杂度。

### 7.8 工具权限

工具分为：

- 只读：读取章节、实体、检索、读取时间线。
- 草稿：生成建议、创建草稿、写入临时结果。
- 写入：修改正文、更新实体、改变伏笔状态。
- 外部：网页搜索、网页抓取、Webhook。

写入和外部工具默认需要审批；每个工具声明输入 schema、权限级别、幂等键和撤销策略。

## 8. 检索设计

### 8.1 默认 FTS5

章节、摘要、实体、笔记建立独立 FTS5 表，索引字段包括标题、正文、别名、标签和描述。中文环境提供：

- 默认使用应用侧分词后写入 FTS5 的 `search_text` 字段，不能依赖 SQLite 原生按词切分中文。
- 无分词器时退化为字符 n-gram 和别名匹配。
- 别名和拼音辅助字段。
- 章节/卷/实体类型过滤。
- 最近章节和当前卷加权。

### 8.2 可选向量模块

定义 `EmbeddingIndex` 接口：

```python
class EmbeddingIndex(Protocol):
    async def upsert(self, chunks: list[Chunk]) -> None: ...
    async def search(self, query: str, limit: int) -> list[Hit]: ...
```

混合检索采用可配置权重的 RRF。未安装向量依赖时自动退化到 FTS5，不影响主流程。

### 8.3 引用溯源

每个召回结果必须携带：项目、章节/实体 ID、段落范围、索引版本和得分。AI 输出中的引用在前端可点击跳回原文。

## 9. API 设计

### 9.1 REST

```text
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{id}/tree
DELETE /api/v1/projects/{id}
GET    /api/v1/chapters/{id}
PATCH  /api/v1/chapters/{id}
DELETE /api/v1/chapters/{id}
POST   /api/v1/chapters/{id}/operations
POST   /api/v1/operations
GET    /api/v1/chapters/{id}/revisions
GET    /api/v1/entities
POST   /api/v1/entities
PATCH  /api/v1/entities/{id}
DELETE /api/v1/entities/{id}
GET    /api/v1/timeline/events
POST   /api/v1/timeline/events
DELETE /api/v1/timeline/events/{id}
GET    /api/v1/foreshadows
PATCH  /api/v1/foreshadows/{id}
DELETE /api/v1/foreshadows/{id}
GET    /api/v1/operations/{id}
POST   /api/v1/operations/{id}/approve
POST   /api/v1/operations/{id}/reject
POST   /api/v1/search
POST   /api/v1/story/validate
GET    /api/v1/story/graph
GET    /api/v1/story/branches
POST   /api/v1/story/branches
PATCH  /api/v1/story/branches/{id}
DELETE /api/v1/story/branches/{id}
POST   /api/v1/reviews/batch
GET    /api/v1/reviews/{id}/report
POST   /api/v1/evaluations/run
POST   /api/v1/offline/sync             # 1.x 预留，Windows 1.0 只使用本地草稿恢复
GET    /api/v1/auth/session
POST   /api/v1/auth/unlock
POST   /api/v1/auth/logout
POST   /api/v1/prompts
GET    /api/v1/prompts
GET    /api/v1/prompts/{id}/versions
POST   /api/v1/prompts/{id}/versions
POST   /api/v1/prompts/preview
POST   /api/v1/context/build
GET    /api/v1/ai/sessions/{id}/messages/{message_id}/context
POST   /api/v1/tools/read_chapter
POST   /api/v1/tools/search_project
POST   /api/v1/tools/read_entity
POST   /api/v1/tools/create_note
POST   /api/v1/tools/propose_text_operation
POST   /api/v1/tools/update_entity
POST   /api/v1/ai/sessions
POST   /api/v1/ai/sessions/{id}/messages
GET    /api/v1/ai/sessions/{id}/events
POST   /api/v1/ai/sessions/{id}/cancel
POST   /api/v1/workflows/{id}/run
POST   /api/v1/projects/{id}/export
POST   /api/v1/projects/import
GET    /api/v1/jobs/{id}
POST   /api/v1/jobs/{id}/cancel
GET    /api/v1/providers
POST   /api/v1/providers
PATCH  /api/v1/providers/{id}
DELETE /api/v1/providers/{id}
POST   /api/v1/providers/{id}/test
```

除全局设置接口外，所有资源接口必须带项目边界或从会话中解析项目边界；服务端不得接受仅由前端传入的项目 ID 作为授权依据。Windows 单用户模式默认使用一次性本地随机 nonce，Tauri 通过受保护的本地 IPC 或环境继承传给 Sidecar，不放入 URL、日志或命令行；启用远程访问时再启用应用密码和会话认证。批量审稿、索引、导出等长任务统一返回 `202 Accepted`、资源 ID 和幂等键结果；普通 CRUD 使用同步响应。

### 9.2 SSE 事件

```text
session.started
context.ready
assistant.delta
assistant.tool_call
assistant.approval_required
assistant.operation_preview
assistant.completed
assistant.failed
job.progress
```

客户端使用 `Last-Event-ID` 恢复流；服务端保存最近事件，避免网络抖动导致内容丢失。

`POST /messages` 返回 `202 Accepted` 和 `message_id`；客户端随后订阅 `/events`。事件至少包含单调递增的 `id`、`session_id`、`type` 和 `created_at`。事件保留到会话完成后至少 24 小时，过期的 `Last-Event-ID` 返回明确的重新拉取指令。

## 10. 安全与隐私

模型、Embedding、Rerank 和网页搜索都可能把项目内容发送到外部服务。每次调用显示数据流向和发送范围；本地模型可以完全离线运行。外部调用默认只发送当前任务必需的上下文，并提供脱敏/不发送正文选项。

- 默认只监听 `127.0.0.1`；公网部署必须显式设置 host。
- 远程 HTTPS 部署使用 Argon2id 密码哈希和 HttpOnly、SameSite、Secure Cookie；Windows localhost 默认使用短期本地令牌。
- Windows 桌面端优先使用 DPAPI/凭据管理器保护 API Key；服务端部署再使用 Fernet 或 AES-GCM，密钥来自环境变量或权限受控的密钥文件。
- CORS 默认关闭跨域，改为显式 allowlist。
- 日志禁止正文、Prompt、API Key 和完整工具参数；异常上报默认关闭。
- 外部搜索和模型请求显示数据流向提示。
- 导出包可选加密；备份前显示包含哪些内容。
- 所有写入操作记录操作者类型（本地用户、AI 会话或插件）、来源、时间、目标和前后哈希。

## 11. 可观测性与质量指标

产品指标：

- 单章编辑保存成功率。
- AI 首 token 延迟、完成率和取消率。
- 检索召回点击率、引用采纳率。
- AI 修改撤销率。
- 章节连续创作天数和字数趋势。

工程指标：

- API p95 延迟 < 300ms（不含 LLM）。
- 普通项目热启动时间 < 3 秒（基准机型、冷启动和 Sidecar 启动时间单独记录）。
- 10 万字项目首次 FTS 索引 < 10 秒；百万字项目作为压力测试，记录索引、搜索和内存曲线。
- 断线重连后事件恢复成功率 100%。
- 关键数据导出后可在空数据库完整恢复。

## 12. 目录建议

```text
app/
  api/              # 路由和 schema
  domain/           # 项目、章节、实体、伏笔
  ai/               # provider、上下文、工作流、工具
  retrieval/        # FTS5 和可选向量适配器
  persistence/      # SQLAlchemy、迁移、仓储
  revisions/        # operation、diff、恢复
  export/           # Markdown、JSON、DOCX、EPUB
  jobs/             # SQLite 持久化任务
frontend/
  features/editor/
  features/assistant/
  features/knowledge/
  features/timeline/
  features/revisions/
  features/settings/
  lib/api/
  lib/sse/
```

## 13. 版本路线图

- **0.1 基础闭环**：项目、章节、编辑器、单 Provider、AI 流式对话、版本记录。
- **0.2 安全写入**：操作事务、选区操作、审批、冲突检测、Prompt 分层和上下文预览。
- **0.3 故事图谱**：实体、来源、状态快照、时间线、伏笔和确定性约束。
- **0.4 生产力**：批量审稿、摘要、创作分析、基础备用模型和完整导出。
- **0.5 扩展**：可选向量检索、专家工作流、评测集、受限插件隔离和本地离线草稿。
- **1.0 Windows 交付**：Tauri Windows 桌面版、稳定迁移协议、更新签名、性能和安全基线；PWA 作为后续交付形态。

## 14. 功能领先验收指标

- 任何 AI 正文修改都能逐条预览、接受、拒绝、撤销和恢复。
- 100% 的 AI 引用可以跳转到章节、实体或事件证据。
- 设定冲突报告至少包含规则、证据和建议，不只返回自然语言结论。
- 20 个章节批量审稿可以暂停、恢复和导出报告。
- Prompt 或模型变更后可以在固定评测集上比较质量、成本和延迟。
- 断网期间的编辑操作在恢复网络后可合并或明确标记冲突。
- 在无向量依赖时，核心搜索、审稿和故事图谱仍可用。

## 15. 成功标准

用户在 5 分钟内可以创建作品、配置一个模型、写下第一章并完成一次 AI 辅助修改；用户可以看到 AI 使用的上下文和引用；任何 AI 写入都能在一个操作内预览、拒绝或恢复；删除或迁移应用不会导致作品被锁定。

1.0 发布前必须满足：10 万字项目可稳定编辑和 FTS5 搜索；20 章批量审稿可暂停、恢复并导出证据报告；Prompt/模型变更可在固定评测集上比较；断网编辑可恢复并提供冲突合并；无向量依赖时核心功能完整可用；Windows 10/11 x64 安装、升级、卸载和数据恢复通过验收。















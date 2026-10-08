# 股析 · AI 投研委员会

> 多智能体（4 个分析 Agent + 1 个 CIO 首席投资官）模拟专业投研团队，为个人投资者提供**可解释、可追溯**的投资研判助手。

## 项目简介

个人投资者往往只盯单一指标，而专业机构依靠**团队辩论**做决策。本项目用多个 AI Agent 模拟这样一支团队：宏观情绪 / 基本面 / 技术面 / 风控（**一票否决权**）各自独立取数、独立表态、互相引用，最后由 **CIO 首席投资官** 综合各方观点，输出带置信度标签与风控结论的《投资备忘录》。

系统的关键设计，是把"严谨的数学计算"与"大模型的分析推理"**严格分开**——指标只由代码计算，大模型只做意图识别、调度与口语化解读，从架构上杜绝"用 if-else 写死剧本"与"大模型胡乱算指标"两类问题。

## 核心特性

| 模块 | 能力 |
|---|---|
| **AI 投研委员会** | 4 个 Agent 气泡式逐步推理 → CIO 博弈裁决（置信度标签、风控否决、折中方案） |
| **组合压力测试** | 录入持仓 → 年化 / 波动 / 最大回撤 / 夏普 / VaR + **蒙特卡洛扇形图**（含 95% VaR 红线）+ 加息·衰退情景冲击与对冲建议 |
| **量化仪表盘** | 技术分析 / 动量&风险 / 多因子 / CAPM 四方法 + ECharts K 线（标注历史最大回撤） |
| **文档问答 RAG** | 上传 / 粘贴财报·纪要 → 检索 + 生成**带引用来源**的回答 |

## 系统架构

系统分为五层，计算与推理职责清晰隔离：

- **数据层（Data Layer）**：本地合规回测快照（2021–2026，`data/csv/*.csv`）+ 可切换的 Tushare / AkShare 实时 API。所有数据来源可溯、对外统一标注。
- **计算层（Compute Layer）**：Python 量化引擎做**确定性数学计算**（夏普比率、最大回撤、MACD 金叉死叉、蒙特卡洛模拟等），结果是可复现、零幻觉的"硬数字"。
- **AI 技术层（AI Layer）**：大模型（LLM）+ RAG，仅负责语言理解与生成。
- **Agent 编排层（Orchestration Layer）**：多智能体（4 Agent + CIO）调度与博弈裁决，大模型**不直接计算任何指标**。
- **前端展示层（Presentation Layer）**：HTML + ECharts，玻璃拟态深色主题。

> **技术严谨性声明**：指标由代码算，AI 只做解读和裁判，绝不瞎算。架构图见 `architecture.png`，时序图见 `sequence.png`（均已嵌入《项目说明书.docx》）。

## 目录结构

```
stock_demo/
├── app.py                 # Flask 后端（路由、接口）
├── analysis.py            # Python 量化引擎（确定性计算）
├── llm.py                 # 大模型调用 + 多智能体编排（离线容错）
├── build_data.py          # 准备本地行情数据（本地优先）
├── build_rag_corpus.py    # 构建 RAG 语料
├── import_real_csvs.py    # 导入真实 CSV 行情
├── make_assets.py         # 生成架构图 / 时序图
├── gen_docx.py            # 生成《项目说明书.docx》
├── shot.mjs               # 开发用：无头浏览器截图（生成文档配图）
├── 启动demo.bat           # Windows 一键启动
├── config.json            # 本地配置（离线安全默认，已提交）
├── config.example.json    # 配置模板（启用大模型时参考）
├── requirements.txt       # 依赖
├── templates/index.html   # 前端单页
├── static/                # 前端依赖（已本地化：echarts.min.js 等）
├── data/                  # 本地行情快照（csv / prices.db / json）
├── rag_corpus/            # RAG 检索语料（.md）
├── shots/                 # 《项目说明书》配图
├── architecture.png       # 五层架构图
├── sequence.png           # 系统时序图
└── 项目说明书.docx        # 项目说明文档
```

## 快速开始

```bash
pip install -r requirements.txt
python build_data.py    # 准备本地历史回测数据（本地优先，见下）
python app.py           # 打开 http://127.0.0.1:5000
```

Windows 用户也可直接**双击 `启动demo.bat`**（会自动装依赖、备数据、起服务）。

**不配置任何大模型也能完整运行**：系统在离线模式下使用本地推理引擎，用真实量化结果生成口语化的辩论与备忘录，结论有据可查。

## 数据说明

为保证稳定性（不因网络 / 限流 / 地域限制导致图表空白），数据层采用**本地优先**策略：

| 优先级 | 数据源 | 说明 |
|---|---|---|
| 1 | 本地历史快照 `data/csv/*.csv` | 真实行情快照（2021–2026），直接读取，零外网、零报错 |
| 2 | 本地高仿真回测引擎（内置兜底） | GBM + 波动率聚集 + 回撤约束，缺快照时自动生成，回撤控制在 20%~30% |
| 3 | Tushare / AkShare 实时 API（可选） | 一行接入即可切换真实实时行情 |

所有标的对外统一标注为 **「数据源：历史真实回测数据 (2021-2026)」**。

### 切换到实时行情（可选）

```python
# —— 一行接入 Tushare，切换真实实时行情 ——
import tushare as ts
ts.set_token("YOUR_TOKEN")
pro = ts.pro_api()
df = pro.daily(ts_code="600519.SH", start_date="20210101", end_date="20261007")
df = df.rename(columns={"trade_date":"date","vol":"volume"})[["date","open","high","low","close","volume"]]
df.to_csv("data/csv/600519.csv", index=False)   # 落盘即被系统采用
```

## 接入大模型（可选）

编辑 `config.json`（参考 `config.example.json`）：

```json
{ "llm": { "enabled": true, "base_url": "https://api.deepseek.com/v1",
           "api_key": "sk-xxx", "model": "deepseek-chat" } }
```

也支持环境变量 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 覆盖。支持 DeepSeek / OpenAI / 通义 / 智谱。

> 注意：仓库默认离线运行，**无需任何配置即可启动**。如需启用大模型，复制 `config.example.json` 为 `config.json` 并填入 Key 即可；该文件已被 `.gitignore` 忽略，不会被提交到公开仓库，可放心使用。

## 典型使用路径

1. **AI 投研委员会**：点"召开投研委员会" → 右侧 ECharts K 线标注"历史最大回撤" → 左侧 4 个 Agent 逐步浮现、互相引用 → CIO 备忘录 + 置信度条 + 折中裁决。
2. **组合压力测试**：录入持仓 → 运行 → 蒙特卡洛扇形图（95% VaR 红线）→ 加息 / 衰退情景表与对冲建议。
3. **量化仪表盘**：切换四种分析方法查看个股。
4. **文档问答 RAG**：粘贴一段财报文字 → 提问 → 获得带引用来源的回答。

## 技术栈

- 后端：Python + Flask + pandas / numpy + 自研轻量多智能体编排
- 前端：HTML + **ECharts**（已本地化离线可用），玻璃拟态深色主题（#0D1117）
- 数据：本地 CSV 快照 / 高仿真回测引擎 → SQLite / JSON（可切 Tushare / AkShare）
- RAG：文档切分 → 中文二元重叠检索 → LLM 生成并引用（无需向量库即可运行）

> 编排层为纯 Python 自研实现，与 Dify / LangGraph 架构兼容、可平滑迁移；未引入低代码平台，以保证对 Agent 编排的理解可见、且零平台依赖、离线可跑。

## 合规与声明

- **数据合规**：Demo 采用本地历史快照（2021–2026），仅供演示与教学，**不构成投资建议**。界面右上角提供 `i` 图标，悬停即见该声明。
- **AI 生成内容标注**：系统所有由大模型生成的文本（投研辩论、CIO 备忘录、RAG 问答）均为 **AI 生成内容**，结论由历史数据推导、存在偏差，仅供参考、风险自担；涉及具体数字时均引用计算层真实输出，不虚构任何指标。
- **RAG 可溯源**：文档问答的回答附带来源片段高亮，可定位原文，杜绝"张冠李戴"。

## 许可证

本项目以 [MIT License](./LICENSE) 开源。版权信息见 `LICENSE` 文件。

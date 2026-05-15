# CLAUDE.md

> 这是给 Claude Code（或其他 AI 编程助手）阅读的项目说明书。
> 每次开始新的编程会话时，请先完整阅读本文件。

---

## 项目目标

构建一个**个人投资研究助理系统**，每日自动：
1. 抓取用户关注板块的新闻（AI、储能、新能源、国债等）
2. 调用 DeepSeek V4 Pro 做摘要 + 投资视角点评
3. 生成**小红书图文格式**的草稿（封面图 + 正文 + 数据图表）
4. 推送到用户手机，**由用户人工审核后发布**（不自动发）

后续阶段会扩展：周度深度策略报告、数据看板、Wind 数据深度整合。

## 当前阶段：第一周 MVP

**只做这件事**：每日早晨 7:30，用户微信收到一份带 AI 点评的板块简报草稿。

**不要在这一阶段做的事**（防止 over-engineering）：
- 不做数据库（用本地 JSON / SQLite 文件）
- 不做 Web 界面
- 不做用户系统、登录、权限
- 不做小红书自动发布（永远不做，合规风险）
- 不做复杂的图表（先文字 + 简单 PNG 图表即可）
- 不做周报、月报（第二阶段）

## 用户画像

- 个人投资者，有 Wind 终端账号（普通终端版，假设带 WindPy 权限）
- 不写代码或代码能力有限，依赖 AI 编程助手生成代码
- 运行环境：一台**专用 Mac**，24 小时开机，Wind 终端保持登录
- 关注 A 股 + 部分美股 + 宏观利率

## 技术栈

| 类别 | 选型 | 备注 |
|---|---|---|
| 语言 | Python 3.10+ | |
| 操作系统 | macOS | |
| AI 模型 | DeepSeek V4 Pro | `deepseek-v4-pro`，OpenAI 兼容协议，base_url `https://api.deepseek.com` |
| 数据：行情/宏观 | WindPy | 需 Wind 终端常驻登录 |
| 数据：新闻 | 财联社电报、华尔街见闻、Wind 资讯（暂定） | 通过 RSS / 公开接口 / WindPy |
| 推送 | Server 酱（Turbo 版） | https://sct.ftqq.com/ |
| 图表 | matplotlib + 中文字体 | 简单清晰即可 |
| 定时 | macOS launchd | 比 cron 更稳，开机自启 |
| 日志 | loguru | 比 logging 好用 |

## 目录结构

```
invest_brief/
├── CLAUDE.md              # 本文件
├── README.md              # 用户上手文档
├── requirements.txt
├── .env.example
├── .gitignore
│
├── config/
│   ├── sectors.yaml       # 关注板块定义、关键词、Wind 代码
│   └── settings.yaml      # 全局设置
│
├── src/
│   ├── main.py            # 主入口
│   ├── collectors/        # 数据采集层
│   ├── processors/        # 处理层（过滤、摘要、格式化）
│   ├── publishers/        # 推送层
│   └── utils/             # 工具（LLM 客户端、图表、日志）
│
├── prompts/
│   ├── framework.md       # ⭐ 用户的投资框架（最关键）
│   └── daily_brief.txt    # 每日简报 prompt 模板
│
├── output/                # 生成的草稿和图表
├── data/                  # 缓存
└── logs/
```

## 代码规范偏好

1. **中文注释**，函数 docstring 必写
2. **错误处理**：所有外部请求（HTTP、Wind、LLM）必须 try/except，失败时降级而非崩溃
3. **重试**：网络请求用 `tenacity` 做指数退避
4. **缓存**：当日新闻和 Wind 数据缓存到 `data/`，调试时复用
5. **日志**：用 loguru，`from loguru import logger`
6. **类型注解**：函数参数和返回值都加 type hint
7. **配置外置**：所有"可能改的"参数放进 `config/*.yaml`，不要硬编码

## ⭐ 投资框架（最关键）

详见 `prompts/framework.md`。**任何摘要任务都要先加载这个文件作为 system prompt 的一部分。**

要点：
- 关注：AI 算力、储能、新能源车、国债利率、海外宏观
- 强信号 = 政策/业绩/超预期数据；弱信号 = 传闻/股价异动
- 点评风格：克制、有数据、多视角、不喊口号

## 输出格式：小红书图文

每日草稿三部分：
1. **封面图** PNG（3:4 比例）：日期 + 板块 + 一句话核心结论 + 关键数据
2. **正文** ≤800 字：钩子 + 3-5 条要闻点评 + 今日观察 + 标签
3. **数据图表** 1-3 张 PNG：板块涨跌、资金流向、关键利率

存放：`output/drafts/YYYY-MM-DD/`

## 常见任务 SOP

### 加新闻源
1. `src/collectors/` 新建 `news_xxx.py`，实现 `fetch() -> List[NewsItem]`
2. `config/sources.yaml` 注册（如无此文件则创建）
3. `src/main.py` 采集循环加上

### 调整点评风格
1. 改 `prompts/framework.md`
2. 改 `prompts/daily_brief.txt`
3. **不要**直接改 `summarizer.py` 里的字符串

### 加新板块
- 只改 `config/sectors.yaml`，不动代码

### 调试不发推送
- `DRY_RUN=true python src/main.py`

## 注意事项

1. **API key 永远不要进 git**
2. **Wind 终端必须保持登录**：启动时做健康检查
3. **测试用历史日期**：`python src/main.py --date 2025-01-15`
4. **DeepSeek 成本**：折扣期约 1-3 元/天
5. **小红书绝不自动发布**：草稿生成后只推送给用户

## 路线图

- **第 1 周**：跑通基础流程，每日推送文本草稿
- **第 2 周**：加封面图 + 数据图表
- **第 3 周**：调优 prompt，让点评接近用户的水准
- **第 4-6 周**：接入更多 Wind 数据；周报雏形
- **第 7 周+**：本地数据看板（Streamlit）；深度研报生成

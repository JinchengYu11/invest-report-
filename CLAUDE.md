# CLAUDE.md

> 这是给 Claude Code（或其他 AI 编程助手）阅读的项目说明书。
> 每次开始新的编程会话时，请先完整阅读本文件。

---

## 项目目标

构建一个**个人投资研究助理系统**，每日自动：
1. 抓取用户关注板块的新闻
2. 调用 DeepSeek V4 Pro 做摘要 + 投资视角点评
3. 生成投资备忘录草稿（后续加图表）
4. 推送到用户微信，**由用户人工审核后发布**（不自动发）

## 当前状态

**基本流程已跑通**（2026-05-16）：

| 步骤 | 文件 | 状态 |
|------|------|------|
| 新闻采集 | `src/collectors/news_cls.py` | 完成（财联社电报） |
| 行情数据 | `src/collectors/market_data.py` | 完成（新浪 + 东方财富免费 API） |
| 行情数据（备选） | `src/collectors/wind_data.py` | 占位（等 WindPy 可用后切回） |
| 过滤分组 | `src/processors/filter.py` | 完成 |
| AI 摘要 | `src/processors/summarizer.py` | 完成（DeepSeek V4 Pro，thinking 模式） |
| 草稿生成 | `src/processors/formatter.py` | 完成 |
| 推送 | `src/publishers/serverchan.py` | 完成（Server 酱 → 微信） |
| 定时 | `scripts/com.user.invest_brief.plist` | ✅ 已部署（每天 7:30） |
| LLM 容错 | `src/utils/llm.py` | ✅ 已加固（180s 超时，5 次重试） |

**尚未完成**：
- 封面图 + 图表生成（`utils/chart.py`）
- WindPy 接入（Mac App Store 版 Wind 不支持 Python 接口，需联系客服要非沙盒版 DMG）
- 第二个新闻源（华尔街见闻）

### 内容框架（已迭代多轮）

逻辑线：**宏观背景 → 四大科技产业链（按当天新闻展开）→ 今日观察**

四大科技产业链：
1. 🧠 AI（上游芯片/HBM → 中游光模块/光纤 → 下游模型/SaaS）
2. 🤖 人形机器人（上游零部件 → 中游本体 → 下游应用）
3. 🔬 半导体/先进制造（上游设备/材料 → 中游制造/封装 → 下游芯片）
4. 🚗 智能驾驶（上游感知硬件 → 中游方案 → 下游整车/Robotaxi）

原则：有新闻的产业链展开写，没有的直接不出现。

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
| 数据：新闻 | 财联社电报 | 公开 JSON 接口 |
| 推送 | Server 酱（Turbo 版） | https://sct.ftqq.com/ |
| 图表 | matplotlib + 中文字体 | 待实现 |
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
│   └── settings.yaml      # 全局设置（LLM/输出/定时）
│
├── src/
│   ├── main.py            # 主入口（5 步流程已串联）
│   ├── collectors/
│   │   ├── news_cls.py      # 财联社电报采集
│   │   ├── market_data.py   # 免费行情数据（新浪+东方财富，当前主力）
│   │   └── wind_data.py     # Wind 行情数据（占位，等 WindPy）
│   ├── processors/
│   │   ├── filter.py      # 去重 + 板块分组
│   │   ├── summarizer.py  # LLM 摘要
│   │   └── formatter.py   # DraftPackage 生成
│   ├── publishers/
│   │   └── serverchan.py  # Server 酱微信推送
│   └── utils/
│       ├── models.py      # 数据模型
│       └── llm.py         # DeepSeek 客户端封装
│
├── prompts/
│   ├── framework.md       # ⭐ 投资框架（产业链地图 + 点评价值观）
│   └── daily_brief.txt    # 每日简报 prompt 模板
│
├── scripts/
│   └── com.user.invest_brief.plist  # launchd 定时任务
│
├── output/                # 生成的草稿
│   └── drafts/YYYY-MM-DD/
├── data/news_cache/       # 新闻采集缓存
└── logs/
```

## 代码规范偏好

1. **中文注释**，函数 docstring 必写
2. **错误处理**：所有外部请求（HTTP、Wind、LLM）必须 try/except，失败时降级而非崩溃
3. **重试**：网络请求用 `tenacity` 做指数退避
4. **缓存**：当日新闻缓存到 `data/news_cache/`，调试时复用
5. **日志**：用 loguru，`from loguru import logger`
6. **类型注解**：函数参数和返回值都加 type hint
7. **配置外置**：所有"可能改的"参数放进 `config/*.yaml`，不要硬编码

## 内容调优（最重要）

输出质量 90% 取决于 prompt，不要改代码逻辑：

### 调整排版/文风/结构
→ 改 `prompts/daily_brief.txt`

### 调整分析框架/产业链逻辑/点评价值观
→ 改 `prompts/framework.md`

### 加新板块或调关键词
→ 只改 `config/sectors.yaml`

## 常见任务 SOP

### 加新闻源
1. `src/collectors/` 新建 `news_xxx.py`，实现 `fetch() -> List[NewsItem]`
2. `src/main.py` 采集循环加上

### 调整产业链结构
1. 改 `prompts/framework.md`（加产业链地图）
2. 改 `prompts/daily_brief.txt`（加输出格式）
3. 改 `config/sectors.yaml`（加板块关键词）

### 跑当天 / 指定日期 / 调试
- `source venv/bin/activate && python src/main.py`                       # 当天
- `python src/main.py --date 2025-11-01`                                # 历史回测
- `DRY_RUN=true python src/main.py`                                     # 只生成不推送
- `DRY_RUN=true python src/main.py --date 2025-11-01`                   # 历史回测 + 不推送

## 注意事项

1. **API key 永远不要进 git**（`.env` 在 `.gitignore` 中）
2. **Wind 终端必须保持登录**：启动时做健康检查
3. **DeepSeek 成本**：折扣期约 1-3 元/天
4. **小红书绝不自动发布**：草稿生成后只推送给用户
5. **输出不加免责声明**：用户自己审核，不需要"以上为 AI 辅助整理"那行

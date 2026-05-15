# 投资研究助理（每日简报版）

每天早上 7:30 自动推送一份**小红书格式的板块投资简报草稿**到你的微信，你审核后手动发布。

---

## 快速上手（首次配置，约 30 分钟）

### 1. 装环境（5 分钟）

```bash
cd ~/Documents
# 复制本项目文件夹到这里，命名为 invest_brief
cd invest_brief

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 装 WindPy（5 分钟）

1. 打开 Wind 终端，登录
2. 命令栏输入 `WAPI`，按提示安装 Python 插件
3. 终端测试：`python -c "from WindPy import w; w.start(); print(w.isconnected())"`
4. 看到 `True` 就成了

常见问题：
- Wind 终端没登录 → 登录
- Python 版本和 Wind 插件不匹配 → 用 3.9 或 3.10

### 3. 配置 API key 和推送（5 分钟）

```bash
cp .env.example .env
# 编辑器打开 .env 填：
# - DEEPSEEK_API_KEY=sk-xxx  (platform.deepseek.com 申请)
# - SERVERCHAN_KEY=SCTxxx    (sct.ftqq.com 扫码绑微信)
```

### 4. 定义关注板块（10 分钟）

打开 `config/sectors.yaml`，按模板改成你关心的板块、关键词、Wind 代码。

### 5. 跑一次试试

```bash
# 不发推送，只在本地生成草稿（调试用）
DRY_RUN=true python src/main.py

# 完整跑一次（会推送到微信）
python src/main.py
```

去 `output/drafts/` 看今天的草稿；微信看推送。

### 6. 设置每天自动跑（5 分钟）

```bash
cp scripts/com.user.invest_brief.plist ~/Library/LaunchAgents/
# 编辑该文件，把 PATH_TO_PROJECT 改成真实路径
launchctl load ~/Library/LaunchAgents/com.user.invest_brief.plist
launchctl list | grep invest_brief
```

完事。明早 7:30 收第一份草稿。

---

## 日常使用

### 收到草稿后怎么发小红书

1. 微信收 Server 酱推送（标题 "📊 今日投资简报草稿 - YYYY-MM-DD"）
2. 点开看 AI 写好的小红书文案
3. 打开 `output/drafts/YYYY-MM-DD/` 取封面图和图表 PNG
4. 满意 → 复制到小红书发布
5. 不满意 → 改文案；如果是 AI 写偏了，编辑 `prompts/framework.md`，明天改善

### 临时跑一次

```bash
python src/main.py
```

### 用历史日期回测

```bash
python src/main.py --date 2025-11-01
```

### 看日志

```bash
tail -f logs/main.log
```

---

## 常见问题

**Q：Wind 终端要每天手动登录吗？**
A：开启 Wind 的"自动登录"。脚本启动时也会检查连接，断了发警告推送。

**Q：DeepSeek 一天花多少钱？**
A：当前折扣期约 1-3 元，月几十块。

**Q：能换成飞书 / Telegram 吗？**
A：能。`src/publishers/` 加新文件实现 `push(content, images)` 即可。

**Q：能自动发小红书吗？**
A：**不行也别做**。账号被封风险高。审核 + 手动发是核心设计。

**Q：草稿质量不满意怎么办？**
A：90% 改 `prompts/framework.md` 就能解决。把你对"什么是好点评"写得更具体。

---

详细架构见 `CLAUDE.md`。

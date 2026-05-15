# M_P_Agent — 多平台竞品分析 Agent

基于大语言模型的电商竞品分析工具，支持通过自然语言对话驱动，自动抓取多个电商平台的商品数据、买家评论，并输出结构化 CSV 报告。

## 支持平台

| 平台 | 地区 | 数据来源 | 货币 |
|------|------|----------|------|
| Amazon | 美国 | Playwright 爬虫 + XLSX | USD |
| eBay | 美国 | Playwright 爬虫 | USD |
| Temu | 美国 | Apify Actor | USD |
| Ozon | 俄罗斯 | Apify Actor | RUB → USD |
| Otto | 德国 | httpx 爬虫 | EUR → USD |
| Allegro | 波兰 | Apify Actor | PLN → USD |
| TikTok Shop | 美国 | Apify Actor | USD |
| Cdiscount | 法国 | Apify Actor | EUR → USD |

## 功能

- 自然语言对话：输入"帮我分析 doogee 在 temu 上的竞品，5个"即可启动分析
- 自动补足数量：当单次抓取/API 调用结果不足时，自动扩页或重试直到满足目标数量
- 评论 LLM 总结：提取买家好评/差评，用本地 LLM 生成中文优缺点摘要
- CSV 导出：每次分析结果保存为带时间戳的 CSV 文件
- SSE 实时进度：前端通过 Server-Sent Events 实时展示抓取进度

## 项目结构

```
mp_agent/
├── application/
│   ├── primary_agent.py        # 对话槽位提取与平台路由
│   ├── competitor_workflows.py # 各平台分析工作流
│   ├── workflow_registry.py    # 工作流注册表
│   └── agent_service.py        # 会话管理与运行调度
├── domain/
│   └── analysis.py             # LLM 分析行构建（gemma 模型）
├── infrastructure/
│   ├── amazon.py / ebay.py / temu.py / ozon.py
│   ├── otto.py / allegro.py / tiktokshop.py / cdiscount.py
│   └── artifacts.py            # CSV 写入
└── presentation/
    └── http.py                 # FastAPI + SSE 接口

frontend/                       # 单页前端（原生 JS）
config/
└── config.py                   # API 密钥、模型地址（已加入 .gitignore）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
# eBay/Amazon Playwright 爬虫还需要：
pip install playwright playwright-stealth
playwright install chromium
```

### 2. 配置

复制并填写配置文件（不会被提交到 git）：

```bash
cp config/config.example.py config/config.py
```

`config/config.py` 需要填写的字段：

```python
# 本地 LLM（基础设施层，用于商品分析）
LLM_BASE_URL = "http://<host>:8000/v1"
LLM_MODEL = "qwen3.6-35b-a3b-fp8"

# 本地 LLM（领域层，用于评论总结）
ANALYSIS_LLM_BASE_URL = "http://<host>:8005/v1"
ANALYSIS_LLM_MODEL = "gemma-4-31b-it-fp8"

# Apify（temu / ozon / allegro）
APIFY_API_TOKEN = "apify_api_..."

# Apify（tiktokshop / cdiscount）
APIFY_API_TOKEN_2 = "apify_api_..."

# Amazon XLSX 路径（本地 Amazon 工具输出）
ASIN_LIST_XLSX_PATH = "/path/to/asin_list.xlsx"
ALL_REVIEWS_XLSX_PATH = "/path/to/all_reviews.xlsx"
```

### 3. 启动服务

```bash
uvicorn app:app --reload --port 8080
```

浏览器打开 `http://localhost:8080`，在对话框中输入分析请求即可。

## 使用示例

```
帮我看一下 doogee 在 temu 的竞品，5个
分析 blackview 在 amazon 上的竞品，10个
查一下 headphones 在 ebay 上的竞品，8个
```

Agent 会自动识别平台和数量，完成后在 `artifacts/` 目录生成 CSV 文件。

## 运行测试

```bash
pytest tests/
```

## 依赖说明

- **FastAPI + uvicorn**：HTTP 服务与 SSE 流
- **openai**：调用本地 LLM（兼容 OpenAI API 格式）
- **apify-client**：调用 Apify Actor（Temu / Ozon / Allegro / TikTok Shop / Cdiscount）
- **playwright + playwright-stealth**：Amazon / eBay 反爬虫浏览器自动化
- **httpx**：Otto 轻量 HTTP 爬虫

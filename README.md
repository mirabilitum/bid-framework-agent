# Bid Framework Generator Agent

[English](README_EN.md) | 中文

将任意甲方招标/磋商文件（PDF/DOCX/DOC）自动转化为标书响应框架目录（Word文档）。

## 工作原理

```
招标文件 ──→ 文档解析 ──→ LLM 分析 ──→ LLM 生成框架 ──→ Word 文档
 (PDF/DOCX)   提取文本     提取评分标准     构建层级化       格式化输出
              表格/截图    格式要求/需求     框架结构
```

核心思路：**让 LLM 理解文档语义，代码只做解析和渲染**。LLM 是可插拔的后端引擎，你用哪家都行。

## 支持的 LLM

| Provider | 命令 | 需要 API Key |
|----------|------|-------------|
| Claude (Anthropic) | `--provider claude` | `ANTHROPIC_API_KEY` |
| OpenAI GPT | `--provider openai` | `OPENAI_API_KEY` |
| Kimi (Moonshot) | `--provider kimi` | `OPENAI_COMPATIBLE_API_KEY` |
| DeepSeek | `--provider deepseek` | `OPENAI_COMPATIBLE_API_KEY` |
| Google Gemini | `--provider gemini` | `OPENAI_COMPATIBLE_API_KEY` |
| 通义千问 (Qwen) | `--provider qwen` | `QWEN_API_KEY` |
| Ollama (本地) | `--provider ollama` | 不需要 |
| 任意 OpenAI 兼容 API | `--provider openai-compatible` | 视服务而定 |
| Mock (测试) | `--provider mock` | 不需要 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入你使用的 LLM 的 Key：

```bash
cp .env.example .env
# 编辑 .env，取消注释并填入你的 Key
```

或者通过环境变量：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # Claude
export OPENAI_API_KEY="sk-..."          # OpenAI
```

### 3. 运行

```bash
# 用 Claude
python main.py -i 招标文件.pdf -p claude

# 用 OpenAI GPT-4o
python main.py -i 招标文件.pdf -p openai --model gpt-4o

# 用 Kimi
python main.py -i 招标文件.pdf -p kimi --api-key sk-xxx

# 用 DeepSeek
python main.py -i 招标文件.pdf -p deepseek --api-key sk-xxx

# 用本地 Ollama
python main.py -i 招标文件.pdf -p ollama --model llama3

# 指定输出路径
python main.py -i 招标文件.pdf -o output/框架.docx -p claude

# 多包文档，只处理包1和包2
python main.py -i 招标文件.pdf -d output/ --packages 1,2

# 保存中间 JSON（分析结果 + 框架结构）
python main.py -i 招标文件.pdf -d output/ --save-json

# 测试模式（不需要 API Key）
python main.py -i 招标文件.pdf -p mock

# 查看所有支持的 provider
python main.py --list-providers
```

### 作为 Python 模块使用

```python
from src import BidFrameworkAgent

# 用 Claude
agent = BidFrameworkAgent(llm_provider="claude")
agent.run(input_file="招标文件.pdf", output_file="output/框架.docx")

# 用 Kimi
agent = BidFrameworkAgent(llm_provider="kimi", api_key="sk-xxx")
agent.run(input_file="招标文件.pdf", output_file="output/框架.docx")

# 用本地 Ollama
agent = BidFrameworkAgent(llm_provider="ollama", model="llama3")
agent.run(input_file="招标文件.pdf", output_file="output/框架.docx")
```

## 功能特性

- **多格式支持**：PDF、DOCX、DOC
- **多 LLM 后端**：9 种 Provider 开箱即用，支持自定义扩展
- **PDF 视觉识别**：自动截图格式模板页面，通过 Vision API 识别排版格式
- **多包处理**：自动检测多采购包，支持评分标准共用判断
- **格式完整保留**：居中/右对齐/缩进/表格等格式标记，渲染为 Word 原生格式
- **骨架原封不动**：严格复制招标文件原文结构，不自创分组
- **`.env` 配置**：API Key 写在 `.env` 文件里，不用每次传参

## 项目结构

```
bid-framework-agent/
├── main.py                  # CLI 入口
├── requirements.txt         # 依赖
├── .env.example             # API Key 配置模板
├── src/
│   ├── __init__.py
│   ├── agent.py             # 主控调度器
│   ├── document_parser.py   # 文档解析（PDF/DOCX/DOC）
│   ├── llm_provider.py      # LLM 接口层（多后端 + 别名 + 自注册）
│   ├── llm_analyzer.py      # LLM 文档分析
│   ├── llm_generator.py     # LLM 框架生成
│   └── document_generator.py # Word 文档生成
├── prompts/
│   ├── analyze_prompt.txt   # 分析提示词（~240行）
│   └── generate_prompt.txt  # 生成提示词（~390行）
├── shared/                  # 共享资源
└── output/                  # 输出目录
```

## 添加自定义 LLM Provider

```python
from src.llm_provider import BaseLLMProvider, register_provider

class MyProvider(BaseLLMProvider):
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key

    def generate(self, prompt, max_tokens=4096, **kwargs):
        # 调用你的 LLM API
        return "..."

register_provider("my-llm", MyProvider)
```

然后 `python main.py -i 文件.pdf -p my-llm` 即可。

## 提示词说明

本项目的核心在于精心设计的提示词，位于 `prompts/` 目录：

### `analyze_prompt.txt` — 文档分析

指导 LLM 从招标文件中提取：
- 项目基本信息（名称、采购方式、预算）
- 评分标准（名称、分值、类别、子项）
- 响应文件格式骨架（5 级优先级源）
- 格式模板完整正文（含视觉对齐标记）
- 采购需求（全文扫描，按主题分类）

### `generate_prompt.txt` — 框架生成

指导 LLM 基于分析结果构建框架：
- 格式模板优先于骨架结构
- 禁止自创分组，严格复制原文
- 仅在"内容格式自拟"节点下展开评分因素
- 完整填充模板文字和评分标准原文
- 支持多包合并/分离策略

## 格式标记规范

提示词和代码之间通过格式标记协议通信：

| 标记 | 含义 | Word 渲染 |
|------|------|-----------|
| `[CENTER]文字` | 居中 | 段落居中对齐 |
| `[RIGHT]文字` | 右对齐 | 段落右对齐 |
| `[TABLE_START]...[TABLE_END]` | 表格 | Word 原生表格 |
| `【xxx】` | 章节头 | 加粗段落 |
| 2/4/6 空格缩进 | 层级缩进 | 视觉缩进 |

## 环境要求

- Python 3.10+
- Windows 上解析 `.doc` 格式需要安装 MS Word 和 `pywin32`

## License

MIT

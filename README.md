# Bid Framework Generator Agent

将任意甲方招标/磋商文件（PDF/DOCX/DOC）自动转化为标书响应框架目录（Word文档）。

## v7 更新说明

v7 是架构重写版本，相比 v6 的主要变化：

- **Prompt 拆分**：单体 prompt 拆为 6 步（分析 3 步 + 生成 3 步），每步专注一件事，规则遵循率大幅提升
- **Prompt Caching**：Claude 调用自动缓存文档上下文，6 步共享同一份缓存，输入 token 成本降低 ~75%
- **Streaming**：所有 Claude API 调用改为流式输出，彻底解决大 JSON 超时问题
- **语义分类法**：去除所有硬编码格式规则，LLM 按功能语义自动分类，任何招标文件格式零改动适配
- **DOCX 格式 1:1 复制**：格式章节内容直接从源文档程序化提取注入，不经 LLM 重新生成
- **模块化 CLI**：拆为独立脚本（parse → screenshot → extract_format → inject → render），支持 skill 模式逐步执行

## 工作原理

```
招标文件 ──→ 文档解析 ──→ LLM识别格式位置 ──→ 截图/提取格式 ──→ LLM分析(3步) ──→ LLM生成(3步) ──→ [DOCX注入] ──→ Word渲染
(PDF/DOCX)   纯文本+表格   LLM判断章节页码    PDF截图/DOCX段落   结构+检索+映射    骨架+展开+填充   格式章节1:1复制   格式化输出
```

核心思路：**让 LLM 理解文档语义，代码只做解析和渲染**。LLM 是可插拔的后端引擎。

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

> Claude 推荐：自动启用 prompt caching（system 消息缓存）和 streaming，成本最优。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # Claude
export OPENAI_API_KEY="sk-..."          # OpenAI
```

### 3. 模块化 CLI 工作流

v7 采用分步 CLI 脚本，每步可独立运行和调试：

```bash
# Step 1: 解析文档（提取文本+表格）
python cli_parse.py 招标文件.pdf -o output/

# Step 2: LLM 识别格式章节位置（人工确认页码范围）

# Step 3: 截图格式章节（PDF）/ 提取格式段落（DOCX）
python cli_screenshot.py 招标文件.pdf 37-45 -o output/screenshots/
python cli_extract_format.py 招标文件.docx "响应文件格式" -o output/

# Step 4-6: LLM 分析 + 生成（由 agent 或 skill 调度）

# Step 5.5: DOCX 格式注入（可选，DOCX 文档专用）
python cli_inject.py 招标文件.docx framework.json output.json

# Step 7: 渲染 Word
python cli_render.py framework.json -o 标书框架.docx
```

### 作为 Python 模块使用

```python
from src.llm_provider import create_llm_provider
from src.llm_analyzer import LLMAnalyzer
from src.llm_framework_generator import LLMFrameworkGenerator
from src.document_parser import DocumentParser
from src.document_generator import DocumentGenerator

# 创建 LLM provider
provider = create_llm_provider("claude")

# 解析文档
parser = DocumentParser()
text, tables = parser.parse("招标文件.pdf")

# LLM 分析（3步：结构提取→全文检索→交叉映射）
analyzer = LLMAnalyzer(provider)
analysis = analyzer.analyze(text, tables)

# LLM 生成框架（3步：骨架→评分展开→内容填充）
generator = LLMFrameworkGenerator(provider)
framework = generator.generate(analysis)

# 渲染 Word
doc_gen = DocumentGenerator()
doc_gen.generate(framework, "output/标书框架.docx")
```

## 功能特性

- **多格式支持**：PDF、DOCX、DOC
- **多 LLM 后端**：9 种 Provider 开箱即用，支持自定义扩展
- **Prompt Caching**：Claude 自动缓存文档上下文，多步调用共享缓存，降低 ~75% 输入成本
- **Streaming**：Claude 调用全部流式输出，防止大 JSON 超时
- **PDF 视觉识别**：自动截图格式模板页面，通过 Vision API 识别排版格式
- **DOCX 格式 1:1 复制**：格式章节直接从源文档程序化提取注入，精确还原排版
- **多包处理**：自动检测多采购包，支持评分标准共用判断
- **格式完整保留**：居中/右对齐/缩进/表格等格式标记，渲染为 Word 原生格式
- **骨架原封不动**：严格复制招标文件原文结构，不自创分组

## 项目结构

```
bid-framework-agent/
├── cli_parse.py              # 文档解析脚本
├── cli_screenshot.py          # PDF 格式章节截图
├── cli_extract_format.py      # DOCX 格式段落提取
├── cli_inject.py              # DOCX 格式内容注入
├── cli_render.py              # Word 渲染脚本
├── requirements.txt           # 依赖
├── src/
│   ├── __init__.py
│   ├── bid_framework_agent_v6.py  # 主控调度器
│   ├── document_parser.py     # 文档解析（PDF/DOCX/DOC）
│   ├── document_generator.py  # Word 文档生成
│   ├── llm_provider.py        # LLM 接口层（多后端 + 缓存 + 流式）
│   ├── llm_analyzer.py        # LLM 分析（3步拆分 prompt）
│   ├── llm_framework_generator.py  # LLM 框架生成（3步拆分 prompt）
│   ├── llm_utils.py           # LLM 调用工具（续写、完整性检测）
│   └── json_repair.py         # JSON 修复与提取
├── prompts/                   # v7 拆分提示词（6个文件）
│   ├── analyze_1_structure.txt    # 分析Step1: 结构提取
│   ├── analyze_2_search.txt       # 分析Step2: 全文检索
│   ├── analyze_3_mapping.txt      # 分析Step3: 交叉映射
│   ├── generate_1_skeleton.txt    # 生成Step1: 骨架构建
│   ├── generate_2_scoring.txt     # 生成Step2: 评分展开
│   └── generate_3_content.txt     # 生成Step3: 内容填充
└── shared/                    # 共享资源（通用格式模板等）
```

## Prompt 拆分架构

v7 将单体 prompt 拆为 6 步，每步专注一件事：

### 分析阶段（3步）

| 步骤 | 文件 | 任务 |
|------|------|------|
| Step 1 | `analyze_1_structure.txt` | 项目信息 + 评分标准 + 骨架 + 格式模板 |
| Step 2 | `analyze_2_search.txt` | 根据评分标准全文检索提取内容 |
| Step 3 | `analyze_3_mapping.txt` | 交叉填充 + 孤立需求识别 |

### 生成阶段（3步）

| 步骤 | 文件 | 任务 |
|------|------|------|
| Step 1 | `generate_1_skeleton.txt` | 骨架构建（content 留空） |
| Step 2 | `generate_2_scoring.txt` | 评分因素展开 |
| Step 3 | `generate_3_content.txt` | 内容填充（模板文字、表格、对齐标记） |

## 格式标记规范

提示词和代码之间通过格式标记协议通信：

| 标记 | 含义 | Word 渲染 |
|------|------|-----------|
| `[CENTER]文字` | 居中 | 段落居中对齐 |
| `[RIGHT]文字` | 右对齐 | 段落右对齐 |
| `[TABLE_START]...[TABLE_END]` | 表格 | Word 原生表格 |
| `[COLS:n]` | 指定列数 | 表格列数控制 |
| `[M:n]` | 横向合并 | 单元格合并 |
| 2/4/6 空格缩进 | 层级缩进 | 视觉缩进 |

## 添加自定义 LLM Provider

```python
from src.llm_provider import BaseLLMProvider, register_provider

class MyProvider(BaseLLMProvider):
    def generate(self, prompt, max_tokens=4096, **kwargs):
        # 调用你的 LLM API
        return "..."

register_provider("my-llm", MyProvider)
```

## 环境要求

- Python 3.10+
- Windows 上解析 `.doc` 格式需要安装 MS Word 和 `pywin32`

## License

MIT

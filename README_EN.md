# Bid Framework Generator Agent

[中文](README.md) | English

Automatically convert procurement/bidding documents (PDF/DOCX/DOC) into structured bid response framework outlines (Word documents).

## How It Works

```
Procurement Doc ──→ Parse ──→ LLM Analysis ──→ LLM Generation ──→ Word Output
  (PDF/DOCX)       Extract    Scoring criteria   Build hierarchical   Formatted
                   text/tables  Format/requirements  framework tree     document
```

Core idea: **let the LLM understand document semantics; code only handles parsing and rendering.** The LLM is a pluggable backend engine — use whichever provider you prefer.

## Supported LLM Providers

| Provider | Command | API Key Env Var |
|----------|---------|-----------------|
| Claude (Anthropic) | `--provider claude` | `ANTHROPIC_API_KEY` |
| OpenAI GPT | `--provider openai` | `OPENAI_API_KEY` |
| Kimi (Moonshot) | `--provider kimi` | `OPENAI_COMPATIBLE_API_KEY` |
| DeepSeek | `--provider deepseek` | `OPENAI_COMPATIBLE_API_KEY` |
| Google Gemini | `--provider gemini` | `OPENAI_COMPATIBLE_API_KEY` |
| Alibaba Qwen | `--provider qwen` | `QWEN_API_KEY` |
| Ollama (local) | `--provider ollama` | Not required |
| Any OpenAI-compat API | `--provider openai-compatible` | Depends on service |
| Mock (testing) | `--provider mock` | Not required |

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API key

Copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env
# Edit .env, uncomment and fill in your key
```

Or set environment variables directly:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # for Claude
export OPENAI_API_KEY="sk-..."          # for OpenAI
```

### 3. Run

```bash
# Claude
python main.py -i procurement_doc.pdf -p claude

# OpenAI GPT-4o
python main.py -i procurement_doc.pdf -p openai --model gpt-4o

# Kimi
python main.py -i procurement_doc.pdf -p kimi --api-key sk-xxx

# DeepSeek
python main.py -i procurement_doc.pdf -p deepseek --api-key sk-xxx

# Local Ollama
python main.py -i procurement_doc.pdf -p ollama --model llama3

# Specify output path
python main.py -i procurement_doc.pdf -o output/framework.docx -p claude

# Multi-package: process packages 1 and 2 only
python main.py -i procurement_doc.pdf -d output/ --packages 1,2

# Save intermediate JSON (analysis + framework)
python main.py -i procurement_doc.pdf -d output/ --save-json

# Test mode (no API key needed)
python main.py -i procurement_doc.pdf -p mock

# List all supported providers
python main.py --list-providers
```

### Use as Python Module

```python
from src import BidFrameworkAgent

# Claude
agent = BidFrameworkAgent(llm_provider="claude")
agent.run(input_file="doc.pdf", output_file="output/framework.docx")

# Kimi
agent = BidFrameworkAgent(llm_provider="kimi", api_key="sk-xxx")
agent.run(input_file="doc.pdf", output_file="output/framework.docx")

# Local Ollama
agent = BidFrameworkAgent(llm_provider="ollama", model="llama3")
agent.run(input_file="doc.pdf", output_file="output/framework.docx")
```

## Features

- **Multi-format input**: PDF, DOCX, DOC
- **Multi-LLM backends**: 9 providers out of the box, extensible via custom registration
- **PDF vision**: Auto-screenshots format template pages and uses Vision API for layout detection
- **Multi-package support**: Auto-detects multiple procurement packages with shared/separate scoring
- **Format preservation**: Centre/right alignment, indentation, tables — all rendered as native Word formatting
- **Faithful structure**: Strictly copies the original document structure without inventing groupings
- **`.env` config**: Store API keys in `.env` file, no need to pass them every time

## Project Structure

```
bid-framework-agent/
├── main.py                  # CLI entry point
├── requirements.txt         # Dependencies
├── .env.example             # API key config template
├── src/
│   ├── __init__.py
│   ├── agent.py             # Main orchestrator
│   ├── document_parser.py   # Document parser (PDF/DOCX/DOC)
│   ├── llm_provider.py      # LLM provider interface (multi-backend + aliases + custom registration)
│   ├── llm_analyzer.py      # LLM-based document analysis
│   ├── llm_generator.py     # LLM-based framework generation
│   └── document_generator.py # Word document renderer
├── prompts/
│   ├── analyze_prompt.txt   # Analysis prompt (~240 lines)
│   └── generate_prompt.txt  # Generation prompt (~390 lines)
├── shared/                  # Shared resources
└── output/                  # Output directory
```

## Adding a Custom LLM Provider

```python
from src.llm_provider import BaseLLMProvider, register_provider

class MyProvider(BaseLLMProvider):
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key

    def generate(self, prompt, max_tokens=4096, **kwargs):
        # Call your LLM API here
        return "..."

register_provider("my-llm", MyProvider)
```

Then run: `python main.py -i doc.pdf -p my-llm`

## Architecture

The agent follows a **4-step pipeline**:

1. **Document Parsing** (`document_parser.py`)
   - Extract text, paragraphs, and tables from PDF/DOCX/DOC
   - For PDFs: identify and screenshot format template pages for vision analysis

2. **LLM Analysis** (`llm_analyzer.py` + `analyze_prompt.txt`)
   - Extract project info, scoring criteria, response format skeleton, format templates, and procurement requirements
   - Uses 5-level priority system to locate the document structure
   - Vision-assisted format detection for PDF documents

3. **LLM Framework Generation** (`llm_generator.py` + `generate_prompt.txt`)
   - Build hierarchical framework based on analysis results
   - Format templates take priority over skeleton structure
   - Scoring factors expanded only under "free-form content" nodes
   - Full-text filling of template content and scoring criteria

4. **Word Rendering** (`document_generator.py`)
   - Convert framework JSON/nodes to formatted Word document
   - Native Word tables, alignment, font sizing (Song Ti 14pt)
   - Chapter cover pages and index pages when applicable

## Content Markers

The prompts and renderer communicate via a marker protocol:

| Marker | Meaning | Word Rendering |
|--------|---------|---------------|
| `[CENTER]text` | Centre-aligned | Paragraph centred |
| `[RIGHT]text` | Right-aligned | Paragraph right-aligned |
| `[TABLE_START]...[TABLE_END]` | Table block | Native Word table |
| `【xxx】` | Section header | Bold paragraph |
| 2/4/6 leading spaces | Indent levels | Visual indentation |

## Requirements

- Python 3.10+
- For `.doc` files on Windows: MS Word + `pywin32` required

## License

MIT

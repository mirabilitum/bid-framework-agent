# 标书框架生成Agent v7

将任意甲方招标/磋商文件（PDF/DOCX/DOC）自动转化为标书响应框架目录（Word文档）。

## 版本定位

v7 是主力版本，基于 v6 代码 + 拆分 prompt 架构。

| 维度 | v6 | v7 |
|------|----|----|
| prompt | 2个大文件（analyze+generate） | 7个拆分文件（分析4步+生成3步） |
| 格式注入 | 内嵌在agent代码中 | 独立 cli_inject.py |
| 使用方式 | GUI exe / CLI exe | Claude Code skill + GUI exe |
| 格式章节检测 | 关键词匹配 | index-based（LLM返回段落索引） |

## 工作流程（8步）

```
Step 0: 字体设置确认
Step 1: 解析文档 (cli_parse.py)
Step 2: 识别格式章节位置 (LLM)
  ↳ format_from_attachments=true → Step 2.5 附件格式处理
Step 3: 获取格式排版信息 (cli_screenshot.py / cli_extract_format.py)
Step 4: 分析文档 (LLM 4步: packages_pre → structure → search → mapping)
Step 5: 生成框架 (LLM 3步: skeleton → scoring → content)
Step 6: DOCX格式注入 (cli_inject.py, 仅DOCX)
Step 7: 生成Word (cli_render.py)
Step 8: 质量检查 (bid-check, 可选)
```

## 文件结构

```
v7/
├── interactive_cli.py         # 交互式CLI入口
├── cli_parse.py               # Step 1: 文档解析
├── cli_screenshot.py          # Step 3: PDF截图
├── cli_extract_format.py      # Step 3: DOCX格式提取
├── cli_inject.py              # Step 6: DOCX格式注入
├── cli_render.py              # Step 7: Word渲染
├── src/
│   ├── bid_framework_agent_v7.py   # Agent主流程
│   ├── document_parser.py     # 文档解析核心（含index-based格式章节检测）
│   ├── document_generator.py  # Word生成核心（支持font_config）
│   ├── llm_provider.py        # LLM Provider抽象
│   ├── llm_analyzer.py        # LLM分析（4步拆分prompt）
│   ├── llm_framework_generator.py  # LLM生成（3步拆分prompt）
│   ├── llm_utils.py           # LLM工具（续写、完整性检测、标题匹配）
│   └── json_repair.py         # JSON修复
├── prompts/
│   ├── analyze_0_packages.txt     # 分析Step0: 包/标段预识别
│   ├── analyze_1_structure.txt    # 分析Step1: 结构提取
│   ├── analyze_2_search.txt       # 分析Step2: 全文检索
│   ├── analyze_3_mapping.txt      # 分析Step3: 交叉填充
│   ├── generate_1_skeleton.txt    # 生成Step1: 骨架构建
│   ├── generate_2_scoring.txt     # 生成Step2: 评分展开
│   ├── generate_3_content.txt     # 生成Step3: 内容填充
│   ├── check_framework.txt        # 质量检查
│   └── check_lessons.txt          # 经验累积
├── build/                     # PyInstaller打包
│   └── interactive.spec
├── shared/
│   └── 响应文件通用格式.docx   # 通用格式兜底
└── 工程文件.md                # 详细开发文档
```

## 环境要求

- Python 3.14
- 依赖：PyMuPDF(fitz)、pdfplumber、python-docx、pywin32、openpyxl、anthropic、lxml

```bash
pip install PyMuPDF pdfplumber python-docx pywin32 openpyxl anthropic lxml -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
```

## Skill 使用方式

v7 主要通过 Claude Code skill 使用，Claude 自己充当 LLM：

```
/bid-framework <招标文件路径>
```

skill 路径：`C:\Users\Administrator\.claude\tools\bid-framework-agent\`
command 路径：`C:\Users\Administrator\.claude\commands\bid-framework.md`

## exe 打包

```bash
cd "F:/code file/v7"
pyinstaller build/interactive.spec
# 输出：build/dist/标书框架生成工具_交互版.exe
```

## 格式标记规范

| 标记 | 含义 |
|------|------|
| `[CENTER]文字` | 居中 |
| `[RIGHT]文字` | 右对齐 |
| `[TABLE_START]...[TABLE_END]` | 表格 |
| 2/4/6空格缩进 | 层级缩进 |

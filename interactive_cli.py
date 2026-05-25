# -*- coding: utf-8 -*-
"""
标书框架生成工具 v7 - 交互式命令行入口
运行方式: 双击exe 或 在cmd中运行
"""

import os
import sys
import json
from typing import Optional, Dict, Any


def get_base_path() -> str:
    """PyInstaller frozen exe的资源路径（prompts等）。"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_exe_dir() -> str:
    """exe所在目录（用于查找.env、输出文件）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- #
#  .env 读取
# --------------------------------------------------------------------------- #

def load_dotenv(path: str) -> Dict[str, str]:
    config: Dict[str, str] = {}
    if not os.path.exists(path):
        return config
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, val = line.partition('=')
                config[key.strip()] = val.strip()
    return config


# --------------------------------------------------------------------------- #
#  Provider 菜单
# --------------------------------------------------------------------------- #

PROVIDERS = [
    # (name, 显示名, 默认模型, 默认base_url)
    ("deepseek",  "DeepSeek（推荐，性价比高）",  "deepseek-chat",          "https://api.deepseek.com/v1"),
    ("doubao",    "豆包 (doubao)",               "doubao-pro-128k",         None),
    ("qwen",      "通义千问",                     "qwen-max",               None),
    ("claude",    "Claude (Anthropic)",           "claude-sonnet-4-20250514", None),
    ("openai",    "OpenAI / 自定义兼容接口",      "gpt-4o",                 None),
]


# --------------------------------------------------------------------------- #
#  交互工具函数
# --------------------------------------------------------------------------- #

def ask(prompt: str, default: Optional[str] = None, secret: bool = False) -> str:
    display = f"{prompt} [{default}]: " if default else f"{prompt}: "
    if secret:
        import getpass
        val = getpass.getpass(display).strip()
    else:
        val = input(display).strip()
    return val if val else (default or "")


def ask_int(prompt: str, default: int) -> int:
    while True:
        val = ask(prompt, str(default))
        try:
            return int(val)
        except ValueError:
            print("  请输入整数")


def banner():
    print()
    print("=" * 60)
    print("   标书框架生成工具 v7")
    print("=" * 60)


# --------------------------------------------------------------------------- #
#  配置收集
# --------------------------------------------------------------------------- #

def collect_provider_config(env: Dict[str, str]):
    """从 .env 或交互式菜单获取 LLM 配置。"""
    p = env.get('LLM_PROVIDER', '').strip()
    k = env.get('LLM_API_KEY', '').strip()
    m = env.get('LLM_MODEL', '').strip()
    u = env.get('LLM_BASE_URL', '').strip()

    if p and k:
        print(f"\n[配置] 已从 .env 加载")
        print(f"       提供商: {p}  模型: {m or '默认'}  Key: {'*' * 8}")
        return p, k, m or None, u or None

    print("\n[配置] 请选择 LLM 提供商:")
    for i, (_, name, _, _) in enumerate(PROVIDERS, 1):
        print(f"  {i}. {name}")

    while True:
        choice = ask("  输入序号", "1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(PROVIDERS):
                break
        except ValueError:
            pass
        print("  无效输入，请重新选择")

    pname, _, default_model, default_url = PROVIDERS[idx]

    print()
    api_key = ask("  API Key", secret=True)
    while not api_key:
        print("  API Key 不能为空")
        api_key = ask("  API Key", secret=True)

    model = ask("  模型名称", default_model)

    if pname == "openai":
        url_input = ask("  API 地址（回车使用 OpenAI 官方）", "")
        base_url = url_input if url_input else None
    else:
        base_url = default_url

    return pname, api_key, model or None, base_url or None


def collect_font_settings() -> Dict[str, Any]:
    print("\n[字体] 字体设置（回车使用默认值）")
    font_name        = ask("  字体名称", "宋体")
    cover_title_size = ask_int("  封面标题字号 pt", 18)
    title_size       = ask_int("  标题字号 pt",   14)
    body_size        = ask_int("  正文字号 pt",   14)
    return {
        "font_name":         font_name,
        "cover_title_size":  cover_title_size,
        "title_size":        title_size,
        "body_size":         body_size,
    }


# --------------------------------------------------------------------------- #
#  质量检查
# --------------------------------------------------------------------------- #

def run_quality_check(output_dir: str, provider_name: str, api_key: str,
                      model: Optional[str], base_url: Optional[str],
                      base_path: str):
    check_prompt_path = os.path.join(base_path, 'prompts', 'check_framework.txt')
    if not os.path.exists(check_prompt_path):
        print("[检查] check_framework.txt 未找到，跳过")
        return

    # Look for JSON files: first in output_dir root, then in pkg_* subdirectories
    parsed_path    = os.path.join(output_dir, 'parsed.json')
    analysis_path  = os.path.join(output_dir, 'analysis.json')
    framework_path = os.path.join(output_dir, 'framework.json')

    # Multi-package mode saves files in pkg_* subdirs; find first available
    if not os.path.exists(analysis_path) or not os.path.exists(framework_path):
        for entry in sorted(os.listdir(output_dir)):
            sub = os.path.join(output_dir, entry)
            if os.path.isdir(sub) and entry.startswith('pkg_'):
                a = os.path.join(sub, 'analysis.json')
                f = os.path.join(sub, 'framework.json')
                if os.path.exists(a) and os.path.exists(f):
                    analysis_path  = a
                    framework_path = f
                    print(f"[检查] 使用子目录 {entry}/ 的文件进行检查")
                    break

    for p, name in [(parsed_path, 'parsed.json'),
                    (analysis_path, 'analysis.json'),
                    (framework_path, 'framework.json')]:
        if not os.path.exists(p):
            print(f"[检查] 缺少 {name}，无法进行质量检查")
            return

    print("\n[检查] 读取文件...")
    with open(check_prompt_path, encoding='utf-8') as f:
        prompt_tmpl = f.read()
    with open(parsed_path, encoding='utf-8') as f:
        parsed = json.load(f)
    with open(analysis_path, encoding='utf-8') as f:
        analysis_text = f.read()
    with open(framework_path, encoding='utf-8') as f:
        framework_text = f.read()

    lessons_path = os.path.join(base_path, 'prompts', 'check_lessons.txt')
    lessons = ""
    if os.path.exists(lessons_path):
        with open(lessons_path, encoding='utf-8') as f:
            lessons = f.read()

    doc_text = parsed.get('full_text', '')[:60000]
    tables_text = parsed.get('tables_text', '')

    prompt = (prompt_tmpl
              .replace('{document_text}', doc_text)
              .replace('{tables_text}', tables_text)
              .replace('{analysis_json}', analysis_text)
              .replace('{framework_json}', framework_text)
              .replace('{check_lessons}', lessons or '暂无历史经验'))

    print("[检查] 正在调用 LLM 执行质量检查，请稍候...")
    from src.llm_provider import create_llm_provider
    kwargs = {}
    if model:
        kwargs['model'] = model
    if base_url:
        kwargs['base_url'] = base_url
    provider = create_llm_provider(provider_name, api_key, **kwargs)
    report = provider.generate(prompt, max_tokens=4096)

    report_path = os.path.join(output_dir, 'check_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"[检查] 报告已保存: {report_path}")

    # 提取并显示评分
    for line in report.splitlines():
        if '评分' in line or '/' in line or '问题' in line or '建议' in line:
            print(f"  {line.strip()}")
            break

    # 追加经验到 check_lessons.txt（写入可写目录，即 exe 目录）
    import datetime
    today = datetime.date.today().isoformat()
    try:
        proj = json.loads(analysis_text).get('project_info', {}).get('name', '未知项目')
    except Exception:
        proj = '未知项目'

    marker = "本次未发现新的规律性问题"
    if marker not in report:
        lessons_write_path = os.path.join(get_exe_dir(), 'check_lessons.txt')
        with open(lessons_write_path, 'a', encoding='utf-8') as f:
            f.write(f"\n\n### {today} - {proj}\n")
            # 提取经验总结部分
            lines = report.splitlines()
            in_summary = False
            for line in lines:
                if '经验总结' in line or '本次经验' in line:
                    in_summary = True
                if in_summary:
                    f.write(line + '\n')
        print(f"[检查] 新经验已追加到: {lessons_write_path}")


# --------------------------------------------------------------------------- #
#  主流程
# --------------------------------------------------------------------------- #

def main():
    # Force unbuffered stdout so all print() output is visible immediately in exe
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    base_path = get_base_path()
    exe_dir   = get_exe_dir()

    # 将 src 加入路径（非 frozen 时）
    if not getattr(sys, 'frozen', False):
        sys.path.insert(0, base_path)

    banner()

    # 加载 .env
    env_path = os.path.join(exe_dir, '.env')
    env = load_dotenv(env_path)
    if env:
        print(f"[.env] 已加载配置文件: {env_path}")

    # 1. LLM 配置
    provider_name, api_key, model, base_url = collect_provider_config(env)

    # 2. 输入文件
    print()
    input_file = ask("[文件] 招标文件路径 (PDF/DOCX/DOC)")
    while (
        not input_file
        or not os.path.exists(input_file)
        or os.path.splitext(input_file)[1].lower() not in ('.pdf', '.docx', '.doc')
    ):
        print("  文件不存在或格式不支持（支持 PDF/DOCX/DOC），请重新输入")
        input_file = ask("[文件] 招标文件路径 (PDF/DOCX/DOC)")

    # 3. 输出目录
    default_out = os.path.join(
        os.path.dirname(os.path.abspath(input_file)),
        "output",
        os.path.splitext(os.path.basename(input_file))[0]
    )
    out_dir = ask("[输出] 输出目录", default_out)
    out_dir = out_dir or default_out
    os.makedirs(out_dir, exist_ok=True)

    # 4. 字体设置
    font_settings = collect_font_settings()

    # 5. 执行
    print("\n" + "=" * 60)
    print("  开始处理")
    print("=" * 60)

    from src.bid_framework_agent_v7 import BidFrameworkAgentV7

    provider_kwargs: Dict[str, Any] = {}
    if model:
        provider_kwargs['model'] = model
    if base_url:
        provider_kwargs['base_url'] = base_url

    agent = BidFrameworkAgentV7(
        llm_provider=provider_name,
        api_key=api_key,
        base_path=base_path,
        **provider_kwargs,
    )

    output_path = agent.run(
        input_file=input_file,
        output_dir=out_dir,
        font_settings=font_settings,
        save_intermediate=True,
    )

    print("\n" + "=" * 60)
    print(f"  完成！输出: {output_path}")
    print("=" * 60)

    # 6. 质量检查
    check_prompt = os.path.join(base_path, 'prompts', 'check_framework.txt')
    if os.path.exists(check_prompt):
        ans = ask("\n是否进行质量检查? (y/N)", "N")
        if ans.lower() in ('y', 'yes'):
            run_quality_check(
                output_dir=out_dir,
                provider_name=provider_name,
                api_key=api_key,
                model=model,
                base_url=base_url,
                base_path=base_path,
            )

    print("\n按回车键退出...")
    input()


if __name__ == "__main__":
    import traceback
    import datetime
    try:
        main()
    except Exception:
        exe_dir = get_exe_dir()
        log_path = os.path.join(exe_dir, 'error.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(traceback.format_exc())
        print(f"\n{'!'*60}", flush=True)
        print(f"  [程序出错] 详情已记录到: {log_path}", flush=True)
        print(f"{'!'*60}", flush=True)
        print(traceback.format_exc(), flush=True)
        print("\n按回车键退出...", flush=True)
        input()

# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for interactive CMD exe

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['..\\interactive_cli.py'],
    pathex=['F:\\code file\\v7'],
    binaries=[],
    datas=[
        ('F:/code file/v7/prompts',              'prompts'),
        ('F:/code file/shared/响应文件通用格式.docx', 'shared'),
    ],
    hiddenimports=(
        collect_submodules('src') +
        collect_submodules('anthropic') +
        collect_submodules('openai') +
        collect_submodules('lxml') +
        collect_submodules('fitz') +
        [
            'pdfplumber',
            'pdfminer',
            'pdfminer.high_level',
            'pdfminer.layout',
            'docx',
            'docx.oxml',
            'docx.oxml.ns',
            'openpyxl',
            'win32com',
            'win32com.client',
            'pythoncom',
            'pywintypes',
            'requests',
            'certifi',
            'charset_normalizer',
            'urllib3',
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'wx'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='标书框架生成工具_交互版',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

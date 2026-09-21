# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

构建：
    pyinstaller --upx-dir upx MCModTranslator.spec

或（无 UPX）：
    pyinstaller MCModTranslator.spec
"""

block_cipher = None

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=[("icon.ico", ".")],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 大包
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "IPython",
        "notebook",
        "jupyter",
        "pytest",
        "setuptools",
        "pip",
        "wheel",
        # 本地模型
        "transformers",
        "torch",
        "tensorflow",
        "sentencepiece",
        # 其他 Qt 绑定
        "PyQt5",
        "PyQt6",
        "PySide2",
        # PySide6 里用不到的（Essentials 已不带，加上更保险）
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtQuickWidgets",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtNetworkAuth",
        "PySide6.QtBluetooth",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtSerialPort",
        "PySide6.QtSensors",
        "PySide6.QtSpatialAudio",
        "PySide6.QtStateMachine",
        "PySide6.QtTextToSpeech",
        "PySide6.QtUiTools",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.QtXml",
        "PySide6.QtConcurrent",
        "PySide6.QtDBus",
        "PySide6.QtPrintSupport",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MCModTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # 有 UPX 时生效；没有就自动跳过
    upx_exclude=["vcruntime140.dll", "python3.dll"],
    runtime_tmpdir=None,
    console=False,               # --windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
)
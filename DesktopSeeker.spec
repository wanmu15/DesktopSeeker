# -*- mode: python ; coding: utf-8 -*-
import os

SITE = r"d:\Users\Administrator\Desktop\tools\DesktopSeeker\.pack-venv\Lib\site-packages"
PYSIDE = os.path.join(SITE, "PySide6")

# 只带运行必需的 Qt 插件（不收集翻译、工具、QML 等）
datas = [
    (os.path.join(PYSIDE, "plugins", "platforms"), "PySide6/plugins/platforms"),
    (os.path.join(PYSIDE, "plugins", "styles"), "PySide6/plugins/styles"),
    (os.path.join(PYSIDE, "plugins", "imageformats"), "PySide6/plugins/imageformats"),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[(r'C:\Users\Administrator\anaconda3\Library\bin\ffi.dll', '.')],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtDesigner',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtSql',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtPrintSupport',
        'PySide6.QtTest',
        'PySide6.QtXml',
        'PySide6.QtDBus',
        'PySide6.QtHelp',
        'PySide6.QtUiTools',
        'PySide6.QtNetworkAuth',
    ],
    noarchive=False,
    optimize=0,
)

# 丢弃未被使用的 Qt 组件（按文件名子串匹配）
DROP = (
    'opengl32sw', 'qt6quick', 'qt6qml', 'qt6designer', 'qmlls', 'qt6labs',
    'qt6sql', 'qt6svg', 'qt6pdf', 'qt6virtualkeyboard', 'qt6charts',
    'qt6datavisualization', 'qt6multimedia', 'qt6webengine', 'qt6positioning',
    'qt6sensors', 'qt6serialport', 'qt6texttospeech', 'qt6bluetooth', 'qt6nfc',
    'qt6remoteobjects', 'qt6scxml', 'qt6statemachine', 'qt6test', 'qt6concurrent',
    'qt6opengl', 'qt6printsupport', 'qt6xml', 'qt6uitools', 'qt6help', 'qt6dbus',
    'qpdf',  # 依赖 Qt6Pdf.dll（已剔除），避免携带无法加载的插件
    'qt6networkauth', 'qt6shadertools', 'qt6spatialaudio', 'qt6grpc',
    'pyside6/qtqml', 'pyside6/qtquick', 'pyside6/qtdesigner', 'pyside6/qtopengl',
    'pyside6/qtsql', 'pyside6/qtsvg', 'pyside6/qtprintsupport', 'pyside6/qttest',
    'pyside6/qtxml', 'pyside6/qtdbus', 'pyside6/qthelp', 'pyside6/qtuitools',
)


def keep(entry):
    name = entry[0].lower().replace('\\', '/')
    return not any(key in name for key in DROP)


a.binaries = [item for item in a.binaries if keep(item)]
a.datas = [item for item in a.datas if keep(item)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DesktopSeeker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
)

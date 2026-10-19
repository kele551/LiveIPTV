# -*- coding: utf-8 -*-
"""打包 LIVE直播源.exe（单文件、无控制台窗口、带图标与 Windows 版本资源）。

用法:
    python build.py            # 打到 builds\\<版本>\\LIVE直播源.exe
    python build.py --debug    # 控制台版（便于看输出），打到 builds\\<版本>\\LIVE直播源-debug.exe

作者: 海风（kele551）   https://github.com/kele551/LiveIPTV
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
ICON = HERE.parent / "builds" / "icon" / "app-E.ico"
MAIN = SRC / "LIVE直播源.py"
PAYLOAD = ["_ed25519.py", "_tray.py", "_toast.py", "tray.ico", "tray_busy.ico",
           "LIVE直播源.ico"]


def read_version():
    text = MAIN.read_text(encoding="utf-8")
    m = re.search(r'^VERSION\s*=\s*"([\d.]+)"', text, re.M)
    if not m:
        raise SystemExit("源码里找不到 VERSION")
    return m.group(1)


def make_version_file(path, version):
    """Windows 版本资源：右键 → 属性 → 详细信息 里能看到版本号与作者。"""
    parts = [int(x) for x in re.findall(r"\d+", version)]
    while len(parts) < 4:
        parts.append(0)
    vtuple = "({})".format(", ".join(str(p) for p in parts[:4]))
    text = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vt}, prodvers={vt},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [
          StringStruct('CompanyName', 'HaiFeng (kele551)'),
          StringStruct('FileDescription', 'LIVE直播源'),
          StringStruct('FileVersion', '{v}'),
          StringStruct('InternalName', 'LiveIPTV'),
          StringStruct('LegalCopyright', 'Copyright (C) 2026 HaiFeng (kele551)'),
          StringStruct('OriginalFilename', 'LIVE直播源.exe'),
          StringStruct('ProductName', 'LIVE直播源'),
          StringStruct('ProductVersion', '{v}'),
        StringStruct('Comments', 'https://github.com/kele551/LiveIPTV')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
""".format(vt=vtuple, v=version)
    Path(path).write_text(text, encoding="utf-8")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="控制台版，便于看输出")
    args = ap.parse_args()

    version = read_version()
    print("版本号: %s" % version)

    missing = [f for f in [MAIN] + [SRC / p for p in PAYLOAD] if not f.is_file()]
    if missing:
        raise SystemExit("缺文件: " + ", ".join(str(p) for p in missing))
    if not ICON.is_file():
        raise SystemExit("缺图标: %s（先跑 tools\\make_icon.py）" % ICON)

    out_dir = HERE.parent / "builds" / ("v" + version)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "LIVE直播源-debug" if args.debug else "LIVE直播源"

    work = Path(tempfile.mkdtemp(prefix="livebuild-"))
    try:
        stage = work / "stage"
        stage.mkdir()
        shutil.copy2(MAIN, stage / MAIN.name)
        for p in PAYLOAD:
            shutil.copy2(SRC / p, stage / p)
        vfile = work / "version.txt"
        make_version_file(vfile, version)

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onefile",
            "--name", name,
            "--icon", str(ICON),
            "--version-file", str(vfile),
            "--distpath", str(work / "dist"),
            "--workpath", str(work / "build"),
            "--specpath", str(work),
            "--noupx",
        ]
        if not args.debug:
            cmd.append("--windowed")
        # tray.ico / tray_busy.ico 是数据文件，PyInstaller 不会自动带上，必须 --add-data 打进包里，
        # 否则托盘只能退回 exe 的大图标（缩到 16 像素必然糊）。
        for data_name in ("tray.ico", "tray_busy.ico", "LIVE直播源.ico"):
            cmd += ["--add-data", str(stage / data_name) + os.pathsep + "."]
        cmd.append(str(stage / MAIN.name))
        print("打包中: %s" % " ".join(cmd))
        r = subprocess.run(cmd, cwd=str(stage))
        if r.returncode != 0:
            raise SystemExit("PyInstaller 失败，退出码 %d" % r.returncode)

        built = work / "dist" / (name + ".exe")
        if not built.is_file():
            raise SystemExit("没找到产物: %s" % built)
        target = out_dir / (name + ".exe")
        shutil.copy2(built, target)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    size = target.stat().st_size
    print("\n产物: %s" % target)
    print("大小: %s 字节 (%.2f MB)" % (format(size, ","), size / 1048576.0))
    print("SHA256: %s" % sha256(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())

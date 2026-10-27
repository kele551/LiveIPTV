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
# 2026-10-25: 以前这里 MAIN/PAYLOAD 全指向 ../src，等于"发出去的包 = 开发目录那份"，
# 改了仓库忘了拷 src 就会静默打出旧代码，而且 src 里还混着 config.json/日志这些运行期文件。
# 现在代码只从仓库读；../src 降级成"不进版本库的资源目录"（离线台标库、成品图标）。
ASSETS = HERE.parent / "src"
# 2026-10-26: 图标改取 ../src/LIVE直播源.ico —— 根 README 第 23 行写明它就是
# builds\icon\app-E.ico 的那一份, 而 app-E.ico 是 make_icon.py 不产出的未入库中间产物
# (脚本只产 app-A/B/C)。上一次清理把它当"icon 草稿"删掉后, 打包在下面的 ICON.is_file()
# 处直接 raise「缺图标」, 等于自己把发版门堵住。改成取已经随包带的 src 那份, 少一个隐性输入。
ICON = ASSETS / "LIVE直播源.ico"
MAIN = HERE / "LIVE直播源.py"
CODE_PAYLOAD = ["_ed25519.py", "_tray.py", "_toast.py", "tray.ico", "tray_busy.ico"]
ASSET_PAYLOAD = ["LIVE直播源.ico"]


def preflight():
    """打包前先过一致性闸门（页面 PAGE 必须等于 _page.html、主程序可编译）。
    用 import 而不是 subprocess：同一个解释器，报错直接打在当前输出里，也省一次启动。"""
    sys.path.insert(0, str(HERE / "tools"))
    try:
        import check_page
    except Exception as e:                     # 工具脚本没了也要说清楚，别默默跳过闸门
        raise SystemExit("找不到 tools/check_page.py，拒绝打包: %s" % e)
    if check_page.main([]) != 0:
        raise SystemExit("一致性检查未通过，拒绝打包")


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
        StringStruct('Comments', 'github.com/kele551/LiveIPTV')
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
    print("代码来源: %s" % HERE)

    preflight()          # 页面与仓库一致性 + 语法：不过就直接拒绝打包

    missing = ([f for f in [MAIN] + [HERE / p for p in CODE_PAYLOAD] if not f.is_file()]
               + [f for f in [ASSETS / p for p in ASSET_PAYLOAD] if not f.is_file()])
    if missing:
        raise SystemExit("缺文件: " + ", ".join(str(p) for p in missing))
    if not ICON.is_file():
        # 2026-10-26: 原来这句提示让人去跑 tools\make_icon.py，但那脚本只产 app-A/B/C，
        # 产不出这里要的图标 —— 报错了照着提示跑还是"缺图标"。改成直接说要放哪个文件。
        raise SystemExit("缺图标: %s（把成品图标放到 ../src/ 下，文件名 %s）" % (ICON, ICON.name))

    out_dir = HERE.parent / "builds" / ("v" + version)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "LIVE直播源-debug" if args.debug else "LIVE直播源"

    work = Path(tempfile.mkdtemp(prefix="livebuild-"))
    try:
        stage = work / "stage"
        stage.mkdir()
        shutil.copy2(MAIN, stage / MAIN.name)
        for p in CODE_PAYLOAD:
            shutil.copy2(HERE / p, stage / p)
        for p in ASSET_PAYLOAD:
            shutil.copy2(ASSETS / p, stage / p)
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
        # 离线台标库必须随包：真机上没有它就是"全靠联网取图"，取不到就没台标
        # （2026-10-24 用户反馈"还是有台标没有显示"）。3.6MB/381 张，包体可接受。
        libs = ASSETS / "logos_lib"
        if libs.is_dir():
            cmd += ["--add-data", str(libs) + os.pathsep + "logos_lib"]
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

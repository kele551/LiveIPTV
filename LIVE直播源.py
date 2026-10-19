#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIVE直播源 v1.3.0  —— 本机直播源整理与控制台
=================================================
单文件、零第三方依赖（只用 Python 标准库）。作者：海风（kele551）
仓库：https://github.com/kele551/LiveIPTV

功能：
  1. 聚合境外公开直播源仓库（GitHub / epg.pw），定时自动更新
  2. 严格有效性验证：只有实测连通（拉得到播放列表/媒体分片）的源才写入 M3U；
     返回网页、登录页、错误页的一律判为失效（不少"看起来可用"的地址其实是这种情况）
  3. 每个频道探测多个候选源，按「实测画质 > 位置对口 > 速度」选出唯一最佳源
  4. 生成标准 M3U（UTF-8 BOM），保存到指定位置，用 PotPlayer / VLC / Kodi 直接打开
  5. 网页控制台：搜索、按分组与画质筛选、勾选频道、一键保存；右下角托盘常驻，
     网页和托盘里都有"退出程序"
  6. 直播源定时自动更新（默认 6 小时）、可注册计划任务 / 开机自启
  7. 程序自身自动更新：version.json + Ed25519 签名，验签通过才升级
  8. 频道名中文化、台标自动解析（逐条实测可用才采用）
  9. 每个源内置备选镜像，主地址失效自动切换

用法：
  LIVE直播源.exe                 # 启动服务并打开网页控制台（托盘常驻）
  LIVE直播源.exe --once          # 静默执行一次更新后退出（计划任务用）
  LIVE直播源.exe --no-browser    # 不自动打开浏览器
  LIVE直播源.exe --no-tray       # 不显示托盘图标
  LIVE直播源.exe --port 9000     # 指定网页端口
"""

import argparse
import concurrent.futures
import json
import os
import re
import ssl
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote, urljoin, urlsplit

try:
    from _ed25519 import checkvalid          # 升级包 Ed25519 验签（纯标准库实现）
except Exception:                            # pragma: no cover - 缺模块时按"验不过"处理，绝不放行
    def checkvalid(sig, msg, pk):
        return False

try:
    from _tray import Tray                   # 右下角托盘图标（ctypes 调 Shell API）
except Exception:                            # 托盘是可选功能，拿不到就只保留网页控制台
    class Tray(object):
        def __init__(self, *a, **k):
            self._ok = False

        def start(self):
            return False

        def stop(self):
            pass

        def notify(self, *a, **k):
            pass

APP_NAME = "LIVE直播源"
AUTHOR = "海风（kele551）"
VERSION = "1.3.0"
REPO_URL = "https://github.com/kele551/LiveIPTV"

# 升级包验签公钥（Ed25519，32 字节十六进制）；对应私钥离线保管，不随仓库分发。
UPDATE_PUBKEY_HEX = "a264516f96cffd7f79c9013fac0e480a8a6469ef5e8d1def71b6ec8df286619a"

# 网页控制台 favicon(64px PNG base64，与 LIVE直播源.ico 同款图标)
FAVICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAAHgklEQVR42u1dP2gsRRi/7sDiOIuARZBrrM7iwMazkAWLYBNSeIUguNh5zUsKMVjINa96xYkQQQhESfEa5YgIPnhI4BWP14StIjZ6xdkYwSPgy7uYZ+LM+W3cvX/7zezs3sze7wdfdbuzM/P7zTfffLM3WyoBAAAAAAAAAAAAAAAAAAAAAAAAgKt4+sLrNWGeMF9Yh+xA2PGEHUR+9+meGnrQPbIleV0i9caQHVOZPkRhH+lbRE7fIOFJ1qdnboGB5ZDeIAKGOZI+z4ZUlwaYyZ546YIDC0ifZ7JuPpjKhvi+xcTPmiIgBAuID4O3bYrqPcYzPbJtA8EkhKBJvKfp6ntEXCODOjWo7J7m1OCB2eROrtKoUyVdeopqzvX0NcTQzbOeLo76voJr7djQmSSGjmLd4Q0mOrFThDlVMWbpgPj/Rk+Pudb2HWqXz8xR9FZ2SqC0bZD3vCnKKgurz7HyEuKZYOXSyxRRDxkd00hJtIwrdoQdCjsRds4g5JyuPaR7vTTCoLYGDA/XAPmRUa9Z9pqwNq3dRwYTOyMqU5a9plm37sqLgEH+UHWDhUZ6y/DuHyfB1FL1DLRxNVxJETDIV3L54tqKsF1hgyWmfAdUh4rBKaF4IqCAL4n8qsKIl674zKLc/xnVqcxsQ5UhglpRyE9qrAr5TWGnGuQcUa6hRWXUo6OWvEmdfmvRtUcaIpN1a+bdL7YLoJe2kTTq9xTnaDki6wbqX48Eltzn73G8AUMEvSJn+Ljk15mjfkDPW8+wPev0jAHTG9QNiKDjKvmeAfI3Gcu5gcr8azCZ1GYIQdZ904AIPNfIry7IibOiXOrgpITNbp7EzxHCLiPB1E65Suo7FQ8kJD22GPcnzfcPsnT1mlPDg6S4gJknMJocs831d1OSP+KMpiW2vZ0wZe2lHDyezcSHmyzBgnm/nmDthOVck1HGsq2ZsHxsM8pI6sOyLW5Pzn+PDefdYfz9icfEwXqexMsNl30QYJ3t625UqZDftCwFC5sxTWZF/gZcvTNTw0YW8z1GvlueYN2kAI7Rqc7ZcR7repjd5pkQwBE60lk7MpHcQeDndkBYTrvsQ0e6bc00AmihA523FgQAAeQjgIuX3755/u2Pt/b3p19k0qjR5p3Yc0atjxLvefbau0brdvHKZry8u/szr5tE9B4dk31srQBkJ0fxz0+/ZiIA2dlRzOv8Sbv+ZfD/TaNLnc6cW4fL7XssAaSF7GMIQFMAkiSd+6bsxTdvrv/487ac6/O/bi5eegsCsF0AkiRJ1i1xgkRJpurzLz+8G3/+va/nXmsaF6++AwHoCkDa1ef34677g47y82W7YqSIeIArgEIHgS4IQI6gWB2Dn9UC0I32VFC36HoIwDIBSJOkRSFJzepeCMBCAaiO4jTeAwKwUACq83ia+AECsFQAkrwoJLlKK4jffmetICAASwWgspYfC+bjz7SeCQHYKgCFbF6aLKIpjHMWEIBZAch5X5KZVF+51xCbLu7/wH6GSUAAhgUwDuwEmbFl3YyNpeePTrTTsRCA5QJ49sb78SXhwycL2yTFoFK+qd1AFa8DASjaohF+9dV3cQ/x3iepBIAg0EIBSFJjc7wgPXy/IRojyEBQtWwIwAEBjKN8sa6PRfliSTi1ShBLQQigoAKQbwhNlhkVRVKeAAJwXACTmb5JXH35jVa5EIAjAhgHfIJkgy9iQABh1JzGZrndrAQwq/7jpdv3j7TLNNofMkeh/gZTfgKYjKZNYNayKysBjJeED59M12HzjjEBFPqdwCIIYPJdgbRuGwJwTACmbaXfCjbxRwiZqjXxxxBbBCDFqm1iqaqxFMVfw/DXMAgAAsDfw/H3cBwQgQMicEQMjojBIVE4JArHxOGYOBwUiYMicVQsjorFYdE4LBrHxRfGsj8uHh+MsM7V5//BCHwyBp+MwUej8NGoVI3AZ+Pml+P+Z+OoIfhw5ITbZ5RVnA9HMqYCfDp2esAU59OxkYbh49Hpye+UXMZTfD4+Dflufz6e2ciAO7/REutUIzt2RCO3FVlKViLlViJLuBZde6SR9TzlZuJM9osLIqgtCHBURRDOv2eWpWDZcQiDfNlXtVKRkBDlhiJoKJRXoQh8sETiB1SHimI/JJHfKBURDBEMOXmCGR6hlfM7C8f0zLJiXbcY7S8m+Qoi0E560EZVGLCNDOfdw8ByTbNu3YRnFJ98RREEaTqEPIPMRewIOxR2wkjYhAmmE7pnh8oop2xrAPJnB4YBg5CuyWg4smk1y8oGn1NljPpQ6LXSKoI6qcfoJDlCfIfa5TM83A21vVpadSRkDCdz4r7lxPeZbemUgKm9g76CEDo2jB7yYh3FuntgPN28OelG/TzFQPX0mdNXZvFM0b1BoLFck4RsZxFRUzS/rUF6GOhh1Gc8p85L2HSJOI9DQngd3dNNmWDquxS8FlkIeRuIz1AIgcXEByA+v0xil7nWztqGVJcGmFmOGLaIgH7OLr6runEFZC+GGk0TXcO7g2Ew6a9s2tZxUXhEXofsgEiN2kHkd5/uAdkAAAAAAAAAAAAAAAAAAAAAAACAu/gXUyTr7G1HmbEAAAAASUVORK5CYII="

_ENV_DATA = os.environ.get("LIVE_DATA", "").strip()
if _ENV_DATA:
    # 测试 / 便携模式：LIVE_DATA 指定数据目录，绝不碰用户正在用的那份
    BASE = Path(_ENV_DATA)
    try:
        BASE.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
elif getattr(sys, "frozen", False):
    # 单文件打包：配置/缓存/日志放到用户数据目录，避免临时解压目录导致数据丢失
    BASE = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    try:
        BASE.mkdir(parents=True, exist_ok=True)
    except OSError:
        BASE = Path(sys.executable).parent
else:
    BASE = Path(__file__).parent

CFG_PATH = BASE / "config.json"
CACHE_PATH = BASE / "channels.json"
LOGO_CACHE_PATH = BASE / "logos.json"
LOG_PATH = BASE / (APP_NAME + ".log")

# ---------------------------------------------------------------- 配置

# 全部使用境外公开源(GitHub raw / iptv-org 站点 / jsdelivr / epg.pw)，
# 按“实测可用率”排序：越靠前的源越可能真有画面，探测时优先级也越高。
SOURCES = [
    # (key, 名称, 列表地址, 默认启用, 区域标签)
    # 2026-10-19 实测(每源均匀抽样 60 条，连通+实际拉流)：CCSH 平台源 77% 可播，
    # 是国内聚合里最好的一份；CCSH 全量 28%，Guovin 15%，iptv-org 中国 32%。
    # 实测(2026-10-19)：live_platforms.m3u 是抖音/淘宝那种"网络直播间"清单，不是电视台，
    # 默认关闭；白名单过滤后它只剩 2 条，留着只会拖慢探测。
    ("ccsh_plat", "CCSH·平台源(直播间,建议关)", "https://raw.githubusercontent.com/CCSH/IPTV/main/live_platforms.m3u", False, "国内"),
    ("ccsh_live", "CCSH·全量源", "https://raw.githubusercontent.com/CCSH/IPTV/main/live.m3u", True, "国内"),
    ("cinauto", "ChinaIPTV·自动更新", "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/cnTV_AutoUpdate.m3u8", True, "国内"),
    ("cn_org", "国内·iptv-org(中国)", "https://iptv-org.github.io/iptv/countries/cn.m3u", True, "国内"),
    ("guovin", "Guovin·IPTV-API", "https://cdn.jsdelivr.net/gh/Guovin/iptv-api@gd/output/result.m3u", True, "国内"),
    ("org_hk", "香港-iptv-org",  "https://iptv-org.github.io/iptv/countries/hk.m3u", True, "港澳台"),
    ("org_tw", "台湾-iptv-org",  "https://iptv-org.github.io/iptv/countries/tw.m3u", True, "港澳台"),
    ("org_mo", "澳门-iptv-org",  "https://iptv-org.github.io/iptv/countries/mo.m3u", True, "港澳台"),
    ("yang",   "国内聚合·YanG(GitHub)", "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u", True, "国内"),
    # 以下三个 2026-10-19 实测全部不可达(0/135 可播)，默认关闭，需要时可在“设置→数据源”打开：
    # Kelvin 的 HK.m3u 38 条全超时；epg.pw 的三份列表指向 stream1.freetv.fun，本网络连不上。
    ("kelvin", "港澳台-Kelvin",  "https://raw.githubusercontent.com/Kelvin0755/iptv-m3u-maker/master/HK.m3u", False, "港澳台"),
    ("epg_hk", "香港-epg.pw",    "https://epg.pw/test_channels_hong_kong.m3u", False, "港澳台"),
    ("epg_tw", "台湾-epg.pw",    "https://epg.pw/test_channels_taiwan.m3u", False, "港澳台"),
    ("epg_mo", "澳门-epg.pw",    "https://epg.pw/test_channels_macau.m3u", False, "港澳台"),
]

# 外语国际频道(可选源，默认关闭；网页“源管理”可勾选开启 —— 因看不懂默认不启用)
ORG_COUNTRIES = [("us", "美国"), ("jp", "日本"), ("kr", "韩国"), ("uk", "英国"), ("fr", "法国"), ("de", "德国"),
                 ("ru", "俄罗斯"), ("in", "印度"), ("br", "巴西"), ("ca", "加拿大"), ("au", "澳大利亚"), ("it", "意大利"),
                 ("es", "西班牙"), ("pt", "葡萄牙"), ("nl", "荷兰"), ("th", "泰国"), ("vn", "越南"), ("ph", "菲律宾"),
                 ("id", "印度尼西亚"), ("tr", "土耳其"), ("sa", "沙特阿拉伯"), ("ae", "阿联酋"), ("za", "南非"),
                 ("mx", "墨西哥"), ("ar", "阿根廷"), ("eg", "埃及"), ("ng", "尼日利亚"), ("kp", "朝鲜"), ("kz", "哈萨克斯坦")]
ORG_CATS = [("news", "新闻"), ("sports", "体育"), ("entertainment", "娱乐"), ("movies", "电影"),
            ("music", "音乐"), ("kids", "少儿"), ("documentary", "纪实"), ("general", "综合"), ("education", "教育")]
COUNTRY_OF_TAG = {}
for _cc, _zh in ORG_COUNTRIES:
    SOURCES.append(("org_" + _cc, "%s·iptv-org" % _zh, "https://iptv-org.github.io/iptv/countries/%s.m3u" % _cc, False, "国际"))
    COUNTRY_OF_TAG["org_" + _cc] = _zh
for _cat, _zh in ORG_CATS:
    SOURCES.append(("cat_" + _cat, "%s·iptv-org" % _zh, "https://iptv-org.github.io/iptv/categories/%s.m3u" % _cat, False, "国际"))
    COUNTRY_OF_TAG["cat_" + _cat] = "国际·" + _zh

# GitHub 直连失败时按顺序尝试的镜像前缀(仅对 raw.githubusercontent.com / github.com 生效，
# github.io 页面不支持前缀代理，实测 404/403 —— 其备选走下方 SOURCE_FALLBACKS 专属地址)
MIRRORS = ["", "https://gh-proxy.com/", "https://ghproxy.net/", "https://ghfast.top/"]

# 每个直播源主地址失效后的备选地址(以下全部为 2026-10 实测可达，按顺序尝试)
SOURCE_FALLBACKS = {
    "kelvin": [
        "https://cdn.jsdelivr.net/gh/Kelvin0755/iptv-m3u-maker@master/HK.m3u",
    ],
    "org_hk": [
        "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/hk.m3u",
        "https://fastly.jsdelivr.net/gh/iptv-org/iptv@master/streams/hk.m3u",
        "https://gcore.jsdelivr.net/gh/iptv-org/iptv@master/streams/hk.m3u",
    ],
    "org_mo": [
        "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/mo.m3u",
        "https://fastly.jsdelivr.net/gh/iptv-org/iptv@master/streams/mo.m3u",
        "https://gcore.jsdelivr.net/gh/iptv-org/iptv@master/streams/mo.m3u",
    ],
    "org_tw": [
        "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/tw.m3u",
        "https://fastly.jsdelivr.net/gh/iptv-org/iptv@master/streams/tw.m3u",
        "https://gcore.jsdelivr.net/gh/iptv-org/iptv@master/streams/tw.m3u",
    ],
    "cinauto": [
        "https://cdn.jsdelivr.net/gh/hujingguang/ChinaIPTV@main/cnTV_AutoUpdate.m3u8",
        "https://fastly.jsdelivr.net/gh/hujingguang/ChinaIPTV@main/cnTV_AutoUpdate.m3u8",
    ],
    "cn_org": [
        "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
        "https://fastly.jsdelivr.net/gh/iptv-org/iptv@master/streams/cn.m3u",
        "https://gcore.jsdelivr.net/gh/iptv-org/iptv@master/streams/cn.m3u",
    ],
    "yang": [
        "https://fastly.jsdelivr.net/gh/YanG-1989/m3u@main/Gather.m3u",
        "https://cdn.jsdelivr.net/gh/YanG-1989/m3u@main/Gather.m3u",
        "https://gcore.jsdelivr.net/gh/YanG-1989/m3u@main/Gather.m3u",
    ],
    "ccsh_plat": [
        "https://cdn.jsdelivr.net/gh/CCSH/IPTV@main/live_platforms.m3u",
        "https://fastly.jsdelivr.net/gh/CCSH/IPTV@main/live_platforms.m3u",
        "https://gcore.jsdelivr.net/gh/CCSH/IPTV@main/live_platforms.m3u",
    ],
    "ccsh_live": [
        "https://cdn.jsdelivr.net/gh/CCSH/IPTV@main/live.m3u",
        "https://fastly.jsdelivr.net/gh/CCSH/IPTV@main/live.m3u",
        "https://gcore.jsdelivr.net/gh/CCSH/IPTV@main/live.m3u",
    ],
    "guovin": [
        "https://fastly.jsdelivr.net/gh/Guovin/iptv-api@gd/output/result.m3u",
        "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u",
        "https://gcore.jsdelivr.net/gh/Guovin/iptv-api@gd/output/result.m3u",
    ],
}
# 国际国家源(iptv-org.github.io 无镜像代理，备选走 raw streams + jsdelivr；分类源无 raw 等价路径不设备选)
for _cc, _zh in ORG_COUNTRIES:
    if ("org_" + _cc) not in SOURCE_FALLBACKS:
        SOURCE_FALLBACKS["org_" + _cc] = [
            "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/%s.m3u" % _cc,
            "https://fastly.jsdelivr.net/gh/iptv-org/iptv@master/streams/%s.m3u" % _cc,
        ]

CFG_VER = 6                    # 当前配置结构版本；load_cfg() 里比"盘上的旧版本"做一次性迁移

def _desktop_dir():
    """真正的桌面目录。

    很多人的桌面被改到了别的盘（这台机器就是 F:\桌面），所以不能猜 ~/Desktop，
    直接问 Windows 要（SHGetKnownFolderPath，失败再退注册表，最后才退回用户目录）。
    """
    try:
        import ctypes
        from ctypes import wintypes
        # FOLDERID_Desktop
        guid = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
        class _GUID(ctypes.Structure):
            _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                        ("d3", wintypes.WORD), ("d4", ctypes.c_byte * 8)]
        path_ptr = ctypes.c_wchar_p()
        ole = ctypes.windll.ole32
        ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        res = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(_GUID.from_buffer_copy(bytes.fromhex(
                "3ACCB4B42CDB4C42B0297FE99A87C641"))), 0, None,
            ctypes.byref(path_ptr))
        if res == 0 and path_ptr.value:
            p = Path(path_ptr.value)
            ole.CoTaskMemFree(path_ptr)
            if p.is_dir():
                return p
    except Exception:
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            v = winreg.QueryValueEx(k, "Desktop")[0]
        p = Path(os.path.expandvars(v))
        if p.is_dir():
            return p
    except Exception:
        pass
    home = Path(os.path.expanduser("~"))
    for p in (home / "Desktop", home / "OneDrive" / "Desktop"):
        try:
            if p.is_dir():
                return p
        except OSError:
            pass
    return home


def _res_path(name):
    """随包文件(图标等)的路径：打包版在 sys._MEIPASS，脚本版在同目录。"""
    try:
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", "")) / name
        return Path(__file__).with_name(name)
    except Exception:
        return Path(name)


DEFAULT_CFG = {
    "port": 8899,
    "open_browser": True,      # 启动后自动打开网页控制台
    "interval_hours": 6,       # 直播源自动更新间隔(小时)
    "backups": 3,              # 每个频道内部探测的候选源数量
    "keep_sd": True,
    "min_mbps": 1.5,          # 低于这个码率的频道不显示/不导出（0=不限）；1.1 Mbps 那种基本是转码冒充源           # 无高清源时是否保留标清频道(供用户自行选择)
    "filter_junk": True,       # 过滤 DJ/相声/助眠/解说 这类非电视频道
    "only_tv": True,           # 只保留"电视台"频道：用 CCSH 人工整理的频道名单做白名单
    "verify_timeout": 4,       # 单源探测超时(秒)
    "concurrency": 256,        # 并发探测数(地址已去重，256 路大部分时间在等 IO)
    "epg_url": "",             # EPG 节目单地址(可选)
    "output_path": str(_desktop_dir() / (APP_NAME + ".m3u")),   # 直播源自动更新保存位置
    "autostart": False,        # 开机自启
    "task_registered": False,  # 是否已注册计划任务(静默更新直播源)
    "self_update": True,       # 程序自身自动更新(检查到新版本会提示)
    "update_url": "https://raw.githubusercontent.com/kele551/LiveIPTV/main/version.json",
    "require_sig": True,       # 升级源必须带 Ed25519 签名(version.json.sig)，验不过拒绝升级
    "tray": True,              # 显示右下角托盘图标
    "update_auto": False,      # 发现新版本是否自动下载替换并重启
    "update_check_hours": 24,  # 程序自更新检查间隔(小时)
    "cfg_ver": 6,              # 配置结构版本(升级时做一次性迁移；见 CFG_VER)
    "sources": {k: on for k, _, _, on, _ in SOURCES},
}

GROUP_RANK = ["香港", "澳门", "台湾", "央视", "卫视", "地方台", "电影", "体育", "游戏", "少儿", "其他"]

# ---------------------------------------------------------------- 基础工具

_SSL_CTX = ssl._create_unverified_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "*/*", "Accept-Encoding": "identity"}


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 2 * 1024 * 1024:
            old = LOG_PATH.with_suffix(".old.log")
            try:
                old.unlink()
            except OSError:
                pass
            LOG_PATH.rename(old)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_cfg():
    cfg = json.loads(json.dumps(DEFAULT_CFG, ensure_ascii=False))
    disk = {}
    try:
        if CFG_PATH.exists():
            disk = json.loads(CFG_PATH.read_text(encoding="utf-8"))
            for k, v in disk.items():
                if k == "sources" and isinstance(v, dict):
                    cfg["sources"].update({k2: bool(v2) for k2, v2 in v.items() if k2 in cfg["sources"]})
                else:
                    cfg[k] = v
    except Exception as e:
        log("配置读取失败，使用默认配置: %s" % e)
    cfg["sources"] = {k: cfg["sources"].get(k, on) for k, _, _, on, _ in SOURCES}
    try:
        cfg["min_mbps"] = max(0.0, min(50.0, float(cfg.get("min_mbps") or 0)))
    except (TypeError, ValueError):
        cfg["min_mbps"] = 1.5
    # 输出路径填成了目录(比如 F:\)时补上默认文件名，否则写 M3U 会失败
    try:
        op = str(cfg.get("output_path") or "")
        if op and Path(op).is_dir():
            cfg["output_path"] = str(Path(op) / (APP_NAME + ".m3u"))
            log("保存位置是个目录，已改为: %s" % cfg["output_path"])
    except OSError:
        pass

    # 一次性配置迁移(v1.2 及更早的配置把几个已被实测判死的源留成了开启，
    # 白白拉长探测时间、还占掉频道的候选名额)：升级到 v1.3 时关掉它们一次，
    # 之后用户自己怎么勾选都尊重，不再改动。
    # 注意：版本号必须读"盘上原来的值"，不能让刚合并进来的默认值先把自己填成最新版。
    try:
        disk_ver = int(disk.get("cfg_ver") or 0)
    except Exception:
        disk_ver = 0
    if disk_ver < CFG_VER:
        dead = [k for k in ("kelvin", "epg_hk", "epg_tw", "epg_mo") if cfg["sources"].get(k)]
        for k in dead:
            cfg["sources"][k] = False
        if dead:
            log("配置升级：已关闭实测不可达的 %d 个源(%s)，可在设置→数据源里重新打开"
                % (len(dead), "、".join(dead)))
        if int(cfg.get("concurrency") or 0) <= 160:
            cfg["concurrency"] = 256  # v1.3 地址去重后可以开更多并发，明显更快
        if cfg["sources"].get("ccsh_plat"):
            cfg["sources"]["ccsh_plat"] = False  # 里面是网络直播间清单，不是电视台
            log("配置升级：已关闭「CCSH·平台源」(它是直播间清单，不是电视台)")
        # 保存位置如果落在盘根(比如 F:\)，用户其实是想存桌面，一起搬过去
        try:
            op = Path(str(cfg.get("output_path") or "").strip() or ".")
            if str(op.parent) == op.anchor:
                cfg["output_path"] = str(_desktop_dir() / (APP_NAME + ".m3u"))
                log("配置升级：保存位置改到桌面 %s" % cfg["output_path"])
        except OSError:
            pass
        if disk_ver < 6 and not str(cfg.get("update_url") or "").strip():
            cfg["update_url"] = "https://raw.githubusercontent.com/kele551/LiveIPTV/main/version.json"
            log("配置升级：升级源地址已指向 GitHub 发布页")
    cfg["cfg_ver"] = CFG_VER
    return cfg


def save_cfg(cfg):
    try:
        CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        log("配置保存失败: %s" % e)


def esc_attr(s):
    return (s or "").replace('"', "'")


# ---------------------------------------------------------------- M3U 解析

ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')
BRACKET_RE = re.compile(r"[（(【\[][^）)】\]]*[）)】\]]")


def parse_m3u(text, tag):
    entries = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("#EXTINF"):
            attrs = dict(ATTR_RE.findall(ln))
            # 取最后一个逗号后的文本作为频道名(对源中混入 UA/属性等脏数据更鲁棒)
            name = ln.rsplit(",", 1)[1].strip() if "," in ln else ""
            name = unicodedata.normalize("NFKC", name).strip()
            q0 = quality(name)          # 画质词取自原始名(中文化后可能丢失标注)
            disp = zh_name(name)        # 显示名中文化(仅映射可确认的台名)
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("#")):
                j += 1
            url = lines[j].strip() if j < len(lines) else ""
            if disp and url and not url.startswith("#"):
                entries.append({
                    "name": disp, "url": url, "tag": tag, "q0": q0,
                    "logo": attrs.get("tvg-logo", ""),
                })
            i = j + 1
        else:
            i += 1
    return entries


# ---------------------------------------------------------------- 分类与画质

MO_KW = re.compile(r"(澳门|澳亚|澳视|tdm|lotus|莲花|澳广视|macau)", re.I)
TW_KW = re.compile(r"(台湾|台视|中视|华视|民视|公视|三立|东森|中天|tvbs|年代|非凡|高点|狼谷|客家|原住|大爱|momo|卫视电影|taiwan|\bcts\b|\bttv\b|\bftv\b|\bset\b)", re.I)
HK_KW = re.compile(r"(香港|港台|翡翠|明珠|tvb|viu|rthk|hoy|开电视|有线|now新闻|now财经|凤凰|星空|美亚|天映|龙祥|国际财经|亚旅|\bhkc\b|\batv\b|hongkong)", re.I)
CCTV_KW = re.compile(r"(cctv|央视|中央|风云|奥林匹克|国防|军事|农业|科教|法制|社会与法|中文国际|戏曲|音乐频道|电影频道|纪录频道|少儿频道|足球频道|世界地理|怀旧剧场|第一剧场|高尔夫|央视台球|兵器科技|卫生健康|女性时尚|文化精品)", re.I)
# 只认"一定是央视"的强特征；弱特征(科教/法制/风云/剧场…)在聚合源里常是地方台，
# 比如"邯郸科教""伊犁经济法制"——光靠 CCTV_KW 会把它们塞进央视分组
CCTV_STRONG = re.compile(r"(cctv|央视|中央|奥林匹克)", re.I)
# 央视付费/专业频道的正式名(出现在 NAME_MAP 里的那批)，弱特征命中时用这张表兜住
CCTV_PAID = {"风云足球", "风云音乐", "风云剧场", "第一剧场", "怀旧剧场", "世界地理", "高尔夫·网球",
             "央视台球", "卫生健康", "兵器科技", "女性时尚", "文化精品", "央视文化精品", "风云I人物志",
             "国防军事", "农业农村", "社会与法", "中文国际", "戏曲", "奥林匹克"}
SD_KW = re.compile(r"(480p?|576p?|标清|\bsd\b)", re.I)
HD_KW = re.compile(r"(1080|1920|fhd|uhd|4k|2160|超高清|蓝光|超清)", re.I)
MID_KW = re.compile(r"(720|\bhd\b|高清)", re.I)
# 游戏/电竞类频道（要放在央视判断之前：「游戏风云」里的"风云"会被 CCTV 关键词抢走）
GAME_KW = re.compile(r"(游戏|电竞|电子竞技|游戏风云|竞速|gtv|esl|lpl|kpl|csgo|dota|"
                     r"英雄联盟|王者荣耀|星际争霸|魔兽世界|和平精英|twitch|虎牙|斗鱼)", re.I)


def classify(name, tag):
    n = name.lower()
    if MO_KW.search(n):
        return "澳门"
    if TW_KW.search(n):
        return "台湾"
    if HK_KW.search(n):
        return "香港"
    if tag in ("org_mo", "epg_mo"):
        return "澳门"
    if tag in ("org_tw", "epg_tw"):
        return "台湾"
    if tag in ("kelvin", "org_hk", "epg_hk"):
        return "香港"
    if GAME_KW.search(n):
        return "游戏"
    # 名字里带"电视台/融媒体/日报"的，基本是地方台。否则"邯郸科教""伊犁经济法制""福州电视台少儿频道"
    # 会因为"科教/法制/少儿频道"这些字被错分进央视。
    if re.search(r"(电视台|融媒体|广播电视台|日报)", n) and not re.search(r"(cctv|央视|中央)", n):
        return "地方台"
    if CCTV_KW.search(n):
        if (CCTV_STRONG.search(n) or name in CCTV_PAID
                or tag not in ("cn_org", "yang", "ccsh_live", "guovin", "cinauto", "ccsh_plat")):
            return "央视"
        # 聚合源里靠"科教/法制/风云"这类弱词命中的，多半是地方台，往下走
    if "卫视" in name:
        return "卫视"
    if re.search(r"(电影|影视|剧场|chc|好莱坞|reel)", n):
        return "电影"
    if re.search(r"(体育|足球|篮球|高尔夫|网球|赛事|欧冠|nba|英超|中超|劲爆|咪咕)", n):
        return "体育"
    if re.search(r"(少儿|卡通|动漫|金鹰|亲子|baby)", n):
        return "少儿"
    # 国内频道主体：来自 iptv-org 中国 / YanG / CCSH / Guovin 聚合，未匹配以上的归为地方台
    if tag in ("cn_org", "yang", "ccsh_plat", "ccsh_live", "guovin", "cinauto"):
        return "地方台"
    # 国际频道：按源标签映射国家(地区)中文名
    if tag in COUNTRY_OF_TAG:
        return COUNTRY_OF_TAG[tag]
    return "其他"


def quality(name):
    n = name.lower()
    if HD_KW.search(n):
        return "1080P"
    if MID_KW.search(n):
        return "HD"
    if SD_KW.search(n):
        return "SD"
    return ""


DROP_RE = re.compile(r"(?i)(1080p|720p|480p|576p|4k|uhd|fhd|\bhd\b|\bsd\b|高清|超清|蓝光|标清|超高清|备份|备用|直播)")


def norm_name(name):
    n = BRACKET_RE.sub("", name)
    n = DROP_RE.sub("", n)
    n = re.sub(r"[\s\-_·:：+'\"‘’“”]+", "", n)
    return n.lower()


CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# ---------------------------------------------------------------- 台名中文化
# 原则：只映射能确认的台名(官方中文名)，无法确认的一律保留原名，确保台名与内容一致。
NAME_MAP = {
    # 央视付费/专业频道(官方中文名)
    "CCTV-Storm Football": "风云足球",
    "CCTV-Storm Music": "风云音乐",
    "CCTV-Storm Theater": "风云剧场",
    "CCTV-The First Theater": "第一剧场",
    "CCTV-Nostalgia Theater": "怀旧剧场",
    "CCTV-World Geography SD": "世界地理",
    "CCTV-Golf & Tennis": "高尔夫·网球",
    "CCTV-Billiards": "央视台球",
    "CCTV-Health": "卫生健康",
    "CCTV-Weapon & Technology": "兵器科技",
    "CCTV-Women's Fashion SD": "女性时尚",
    "CCTV-Culture of Quality SD": "文化精品",
    # 香港(官方译名/通行名)
    "Jade": "翡翠台",
    "Golden Jade": "黄金翡翠台",
    "Mei Ah Movie Channel": "美亚电影台",
    "Phoenix Chinese Channel": "凤凰中文台",
    "Phoenix InfoNews Channel": "凤凰资讯台",
    "RTHK TV 31": "港台电视31", "RTHK TV 32": "港台电视32", "RTHK TV 33": "港台电视33",
    "RTHK TV 34": "港台电视34", "RTHK TV 35": "港台电视35",
    "RHK31 HD": "港台电视31", "RHK32 HD": "港台电视32", "RHK33 HD": "港台电视33",
    "TVBJ2 HD": "TVB J2",
    "Celestial Movies": "天映频道",
    "Hong Kong International Business Channel": "香港国际财经台",
    "HOY Infotainment": "HOY资讯台",
    "ViuTV HD": "ViuTV", "ViuTV Six HD": "ViuTVsix",
    # 澳门
    "TDM Ou Mun": "澳视澳门",
    "Canal Macau": "澳门葡文台",
    "Lotus TV": "莲花卫视",
    # 台湾(官方中文名)
    "CTS": "华视", "CTS News": "华视新闻",
    "TTV": "台视",
    "FTV": "民视", "FTV (Taiwan)": "民视",
    "SET News": "三立新闻",
    "CTi Variety": "中天综合台",
    "EBC News": "东森新闻",
    "EBC Financial News": "东森财经新闻",
    "DaAi 1": "大爱一台", "DaAi 2": "大爱二台",
    "Good TV": "好消息电视台", "Good TV (Taiwan)": "好消息电视台",
    "Good 2": "好消息二台",
    "Hakka TV": "客家电视台",
    "Indigenous TV": "原住民族电视台",
    "Taiwan Indigenous TV": "原住民族电视台",
    "TVBS News": "TVBS新闻台",
    "TVBS-Asia": "TVBS亚洲台",
    "NTD TV Asia-Pacific": "新唐人亚太台",
    "Supreme Master TV": "无上师电视台",
    # 卫视(省级卫星频道，iptv-org 英文名为官方对应)
    "Heilongjiang TV": "黑龙江卫视", "Hebei TV": "河北卫视", "Guizhou TV": "贵州卫视",
    "Tianjin TV": "天津卫视", "Liaoning TV": "辽宁卫视", "Anhui TV": "安徽卫视",
    "Nei Monggol TV": "内蒙古卫视", "Hunan TV": "湖南卫视", "Jiangxi TV": "江西卫视",
    "Qinghai TV": "青海卫视", "Shandong TV": "山东卫视",
    "Xinjiang TV 1": "新疆卫视",
    "Xizang TV Chinese": "西藏卫视", "Xizang TV Tibetan": "西藏藏语卫视",
    "Bingtuan Satellite TV": "兵团卫视",
    "Yanbian Satellite TV": "延边卫视",
    "Kangba TV": "康巴卫视",
    "Ando TV": "安多卫视",
    # 少儿/专题/购物
    "Golden Eagle Cartoon": "金鹰卡通",
    "BRTV Kaku Childrens Channel": "卡酷少儿",
    "You Man Cartoon Channel": "优漫卡通",
    "CETV-1": "中国教育一台", "CETV-2": "中国教育二台",
    "Documentary Humanities Channel": "纪实人文",
    "China Weather Channel": "中国气象频道",
    "Fengshang Shopping Channel": "风尚购物",
    "Dragon TV International": "东方卫视国际",
    "Zhejiang International Channel": "浙江国际频道",
    # 地方台(仅英语与官方通名一一对应的)
    "Fujian Comprehensive Channel": "福建综合频道",
    "Guangxi Variety & Travel Channel": "广西综艺旅游频道",
    "Xuzhou Economic Life": "徐州经济生活",
    "Jiuquan TV News Comprehensive": "酒泉新闻综合",
    "Harbin Comprehensive News Channel": "哈尔滨新闻综合",
    "Harbin Movie Channel": "哈尔滨影视",
    "Lanzhou Comprehensive News Channel": "兰州新闻综合",
    "Lanzhou Culture & Tourism Channel": "兰州文化旅游",
    "Dongguan Comprehensive News Channel": "东莞新闻综合",
    "Chifeng Comprehensive News Chanel": "赤峰新闻综合",
    "Anshun Comprehensive News Channel": "安顺新闻综合",
    "Chaozhou Public Channel": "潮州公共",
    "Chuzhou News Channel": "滁州新闻",
    "Chuzhou Public Channel": "滁州公共",
    "Chuzhou Science & Education Channel": "滁州科教",
    "Chuxiong News Channel": "楚雄新闻",
    "Hebi News Channel": "鹤壁新闻",
    "Pingxiang TV News": "萍乡新闻",
    "Xi'an Silk Road Channel": "西安丝路",
    # 省级子频道(官方通名)
    "Shandong TV Qilu": "山东齐鲁", "Shandong TV Sports": "山东体育",
    "Shandong TV Life": "山东生活", "Shandong TV Variety": "山东综艺",
    "Shandong TV Children's": "山东少儿", "Shandong TV Agricultural Science": "山东农科",
    "Jiangsu City": "江苏城市", "Jiangsu Educational": "江苏教育",
    "Jiangsu Movie": "江苏影视", "Jiangsu Public & News": "江苏公共新闻",
    "Jiangsu Sports & Leisure": "江苏体育休闲", "Jiangsu Variety": "江苏综艺",
    "Jiangxi Children's": "江西少儿", "Jiangxi City": "江西都市",
    "Jiangxi Economy & Life": "江西经济生活", "Jiangxi Movie": "江西影视",
    "Jiangxi Public & Agriculture": "江西公共农业",
    "Hunan News": "湖南新闻", "Hunan Politics & Law": "湖南政法",
}
NAME_MAP_LC = {k.lower(): v for k, v in NAME_MAP.items()}
# 画质词(用于 CCTV 编号频道后缀识别；这些词描述的是流画质而非频道身份)
_QTOK = r"(?:uhd|fhd|hd|sd|4k|8k|1080p|720p|480p|576p|超高清|高清|超清|标清|蓝光)"
CCTV_NUM_RE = re.compile(r"(?i)^CCTV[-\s]?(\d{1,2}[Kk]?)(?:[\s\-]+([\w &·+\-]*))?$")


def zh_name(name):
    """显示名中文化：CCTV 编号族归一(如 CCTV-4K HD -> CCTV4K)；精确映射表；其余原样保留"""
    base = BRACKET_RE.sub("", name)
    base = re.sub(r"\s+", " ", base).strip()
    if not base:
        return name.strip()
    m = CCTV_NUM_RE.match(base)
    if m:
        rest = (m.group(2) or "").strip()
        if not rest or re.fullmatch(r"(?i)%s(?:[\s\-_+]*%s)*" % (_QTOK, _QTOK), rest):
            return "CCTV" + m.group(1).upper()
    z = NAME_MAP.get(base) or NAME_MAP_LC.get(base.lower())
    if z:
        return z
    return base


# 聚合源里混着不少"网络直播间"（DJ 串烧、相声小品、助眠白噪音、影视解说、虚拟主播…），
# 它们不是电视频道，留着只会把频道表搞乱。设置里可以关掉这个过滤(cfg.filter_junk)。
JUNK_RE = re.compile(r"(?i)(《|》|\bdj\b|相声|小品|评书|有声书|歌曲|情歌|舞曲|助眠|白噪音|asmr|"
                     r"回放|录播|vtuber|虚拟主播|鬼畜|解说|混剪|合集|雨声|纯音乐|轻音乐)")


# ---------------------------------------------------------------- 电视台白名单
# 关键词过滤只能挡住"DJ/相声"这类明显的，挡不住影视切片和网络直播间
# （《监狱风云2》《抗日神片…》、主播名《蔡恩雨Priscilla》…）。
# 所以再加一道白名单：只用 CCSH/IPTV 仓库人工整理过的频道名单
# （央视 39 + 港澳台 119 + 卫视 45 + 30 个省的频道表），名单里没有的不当电视台。
# 设置里可以关掉(cfg.only_tv)；白名单抓不到时自动跳过这道过滤，不会把频道表清空。
TVLIST_PATH = BASE / "tvlist.json"
TVLIST_TTL = 7 * 86400
TVLIST_BASE = "https://cdn.jsdelivr.net/gh/CCSH/IPTV@main/"
TVLIST_FILES = (["主频道/央视频道.txt", "主频道/港澳台.txt", "主频道/卫视频道.txt"] + [
    "地方台/%s频道.txt" % p for p in (
        "上海", "云南", "内蒙", "北京", "吉林", "四川", "天津", "宁夏", "安徽", "山东",
        "山西", "广东", "广西", "新疆", "江苏", "江西", "河北", "河南", "浙江", "海南",
        "湖北", "湖南", "甘肃", "福建", "西藏", "贵州", "辽宁", "重庆", "陕西", "青海",
        "黑龙江")])
_WL_QT = re.compile(r"(?i)(1080p|720p|480p|4k|8k|uhd|fhd|\bhd\b|\bsd\b|高清|超清|蓝光|标清|超高清)")
TV_NAMES = ()          # 归一化后的白名单元组
TV_BY_HEAD = {}        # 首字 -> 该首字下的白名单名，避免每条频道都跟 1700 个名字比对


def tv_norm(name):
    """频道名归一：全角转半角、去括号注释/画质词/空格与标点、转大写"""
    t = unicodedata.normalize("NFKC", name or "")
    t = BRACKET_RE.sub("", t)
    t = _WL_QT.sub("", t)
    t = re.sub(r"[\s\-_·.。,，、/|]+", "", t)
    return t.upper()


def _build_tv_index(names):
    global TV_NAMES, TV_BY_HEAD
    TV_NAMES = tuple(sorted({n for n in names if n}))
    idx = {}
    for n in TV_NAMES:
        idx.setdefault(n[0], []).append(n)
    TV_BY_HEAD = idx


def is_tv(name):
    """是不是"电视台"：和白名单里的名字完全相同，或互为前缀（CCTV1 / CCTV-1 综合 都算）"""
    k = tv_norm(name)
    if not k:
        return False
    bucket = TV_BY_HEAD.get(k[0]) or ()
    for w in bucket:
        if k == w:
            return True
        if len(w) >= 3 and (k.startswith(w) or w.startswith(k)):
            return True
    return False


def _load_tvlist():
    try:
        d = json.loads(TVLIST_PATH.read_text(encoding="utf-8"))
        if time.time() - float(d.get("ts") or 0) < TVLIST_TTL:
            names = d.get("names") or []
            if len(names) >= 100:
                _build_tv_index(names)
                return len(TV_NAMES)
    except Exception:
        pass
    return 0


def _fetch_tvlist():
    urls = [TVLIST_BASE + quote(f) for f in TVLIST_FILES]
    texts = []

    def one(u):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA),
                                        timeout=12, context=_SSL_CTX) as r:
                return r.read().decode("utf-8-sig", "ignore")
        except Exception:
            return ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        texts = [t for t in ex.map(one, urls) if t.strip()]
    names = []
    for t in texts:
        names += [x.strip() for x in t.splitlines() if x.strip()]
    norm = sorted({tv_norm(n) for n in names if tv_norm(n)})
    if len(norm) >= 100:
        try:
            TVLIST_PATH.write_text(json.dumps({"ts": time.time(), "names": norm}, ensure_ascii=False),
                                   encoding="utf-8")
        except OSError:
            pass
        _build_tv_index(norm)
        log("电视台名单: %d 个名字（来自 %d/%d 个名单文件）" % (len(TV_NAMES), len(texts), len(urls)))
    return len(TV_NAMES)


def ensure_tvlist(force=False):
    n = 0 if force else _load_tvlist()
    if not n:
        n = _fetch_tvlist()
    return n


def keep_entry(e, cfg):
    if e["tag"].startswith("epg_") and not CJK_RE.search(e["name"]):
        return False
    if cfg.get("filter_junk", True) and JUNK_RE.search(e["name"]):
        return False
    if cfg.get("only_tv", True) and TV_NAMES and not is_tv(e["name"]):
        return False
    g = classify(e["name"], e["tag"])
    if g in ("香港", "澳门", "台湾"):
        return True
    if quality(e["name"]) == "SD" and not cfg["keep_sd"]:
        return False
    return True


# ---------------------------------------------------------------- 网络探测

def _open(url, timeout):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=_SSL_CTX)


def probe_reach(e, timeout):
    """第一阶段：可达性 + 首包时间。返回 (ok, ttfb_ms, note)"""
    url = e["url"]
    if not url.startswith(("http://", "https://")):
        m = re.match(r"\w+://([^/:]+)(?::(\d+))?", url)
        if not m:
            return False, 0, "地址无法解析"
        try:
            t0 = time.monotonic()
            s = socket.create_connection((m.group(1), int(m.group(2) or 1935)), timeout=timeout)
            s.close()
            return True, round((time.monotonic() - t0) * 1000), "非HTTP流(TCP探测)"
        except Exception:
            return False, 0, "TCP不可达"
    try:
        t0 = time.monotonic()
        resp = _open(url, timeout)
        ttfb = round((time.monotonic() - t0) * 1000)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        head = b""
        try:
            head = resp.read(1024) or b""
        except Exception:
            pass
        resp.close()
        low = head[:1024].lower()
        # 很多"看着能连"的地址其实返回的是网页(频道主页/登录页/错误页)，要判为失效
        if ctype.startswith("text/html") or b"<html" in low or b"<!doctype" in low:
            return False, ttfb, "返回网页(非直播流)"
        return True, ttfb, ""
    except Exception:
        return False, 0, "不可达"


def probe_stream(e, timeout, budget=0.7, max_bytes=786432):
    """一次连接同时判断：能不能连、是不是真流(不是网页)、能不能拉出画面、大概几兆、分辨率多少。

    返回 (ok, ttfb_ms, note, mbps, res_h)。
    budget 是"读多久算够"的秒数，max_bytes 是最多读多少字节 —— 两者都刻意压得很小，
    只为判断可用性与大致画质，不是为了测速跑分。
    """
    url = e["url"]
    if not url.startswith(("http://", "https://")):
        m = re.match(r"\w+://([^/:]+)(?::(\d+))?", url)
        if not m:
            return False, 0, "地址无法解析", 0.0, 0
        try:
            t0 = time.monotonic()
            sk = socket.create_connection((m.group(1), int(m.group(2) or 1935)), timeout=timeout)
            sk.close()
            return True, round((time.monotonic() - t0) * 1000), "非HTTP流(TCP探测)", 0.0, 0
        except Exception:
            return False, 0, "TCP不可达", 0.0, 0
    try:
        t0 = time.monotonic()
        resp = _open(url, timeout)
        ttfb = round((time.monotonic() - t0) * 1000)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        res_h = 0
        if ".m3u8" in url.lower() or "mpegurl" in ctype:
            data = resp.read(262144).decode("utf-8", "ignore")
            resp.close()
            low = data[:2048].lower()
            if "<html" in low or "<!doctype" in low:
                return False, ttfb, "返回网页(非直播流)", 0.0, 0
            cands = []
            for attrs, seg in re.findall(r"#EXT-X-STREAM-INF:([^\n]*)\n([^\r\n]+)", data):
                bwm = re.search(r"BANDWIDTH=(\d+)", attrs)
                resm = re.search(r"RESOLUTION=(\d+)x(\d+)", attrs)
                cands.append((int(bwm.group(1)) if bwm else 0,
                              seg.strip(), int(resm.group(2)) if resm else 0))
            if cands:
                _, seg, res_h = max(cands, key=lambda v: v[0])
            else:
                lines = [l.strip() for l in data.splitlines() if l.strip() and not l.startswith("#")]
                seg = next((l for l in lines if ".ts" in l or ".m4s" in l or ".flv" in l), "")
                if not seg:
                    return False, ttfb, "清单里没有可播放分片", 0.0, res_h
            target = seg if seg.startswith("http") else url.rsplit("/", 1)[0] + "/" + seg
            resp = _open(target, timeout)
        total = 0
        head = b""
        t_read = time.monotonic()
        while total < max_bytes and time.monotonic() - t_read < budget:
            try:
                b = resp.read(65536)
            except Exception:
                break
            if not b:
                break
            if not head:
                head = b[:1024]
            total += len(b)
        dt = time.monotonic() - t_read
        try:
            resp.close()
        except Exception:
            pass
        low = head.lower()
        if "text/html" in ctype or b"<html" in low or b"<!doctype" in low:
            return False, ttfb, "返回网页(非直播流)", 0.0, 0
        if total <= 0:
            return False, ttfb, "连得上但拉不到画面", 0.0, res_h
        # 读太少会算出几百 Mbps 的假数字(64KB 在 2ms 内读完≈262 Mbps)，而且一批源会卡在同一个
        # 上限上，排序看着全是同一档。这里至少凑够 0.05 秒的窗口，封顶 300 Mbps。
        mbps = round(min(300.0, (total * 8 / 1e6) / max(dt, 0.05)), 2)
        return True, ttfb, "", mbps, res_h
    except Exception:
        return False, 0, "不可达", 0.0, 0


def probe_speed(e, timeout):
    """第二阶段：实际下载媒体分片测吞吐。返回 (ok, mbps, res_h)，res_h=主清单实测分辨率高(像素，0=未知)"""
    url = e["url"]
    if not url.startswith(("http://", "https://")):
        return False, 0.0, 0
    try:
        resp = _open(url, timeout)
        target = url
        res_h = 0
        if ".m3u8" in url.lower() or "mpegurl" in resp.headers.get("Content-Type", ""):
            data = resp.read(262144).decode("utf-8", "ignore")
            resp.close()
            # 主清单：按 BANDWIDTH 选最高档，同时取该档 RESOLUTION 的实测高度
            cands = []
            for attrs, seg in re.findall(r"#EXT-X-STREAM-INF:([^\n]*)\n(\S+)", data):
                bwm = re.search(r"BANDWIDTH=(\d+)", attrs)
                resm = re.search(r"RESOLUTION=(\d+)x(\d+)", attrs)
                cands.append((int(bwm.group(1)) if bwm else 0,
                              seg, int(resm.group(2)) if resm else 0))
            if cands:
                _, seg, res_h = max(cands, key=lambda v: v[0])
            else:
                lines = [l.strip() for l in data.splitlines() if l.strip() and not l.startswith("#")]
                seg = next((l for l in lines if ".ts" in l or ".m4s" in l), None)
                if not seg:
                    return True, 0.0, res_h
            target = seg if seg.startswith("http") else url.rsplit("/", 1)[0] + "/" + seg
            resp = _open(target, timeout)
        t0 = time.monotonic()
        total = 0
        while total < 256 * 1024 and time.monotonic() - t0 < 1.5:
            b = resp.read(65536)
            if not b:
                break
            total += len(b)
        dt = time.monotonic() - t0
        resp.close()
        if total <= 0:
            return False, 0.0, res_h
        return True, round((total * 8 / 1e6) / max(dt, 0.001), 2), res_h
    except Exception:
        return False, 0.0, 0


def score_src(s):
    """排序分：越小越优(仅用于展示排序，不影响 M3U 导出的最佳源判定)"""
    sc = s.get("ttfb") or 9999
    mbps = s.get("mbps") or 0
    if mbps < 3:
        sc += 800
    if mbps < 1:
        sc += 2000
    return sc


# 位置基准：频道所属区域优先匹配的源标签(用于「区域是否对口」判定)
REGION_TAG = {
    "香港": {"kelvin", "org_hk", "epg_hk"},
    "澳门": {"org_mo", "epg_mo"},
    "台湾": {"org_tw", "epg_tw"},
    "国内": {"cn_org", "yang"},
}


def _src_quality(s, ch):
    """推断该源的画质等级 1-4：优先流内实测分辨率，其次 URL/频道名 (4=4K+, 3=1080P, 2=720P, 1=标清/未知)"""
    res_h = s.get("res") or 0
    if res_h >= 2000:
        return 4
    if res_h >= 1000:
        return 3
    if res_h >= 620:
        return 2
    u = (s.get("url") or "").lower()
    if re.search(r"4k|2160|uhd|8k", u):
        return 4
    if re.search(r"1080|1920|fhd|超高清|蓝光", u):
        return 3
    if re.search(r"720|\bhd\b|高清", u):
        return 2
    q = ch.get("quality")
    if q == "1080P":
        return 3
    if q == "HD":
        return 2
    return 1


def pick_best_source(ch):
    """程序权威筛选：在已验证可用的源中，按「图像质量 > 位置基准 > 链接速度」选出唯一最佳源。
    返回被选中的源(dict)；无可用源返回 None。该最佳源即为写入 M3U 的唯一地址(不列备选)。"""
    live = [s for s in ch["sources"] if s.get("live") and s.get("url")]
    if not live:
        return None
    region = REGION_TAG.get(ch["group"], set())

    def score(s):
        q = _src_quality(s, ch)                       # 图像质量(越高越好)
        loc = 1 if s["tag"] in region else 0          # 位置基准：源的区域标签是否对口
        ttfb = s.get("ttfb") or 9999                  # 链接速度：首包延迟(越低越好)
        mbps = s.get("mbps") or 0                     # 链接速度：吞吐(越高越好)
        spd = max(0.0, (2000 - ttfb) / 500.0) + min(mbps, 40) * 0.5
        return (q, loc, spd)
    return max(live, key=score)


# ---------------------------------------------------------------- 台标解析

# 图标库模板({name} 为 URL 编码后的中文台名)；均为 2026-10 实测用户网络可达
LOGO_TPLS = [
    "https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/logo/{name}.png",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/{name}.png",
]
LOGO_TTL = 7 * 86400          # 台标实测结果缓存 7 天
_LOGO_CACHE = {}              # url -> [unix_ts, ok]

def _load_logo_cache():
    try:
        if LOGO_CACHE_PATH.exists():
            d = json.loads(LOGO_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                for k, v in d.items():
                    if isinstance(v, list) and len(v) == 2:
                        _LOGO_CACHE[k] = [float(v[0]), bool(v[1])]
    except Exception:
        pass

def _save_logo_cache():
    try:
        LOGO_CACHE_PATH.write_text(json.dumps(_LOGO_CACHE, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass

def _check_logo(url, timeout=2):
    """HTTP 200 且响应头几个字节为 PNG/JPEG 魔数才认定为可用台标(防 JSON/HTML 冒充)"""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                    timeout=timeout, context=_SSL_CTX) as r:
            head = r.read(16)
        return head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff")
    except Exception:
        return False

def resolve_logo(name, src_logo):
    """台标候选链：源自带(逐条实测) -> CCSH 图标库(中文名) -> fanmingming 图标库(中文名)。
    任何候选必须实测 200+图片魔数才采用；结果缓存 7 天。返回可用 URL 或空串。"""
    # 源自带的台标直接采用(全是 https 图片地址，逐条实测白花时间)；只有它缺失才去图标库找
    if src_logo and src_logo.startswith(("https://", "http://")):
        return src_logo
    cands = []
    qn = quote(name)
    cands += [t.format(name=qn) for t in LOGO_TPLS]
    now = time.time()
    for u in cands:
        ent = _LOGO_CACHE.get(u)
        if ent and now - ent[0] < LOGO_TTL:
            if ent[1]:
                return u
            continue
        ok = _check_logo(u)
        _LOGO_CACHE[u] = [now, ok]
        if ok:
            return u
    return ""


# 判定为「网页/中转页」的地址记下来，短期内不再重复探测(也避免重复触发杀软)
BLOCK_HOSTS = {"live.iill.top", "www.iill.top"}
BAD_URL_PATH = BASE / "bad_urls.json"
BAD_URL_TTL = 3 * 86400
_BAD_URLS = None


def _load_bad_urls():
    global _BAD_URLS
    if _BAD_URLS is None:
        _BAD_URLS = {}
        try:
            raw = json.loads(BAD_URL_PATH.read_text("utf-8"))
            if isinstance(raw, dict):
                now = time.time()
                _BAD_URLS = {k: v for k, v in raw.items()
                             if isinstance(v, (int, float)) and now - v < BAD_URL_TTL}
        except Exception:
            _BAD_URLS = {}
    return _BAD_URLS


def _save_bad_urls():
    try:
        BAD_URL_PATH.write_text(json.dumps(_load_bad_urls(), ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def mark_bad_url(url):
    if not url:
        return
    _load_bad_urls()[url] = time.time()


HOST_STATE_PATH = BASE / "hosts.json"
_HOST_STATE = None


def _load_host_state():
    global _HOST_STATE
    if _HOST_STATE is None:
        try:
            raw = json.loads(HOST_STATE_PATH.read_text("utf-8"))
            _HOST_STATE = raw if isinstance(raw, dict) else {}
        except Exception:
            _HOST_STATE = {}
    return _HOST_STATE


def _save_host_state(st):
    try:
        HOST_STATE_PATH.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------- 更新器

class Updater:
    def __init__(self, cfg):
        self.cfg = cfg
        self.channels = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.prev_live = set()      # 上次更新里能用的地址(增量更新的起点)
        _load_logo_cache()
        self.state = {
            "updating": False, "phase": "空闲", "done": 0, "total": 0,
            "last_update": "", "next_update": 0, "error": "",
            "next_self_update": 0, "self_update_msg": "",
            "stats": {"channels": 0, "sources": 0, "live": 0, "hkmt": 0, "by_group": {}},
            "source_stats": {},   # key -> {name, ok, count, ms, url, region}
        }
        self.argv = []

    # ---------- 抓取 ----------
    def fetch_all(self):
        cfg = self.cfg
        enabled = [it for it in SOURCES if cfg["sources"].get(it[0])]
        if cfg.get("only_tv", True) and not TV_NAMES:
            if ensure_tvlist():
                log("只保留电视台频道：已载入 %d 个频道名做白名单" % len(TV_NAMES))
            else:
                log("提示: 电视台名单获取失败，本轮不做白名单过滤（频道可能混入影视切片）")
        self.state.update(phase="正在下载直播源列表", done=0, total=len(enabled))
        lock = threading.Lock()
        per_source = {}

        # raw.githubusercontent 在这条线路上经常直连不通；先快速探一下，不通就整轮直接走镜像，
        # 避免每个源都白等一次超时(实测这一项能省 40 秒以上)
        direct_bad = set()
        try:
            _open("https://raw.githubusercontent.com/", 4).close()
        except Exception:
            direct_bad.add("raw.githubusercontent.com")
            log("提示: GitHub raw 直连不通，本轮自动走镜像加速")

        def fetch_one(item):
            key, name, url, _, region = item
            t0 = time.monotonic()
            urls = [url]
            for fb in SOURCE_FALLBACKS.get(key, ()):
                if fb not in urls:
                    urls.append(fb)
            text, used = None, ""
            # 尝试顺序：备选地址(jsdelivr 等免代理线路) -> 镜像前缀 -> 直连。
            # 直连不通时把直连放最后，能省掉每个源白等一次超时。
            plan = []
            for u in urls[1:]:
                if (urlparse(u).hostname or "").lower() not in direct_bad and u not in plan:
                    plan.append(u)
            for u in urls:
                host = (urlparse(u).hostname or "").lower()
                if host not in direct_bad and u not in plan:
                    plan.append(u)
            for u in urls:
                if (urlparse(u).hostname or "").lower() in ("raw.githubusercontent.com", "github.com"):
                    for m in MIRRORS:
                        cand = m + u
                        if m and cand not in plan:
                            plan.append(cand)
            if not plan:
                plan = list(urls)
            for u in plan:
                try:
                    with urllib.request.urlopen(urllib.request.Request(u, headers=UA),
                                                timeout=8, context=_SSL_CTX) as r:
                        t = r.read().decode("utf-8", "ignore")
                    if t and "#EXTINF" in t:
                        text, used = t, u
                        break
                except Exception:
                    continue
            n = 0
            es = []
            if text:
                es = [e for e in parse_m3u(text, key) if keep_entry(e, cfg)]
                n = len(es)
                if used != url:
                    log("源[%s] 备选地址生效 %s -> %d 条" % (name, used, n))
                else:
                    log("源[%s] 获取 %d 条" % (name, n))
            else:
                log("源[%s] 所有地址(含备选)均失败" % name)
            with lock:
                per_source[key] = (name, region, es, used or url, bool(text))
                self.state["source_stats"][key] = {
                    "name": name, "region": region, "ok": bool(text), "count": n,
                    "ms": int((time.monotonic() - t0) * 1000),
                    "url": used or url, "fallback": bool(text and used != url),
                    "live_ratio": None, "sample": 0, "sample_ok": 0,
                }

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            list(ex.map(fetch_one, enabled))

        # 每个源抽 20 条实测一下"能播多少"(不是全测，全测太慢)：
        # 结果既写进界面的源列表，也用来给候选地址排序、把明显不行的源剪掉
        sample_todo = []
        for key, (name, region, es, used, ok) in per_source.items():
            if es:
                step = max(1, len(es) // 20)
                for e in es[::step][:20]:
                    sample_todo.append((key, e))
        self.state.update(phase="源健康抽样", done=0, total=len(sample_todo))
        scnt = [0]
        sstat = {}
        for key in per_source:
            sstat[key] = [0, 0]

        def sample(item):
            key, e = item
            ok, _, _ = probe_reach(e, 2.0)
            with lock:
                sstat[key][0] += 1
                if ok:
                    sstat[key][1] += 1
                scnt[0] += 1
                self.state["done"] = scnt[0]

        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            list(ex.map(sample, sample_todo))
        for key, (n, good) in sstat.items():
            st = self.state["source_stats"].get(key)
            if not st:
                continue
            st["sample"] = n
            st["sample_ok"] = good
            st["live_ratio"] = round(good / float(n), 3) if n else 0.0
        for key, st in sorted(self.state["source_stats"].items(),
                              key=lambda kv: -(kv[1].get("live_ratio") or 0)):
            if st.get("sample"):
                log("源[%s] 抽样可用率 %d/%d" % (st["name"], st["sample_ok"], st["sample"]))

        out = []
        for key, (name, region, es, used, ok) in per_source.items():
            out.extend(es)
        return out

    # ---------- 合并去重 ----------
    @staticmethod
    def merge(entries):
        merged = {}
        for e in entries:
            k = norm_name(e["name"])
            if not k:
                continue
            q0 = e.get("q0") or quality(e["name"])
            if k not in merged:
                merged[k] = {"name": e["name"], "group": classify(e["name"], e["tag"]),
                             "logo": e["logo"], "quality": q0, "sources": []}
            ch = merged[k]
            # 显示名优先用不带括号注释的；其次优先中文名(多源同一频道时统一为中文)
            if BRACKET_RE.search(ch["name"]) and not BRACKET_RE.search(e["name"]):
                ch["name"] = e["name"]
            if not CJK_RE.search(ch["name"]) and CJK_RE.search(e["name"]):
                ch["name"] = e["name"]
            if e["logo"] and not ch["logo"]:
                ch["logo"] = e["logo"]
            if q0 == "1080P":
                ch["quality"] = "1080P"
            ch["sources"].append({"url": e["url"], "tag": e["tag"], "ttfb": 0, "mbps": 0, "live": False, "note": ""})
        for ch in merged.values():
            seen, uniq = set(), []
            for s in ch["sources"]:
                if s["url"] not in seen:
                    seen.add(s["url"])
                    uniq.append(s)
            ch["sources"] = uniq
        return merged

    # ---------- 连通性 + 吞吐(按 URL 去重；上次在用的先探，够用就不再多探) ----------
    def verify(self, merged):
        cfg = self.cfg
        cap = max(1, min(cfg["backups"] + 1, 5))
        workers = max(8, int(cfg["concurrency"]))

        # 按"源抽样可用率"给候选排序：可用率高的源先上，明显不行的源只留一条兜底。
        # 这样要探测的地址少一大截，结果也更干净(不会满屏都是死链)。
        ratio = {}
        for k, st in (self.state.get("source_stats") or {}).items():
            r = st.get("live_ratio")
            ratio[k] = 0.5 if r is None else float(r)
        best_ratio = max(ratio.values()) if ratio else 0.5
        floor = max(0.05, best_ratio * 0.35)

        by_url, order, owner = {}, [], {}
        for k, ch in merged.items():
            cand = sorted(ch["sources"], key=lambda s: (-ratio.get(s["tag"], 0.5), s["url"]))
            keep = [s for s in cand if ratio.get(s["tag"], 0.5) >= floor][:cap] or cand[:1]
            ch["sources"] = keep + [s for s in ch["sources"] if s not in keep]
            for s in keep:
                u = s["url"]
                if u not in by_url:
                    by_url[u] = []
                    order.append(u)
                    owner[u] = set()
                by_url[u].append(s)
                owner[u].add(k)

        lock = threading.Lock()
        counter = [0]
        bad = _load_bad_urls()
        hstate = _load_host_state()
        prev = set(getattr(self, "prev_live", ()) or ())

        def host_of(u):
            try:
                return (urlparse(u).hostname or "").lower()
            except Exception:
                return ""

        def hp_of(u):
            try:
                pu = urlparse(u)
                port = pu.port or (443 if pu.scheme == "https" else 80)
                return "%s:%d" % ((pu.hostname or "").lower(), port)
            except Exception:
                return u

        def is_blocked(u):
            if u in bad or host_of(u) in BLOCK_HOSTS:
                return True
            hs = hstate.get(hp_of(u)) or {}
            if (hs.get("ok", 0) == 0 and hs.get("dead", 0) >= 4
                    and time.time() - float(hs.get("ts", 0)) < 3 * 86400):
                return True      # 近三天这个服务器一次都没通过，别浪费时间
            return False

        def mark(u, ok, ttfb, note):
            for s in by_url[u]:
                s["live"], s["ttfb"], s["note"] = ok, ttfb, note

        def probe_batch(urls, timeout, phase):
            if not urls:
                return
            self.state.update(phase=phase, done=0, total=len(urls))
            counter[0] = 0

            def work(u):
                ok, ttfb, note = probe_reach(by_url[u][0], timeout)
                if not ok and note.startswith("返回网页"):
                    mark_bad_url(u)
                mark(u, ok, ttfb, note)
                with lock:
                    counter[0] += 1
                    self.state["done"] = counter[0]

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(work, urls))

        # 0) 拉黑/上次判定不通的地址，直接标失效，不再访问
        todo = []
        for u in order:
            if is_blocked(u):
                mark(u, False, 0, "跳过(上次判定为网页/中转页或整站不通)")
            else:
                todo.append(u)
        n_skip = len(order) - len(todo)

        # 1) 一次连接同时拿到：能不能连 / 是不是网页 / 能不能出画面 / 大概几兆 / 分辨率
        #    (原来要分"连通性 → 慢速重试 → 测速"三段，同一地址连两三遍，这是整轮最慢的地方)
        t0 = time.monotonic()
        self.state.update(phase="探测并验证直播流", done=0, total=len(todo))
        counter[0] = 0


        def work(u):
            recs = by_url[u]
            ok, ttfb, note, mbps, res_h = probe_stream(recs[0], timeout=2.5)
            if not ok and note.startswith("返回网页"):
                mark_bad_url(u)
            # 能连上但吞吐低到 0.5 Mbps 以下，播起来必然卡：直接当不能用，别让它挤掉好线路
            if ok and mbps and mbps < 0.5:
                ok, note = False, "速度过慢(%.2f Mbps)" % mbps
            for sl in recs:
                sl["live"], sl["ttfb"], sl["note"] = ok, ttfb, note
                if ok:
                    if mbps:
                        sl["mbps"] = mbps
                    if res_h:
                        sl["res"] = res_h
            with lock:
                counter[0] += 1
                self.state["done"] = counter[0]

        # 一个线程池跑完：分批建池会让每批都重新起几百个线程，白白多花十几秒
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(work, todo))

        n_ok = sum(1 for u in order if by_url[u][0]["live"])
        log("探测完成: %d 个地址里 %d 个能出画面(%.0fs；跳过 %d 个已知不通的、%d 个上次在用)"
            % (len(order), n_ok, time.monotonic() - t0, n_skip, len(prev & set(order))))
        _save_bad_urls()

        # 记下每个服务器的成/败，下一轮直接跳过长期不通的(省时间，也少扰民)
        for u in order:
            hp = hp_of(u)
            hs = hstate.setdefault(hp, {"ts": time.time(), "ok": 0, "dead": 0})
            if by_url[u][0]["live"]:
                hs["ok"] = int(hs.get("ok", 0)) + 1
            else:
                hs["dead"] = int(hs.get("dead", 0)) + 1
            hs["ts"] = time.time()
        _save_host_state(hstate)

    # ---------- 台标 ----------
    def resolve_logos(self, channels):
        """只给实测可播的频道解析台标；候选链全部实测(200+图片魔数)，结果缓存 7 天"""
        todo = [(k, ch) for k, ch in channels.items() if ch.get("best") and ch["best"].get("live")]
        if not todo:
            return
        self.state.update(phase="解析台标", done=0, total=len(todo))
        cnt = [0]

        def one(item):
            _, ch = item
            try:
                ch["logo"] = resolve_logo(ch["name"], ch.get("logo", ""))
            except Exception:
                pass
            cnt[0] += 1
            self.state["done"] = cnt[0]

        t_logo0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            list(ex.map(one, todo))
        _save_logo_cache()
        n_logo = sum(1 for _, ch in todo if ch["logo"])
        log("台标解析完成: %d/%d 频道有台标(%.0fs)" % (n_logo, len(todo), time.monotonic() - t_logo0))

    # ---------- 组装 ----------
    @staticmethod
    def finalize(merged, backups):
        out = {}
        for k, ch in merged.items():
            live = sorted((s for s in ch["sources"] if s["live"]), key=score_src)
            best = pick_best_source(ch)   # 程序权威筛选的唯一最佳源(画质=名称+流内实测分辨率)
            q = ch["quality"] or ""
            if best:
                rh = best.get("res") or 0
                if rh >= 2000:
                    q = "4K"
                elif rh >= 1000 and q != "4K":
                    q = "1080P"
                elif rh >= 620 and q not in ("1080P", "4K"):
                    q = "HD"
            out[k] = {
                "key": k, "name": ch["name"], "group": ch["group"],
                "quality": q, "logo": ch["logo"],
                "sources": live[:backups], "live_count": len(live),
                "playable": bool(best and best.get("url", "").startswith("http")),
                "best": best,
            }
        return out

    # ---------- 完整更新 ----------
    def run_once(self):
        if self.state["updating"]:
            return False
        self.state.update(updating=True, error="", done=0, total=0)
        t0 = time.time()
        tray_busy(True)          # 托盘图标切"方块"：一眼看出正在更新
        try:
            self.prev_live = set()
            for ch in (self.channels or {}).values():
                for s in ch.get("sources") or ():
                    if s.get("live"):
                        self.prev_live.add(s["url"])
                b = ch.get("best") or {}
                if b.get("url"):
                    self.prev_live.add(b["url"])
            entries = self.fetch_all()
            log("共获取 %d 条原始记录" % len(entries))
            merged = self.merge(entries)
            log("去重后 %d 个频道" % len(merged))
            self.verify(merged)
            channels = self.finalize(merged, self.cfg["backups"])
            self.resolve_logos(channels)
            with self.lock:
                self.channels = channels
            self.state["stats"] = self.compute_stats(channels)
            self.state["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.state["next_update"] = time.time() + self.cfg["interval_hours"] * 3600
            self.state["phase"] = "完成"
            self.save_cache(channels)
            n, skip = self.write_m3u(self.cfg["output_path"])
            st = self.state["stats"]
            cost = time.time() - t0
            log("更新完成: 频道 %d(可用 %d) / 写入源 %d / 港澳台 %d / 跳过失效频道 %d，耗时 %.0fs"
                % (st["channels"], st["live"], n, st["hkmt"], skip, cost))
            tray_busy(False)     # 先把托盘换回三角，再弹提示，免得提示里挂着"更新中"
            tray_notify("更新完成",
                        "%d 个频道可用 · 用时 %.0f 秒" % (st["live"], cost))
            return True
        except Exception as e:
            self.state["error"] = str(e)
            log("更新失败: %s" % e)
            tray_notify("更新失败", str(e)[:120])
            return False
        finally:
            tray_busy(False)     # 不管成功失败，都换回"三角"
            self.state["updating"] = False

    @staticmethod
    def compute_stats(channels):
        by_group = {}
        ns = nl = nh = 0
        for ch in channels.values():
            by_group[ch["group"]] = by_group.get(ch["group"], 0) + 1
            ns += len(ch["sources"])
            nl += 1 if ch["sources"] else 0
            if ch["group"] in ("香港", "澳门", "台湾"):
                nh += 1
        return {"channels": len(channels), "sources": ns, "live": nl, "hkmt": nh, "by_group": by_group}

    def save_cache(self, channels):
        try:
            CACHE_PATH.write_text(json.dumps({
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "channels": channels,
            }, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            log("缓存保存失败: %s" % e)

    def load_cache(self):
        try:
            if not CACHE_PATH.exists():
                return False
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            saved = datetime.fromisoformat(data["saved_at"])
            age_h = (datetime.now() - saved).total_seconds() / 3600
            if age_h > self.cfg["interval_hours"]:
                return False
            self.channels = data["channels"]
            self.state["stats"] = self.compute_stats(self.channels)
            self.state["last_update"] = saved.strftime("%Y-%m-%d %H:%M:%S")
            self.state["next_update"] = time.time() + max(0, self.cfg["interval_hours"] - age_h) * 3600
            log("已加载缓存: %d 频道(%.1f 小时前更新)" % (len(self.channels), age_h))
            return True
        except Exception as e:
            log("缓存加载失败: %s" % e)
            return False

    # ---------- M3U 写出(每频道只写程序筛选出的唯一最佳源，不列备选) ----------
    def write_m3u(self, path, keys=None):
        with self.lock:
            channels = self.channels
        if not channels:
            log("无频道数据，跳过 M3U 写出(保留原文件)")
            return 0, 0
        lines = ["#EXTM3U"]
        if self.cfg["epg_url"]:
            lines[0] += ' x-tvg-url="%s"' % self.cfg["epg_url"]
        lines.append("# 由 %s v%s 生成于 %s" % (APP_NAME, VERSION, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        lines.append("# 筛选标准(程序权威)：画质(实测分辨率4K/1080P优先) > 区域基准 > 链接速度；每个频道仅保留唯一最佳源")
        n_src = n_ch = n_skip = 0
        present = sorted({ch["group"] for ch in channels.values()},
                         key=lambda g: (GROUP_RANK.index(g) if g in GROUP_RANK else 50, g))
        for g in present:
            gch = sorted((c for c in channels.values() if c["group"] == g),
                         key=lambda c: (-((c.get("best") or {}).get("mbps") or 0), c["name"]))
            for ch in gch:
                if keys is not None and ch["key"] not in keys:
                    continue
                best = ch.get("best")
                if not best or not best.get("live") or not best.get("url"):
                    if keys is None:
                        n_skip += 1
                    continue
                mm = float(self.cfg.get("min_mbps") or 0)
                if mm and (best.get("mbps") or 0) < mm:
                    n_skip += 1
                    continue
                n_ch += 1
                n_src += 1
                lines.append('#EXTINF:-1 tvg-name="%s" tvg-logo="%s" group-title="%s",%s'
                             % (esc_attr(ch["name"]), esc_attr(ch["logo"]), g, ch["name"]))
                lines.append(best["url"])
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
        return n_src, n_skip

    # ---------- 循环 ----------
    def loop(self):
        while not self.stop.is_set():
            # 直播源自动更新
            if time.time() >= self.state["next_update"]:
                self.run_once()
            # 程序自身自动更新(可配置检查间隔，发现新版可选自动替换)
            if time.time() >= self.state.get("next_self_update", 0):
                self.state["next_self_update"] = time.time() + max(1, self.cfg.get("update_check_hours", 24)) * 3600
                if self.cfg.get("self_update") and self.cfg.get("update_url"):
                    try:
                        info = check_self_update(self.cfg)
                        if info and self.cfg.get("update_auto"):
                            res = apply_self_update(info, self.argv)
                            if res is True:
                                self.state["self_update_msg"] = "已更新到新版本并重启"
                                log("程序已自更新，退出旧进程以让新版本接管")
                                os._exit(0)
                            elif isinstance(res, dict):
                                self.state["self_update_msg"] = res.get("msg", "")
                        elif info:
                            self.state["self_update_msg"] = "发现新版本 v%s" % info["version"]
                            tray_notify("有新版本 v%s" % info["version"],
                                        "打开控制台 → 设置里可以一键升级")
                        else:
                            self.state["self_update_msg"] = ""
                    except Exception as e:
                        log("程序自更新检查异常: %s" % e)
            self.stop.wait(30)


# ---------------------------------------------------------------- 网页控制台

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LIVE直播源</title>
<link rel="icon" href="__FAVICON__">
<style>
:root{
  --accent:#e11d2e; --accent-d:#c21423; --accent-l:#fdecee;
  --bg:#f4f5f7; --card:#fff; --txt:#1b1f24; --sub:#6b7280; --line:#e6e8ec;
  --ok:#16a34a; --warn:#d97706; --bad:#dc2626;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 8px 24px -12px rgba(16,24,40,.18);
  --r:14px;
}
html[data-theme="dark"]{
  --bg:#101216; --card:#181c22; --txt:#e8eaee; --sub:#9aa2ae; --line:#262c35;
  --accent-l:#3a1218; --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -14px rgba(0,0,0,.7);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
  font:14px/1.55 "Segoe UI","Microsoft YaHei UI","Microsoft YaHei",system-ui,-apple-system,sans-serif;
  -webkit-font-smoothing:antialiased}
button{font:inherit;cursor:pointer;border:0;background:none;color:inherit}
input,select{font:inherit;color:inherit}
a{color:var(--accent);text-decoration:none}

/* ---------------- 顶栏 ---------------- */
header{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--card) 88%,transparent);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.hbar{max-width:1120px;margin:0 auto;padding:8px 18px;display:flex;align-items:center;gap:12px}
.logo{width:38px;height:38px;border-radius:0;box-shadow:none;background:transparent;display:block}
.brand{display:flex;flex-direction:column;line-height:1.15}
.brand b{font-size:16px;letter-spacing:.2px}
.brand span{font-size:11px;color:var(--sub)}
.pill{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 10px;border-radius:999px;
  background:var(--bg);border:1px solid var(--line);font-size:12px;color:var(--sub);white-space:nowrap}
.dot{width:7px;height:7px;border-radius:50%;background:var(--sub)}
.dot.on{background:var(--ok);box-shadow:0 0 0 3px color-mix(in srgb,var(--ok) 18%,transparent)}
.dot.run{background:var(--accent);animation:blink 1s infinite}
/* 状态图标跟右下角托盘同款：红圆角方块 + 白三角（空闲） / 白方块（更新中） */
.ti{width:15px;height:15px;border-radius:4.5px;flex:0 0 auto;position:relative;
  background:linear-gradient(180deg,#f50a38,#c4001a);box-shadow:0 1px 2px rgba(225,29,46,.35)}
.ti::after{content:"";position:absolute;left:5.5px;top:3.5px;width:0;height:0;
  border-left:6px solid #fff;border-top:4px solid transparent;border-bottom:4px solid transparent}
.ti.run::after{left:4.5px;top:4.5px;width:6px;height:6px;border:0;background:#fff;border-radius:1px}
.ti.run{animation:blink 1s infinite}
.ti.off{filter:grayscale(1);opacity:.55}
@keyframes blink{50%{opacity:.25}}
.spacer{flex:1}
.btn{height:32px;padding:0 13px;border-radius:10px;border:1px solid var(--line);background:var(--card);
  color:var(--txt);font-size:13px;display:inline-flex;align-items:center;gap:6px;transition:.15s}
.btn:hover{border-color:color-mix(in srgb,var(--accent) 45%,var(--line));color:var(--accent)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.btn.primary:hover{background:var(--accent-d);color:#fff}
.btn.danger:hover{border-color:var(--bad);color:var(--bad)}
.btn:disabled{opacity:.5;cursor:not-allowed}

/* 进度条 */
.pwrap{height:3px;background:transparent;overflow:hidden}
.pwrap.show{background:var(--line)}
.pbar{height:100%;width:0;background:linear-gradient(90deg,var(--accent),#ff6b7a);transition:width .35s}

/* ---------------- 主体 ---------------- */
main{max-width:1120px;margin:0 auto;padding:12px 18px 84px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow)}
.stat{padding:8px 12px}
.stat b{display:block;font-size:19px;line-height:1.15;font-variant-numeric:tabular-nums}
.stat span{font-size:11.5px;color:var(--sub)}
.phase{font-size:12px;color:var(--sub);padding:0 2px 8px;grid-column:1/-1}

.toolbar{padding:9px 12px;display:flex;flex-direction:column;gap:8px}
.row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.search{flex:1;min-width:180px;height:32px;border:1px solid var(--line);border-radius:10px;
  background:var(--bg);padding:0 12px;outline:none}
.search:focus{border-color:var(--accent);background:var(--card)}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{height:26px;padding:0 10px;border-radius:999px;border:1px solid var(--line);background:transparent;
  font-size:12.5px;color:var(--sub);transition:.15s}
.chip:hover{color:var(--txt);border-color:color-mix(in srgb,var(--accent) 35%,var(--line))}
.chip.on{background:var(--accent-l);border-color:color-mix(in srgb,var(--accent) 40%,var(--line));color:var(--accent);font-weight:600}
.qsep{width:1px;height:20px;background:var(--line);margin:0 2px}

/* 列表 */
.list{margin-top:10px;overflow:hidden}
.thead,.tr{display:grid;grid-template-columns:44px 1fr 92px 132px 1fr;align-items:center;gap:8px;padding:0 10px}
.thead{height:32px;font-size:12px;color:var(--sub);border-bottom:1px solid var(--line);background:var(--card)}
.tbody{max-height:calc(100vh - 268px);overflow:auto}
.tr{height:40px;border-bottom:1px solid color-mix(in srgb,var(--line) 60%,transparent)}
.tr:hover{background:color-mix(in srgb,var(--accent) 4%,transparent)}
.tr.dead{opacity:.45}
.nm{display:flex;align-items:center;gap:9px;min-width:0}
.nm img{width:20px;height:20px;border-radius:5px;object-fit:contain;background:var(--bg);flex:0 0 auto}
.nm .t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nsrc{font-size:11px;color:var(--sub);background:var(--bg);border-radius:6px;padding:0 5px;flex:0 0 auto}
.grp{font-size:12.5px;color:var(--sub)}
.qa{display:flex;align-items:center;gap:6px;font-size:12.5px}
.tag{font-size:11px;font-weight:700;padding:1px 6px;border-radius:6px;background:var(--bg);color:var(--sub);border:1px solid var(--line)}
.tag.q4{color:#7c3aed;border-color:#ddd6fe;background:#f5f3ff}
.tag.q3{color:#0369a1;border-color:#bae6fd;background:#f0f9ff}
.tag.q2{color:#4d7c0f;border-color:#d9f99d;background:#f7fee7}
.spd{font-size:11.5px;color:var(--sub);font-variant-numeric:tabular-nums}
.host{font-size:12px;color:var(--sub);display:flex;align-items:center;gap:6px;min-width:0}
.host .h{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mini{opacity:0;height:22px;padding:0 8px;border-radius:7px;border:1px solid var(--line);
  background:var(--card);font-size:11.5px;color:var(--sub);transition:.15s;flex:0 0 auto}
.tr:hover .mini{opacity:1}
.mini:hover{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
.lowb{font-size:10.5px;color:#b45309;background:#fffbeb;border:1px solid #fde68a;
  border-radius:5px;padding:0 4px;flex:0 0 auto}
input[type=checkbox]{width:16px;height:16px;accent-color:var(--accent);cursor:pointer}
.empty{padding:36px 16px;text-align:center;color:var(--sub);font-size:13px}

/* 底栏 */
footer{position:fixed;left:0;right:0;bottom:0;z-index:40;background:color-mix(in srgb,var(--card) 94%,transparent);
  backdrop-filter:blur(10px);border-top:1px solid var(--line)}
.fbar{max-width:1120px;margin:0 auto;padding:8px 18px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.sel{font-size:13px;color:var(--sub);white-space:nowrap}
.sel b{color:var(--accent)}
.field{height:32px;border:1px solid var(--line);border-radius:10px;background:var(--bg);padding:0 10px;outline:none;min-width:0}
.field:focus{border-color:var(--accent);background:var(--card)}
#outdir{flex:1;min-width:220px}
#fname{width:150px}

/* 弹窗 */
.mask{position:fixed;inset:0;background:rgba(15,18,23,.45);display:none;align-items:center;justify-content:center;
  z-index:60;padding:20px}
.mask.show{display:flex}
.dlg{background:var(--card);border-radius:16px;box-shadow:0 24px 60px -20px rgba(0,0,0,.5);
  width:min(760px,100%);max-height:88vh;display:flex;flex-direction:column;overflow:hidden}
.dlg.sm{width:min(420px,100%)}
.dhead{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px}
.dhead b{font-size:15px}
.dbody{padding:16px 20px;overflow:auto}
.dfoot{padding:12px 20px;border-top:1px solid var(--line);display:flex;justify-content:flex-end;gap:8px}
.sec{margin-bottom:18px}
.sec>h4{margin:0 0 10px;font-size:12.5px;color:var(--sub);font-weight:600;letter-spacing:.3px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.f{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--sub)}
.f input[type=text],.f input[type=number]{height:34px;border:1px solid var(--line);border-radius:9px;
  background:var(--bg);padding:0 10px;color:var(--txt);outline:none;width:100%}
.f input:focus{border-color:var(--accent);background:var(--card)}
.f label.ck{display:flex;align-items:center;gap:8px;height:34px;color:var(--txt);font-size:13px;cursor:pointer}
.srcs{display:grid;grid-template-columns:1fr 1fr;gap:4px 12px}
.src{display:flex;align-items:center;gap:8px;font-size:12.5px;padding:5px 6px;border-radius:8px}
.src:hover{background:var(--bg)}
.src .st{width:8px;height:8px;border-radius:50%;flex:0 0 auto}
.src .n{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.src .m{color:var(--sub);font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap}
.hint{font-size:12px;color:var(--sub);line-height:1.6}
.err{color:var(--bad)}

/* toast */
#toast{position:fixed;left:50%;bottom:84px;transform:translateX(-50%) translateY(14px);z-index:70;
  background:#1b1f24;color:#fff;font-size:13px;padding:10px 16px;border-radius:10px;opacity:0;
  pointer-events:none;transition:.22s;max-width:88vw;box-shadow:0 12px 30px -10px rgba(0,0,0,.6)}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
@media(max-width:820px){
  .cards{grid-template-columns:1fr 1fr}
  .thead,.tr{grid-template-columns:40px 1fr 96px 0 0;gap:6px}
  .thead>div:nth-child(4),.thead>div:nth-child(5),.tr>*:nth-child(4),.tr>*:nth-child(5){display:none}
  #fname{width:110px}
}
</style>
</head>
<body>
<header>
  <div class="hbar">
    <img class="logo" src="__FAVICON__" alt="">
    <div class="brand"><b>LIVE直播源</b><span>港澳台 + 央视卫视 + 地方台 · 自动测速挑源</span></div>
    <span class="pill" id="verPill">v-</span>
    <span class="pill"><i class="ti" id="stDot"></i><span id="stTxt">启动中…</span></span>
    <span class="spacer"></span>
    <button class="btn primary" id="btnUpdate">立即更新</button>
    <button class="btn" id="btnCfg">设置</button>
    <button class="btn danger" id="btnQuit">退出</button>
  </div>
  <div class="pwrap" id="progwrap"><div class="pbar" id="prog"></div></div>
</header>

<main>
  <div class="cards">
    <div class="card stat"><b id="sChan">-</b><span>实测可用频道</span></div>
    <div class="card stat"><b id="sSrc">-</b><span>频道总数</span></div>
    <div class="card stat"><b id="sHkmt">-</b><span>港澳台频道</span></div>
    <div class="card stat"><b id="sTime">-</b><span>上次更新</span></div>
  </div>

  <div class="card toolbar">
    <div class="row">
      <input class="search" id="q" placeholder="搜索频道名，例如 CCTV5 / 翡翠台 / 湖南卫视">
      <select class="field sortsel" id="sort" title="排序方式">
        <option value="speed">最快优先</option>
        <option value="group">按分组</option>
        <option value="name">按名称</option>
      </select>
      <button class="btn" id="btnAll">全选</button>
      <button class="btn" id="btnInv">反选</button>
    </div>
    <div class="row chips" id="chips"></div>
    <div class="row chips" id="chipsQ">
      <button class="chip" data-q="4">4K</button>
      <button class="chip" data-q="1080P">1080P</button>
      <button class="chip" data-q="HD">高清</button>
      <span class="qsep"></span>
            <button class="chip" data-qk="alive">仅可用</button>
    </div>
  </div>

  <div class="card list">
    <div class="thead"><div><input type="checkbox" id="ckAll"></div><div>频道</div><div>分组</div><div>画质 / 实测</div><div>首选源</div></div>
    <div class="tbody" id="rows"><div class="empty">点右上角「立即更新」开始检测直播源。<br><span class="hint">每一轮都会重新实测，不会沿用上次的结果。</span></div></div>
  </div>
</main>

<footer>
  <div class="fbar">
    <span class="sel">已选 <b id="selN">0</b> / <span id="selT">0</span> 个频道</span>
    <input class="field" id="outdir" placeholder="保存目录">
    <input class="field" id="fname" value="直播源.m3u">
    <button class="btn" id="btnBrowse">选目录</button>
    <button class="btn" id="btnFolder">打开目录</button>
    <button class="btn primary" id="btnSave">保存 M3U</button>
  </div>
</footer>

<!-- 设置 -->
<div class="mask" id="cfgMask">
  <div class="dlg">
    <div class="dhead"><b>设置</b><span class="spacer"></span>
      <button class="btn" id="btnCfgX">关闭</button></div>
    <div class="dbody">
      <div class="sec">
        <h4>更新</h4>
        <div class="grid2">
          <div class="f">自动更新间隔（小时）<input type="number" id="c_int" min="1" max="72"></div>
          <div class="f">每个频道备用源数量<input type="number" id="c_bak" min="1" max="8"></div>
    <div class="f">最低码率 Mbps（低于此值当假的，0=不限）
      <input type="number" id="c_min" min="0" max="50" step="0.5"></div>
          <div class="f">EPG 节目单地址（可留空）<input type="text" id="c_epg" placeholder="http://…/epg.xml"></div>
          <div class="f">保存位置<input type="text" id="c_out" placeholder="M3U 输出路径"></div>
        </div>
        <div class="grid2" style="margin-top:10px">
          <label class="f ck"><input type="checkbox" id="c_sd">保留标清频道</label>
          <label class="f ck"><input type="checkbox" id="c_tv">只保留电视台频道（白名单，列表更干净）</label>
          <label class="f ck"><input type="checkbox" id="c_junk">过滤非电视频道（DJ / 相声 / 助眠等）</label>
          <label class="f ck"><input type="checkbox" id="c_browser">启动时自动打开网页</label>
        </div>
      </div>

      <div class="sec">
        <h4>程序</h4>
        <div class="grid2">
          <label class="f ck"><input type="checkbox" id="c_tray">显示右下角托盘图标</label>
          <label class="f ck"><input type="checkbox" id="c_auto">开机自动启动</label>
          <label class="f ck"><input type="checkbox" id="c_task">按间隔用计划任务后台更新</label>
          <label class="f ck"><input type="checkbox" id="c_su">检查程序新版本</label>
          <label class="f ck"><input type="checkbox" id="c_sig">升级包必须验签（推荐）</label>
          <label class="f ck"><input type="checkbox" id="c_suauto">发现新版本自动下载</label>
        </div>
        <div class="grid2" style="margin-top:10px">
          <div class="f">升级源地址（version.json）<input type="text" id="c_url" placeholder="https://…/version.json"></div>
          <div class="f">检查间隔（小时）<input type="number" id="c_suh" min="1" max="720"></div>
        </div>
        <div class="row" style="margin-top:10px">
          <button class="btn" id="btnSelfCheck">检查更新</button>
          <span class="hint" id="selfMsg">当前版本 <b id="c_cur">-</b></span>
        </div>
      </div>

      <div class="sec">
        <h4>数据源（绿=可用，数字=抓到的条目）</h4>
        <div class="srcs" id="c_srcs"></div>
        <div class="hint" style="margin-top:8px">改完点「保存设置」；关掉的源下次更新就不再抓。</div>
      </div>
    </div>
    <div class="dfoot">
      <button class="btn" id="btnCfgCancel">取消</button>
      <button class="btn primary" id="btnCfgSave">保存设置</button>
    </div>
  </div>
</div>

<!-- 退出确认 -->
<div class="mask" id="quitMask">
  <div class="dlg sm">
    <div class="dhead"><b>退出程序？</b></div>
    <div class="dbody hint">退出后网页控制台就打不开了，已保存的 M3U 文件和频道数据都会保留。<br>下次双击图标即可重新启动。</div>
    <div class="dfoot">
      <button class="btn" id="btnQuitNo">取消</button>
      <button class="btn primary" id="btnQuitYes">退出程序</button>
    </div>
  </div>
</div>

<div id="toast"></div>
<script>
"use strict";
var CH=[], sel=new Set(), grp="", qf="", qk="", q="", sk="speed", lastLoaded="", timer=null, dirty=false;
var fresh=false, wasUpdating=false;   // fresh=本次打开后跑完过一轮更新，才把频道列出来
var GORDER=["香港","澳门","台湾","央视","卫视","地方台","电影","体育","游戏","少儿","其他"];
var $=function(id){return document.getElementById(id)};

function toast(msg,ms){
  var t=$("toast"); t.textContent=msg; t.classList.add("show");
  clearTimeout(t._t); t._t=setTimeout(function(){t.classList.remove("show")}, ms||2600);
}
function saveSel(){
  try{localStorage.setItem("livesel", JSON.stringify([].concat(Array.from(sel))));}catch(e){}
}
function loadSel(){
  try{ var a=JSON.parse(localStorage.getItem("livesel")||"null"); if(a&&a.length){sel=new Set(a);return true;} }catch(e){}
  return false;
}
// 主题跟随系统
function applyTheme(){
  var d=window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme=d?"dark":"light";
}
if(window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change",applyTheme);
applyTheme();

function spd(c){
  var s=c.best||{}, r=s.res||0, m=s.mbps||0;
  if(r>=2000) return "4K";
  if(r>=1000) return "1080P";
  if(r>=620) return "HD";
  return c.quality||"";
}
function tagCls(c){
  var r=((c.best||{}).res)||0;
  if(r>=2000) return "tag q4";
  if(r>=1000) return "tag q3";
  if(r>=620) return "tag q2";
  return "tag";
}
function host(u){ try{ return new URL(u).host; }catch(e){ return u||"" } }
function isHkmt(c){ return ["香港","澳门","台湾"].indexOf(c.group)>=0 }

function gidx(g){ var i=GORDER.indexOf(g); return i<0?90:i }
function mb(c){ return ((c.best||{}).mbps)||0 }
function filtered(){
  var kw=q.trim().toLowerCase();
  var list=CH.filter(function(c){
    if(grp && c.group!==grp) return false;
    if(qf && spd(c)!==qf) return false;
    if(qk==="hkmt" && !isHkmt(c)) return false;
    if(qk==="alive" && !(c.best&&c.best.live)) return false;
    if(kw && (c.name||"").toLowerCase().indexOf(kw)<0) return false;
    return true;
  });
  list.sort(function(a,b){
    if(sk==="speed"){
      var d=mb(b)-mb(a);
      if(d) return d;                 // 实测快的排前面
    }
    if(sk==="speed"||sk==="group"){
      var g=gidx(a.group)-gidx(b.group);
      if(g) return g;
    }
    return (a.name||"").localeCompare(b.name||"","zh");
  });
  return list;
}

function renderChips(){
  var gs=[], seen={};
  CH.forEach(function(c){ if(!seen[c.group]){seen[c.group]=1;gs.push(c.group)} });
  var order=["香港","澳门","台湾","央视","卫视","地方台","电影","体育","游戏","少儿","其他"];
  gs.sort(function(a,b){
    var ia=order.indexOf(a), ib=order.indexOf(b);
    return (ia<0?99:ia)-(ib<0?99:ib);
  });
  var html='<button class="chip'+(grp?"":" on")+'" data-g="">全部</button>';
  gs.forEach(function(g){
    var n=CH.filter(function(c){return c.group===g}).length;
    html+='<button class="chip'+(grp===g?" on":"")+'" data-g="'+esc(g)+'">'+esc(g)+' '+n+'</button>';
  });
  $("chips").innerHTML=html;
}
function esc(s){
  return String(s==null?"":s).replace(/[&<>"']/g,function(m){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m];
  });
}
function renderQ(){
  [].forEach.call($("chipsQ").querySelectorAll(".chip"),function(b){
    var on = b.dataset.q ? (qf===b.dataset.q) : (qk===b.dataset.qk);
    b.classList.toggle("on", !!on);
  });
}

function renderRows(){
  var list=filtered(), rows=$("rows");
  if(!CH.length){
    rows.innerHTML='<div class="empty">还没有频道。<br>点右上角「立即更新」，跑完（约 1~2 分钟）就会把实测可用的频道列在这里。</div>';
    updCount(); return;
  }
  if(!list.length){ rows.innerHTML='<div class="empty">没有符合条件的频道。清空搜索或切回「全部」看看。</div>'; updCount(); return; }
  var html="";
  list.forEach(function(c){
    var alive=c.best&&c.best.live;
    var n=(c.sources||[]).length;
    html+='<div class="tr'+(alive?"":" dead")+'" data-k="'+esc(c.key)+'">'
      +'<div><input type="checkbox" data-ck="'+esc(c.key)+'"'+(sel.has(c.key)?" checked":"")+'></div>'
      +'<div class="nm"><img loading="lazy" src="'+esc(c.logo||"")+'" onerror="this.style.visibility=\'hidden\'">'
      +'<span class="t">'+esc(c.name)+'</span>'+(n>1?'<span class="nsrc">'+n+' 源</span>':'')+'</div>'
      +'<div class="grp">'+esc(c.group)+'</div>'
      +'<div class="qa"><span class="'+tagCls(c)+'">'+esc(spd(c)||"未知")+'</span>'
      +'<span class="spd">'+(alive?(c.best.mbps?(c.best.mbps.toFixed(1)+" Mbps"):"可用"):"不可用")+'</span></div>'
      +'<div class="host"><span class="h">'+esc(alive?host(c.best.url).split(":")[0]:"—")+'</span>'
      +((alive&&c.best.mbps&&c.best.mbps<2)?'<span class="lowb" title="码率不到 2 Mbps，多半是压缩转发源，画面不一定是这个台">低码率</span>':'')
      +'</div>'
      +'</div>';
  });
  rows.innerHTML=html;
  updCount();
}

function updCount(){
  var list=filtered(), n=0;
  list.forEach(function(c){ if(sel.has(c.key)) n++ });
  $("selN").textContent=n;
  $("selT").textContent=list.length;
  var all=list.length>0 && n===list.length;
  var ck=$("ckAll"); ck.checked=all; ck.indeterminate=(n>0&&!all);
  var bs=$("btnSave"); if(bs){ bs.disabled = n===0; bs.title = n? "保存已勾选的频道" : "先勾选要保存的频道"; }
}

function loadChannels(){
  fetch("/api/channels").then(function(r){return r.json()}).then(function(d){
    CH=d.channels||[];
    sel=new Set();          // 每次打开都从"一个都不勾"开始，由用户自己挑；也不继承上次的勾选
    selLoaded=true;
    if(d.save_dir && !$("outdir").value) $("outdir").value=d.save_dir;
    renderChips(); renderRows();
    dirty=true;
  }).catch(function(){ toast("读取频道失败，稍后重试") });
}
var selLoaded=false;
function loadSelSilent(){
  if(selLoaded) return true;
  selLoaded=true;
  return loadSel();
}

function loadStatus(){
  fetch("/api/status").then(function(r){return r.json()}).then(function(s){
    VERSION=s.version; $("verPill").textContent="v"+s.version;
    // 保存目录一开始就填好（默认在桌面），别让用户看到空框再以为是别的盘
    if(s.desktop) DESKTOP=s.desktop;
    if(s.save_path && !$("outdir").value){
      var sp=String(s.save_path), i=Math.max(sp.lastIndexOf("\\"), sp.lastIndexOf("/"));
      if(i>0) $("outdir").value=sp.slice(0,i);
    }
    var dot=$("stDot"), txt=$("stTxt");
    if(s.updating){
      dot.className="ti run"; txt.textContent=s.phase||"更新中";
      $("progwrap").classList.add("show");
      var p=s.total?Math.round(s.done*100/s.total):3;
      $("prog").style.width=Math.max(3,Math.min(100,p))+"%";
      $("btnUpdate").disabled=true;
    }else{
      dot.className="ti"; txt.textContent="就绪";
      $("progwrap").classList.remove("show"); $("prog").style.width="0";
      $("btnUpdate").disabled=false;
      if(s.error){ dot.className="ti off"; txt.textContent="上次更新失败"; }
    }
    if(s.stats){
      $("sChan").textContent=s.stats.live||0;
      $("sSrc").textContent=s.stats.channels||0;
      $("sHkmt").textContent=s.stats.hkmt||0;
    }
    $("sTime").textContent=friendly(s.last_update);
    if(s.tray===false && !window._trayWarn){ window._trayWarn=1; }
    // 打开页面时不要直接铺出上次缓存的结果：必须是这一轮跑完，才把实测结果列出来
    if(s.updating){ wasUpdating=true; }
    if(!s.updating && wasUpdating){
      wasUpdating=false; fresh=true; lastLoaded=s.last_update||"";
      loadChannels();
      toast("更新完成："+(s.stats&&s.stats.live||0)+" 个频道实测可用");
    }
  }).catch(function(){});
}
function friendly(t){
  if(!t) return "-";
  var d=new Date(String(t).replace(" ","T"));
  if(isNaN(d.getTime())) return t;
  var diff=(Date.now()-d.getTime())/60000;
  if(diff<1) return "刚刚";
  if(diff<60) return Math.round(diff)+" 分钟前";
  if(diff<1440) return Math.round(diff/60)+" 小时前";
  return (d.getMonth()+1)+"/"+d.getDate()+" "+("0"+d.getHours()).slice(-2)+":"+("0"+d.getMinutes()).slice(-2);
}

/* ---- 交互 ---- */
$("q").addEventListener("input",function(){ q=this.value; renderRows() });
try{ var _sk=localStorage.getItem("livesort"); if(_sk) sk=_sk }catch(e){}
$("sort").value=sk;
$("sort").addEventListener("change",function(){ sk=this.value; try{localStorage.setItem("livesort",sk)}catch(e){}; renderRows() });
$("chips").addEventListener("click",function(e){
  var b=e.target.closest(".chip"); if(!b) return;
  grp=b.dataset.g||""; renderChips(); renderRows();
});
$("chipsQ").addEventListener("click",function(e){
  var b=e.target.closest(".chip"); if(!b) return;
  if(b.dataset.q){ qf=(qf===b.dataset.q)?"":b.dataset.q; qk=""; }
  else { qk=(qk===b.dataset.qk)?"":b.dataset.qk; qf=""; }
  renderQ(); renderRows();
});
$("rows").addEventListener("click",function(e){
  var ck=e.target.closest("input[data-ck]"); if(!ck) return;
  var k=ck.dataset.ck;
  if(ck.checked) sel.add(k); else sel.delete(k);
  saveSel(); updCount();
  var tr=ck.closest(".tr"); if(tr) tr.style.background="";
});
$("ckAll").addEventListener("change",function(){
  var list=filtered();
  if(this.checked) list.forEach(function(c){sel.add(c.key)});
  else list.forEach(function(c){sel.delete(c.key)});
  saveSel(); renderRows();
});
$("btnAll").addEventListener("click",function(){
  filtered().forEach(function(c){sel.add(c.key)}); saveSel(); renderRows();
});
$("btnInv").addEventListener("click",function(){
  filtered().forEach(function(c){ if(sel.has(c.key)) sel.delete(c.key); else sel.add(c.key) });
  saveSel(); renderRows();
});
$("btnUpdate").addEventListener("click",function(){
  var b=this; b.disabled=true; b.textContent="更新中…";
  CH=[]; sel=new Set(); fresh=false; wasUpdating=false; renderChips(); renderRows();
  fetch("/api/update",{method:"POST"}).then(function(r){return r.json()}).then(function(d){
    if(!d.ok) toast(d.msg||"更新启动失败");
    else toast("已开始更新：抓取源 → 测速 → 挑最佳源，请稍候");
  }).catch(function(){toast("请求失败")}).then(function(){
    setTimeout(function(){b.textContent="立即更新";},1500);
  });
});
$("btnSave").addEventListener("click",function(){
  var keys=Array.from(sel), dir=$("outdir").value.trim(), fn=$("fname").value.trim()||"直播源.m3u";
  if(!keys.length) return toast("还没有选频道：勾选几个，或点「全选」");
  if(!dir) return toast("请先填保存目录（或点「选目录」）");
  var b=this; b.disabled=true;
  fetch("/api/export",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({keys:keys,dir:dir,filename:fn})})
    .then(function(r){return r.json()}).then(function(d){
      b.disabled=false;
      if(!d.ok) return toast(d.msg||"保存失败");
      var m="已保存 "+d.count+" 个频道到 "+d.path;
      if(d.skipped) m+="（"+d.skipped+" 个频道当前没有可用源，已跳过）";
      toast(m,4200);
    }).catch(function(){ b.disabled=false; toast("保存请求失败") });
});
$("btnBrowse").addEventListener("click",function(){
  fetch("/api/pickdir",{method:"POST"}).then(function(r){return r.json()}).then(function(d){
    if(d.path) $("outdir").value=d.path;
  }).catch(function(){toast("打开目录选择框失败")});
});
$("btnFolder").addEventListener("click",function(){
  var d=$("outdir").value.trim();
  if(!d) return toast("先填目录");
  fetch("/api/open",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:d})})
    .then(function(){toast("已打开目录")}).catch(function(){toast("打开失败")});
});

/* ---- 设置 ---- */
var SRCS=[];
function openCfg(){
  fetch("/api/settings").then(function(r){return r.json()}).then(function(c){
    $("c_int").value=c.interval_hours; $("c_bak").value=c.backups;
    $("c_epg").value=c.epg_url||""; $("c_out").value=c.output_path||"";
    $("c_sd").checked=!!c.keep_sd; $("c_browser").checked=!!c.open_browser;
    $("c_junk").checked=c.filter_junk!==false;
    $("c_tv").checked=c.only_tv!==false;
    $("c_min").value=(c.min_mbps===undefined?1.5:c.min_mbps);
    $("c_tray").checked=!!c.tray; $("c_auto").checked=!!c.autostart; $("c_task").checked=!!c.task_registered;
    $("c_su").checked=!!c.self_update; $("c_sig").checked=c.require_sig!==false;
    $("c_suauto").checked=!!c.update_auto; $("c_url").value=c.update_url||"";
    $("c_suh").value=c.update_check_hours||24; $("c_cur").textContent=VERSION;
    // 数据源列表按"该用的在前、建议关/已关的在后"排，别让直播间源占着第一屏
    SRCS=(c.source_list||[]).slice().sort(function(a,b){
      var d=(a.def_on?0:1)-(b.def_on?0:1); if(d) return d;
      return ((c.sources[a.key]?0:1)-(c.sources[b.key]?0:1));
    });
    fetch("/api/status").then(function(r){return r.json()}).then(function(s){
      var st=s.source_stats||{};
      $("c_srcs").innerHTML=SRCS.map(function(x){
        var e=st[x.key];
        var col=!e?"var(--sub)":(e.ok?"var(--ok)":"var(--bad)");
        var meta=!e?"未抓取":(e.ok?("<b>"+e.count+"</b> 条 · "+e.ms+"ms"+(e.fallback?" · 备选":"")+""):"抓取失败");
        var offc=c.sources[x.key]?"":" off";
        return '<label class="src'+offc+'"><input type="checkbox" data-src="'+esc(x.key)+'"'+(c.sources[x.key]?" checked":"")+'>'
          +'<i class="st" style="background:'+col+'"></i><span class="n">'+esc(x.name)+'</span>'
          +'<span class="m">'+meta+'</span></label>';
      }).join("");
      $("cfgMask").classList.add("show");
    });
  }).catch(function(){toast("读取设置失败")});
}
var VERSION="-", DESKTOP="";
function useDesktop(){ if(!DESKTOP){ toast("还没拿到桌面路径，稍等一秒再点"); return } $("outdir").value=DESKTOP; }
function closeCfg(){ $("cfgMask").classList.remove("show") }
$("btnCfg").addEventListener("click",openCfg);
$("btnCfgX").addEventListener("click",closeCfg);
$("btnCfgCancel").addEventListener("click",closeCfg);
$("cfgMask").addEventListener("click",function(e){ if(e.target===this) closeCfg() });
$("btnCfgSave").addEventListener("click",function(){
  var srcs={};
  [].forEach.call(document.querySelectorAll("[data-src]"),function(x){ srcs[x.dataset.src]=x.checked });
  var body={
    interval_hours:+$("c_int").value, backups:+$("c_bak").value,
    keep_sd:$("c_sd").checked, filter_junk:$("c_junk").checked, only_tv:$("c_tv").checked,
    min_mbps:(parseFloat($("c_min").value)||0),
    output_path:$("c_out").value.trim(),
    epg_url:$("c_epg").value.trim(), open_browser:$("c_browser").checked,
    tray:$("c_tray").checked, autostart:$("c_auto").checked, task_registered:$("c_task").checked,
    self_update:$("c_su").checked, require_sig:$("c_sig").checked, update_auto:$("c_suauto").checked,
    update_url:$("c_url").value.trim(), update_check_hours:+$("c_suh").value, sources:srcs
  };
  fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){ toast("设置已保存，新的更新间隔从下次开始生效"); closeCfg(); loadStatus(); }
      else toast(d.msg||"保存失败");
    }).catch(function(){toast("保存失败")});
});
$("btnSelfCheck").addEventListener("click",function(){
  var b=this; b.disabled=true;
  $("selfMsg").textContent="正在检查…";
  fetch("/api/selfcheck").then(function(r){return r.json()}).then(function(d){
    b.disabled=false;
    if(d.latest && d.latest.version){
      $("selfMsg").innerHTML='发现新版本 <b>v'+esc(d.latest.version)+'</b> <button class="btn" id="btnDoUpd">下载并升级</button>';
      $("btnDoUpd").onclick=function(){
        this.disabled=true; this.textContent="下载中…";
        fetch("/api/selfupdate",{method:"POST"}).then(function(r){return r.json()}).then(function(x){
          toast(x.msg||(x.ok?"已开始升级":"升级失败"),5000);
        });
      };
    }else if(d.latest===false){ $("selfMsg").textContent="已是最新版本 v"+d.current; }
    else { $("selfMsg").textContent=d.msg||"检查失败（没配置升级源或网络不通）"; }
  }).catch(function(){ b.disabled=false; $("selfMsg").textContent="检查失败" });
});

/* ---- 退出 ---- */
$("btnQuit").addEventListener("click",function(){ $("quitMask").classList.add("show") });
$("btnQuitNo").addEventListener("click",function(){ $("quitMask").classList.remove("show") });
$("btnQuitYes").addEventListener("click",function(){
  var b=this; b.disabled=true; b.textContent="正在退出…";
  fetch("/api/quit",{method:"POST"}).then(function(){
    document.body.innerHTML='<div style="height:100vh;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;color:#6b7280;font:14px system-ui"><b style="font-size:18px;color:#1b1f24">LIVE直播源 已退出</b><span>可以关闭这个页面了</span></div>';
  }).catch(function(){
    document.body.innerHTML='<div style="padding:40px;text-align:center;color:#6b7280">已退出（或后台正在关闭），可以关闭这个页面了。</div>';
  });
});

document.addEventListener("keydown",function(e){
  if(e.key==="Escape"){ closeCfg(); $("quitMask").classList.remove("show") }
  if((e.ctrlKey||e.metaKey)&&e.key==="s"){ e.preventDefault(); $("btnSave").click() }
  if((e.ctrlKey||e.metaKey)&&e.key==="f"){ e.preventDefault(); $("q").focus() }
});

// 打开页面时只查状态：不铺上次缓存的频道，等用户自己点「立即更新」跑完再列出来
showEmpty(); loadStatus(); setInterval(loadStatus,2000);
function showEmpty(){
  renderChips(); renderRows(); updCount();
}
</script>

</html>
"""


# ---------------------------------------------------------------- HTTP 服务

class Handler(BaseHTTPRequestHandler):
    updater = None
    cfg = None
    argv = []

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self._html(PAGE.replace("__FAVICON__", "data:image/png;base64," + FAVICON_B64))
        if path == "/api/status":
            st = dict(self.updater.state)
            with self.updater.lock:
                nch = len(self.updater.channels)
            return self._json({
                "updating": st["updating"], "phase": st["phase"], "done": st["done"],
                "total": st["total"], "last_update": st["last_update"],
                "next_update": st["next_update"], "error": st["error"],
                "version": VERSION, "self_update_msg": st.get("self_update_msg", ""),
                "stats": st["stats"], "cached_channels": nch,
                "source_stats": st.get("source_stats", {}),
                "tray": bool(_TRAY is not None and _TRAY._ok),
                "save_path": self.cfg.get("output_path", ""),
            "desktop": str(_desktop_dir()),
            })
        if path == "/api/selfcheck":
            info = check_self_update(self.cfg, force=True)
            return self._json({"current": VERSION,
                               "latest": info if info else None,
                               "enabled": bool(self.cfg.get("self_update")),
                               "url": self.cfg.get("update_url", ""),
                               "msg": ("" if info is None else ("已是最新" if info is False else "发现新版本 v%s" % info["version"]))})
        if path == "/api/selfupdate":
            info = check_self_update(self.cfg, force=True)
            if not info or info is False:
                return self._json({"ok": False, "msg": "已是最新或未配置更新地址"})
            res = apply_self_update(info, Handler.argv)
            if res:
                if isinstance(res, dict):
                    if res.get("replacing"):
                        # 已交给替换脚本：先把回复发出去，再退出本进程让脚本换文件
                        threading.Timer(1.2, request_quit).start()
                        return self._json({"ok": True, "replacing": True, "msg": res.get("msg", "")})
                    return self._json({"ok": True, "manual": True, "path": res.get("path", ""), "msg": res.get("msg", "")})
                return self._json({"ok": True, "restart": True})
            return self._json({"ok": False, "msg": "更新失败，详见日志"})
        if path == "/api/channels":
            with self.updater.lock:
                channels = list(self.updater.channels.values())
            # 只返回实测有可用源的频道(无源频道不列举)；再按"最低码率"过滤掉压缩转发源
            mm = float(self.cfg.get("min_mbps") or 0)
            channels = [c for c in channels if c.get("best") and c["best"].get("live")
                        and (not mm or (c["best"].get("mbps") or 0) >= mm)]
            channels.sort(key=lambda c: (GROUP_RANK.index(c["group"]) if c["group"] in GROUP_RANK else 50,
                                         -(c["best"].get("mbps") or 0), c["name"]))
            return self._json({"channels": channels,
                               "save_dir": str(Path(self.cfg["output_path"]).parent),
                               "saved_at": self.updater.state["last_update"]})
        if path == "/api/settings":
            return self._json({
                **{k: v for k, v in self.cfg.items() if k != "sources"},
                "sources": self.cfg["sources"],
                "source_list": [{"key": k, "name": n, "on": self.cfg["sources"].get(k),
                                     "def_on": on}
                                    for k, n, _, on, _ in SOURCES],
            })
        if path == "/live.m3u":
            p = Path(self.cfg["output_path"])
            data = p.read_bytes() if p.exists() else b""
            self.send_response(200)
            self.send_header("Content-Type", "audio/x-mpegurl; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="live.m3u"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/open":
            p = parse_qs(urlparse(self.path).query).get("path", [""])[0]
            if p and Path(p).exists():
                try:
                    os.startfile(p)  # noqa
                    return self._json({"ok": True})
                except Exception as e:
                    return self._json({"ok": False, "msg": str(e)})
            return self._json({"ok": False, "msg": "文件不存在"})
        self._json({"ok": False, "msg": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            data = json.loads(self._body().decode("utf-8") or "{}")
        except Exception:
            data = {}
        if path == "/api/quit":
            threading.Timer(0.3, request_quit).start()
            return self._json({"ok": True, "msg": "正在退出"})
        if path == "/api/update":
            if self.updater.state["updating"]:
                return self._json({"ok": False, "msg": "更新已在进行中"})
            threading.Thread(target=self.updater.run_once, daemon=True).start()
            return self._json({"ok": True})
        if path == "/api/export":
            keys = set(data.get("keys") or [])
            dir_ = (data.get("dir") or "").strip()
            fn = (data.get("filename") or "直播源.m3u").strip()
            fn = re.sub(r'[\\/:*?"<>|]', "_", fn) or "直播源.m3u"
            if not fn.lower().endswith(".m3u"):
                fn += ".m3u"
            if not keys:
                return self._json({"ok": False, "msg": "没有选择任何频道"})
            if not dir_:
                return self._json({"ok": False, "msg": "未指定保存位置"})
            try:
                target = Path(dir_) / fn
                n_src, _ = self.updater.write_m3u(target, keys=keys)
                # 统计被跳过的失效频道数(无可用最佳源)
                with self.updater.lock:
                    chs = self.updater.channels
                skipped = sum(1 for k in keys if k in chs and not (chs[k].get("best") and chs[k]["best"].get("live")))
                return self._json({"ok": True, "count": n_src, "path": str(target), "skipped": skipped})
            except Exception as e:
                return self._json({"ok": False, "msg": "保存失败: %s" % e})
        if path == "/api/settings":
            try:
                new = {k: data[k] for k in ("interval_hours", "backups", "keep_sd", "filter_junk", "only_tv", "min_mbps",
         "output_path",
                                            "epg_url", "open_browser", "autostart", "task_registered",
                                            "self_update", "update_url", "update_auto", "require_sig",
                                            "tray", "update_check_hours") if k in data}
                self.cfg.update(new)
                self.cfg["update_check_hours"] = max(1, min(720, int(self.cfg.get("update_check_hours", 24))))
                self.cfg["require_sig"] = bool(self.cfg.get("require_sig", True))
                if "sources" in data:
                    for k, v in data["sources"].items():
                        if k in self.cfg["sources"]:
                            self.cfg["sources"][k] = bool(v)
                self.cfg["interval_hours"] = max(1, min(72, int(self.cfg["interval_hours"])))
                self.cfg["backups"] = max(1, min(8, int(self.cfg["backups"])))
                try:
                    self.cfg["min_mbps"] = max(0.0, min(50.0, float(self.cfg.get("min_mbps") or 0)))
                except (TypeError, ValueError):
                    self.cfg["min_mbps"] = 0.0
                if self.cfg["output_path"]:
                    Path(self.cfg["output_path"]).parent.mkdir(parents=True, exist_ok=True)
                manage_task(self.cfg["task_registered"], self.cfg["interval_hours"])
                manage_autostart(self.cfg["autostart"])
                save_cfg(self.cfg)
                self.updater.cfg = self.cfg
                self.updater.state["next_update"] = time.time() + self.cfg["interval_hours"] * 3600
                sync_tray(self.cfg)      # 设置里开关托盘，立刻生效
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"ok": False, "msg": "保存失败: %s" % e})
        if path == "/api/pickdir":
            p = pick_folder()
            return self._json({"path": p} if p else {"path": "", "msg": "已取消选择"})
        if path == "/api/open":
            p = data.get("path") or ""
            if p and Path(p).exists():
                try:
                    os.startfile(p)  # noqa
                    return self._json({"ok": True})
                except Exception as e:
                    return self._json({"ok": False, "msg": str(e)})
            return self._json({"ok": False, "msg": "文件不存在"})
        self._json({"ok": False, "msg": "not found"}, 404)


# ---------------------------------------------------------------- 系统集成

TASK_NAME = APP_NAME + "自动更新"
BOOT_NAME = APP_NAME + "自启"

_TRAY = None          # 右下角托盘图标（_tray.Tray 实例）
_TOAST = None         # 右下角自绘提示卡片（_toast.Toast 实例）
_SERVER = None        # ThreadingHTTPServer 实例，退出时用
_UPDATER = None       # Updater 实例，托盘菜单要读它的状态


def _tray_status():
    """给托盘菜单用的状态文案：版本 + 可用频道 + 上次更新时间。"""
    st = getattr(_UPDATER, "state", None) or {}
    stats = st.get("stats") or {}
    live = stats.get("live") or 0
    last = st.get("last_update") or ""
    header = "%s v%s" % (APP_NAME, VERSION)
    if st.get("updating"):
        total = st.get("total") or 0
        done = st.get("done") or 0
        info = "%s %.0f%%" % (st.get("phase") or "更新中", (done * 100.0 / total) if total else 0)
        progress = "%d/%d" % (done, total) if total else ""
    else:
        info = ("%d 个频道可用 · %s" % (live, last)) if last else "还没更新过，点「立即更新频道」"
        progress = ""
    return {"header": header, "info": info, "updating": bool(st.get("updating")),
            "progress": progress,
            "tip": ("%s\n%s" % (header, info))[:120]}


def tray_notify(title, text):
    """右下角提示：优先用自绘卡片（不依赖系统通知，也没有糊掉的小图标），
    卡片起不来时退回系统气泡。没开托盘就静默跳过（日志里仍有）。"""
    try:
        if _TOAST is not None and getattr(_TOAST, "ok", False):
            _TOAST.show(title, text)
        elif _TRAY is not None and getattr(_TRAY, "_ok", False):
            _TRAY.notify(title, text)
        if _TRAY is not None and getattr(_TRAY, "_ok", False):
            _TRAY.refresh_tip()
    except Exception:
        pass


def open_console():
    """用默认浏览器打开控制台（端口按实际监听的那个来）。"""
    try:
        if _SERVER is not None:
            webbrowser.open("http://127.0.0.1:%d/" % _SERVER.server_address[1])
    except Exception as e:
        log("打开网页失败: %s" % e)


def open_output_dir():
    """打开当前 M3U 所在目录。"""
    try:
        d = Path(load_cfg()["output_path"]).parent
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(str(d))  # noqa
    except Exception as e:
        log("打开目录失败: %s" % e)


def request_quit():
    """退出程序：先收托盘、再关服务，最后结束进程。托盘菜单和网页的「退出」都走这里。"""
    global _TRAY
    log("收到退出请求，正在退出…")
    try:
        if _TRAY is not None:
            _TRAY.stop()
            _TRAY = None
    except Exception:
        pass

    def _bye():
        time.sleep(0.25)
        try:
            if _SERVER is not None:
                _SERVER.shutdown()
        except Exception:
            pass
        time.sleep(0.15)
        os._exit(0)

    threading.Thread(target=_bye, daemon=True).start()


def sync_tray(cfg):
    """按配置起停托盘图标。失败只记日志，不影响网页控制台。"""
    global _TRAY
    want = bool(cfg.get("tray", True)) and not getattr(main, "no_tray", False)
    try:
        if want and (_TRAY is None or not _TRAY._ok):
            if _TRAY is not None:
                try:
                    _TRAY.stop()
                except Exception:
                    pass
            global _TOAST
        if _TOAST is None:
            try:
                import _toast as _toastmod
                _TOAST = _toastmod.init(on_click=open_console, app_icon=_app_icon_file())
                log("提示卡片: %s" % ("已就绪(自绘,带程序图标)" if getattr(_TOAST, "ok", False) else "不可用,退回系统气泡"))
            except Exception as e:
                _TOAST = None
                log("提示卡片初始化失败: %s" % e)
            _TRAY = Tray(APP_NAME + " v" + VERSION, _icon_path(),
                         icon_file=_tray_icon_file(),
                         icon_busy=_tray_busy_file(),
                         app_icon=_app_icon_file(),
                         on_open=open_console,
                         on_update=lambda: threading.Thread(target=Handler.updater.run_once, daemon=True).start(),
                         on_folder=open_output_dir,
                         on_quit=request_quit,
                         status_provider=_tray_status)
            if _TRAY.start():
                log("托盘图标: %s" % ("tray.ico(随身小图标)" if _tray_icon_file() else "exe 大图标(会糊)"))
            else:
                log("托盘图标创建失败（不影响网页控制台）")
                _TRAY = None
        elif not want and _TRAY is not None:
            _TRAY.stop()
            _TRAY = None
            log("已关闭托盘图标")
    except Exception as e:
        log("托盘初始化失败: %s" % e)
        _TRAY = None


def _tray_icon_file():
    """随包的托盘小图标（红方块+播放键），16/24 像素比缩小 exe 图标清楚得多。"""
    try:
        p = _res_path("tray.ico")
        return str(p) if p.exists() else ""
    except Exception:
        return ""


def _app_icon_file():
    """随包的程序图标（红徽标），气泡提示里用它——托盘那个小三角放大了更糊。"""
    try:
        p = _res_path(APP_NAME + ".ico")
        return str(p) if p.exists() else ""
    except Exception:
        return ""


def _tray_busy_file():
    """更新中用的图标（红方块+白方块），和空闲的"三角"一眼能分开。"""
    try:
        p = _res_path("tray_busy.ico")
        return str(p) if p.exists() else ""
    except Exception:
        return ""


def tray_busy(flag):
    """更新开始/结束的时候换托盘图标（没开托盘就什么都不做）。"""
    t = _TRAY
    if t is None:
        return
    try:
        if getattr(t, "_ok", False):
            t.set_busy(flag)
            log("托盘图标: %s" % ("更新中(方块)" if flag else "空闲(三角)"))
    except Exception:
        log("切换托盘图标失败: %s" % traceback.format_exc(limit=1))


def _icon_path():
    """托盘用的图标：打包版取 exe 自身图标，脚本版用同目录的 ico。"""
    try:
        if getattr(sys, "frozen", False):
            return sys.executable
        for p in (Path(__file__).with_suffix(".ico"), BASE / (APP_NAME + ".ico")):
            if p.exists():
                return str(p)
        return sys.executable
    except Exception:
        return sys.executable


def _already_running(cfg):
    """单实例：本机已有一个控制台在跑时返回它的端口。"""
    for p in range(int(cfg.get("port", 8899)), int(cfg.get("port", 8899)) + 10):
        s = socket.socket()
        s.settimeout(0.4)
        try:
            s.connect(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return 0



def _exe():
    """返回可在 schtasks /TR 中直接使用的已加引号命令"""
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    return '"%s" "%s"' % (sys.executable, Path(__file__).resolve())


def manage_task(register, interval_h):
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if register:
            interval_h = max(1, min(72, int(interval_h)))
            # schtasks /SC HOURLY 的 /MO 最大 23，>=24 小时改用按天调度
            if interval_h >= 24:
                sched = ["/SC", "DAILY", "/MO", str(max(1, int(round(interval_h / 24.0))))]
            else:
                sched = ["/SC", "HOURLY", "/MO", str(interval_h)]
            cmd = ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", "%s --once" % _exe(),
                   ] + sched + ["/RL", "LIMITED", "/F"]
            r = subprocess.run(cmd, capture_output=True, timeout=25, creationflags=flags)
            log("注册计划任务 rc=%s %s" % (r.returncode, r.stderr.decode("gbk", "ignore")[:150]))
        else:
            subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                           capture_output=True, timeout=25, creationflags=flags)
            log("已删除计划任务")
    except Exception as e:
        log("计划任务操作失败: %s" % e)


def manage_autostart(enable):
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if enable:
            cmd = ["schtasks", "/Create", "/TN", BOOT_NAME, "/TR", _exe(),
                   "/SC", "ONLOGON", "/RL", "LIMITED", "/F"]
            subprocess.run(cmd, capture_output=True, timeout=25, creationflags=flags)
            log("已设置开机自启")
        else:
            subprocess.run(["schtasks", "/Delete", "/TN", BOOT_NAME, "/F"],
                           capture_output=True, timeout=25, creationflags=flags)
            log("已取消开机自启")
    except Exception as e:
        log("开机自启设置失败: %s" % e)


def pick_folder():
    """通过 PowerShell 打开原生文件夹选择框，返回选择的路径。

    注意：选择框是"我们"（后台服务进程）弹出来的，默认会躲在浏览器窗口后面，
    用户根本看不见。所以给它挂一个置顶的隐形 owner 窗口，弹出来就在最前面。
    """
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$o=New-Object System.Windows.Forms.Form;"
        "$o.TopMost=$true;$o.ShowInTaskbar=$false;$o.FormBorderStyle='None';"
        "$o.StartPosition='CenterScreen';$o.Width=1;$o.Height=1;$o.Opacity=0;"
        "$o.Show();"
        "$f=New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$f.Description='选择 M3U 保存位置';"
        "if($env:LIVE_PICK_INIT -and (Test-Path $env:LIVE_PICK_INIT)){$f.SelectedPath=$env:LIVE_PICK_INIT};"
        "$r=$f.ShowDialog($o);$o.Close();"
        "if($r -eq 'OK'){Write-Output $f.SelectedPath}"
    )
    try:
        env = dict(os.environ)
        try:
            env["LIVE_PICK_INIT"] = str(Path(load_cfg()["output_path"]).parent)
        except Exception:
            pass
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps],
                           capture_output=True, timeout=240, env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = r.stdout.decode("utf-8", "ignore").strip()
        return out if out and Path(out).is_dir() else ""
    except Exception as e:
        log("文件夹选择框失败: %s" % e)
        return ""


# ---------------------------------------------------------------- 程序自更新

def _ver_tuple(v):
    try:
        return tuple(int(x) for x in re.findall(r"\d+", v)[:3])
    except Exception:
        return (0,)


def _fetch_bytes(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                timeout=timeout, context=_SSL_CTX) as r:
        return r.read()


def _verify_manifest(raw, sig_hex):
    """Ed25519 验签：raw=version.json 原始字节，sig_hex=64 字节签名的十六进制。"""
    try:
        sig = bytes.fromhex("".join(sig_hex.split()))
        pk = bytes.fromhex(UPDATE_PUBKEY_HEX)
        return bool(checkvalid(sig, raw, pk))
    except Exception as e:
        log("验签异常: %s" % e)
        return False


def check_self_update(cfg, force=False):
    """检查程序新版本。返回 {"version","url","notes","sha256","size"} / False(已最新) / None(失败)。

    update_url 指向的 version.json 形如:
      {"version":"1.3.1","url":"https://.../LIVE直播源.exe","notes":"...","sha256":"...","size":123}
    同目录必须有 version.json.sig（私钥签的 Ed25519 签名，十六进制）。
    验签不过一律拒绝升级 —— 升级源被篡改、或换了个别人的包，都升不上去。"""
    if not cfg.get("update_url"):
        return None
    if not force and not cfg.get("self_update"):
        return None
    try:
        raw = _fetch_bytes(cfg["update_url"])
        data = json.loads(raw.decode("utf-8", "ignore"))
        try:
            sig = _fetch_bytes(cfg["update_url"] + ".sig", 15).decode("ascii", "ignore")
        except Exception:
            sig = ""
        if cfg.get("require_sig", True):
            if not sig.strip():
                log("升级源缺少签名文件(version.json.sig)，按安全策略拒绝升级")
                return None
            if not _verify_manifest(raw, sig):
                log("升级源签名校验失败，拒绝升级(升级源可能被篡改)")
                return None
        elif sig.strip() and not _verify_manifest(raw, sig):
            log("升级源签名无效，拒绝升级")
            return None
        latest = str(data.get("version", ""))
        if not latest:
            return None
        if _ver_tuple(latest) > _ver_tuple(VERSION):
            return {"version": latest,
                    "url": data.get("url", ""),
                    "notes": data.get("notes", ""),
                    "sha256": (data.get("sha256") or "").lower(),
                    "size": int(data.get("size") or 0)}
        return False  # 已是最新
    except Exception as e:
        log("检查程序更新失败: %s" % e)
        return None


def _ps_quote(p):
    """PowerShell 单引号字面量（内部单引号写成两个）。"""
    return "'" + str(p).replace("'", "''") + "'"


def _spawn_replacer(new_exe):
    """单文件 exe 自更新：起一个隐藏脚本，等本进程退出后替换文件并重启。

    运行中的 exe 不能直接覆盖，所以必须借一个独立进程来做；
    最多等 28 秒（40 次 × 0.7 秒），换完就启动新版本，再删掉临时文件和自己。
    """
    try:
        target = Path(sys.executable).resolve()
        script = Path(new_exe).parent / "apply_update.ps1"
        text = (
            "$ErrorActionPreference = 'Stop'\n"
            "Start-Sleep -Milliseconds 1200\n"
            "$src = %s\n"
            "$dst = %s\n"
            "$ok = $false\n"
            "for ($i = 0; $i -lt 40; $i++) {\n"
            "  try { Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop; $ok = $true; break }\n"
            "  catch { Start-Sleep -Milliseconds 700 }\n"
            "}\n"
            "if ($ok) { Start-Process -FilePath $dst }\n"
            "Start-Sleep -Milliseconds 800\n"
            "Remove-Item -LiteralPath $src -Force -ErrorAction SilentlyContinue\n"
            "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n"
        ) % (_ps_quote(new_exe), _ps_quote(target))
        script.write_text(text, encoding="utf-8-sig")
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", str(script)],
            creationflags=0x08000000,   # CREATE_NO_WINDOW
            close_fds=True)
        return True
    except Exception as e:
        log("启动自动替换脚本失败: %s" % e)
        return False


def apply_self_update(info, args):
    """下载新版本。返回 True/字典表示已处理；单文件打包下无法可靠原地替换，改为下载到数据目录并提示手动替换。"""
    url = info.get("url")
    if not url:
        log("新版本缺少下载地址，跳过自更新")
        return False
    import tempfile
    tmp = None
    try:
        log("开始下载新版本 %s …" % info.get("version"))
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                    timeout=180, context=_SSL_CTX) as r:
            data = r.read()
        if len(data) < 1024 * 100:
            raise ValueError("下载文件过小(<100KB)，疑似无效")
        sha = (info.get("sha256") or "").lower()
        if sha:
            import hashlib
            got = hashlib.sha256(data).hexdigest()
            if got != sha:
                raise ValueError("下载文件 sha256 不符(升级包损坏或被替换)，已放弃")
            log("升级包 sha256 校验通过")
        size = int(info.get("size") or 0)
        if size and abs(len(data) - size) > 1024:
            raise ValueError("下载文件大小与升级源不符，已放弃")
        if getattr(sys, "frozen", False):
            # 单文件打包：运行中的 exe 不能被覆盖，交给一个独立小脚本等本进程退出后再换文件
            dest = BASE / "update" / ("%s_%s.exe" % (APP_NAME, info.get("version")))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if _spawn_replacer(dest):
                msg = "新版本 v%s 已校验通过，正在自动替换并重启…" % info.get("version")
                log(msg)
                return {"replacing": True, "msg": msg}
            msg = ("新版本 v%s 已下载到 %s ，关闭本程序后用它替换原 exe 即可完成升级。"
                   % (info.get("version"), dest))
            log(msg)
            return {"manual": True, "path": str(dest), "msg": msg}
        fd, tmp = tempfile.mkstemp(suffix=".py")
        os.write(fd, data)
        os.close(fd)
        target = os.path.abspath(__file__)
        bak = target + ".bak"
        try:
            if os.path.exists(bak):
                os.remove(bak)
        except OSError:
            pass
        try:
            os.rename(target, bak)   # Windows 允许重命名正在运行的 exe
        except OSError as e:
            log("无法重命名旧程序，将尝试直接覆盖: %s" % e)
        os.replace(tmp, target)
        tmp = None
        log("新版本已就位，正在启动新进程…")
        try:
            subprocess.Popen([sys.executable, target] + list(args))
        except Exception as e:
            log("启动新进程失败: %s" % e)
        return True
    except Exception as e:
        log("应用程序更新失败: %s" % e)
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False

def main():
    global _SERVER
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--once", action="store_true", help="执行一次更新后退出")
    ap.add_argument("--no-browser", action="store_true", help="启动时不自动打开网页")
    ap.add_argument("--no-tray", action="store_true", help="不显示右下角托盘图标")
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()
    main.no_tray = bool(args.no_tray)

    cfg = load_cfg()
    if args.port:
        cfg["port"] = args.port
    save_cfg(cfg)

    # 单实例：控制台已经开着时，先把网页调出来，不重复起进程（计划任务 --once 不受影响）
    if not args.once:
        port = _already_running(cfg)
        if port:
            log("控制台已在运行: http://127.0.0.1:%d/" % port)
            if not args.no_browser:
                webbrowser.open("http://127.0.0.1:%d/" % port)
            return

    # 清理上次自更新遗留的备份文件
    try:
        _bak = (sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)) + ".bak"
        if os.path.exists(_bak):
            os.remove(_bak)
    except OSError:
        pass

    global _UPDATER
    up = Updater(cfg)
    _UPDATER = up              # 托盘菜单读它的状态（版本/可用频道数/更新时间）
    up.argv = sys.argv[1:]

    if args.once:
        log("进入一次性更新模式")
        up.load_cache()      # 有缓存就先复用"上次在用的地址"，只复测这些，省一大截时间
        up.run_once()
        return

    if not up.load_cache():
        threading.Thread(target=up.run_once, daemon=True).start()
    threading.Thread(target=up.loop, daemon=True).start()

    Handler.updater = up
    Handler.cfg = cfg
    Handler.argv = up.argv
    httpd = None
    for p in range(cfg["port"], cfg["port"] + 10):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    if httpd is None:
        log("无法绑定端口 %d-%d" % (cfg["port"], cfg["port"] + 9))
        sys.exit(1)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    _SERVER = httpd
    log("%s v%s 已启动: %s" % (APP_NAME, VERSION, url))
    log("M3U 保存位置: %s" % cfg["output_path"])
    sync_tray(cfg)
    if not args.no_browser and cfg.get("open_browser", True):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if _TRAY is not None:
                _TRAY.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()

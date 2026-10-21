#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIVE直播源 v1.4.1  —— 本机直播源整理与控制台
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
import tempfile
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
VERSION = "1.4.1"
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
    # 用户 2026-10-19 亲手核对的一批公网源(14 条，实测全部 200 可出画面)，内置成"精选源"，
    # 优先级最高：同一频道有多个候选时，来自这里的地址会被优先探测/优选。
    ("curated", "精选源(人工核对)", "builtin", True, "国内"),
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

# 精选源：人工核对过的公网地址（2026-10-19 全部实测 200 + mpegurl）。
# 直接内嵌成 M3U 文本，不依赖任何网络列表，也不会被别的源覆盖掉。
CURATED = [
    # 央视一/二套固定钉住：CCTV1 的公网源最容易被掐，实测这两条一直通
    ("CCTV1", "http://113.57.140.161:10081/newlive/live/hls/1/live.m3u8", "央视"),
    ("CCTV1", "http://221.226.51.220:50081/newlive/live/hls/1/live.m3u8", "央视"),
    ("CCTV4K", "http://107.150.52.50:82/live/cctv4k.m3u8", "央视"),
    ("CCTV2 财经", "http://8.138.7.223/tv/cctv2.php", "央视"),
    ("CCTV8K", "http://107.150.52.50:82/live/cctv8k.m3u8", "央视"),
    ("湖南卫视", "http://hlsal-ldvt.qing.mgtv.com/nn_live/nn_x64/Y2RuZXhfaWQ9YWxfaGxzX2xkdnQmZT02OTE0NjA0JnY9MSZpZD1ITldTWkdTVCZzPTcwN2RiYTc2YzJjNmJmMTQ4MmUyZGYzOWU2NWM3YWFi/HNWSZGST.m3u8", "卫视"),
    # 用户实测：1036 放的是凤凰资讯、1037 放的是凤凰中文，名字按实际画面登记
    ("凤凰资讯台", "http://120.198.95.220:9901/tsfile/live/1036_1.m3u8?key=txiptv&playlive=1&down=1", "香港"),
    ("凤凰中文台", "http://120.198.95.220:9901/tsfile/live/1037_1.m3u8?key=txiptv&playlive=1&down=1", "香港"),
    ("翡翠台", "http://103.172.187.30:12000/stream/mytv/null-1/master.m3u8", "香港"),
    ("黄金翡翠", "http://103.172.187.30:12000/stream/mytv/null-12/master.m3u8", "香港"),
    ("电影台", "http://103.172.187.30:12000/stream/mytv/null-10/master.m3u8", "香港"),
    ("黄金华剧台", "http://103.172.187.30:12000/stream/mytv/null-8/master.m3u8", "香港"),
    ("八大娱乐台", "http://103.172.187.30:12000/stream/mytv/null-4/master.m3u8", "台湾"),
    ("美亚电影台", "http://103.172.187.30:12000/stream/mytv/null-9/master.m3u8", "香港"),
    ("亚洲剧", "http://103.172.187.30:12000/stream/mytv/null-11/master.m3u8", "香港"),
    ("TVBS亚洲台", "http://38.64.72.148/hls/modn/list/4005/playlist.m3u8", "香港"),
    ("民视新闻台", "http://38.64.72.148/hls/modn/list/4012/playlist.m3u8", "台湾"),
]
CURATED_M3U = "#EXTM3U\n" + "".join(
    '#EXTINF:-1 tvg-name="%s" group-title="%s",%s\n%s\n' % (n, g, n, u) for n, u, g in CURATED
)
CURATED_NAMES = {n for n, _, _ in CURATED}
# 精选源的分组是人工核对过的，不能被关键词猜错（凤凰卫视中文台会被"卫视"抢走、
# 翡翠台系列会被误分到台湾）。所以分组直接按这里的 g 落。
CURATED_GROUP = {n: g for n, _, g in CURATED}

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

CFG_VER = 8                    # 当前配置结构版本；load_cfg() 里比"盘上的旧版本"做一次性迁移

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
    "hide_local": True,        # 不显示地级市/县级台(名字带地名的那些)，列表只留大台
    "urls_per_channel": 1,     # 每个频道写几条线路(>1 时播放器里会出现同名条目，按需开)
    "lan": False,              # 允许同一 Wi-Fi 的手机/平板访问控制台并订阅 M3U
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
    "cfg_ver": 8,              # 配置结构版本(升级时做一次性迁移；见 CFG_VER)
    "sources": {k: on for k, _, _, on, _ in SOURCES},
}

# 列表默认顺序：常看的在前(CCTV/卫视/港澳台)，地级台垫底
def _lan_ip():
    """本机在局域网里的 IPv4（拿不到返回空串）。只是让系统选一下出口网卡，不发包。"""
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.settimeout(0.5)
        sk.connect(("223.5.5.5", 80))
        ip = sk.getsockname()[0]
        sk.close()
        return "" if ip.startswith("127.") else ip
    except Exception:
        return ""


def cctv_base(name):
    """是不是"标准台"名字(CCTV4 是，CCTV4K / CCTV-4 Europe 不是)，用于同号内排序。"""
    return 0 if re.fullmatch(r"cctv[-\s]?\d{1,2}", (name or "").strip(), re.I) else 1


def cctv_num(name):
    """CCTV 频道的编号(用于把 CCTV1..CCTV17 排整齐)；不是 CCTV 的返回 99。"""
    m = re.search(r"cctv[\-\s]*(\d{1,2})", name or "", re.I)
    return int(m.group(1)) if m else 99


GROUP_RANK = ["央视", "卫视", "香港", "澳门", "台湾", "体育", "电影", "少儿", "游戏", "国际·综合", "地方台", "其他"]

# ---------------------------------------------------------------- 基础工具

_SSL_CTX = ssl._create_unverified_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "*/*", "Accept-Encoding": "identity"}


_LOG_LOCK = threading.Lock()


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
        # 多线程(探测/台标/吞吐复测)同时写会撕开多字节字符，写出半截乱码，加锁串起来
        with _LOG_LOCK:
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
        if int(cfg.get("urls_per_channel") or 0) > 1:
            cfg["urls_per_channel"] = 1  # 每条线路单独一行会变成播放器里的"无名 url"，默认只写一条
            log("配置升级：每个频道只写 1 条线路(多条会让播放列表变乱，需要时在设置里调)")
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
    if tag == "curated" and name in CURATED_GROUP:
        return CURATED_GROUP[name]
    if MO_KW.search(n):
        return "澳门"
    if re.search(r"tvb", n):
        return "香港"
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
    if tag in ("cn_org", "yang", "ccsh_plat", "ccsh_live", "guovin", "cinauto", "curated"):
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
    if (cfg.get("only_tv", True) and TV_NAMES and e.get("tag") != "curated"
            and not is_tv(e["name"])):
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


# 假源特征：一批"通用中转"站点对任何 id 都回同一段占位视频
# （实测 zby.lskk.top/cdnlive.php -> pan.dfkj.live/tokenerror.mp4），测速照样有数字、
# 也能"播出画面"，但画面根本不是那个频道 —— 用户看到的就是"假频道"。
FAKE_HOSTS = {"pan.dfkj.live"}
FAKE_PATH_KW = ("tokenerror", "token_error", "nochannel", "notfound.mp4", "placeholder")


def _is_fake_target(final_url):
    low = (final_url or "").lower()
    if (urlparse(low).hostname or "") in FAKE_HOSTS:
        return True
    return any(k in low for k in FAKE_PATH_KW)


# ------------------------------------------------------------------ 实测分辨率
# 为什么要自己解析：标称分辨率（频道名/URL 里的 1080P、4K）根本不可信 ——
# 实测过 107.150.52.50 的 "cctv4k/cctv8k" 两条源，真实画面是 1920x1080 的 H.264；
# 而 湖南卫视 那条 3840x2160 的 HEVC 只有 1.4 Mbps。只有从码流本身读出宽高才作数。
# 做法：TS 分片 -> PAT 找 PMT -> PMT 找视频 PID 与编码类型 -> 收集 PES 载荷 ->
# 找 SPS(H.264 NAL=7 / HEVC NAL=33) -> 按标准语法解出宽高(含 conformance crop)。
_AUDIO_STREAM_TYPES = {0x03, 0x04, 0x0F, 0x11, 0x81, 0x82, 0x87, 0x88}
_VIDEO_STREAM_TYPES = {0x1B: "H.264", 0x24: "HEVC", 0x02: "MPEG-2", 0x01: "MPEG-1",
                       0x10: "MPEG-4", 0x42: "AVS2", 0xD2: "AVS2", 0xD4: "AVS3",
                       0x21: "JPEG", 0xEA: "VC-1"}


class _BitReader:
    """按位读比特流（SPS 解析用）。"""

    def __init__(self, buf, byte_pos=0):
        self.b = buf
        self.p = byte_pos * 8

    def bit(self):
        i = self.p >> 3
        if i >= len(self.b):
            raise IndexError
        v = (self.b[i] >> (7 - (self.p & 7))) & 1
        self.p += 1
        return v

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v

    def ue(self):
        z = 0
        while self.bit() == 0:
            z += 1
            if z > 32:
                raise ValueError("ue too long")
        return (1 << z) - 1 + self.bits(z)

    def se(self):
        v = self.ue()
        return (v + 1) // 2 if v % 2 else -(v // 2)

    def skip(self, n):
        self.p += n


def _nal_unescape(nal):
    """去掉防竞争字节 00 00 03 -> 00 00。"""
    out = bytearray()
    i, n = 0, len(nal)
    while i < n:
        if i + 2 < n and nal[i] == 0 and nal[i + 1] == 0 and nal[i + 2] == 3:
            out += b"\x00\x00"
            i += 3
            continue
        out.append(nal[i])
        i += 1
    return bytes(out)


def _nal_units(payload):
    """按起始码切出 NAL 单元，返回 [(首字节, 原始字节)]。
    用 bytes.find 找起始码(C 速度)：几百 KB 的分片逐字节扫太慢，会把整轮更新拖成几分钟。"""
    starts = []
    i, n = 0, len(payload)
    find = payload.find
    while i + 3 < n:
        j = find(b"\x00\x00\x01", i)
        if j < 0:
            break
        starts.append(j + 3)
        i = j + 3
    out = []
    for k, s in enumerate(starts):
        e = starts[k + 1] - 3 if k + 1 < len(starts) else n
        if e > s:
            out.append((payload[s], payload[s:e]))
    return out


def _h264_sps_size(rbsp):
    """H.264 SPS -> (宽, 高)。"""
    br = _BitReader(rbsp, 1)
    profile = br.bits(8)
    br.bits(8)
    br.bits(8)
    br.ue()
    if profile in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134):
        chroma = br.ue()
        if chroma == 3:
            br.bit()
        br.ue()
        br.ue()
        br.bit()
        if br.bit():
            for i in range(8 if chroma != 3 else 12):
                if br.bit():
                    last, nxt = 8, 8
                    for _ in range(16 if i < 6 else 64):
                        if nxt:
                            nxt = (last + br.se() + 256) % 256
                        last = nxt or last
    br.ue()
    poc = br.ue()
    if poc == 0:
        br.ue()
    elif poc == 1:
        br.bit()
        br.se()
        br.se()
        for _ in range(br.ue()):
            br.se()
    br.ue()
    br.bit()
    w_mbs = br.ue() + 1
    h_map = br.ue() + 1
    frame_only = br.bit()
    if not frame_only:
        br.bit()
    br.bit()
    cl = cr = ct = cb = 0
    if br.bit():
        cl, cr, ct, cb = br.ue(), br.ue(), br.ue(), br.ue()
    w = w_mbs * 16 - (cl + cr) * 2
    h = (2 - frame_only) * h_map * 16 - (ct + cb) * 2 * (2 - frame_only)
    return w, h


def _hevc_sps_size(rbsp):
    """HEVC SPS -> (宽, 高)。"""
    br = _BitReader(rbsp, 2)
    br.bits(4)
    sub = br.bits(3)
    br.bit()
    br.bits(2 + 1 + 5)      # profile_space/tier/profile_idc
    br.bits(32)             # compatibility flags
    br.bits(48)             # constraint flags
    br.bits(8)              # level_idc
    prof = []
    for _ in range(sub):
        prof.append(br.bit())
        br.bit()
    if sub > 0:
        for _ in range(sub, 8):
            br.bits(2)
    for pf in prof:
        if pf:
            br.skip(88)
    br.ue()                 # sps id
    chroma = br.ue()
    if chroma == 3:
        br.bit()
    w = br.ue()
    h = br.ue()
    if br.bit():            # conformance_window_flag
        l, r, t, b = br.ue(), br.ue(), br.ue(), br.ue()
        sx, sy = (2, 2) if chroma == 1 else ((2, 1) if chroma == 2 else (1, 1))
        w -= (l + r) * sx
        h -= (t + b) * sy
    return w, h


def _mp4_boxes(data, start=0, end=None):
    """遍历 ISO-BMFF(MP4) box，产出 (类型, 载荷字节)。"""
    end = len(data) if end is None else end
    i = start
    while i + 8 <= end:
        size = int.from_bytes(data[i:i + 4], "big")
        typ = data[i + 4:i + 8]
        head = 8
        if size == 1:
            if i + 16 > end:
                break
            size = int.from_bytes(data[i + 8:i + 16], "big")
            head = 16
        elif size == 0:
            size = end - i
        if size < head or i + size > end:
            break
        yield typ, data[i + head:i + size]
        i += size


def parse_mp4_video(data):
    """从 fMP4/CMAF 的 moov 里读 (编码, 宽, 高)。
    分辨率在 tkhd 的 width/height(16.16 定点)；编码看 stsd 里的 sample entry 类型。
    媒体分片(.m4s)本身没有 moov，必须把 EXT-X-MAP 的初始化段一起传进来。"""
    if not data or b"moov" not in data[:400000] and b"moov" not in data:
        return "", 0, 0
    codec, w, h = "", 0, 0
    for typ, moov in _mp4_boxes(data):
        if typ != b"moov":
            continue
        for t2, trak in _mp4_boxes(moov):
            if t2 != b"trak":
                continue
            cw = ch_ = 0
            trak_codec = ""
            for t3, p3 in _mp4_boxes(trak):
                if t3 == b"tkhd":
                    ver = p3[0] if p3 else 0
                    off = 76 if ver == 0 else 88
                    if len(p3) >= off + 8:
                        cw = int.from_bytes(p3[off:off + 4], "big") >> 16
                        ch_ = int.from_bytes(p3[off + 4:off + 8], "big") >> 16
                elif t3 == b"mdia":
                    for t4, p4 in _mp4_boxes(p3):
                        if t4 != b"minf":
                            continue
                        for t5, stbl in _mp4_boxes(p4):
                            if t5 != b"stbl":
                                continue
                            for t6, stsd in _mp4_boxes(stbl):
                                if t6 != b"stsd":
                                    continue
                                for t7, entry in _mp4_boxes(stsd, 8):
                                    name = entry[:4]
                                    if name in (b"avc1", b"avc3", b"hvc1", b"hev1",
                                                b"av01", b"mp4v", b"vp09"):
                                        trak_codec = {
                                            b"avc1": "H.264", b"avc3": "H.264",
                                            b"hvc1": "HEVC", b"hev1": "HEVC",
                                            b"av01": "AV1", b"mp4v": "MPEG-4",
                                            b"vp09": "VP9"}[name]
                                        # sample entry 里 avcC/hvcC 还带一份 SPS，tkhd 没尺寸时补
                                        if cw <= 0:
                                            for t8, p8 in _mp4_boxes(entry, 78):
                                                if t8 == b"avcC" and len(p8) > 7:
                                                    try:
                                                        n = p8[5] & 0x1F
                                                        sps = p8[6:6 + n]
                                                        _cw2, _h2 = _h264_sps_size(_nal_unescape(sps))
                                                        cw, ch_ = _cw2, _h2
                                                    except Exception:
                                                        pass
            if cw > 0 and ch_ > 0:
                return trak_codec or codec, cw, ch_
            if trak_codec and not codec:
                codec = trak_codec
    return codec, 0, 0


def _more_segments(text, base, limit=2):
    """清单里除第一片之外的后续分片(按出现顺序，最多 limit 个)，用来换一片再找 SPS。"""
    out = []
    dur = 0.0
    seen = 0
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#EXTINF:"):
            try:
                dur = float(s[8:].split(",")[0].strip())
            except Exception:
                dur = 0.0
            continue
        if s.startswith("#"):
            continue
        pure = s.split("?", 1)[0].split("#", 1)[0].lower()
        if not pure.endswith((".ts", ".m4s", ".mp4")):
            continue
        seen += 1
        if seen == 1:
            continue                      # 第一片已经在主循环里读过了
        out.append((urljoin(base, s), dur))
        if len(out) >= limit:
            break
    return out


def _mpeg2_seq_size(rbsp):
    """MPEG-2 序列头(0xB3) -> (宽, 高)。IPTV 里还有一批老 MPEG-2 编码的卫视。"""
    br = _BitReader(rbsp, 1)          # 跳过 0xB3 本身
    w = br.bits(12)
    h = br.bits(12)
    return w, h


def parse_ts_video(data):
    """从 TS 分片字节里读出 (编码, 宽, 高)。读不出来返回 ("", 0, 0)，绝不给猜的数字。"""
    if not data or len(data) < 1880 or data[0] != 0x47:
        return "", 0, 0
    pkt = 188
    pmt_pid = video_pid = stream_type = -1
    audio_pids = set()
    for off in range(0, min(len(data), pkt * 4000), pkt):
        p = data[off:off + pkt]
        if len(p) < pkt or p[0] != 0x47:
            continue
        if ((p[1] & 0x1F) << 8) | p[2] != 0:
            continue
        afc = (p[3] >> 4) & 3
        pos = 4
        if afc & 2:
            pos += 1 + p[4]
        if not (afc & 1) or pos >= pkt:
            continue
        sec = p[pos + 1 + p[pos]:]
        if len(sec) > 8 and sec[0] == 0x00:
            slen = ((sec[1] & 0x0F) << 8) | sec[2]
            body = sec[8:3 + slen - 4]
            for i in range(0, len(body) - 3, 4):
                if (body[i] << 8) | body[i + 1]:
                    pmt_pid = ((body[i + 2] & 0x1F) << 8) | body[i + 3]
                    break
        if pmt_pid >= 0:
            break
    if pmt_pid < 0:
        return "", 0, 0
    for off in range(0, min(len(data), pkt * 4000), pkt):
        p = data[off:off + pkt]
        if len(p) < pkt or p[0] != 0x47:
            continue
        if ((p[1] & 0x1F) << 8) | p[2] != pmt_pid:
            continue
        afc = (p[3] >> 4) & 3
        pos = 4
        if afc & 2:
            pos += 1 + p[4]
        if not (afc & 1) or pos >= pkt:
            continue
        sec = p[pos + 1 + p[pos]:]
        if len(sec) < 12 or sec[0] != 0x02:
            continue
        slen = ((sec[1] & 0x0F) << 8) | sec[2]
        pinfo = ((sec[10] & 0x0F) << 8) | sec[11]
        body = sec[12 + pinfo:3 + slen - 4]
        for i in range(0, len(body) - 4, 5):
            st = body[i]
            epid = ((body[i + 1] & 0x1F) << 8) | body[i + 2]
            if st in _VIDEO_STREAM_TYPES:
                if video_pid < 0:
                    stream_type, video_pid = st, epid
            elif st in _AUDIO_STREAM_TYPES:
                audio_pids.add(epid)
        if video_pid >= 0:
            break
    if video_pid < 0:
        # 私有封装(实测 CCTV3 / CCTV-5+ 的 PMT 里只写 0x8B / 0xE0，没写视频流)：
        # 认不出类型时就拿"包最多的那个 PID"当视频，三种编码各试一遍
        cnt = {}
        for off in range(0, len(data), pkt):
            q = data[off:off + pkt]
            if len(q) < pkt or q[0] != 0x47:
                continue
            pid = ((q[1] & 0x1F) << 8) | q[2]
            if pid in (0, 0x11, 0x1FFF, pmt_pid) or pid in audio_pids:
                continue
            cnt[pid] = cnt.get(pid, 0) + 1
        if not cnt:
            return "", 0, 0
        video_pid = max(cnt, key=lambda k: cnt[k])
        stream_type = 0
    buf = bytearray()
    for off in range(0, len(data), pkt):
        p = data[off:off + pkt]
        if len(p) < pkt or p[0] != 0x47:
            break
        if ((p[1] & 0x1F) << 8) | p[2] != video_pid:
            continue
        afc = (p[3] >> 4) & 3
        pos = 4
        if afc & 2:
            pos += 1 + p[4]
        if not (afc & 1) or pos >= pkt:
            continue
        payload = p[pos:]
        if (p[1] >> 6) & 1:          # PES 起始：跳过 PES 头
            if len(payload) >= 9 and payload[:3] == b"\x00\x00\x01":
                payload = payload[9 + payload[8]:]
            else:
                continue
        buf += payload
        # 只收视频载荷，但别太小气：SPS/IDR 大概每 1~2 秒才来一次，
        # 原来 300KB(10M 码率只有 0.24 秒)常常整段都碰不到 SPS，分辨率就白读了。
        if len(buf) > 3000000:
            break
    if not buf:
        return "", 0, 0
    # 按 PMT 给的编码优先，认不出来就把 H.264 / HEVC / MPEG-2 都试一遍
    order = {0x1B: ("H.264", "HEVC", "MPEG-2"), 0x24: ("HEVC", "H.264", "MPEG-2"),
             0x02: ("MPEG-2", "H.264"), 0x42: ("AVS2", "H.264"), 0xD2: ("AVS2", "H.264"),
             0xD4: ("AVS3", "HEVC")}.get(stream_type, ("H.264", "HEVC", "MPEG-2"))
    nals = _nal_units(bytes(buf))
    for want in order:
        for first, raw in nals:
            try:
                if want == "H.264" and (first & 0x1F) == 7:
                    w, h = _h264_sps_size(_nal_unescape(raw))
                    if w > 0 and h > 0:
                        return want, w, h
                elif want == "HEVC" and ((first >> 1) & 0x3F) == 33:
                    w, h = _hevc_sps_size(_nal_unescape(raw))
                    if w > 0 and h > 0:
                        return want, w, h
                elif want == "MPEG-2" and first == 0xB3:
                    w, h = _mpeg2_seq_size(raw)
                    if w > 0 and h > 0:
                        return want, w, h
            except Exception:
                continue
    return _VIDEO_STREAM_TYPES.get(stream_type, ""), 0, 0


def probe_stream(e, timeout, budget=1.5, max_bytes=2621440, want_res=True):  # noqa: C901
    """一次连接同时判断：能不能连、是不是真流、能不能拉出画面、真实码率、分辨率。

    返回 (ok, ttfb_ms, note, mbps, res_h, speed)：
      mbps  = 真实码率(分片字节数 / 分片时长)，和播放器里看到的一致；
      speed = 我这边的下载吞吐，用来排"最快优先"。
    HLS 要顺着三层走：主清单 -> 变体清单 -> 真正带画面的分片(.ts/.m4s)，只读分片才测得出
    "播放器实际能拿到多少"；只读清单会算出几百 Mbps 的假数字(实测过)。
    """
    url = e["url"]
    if not url.startswith(("http://", "https://")):
        m = re.match(r"\w+://([^/:]+)(?::(\d+))?", url)
        if not m:
            return False, 0, "地址无法解析", 0.0, 0, 0.0
        try:
            t0 = time.monotonic()
            sk = socket.create_connection((m.group(1), int(m.group(2) or 1935)), timeout=timeout)
            sk.close()
            return True, round((time.monotonic() - t0) * 1000), "非HTTP流(TCP探测)", 0.0, 0, 0.0
        except Exception:
            return False, 0, "TCP不可达", 0.0, 0, 0.0
    try:
        t0 = time.monotonic()
        # 整条探测的硬时限：单次 socket 超时管不住"读 1.2MB 分片"那种慢速续传，
        # 实测有地址单条卡了 131 秒(精选源补测那一步)，把整轮更新拖长。
        hard = t0 + max(4.0, timeout * 2.0)
        resp = _open(url, timeout)
        ttfb = round((time.monotonic() - t0) * 1000)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if _is_fake_target(resp.geturl() or url):
            resp.close()
            return False, ttfb, "假源(跳转到占位视频)", 0.0, 0, 0.0

        def read_text(r):
            try:
                return r.read(262144).decode("utf-8", "ignore")
            finally:
                try:
                    r.close()
                except Exception:
                    pass

        def first_segment(text, base):
            """返回 (分片地址, 该分片时长秒)。分片地址几乎都带查询串
            (stream.m3u8?uid=…、live_1.ts?key=…)，必须去掉 ?后面再判后缀。"""
            dur = 0.0
            for ln in text.splitlines():
                s = ln.strip()
                if not s:
                    continue
                if s.startswith("#EXTINF:"):
                    try:
                        dur = float(s[8:].split(",")[0].strip())
                    except Exception:
                        dur = 0.0
                    continue
                if s.startswith("#"):
                    continue
                pure = s.split("?", 1)[0].split("#", 1)[0].lower()
                if pure.endswith((".ts", ".m4s", ".flv", ".mp4", ".aac", ".m3u8", ".mp3")):
                    return urljoin(base, s), dur
                if s.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                    return urljoin(base, s), dur
            return "", 0.0

        res_h = 0
        seg_dur = 0.0
        seg_len = 0
        mediatxt = ""          # 媒体清单原文（换下一片再试、找 EXT-X-MAP 初始化段都要用）
        base_url = url
        if ".m3u8" in url.lower() or "mpegurl" in ctype:
            text = read_text(resp)
            low = text[:2048].lower()
            if "<html" in low or "<!doctype" in low:
                return False, ttfb, "返回网页(非直播流)", 0.0, 0, 0.0
            cands = []
            for attrs, seg in re.findall(r"#EXT-X-STREAM-INF:([^\n]*)\n([^\r\n#]+)", text):
                bwm = re.search(r"BANDWIDTH=(\d+)", attrs)
                resm = re.search(r"RESOLUTION=(\d+)x(\d+)", attrs)
                cands.append((int(bwm.group(1)) if bwm else 0, seg.strip(),
                              int(resm.group(2)) if resm else 0))
            if cands:
                # 主清单：取最高码率那一档，再进它的变体清单找分片
                _, seg, res_h = max(cands, key=lambda v: v[0])
                vurl = urljoin(url, seg)
                vresp = _open(vurl, timeout)
                if _is_fake_target(vresp.geturl() or vurl):
                    vresp.close()
                    return False, ttfb, "假源(跳转到占位视频)", 0.0, res_h, 0.0
                vtext = read_text(vresp)
                media_text = vtext
                mediatxt, base_url = vtext, (vresp.geturl() or vurl)
                target, seg_dur = first_segment(vtext, base_url)
            else:
                media_text = text
                mediatxt, base_url = text, (resp.geturl() or url)
                target, seg_dur = first_segment(text, base_url)
            # 真直播的清单永远不会有 EXT-X-ENDLIST；带这个标记又很短的，基本都是
            # 广告占位/循环录播(换了台标也放同一条片子)，直接判掉
            if "#EXT-X-ENDLIST" in (media_text or "").upper():
                return False, ttfb, "录播/广告占位(清单已结束)", 0.0, res_h, 0.0
            if not target:
                return False, ttfb, "清单里没有可播放分片", 0.0, res_h, 0.0
            resp = _open(target, timeout)
            if _is_fake_target(resp.geturl() or target):
                resp.close()
                return False, ttfb, "假源(跳转到占位视频)", 0.0, res_h, 0.0
            try:
                seg_len = int(resp.headers.get("Content-Length") or 0)
            except Exception:
                seg_len = 0

        total = 0
        head = b""
        t_read = 0.0
        first_len = 0
        reached_eof = False
        buf = bytearray()      # 留一段原始分片，用来解析真实分辨率/编码
        got_wh = (0, 0)        # 已解析出的 (宽, 高)，解析出来就不再往 buf 里堆
        got_codec = ""
        # 分片里找不到 SPS 的(低码率 4K、IDR 稀疏、被切片的首段)就多读一点再试，
        # 但一旦解析出来立刻停止堆积，正常分片 400KB 就够，内存不会失控。
        RES_STAGES = (400000, 900000, 2000000)
        stage = 0
        # 测速窗口至少 0.8 秒：命中"同服务器已知速度"时原来只有 0.35 秒，
        # 这段时间还夹着慢启动，测出来的吞吐比真实值低一大截(实测 8M 的台只剩 1M)。
        win = max(budget, 0.8)
        while (total < max_bytes and time.monotonic() < hard
               and (t_read <= 0 or time.monotonic() - t_read < win)):
            try:
                b = resp.read(65536)
            except Exception:
                break
            if not b:
                reached_eof = True
                break
            if want_res and not got_wh[1] and len(buf) < RES_STAGES[-1]:
                buf += b[:RES_STAGES[-1] - len(buf)]
            if t_read <= 0:
                # 第一块只用来认内容(TLS 握手与慢启动都算在这块里)，不计入测速窗口
                head = b[:1024]
                first_len = len(b)
                t_read = time.monotonic()
                continue
            total += len(b)
            if want_res and not got_wh[1] and len(buf) >= RES_STAGES[stage]:
                stage = min(stage + 1, len(RES_STAGES) - 1)
                if buf[:4] == b"\x00\x00\x00" or b"ftyp" in buf[:64] or b"styp" in buf[:64]:
                    _c, _w, _h = parse_mp4_video(bytes(buf))
                else:
                    _c, _w, _h = parse_ts_video(bytes(buf))
                if _c and not got_codec:
                    got_codec = _c
                if _h > 0:
                    got_wh = (_w, _h)
                    buf = bytearray()          # 已经拿到了，省内存
        dt = (time.monotonic() - t_read) if t_read > 0 else 0.0
        # 分辨率补读：命中"同服务器已知速度"时测速窗口只有 0.35 秒，10M 的台才 400KB，
        # SPS 还没轮到就收摊了。这里再补读一小段专门找 SPS(最多 1.2 秒 / 1.6MB)，
        # 补读的字节不计入 total，不影响 speed 与码率口径。
        if want_res and not got_wh[1] and not reached_eof:
            t_fix = time.monotonic()
            next_try = len(buf) + 300000
            while (time.monotonic() - t_fix < 1.2 and len(buf) < 1600000
                   and time.monotonic() < hard):
                try:
                    b = resp.read(65536)
                except Exception:
                    break
                if not b:
                    break
                buf += b
                if len(buf) < next_try:
                    continue
                next_try = len(buf) + 300000
                if buf[:4] == b"\x00\x00\x00" or b"ftyp" in buf[:64] or b"styp" in buf[:64]:
                    _c, _w, _h = parse_mp4_video(bytes(buf))
                else:
                    _c, _w, _h = parse_ts_video(bytes(buf))
                if _c and not got_codec:
                    got_codec = _c
                if _h > 0:
                    got_wh = (_w, _h)
                    buf = bytearray()
                    break
        try:
            resp.close()
        except Exception:
            pass
        low = head.lower()
        if "text/html" in ctype or b"<html" in low or b"<!doctype" in low:
            return False, ttfb, "返回网页(非直播流)", 0.0, 0, 0.0
        if total <= 0:
            return False, ttfb, "连得上但拉不到画面", 0.0, res_h, 0.0
        # 0.25 秒下限：更短的突发只是服务器缓冲，不能当真实带宽
        speed = round(min(300.0, (total * 8 / 1e6) / max(dt, 0.25)), 2)
        # 真实码率 = 分片字节 / 分片时长，和播放器里显示的一致(实测凤凰资讯 6.22、
        # CCTV2 4.29，与用户手工测的 6.2/4.4 对得上)。
        mbps = 0.0
        if seg_len > 0 and seg_dur > 0:
            mbps = round(min(300.0, seg_len * 8 / 1e6 / seg_dur), 2)
        elif seg_dur > 0 and seg_len == 0 and reached_eof and "mpegurl" not in ctype:
            # 分片没有 Content-Length(分块传输)：整片已经读完，用实际读到的字节数反推码率。
            # 只认媒体分片，别把嵌套清单(.m3u8)的纯文本当成一个分片。
            got = first_len + total
            if got > 0:
                mbps = round(min(300.0, got * 8 / 1e6 / seg_dur), 2)
        # 真实分辨率：能有主清单 RESOLUTION 就用，没有就从码流里读 SPS。
        # 标称分辨率不可信(实测 "cctv8k" 的源其实是 1080p)，所以只认码流里读出来的。
        codec, _w, _h = got_codec or "", got_wh[0], got_wh[1]
        if want_res and not _h:
            codec, _w, _h = parse_ts_video(bytes(buf)) if buf[:4] == b"\x47" else parse_mp4_video(bytes(buf))
        if want_res and not _h and mediatxt:
            # ① fMP4/CMAF：分片里没有 moov，尺寸在 EXT-X-MAP 的初始化段里
            m = re.search(r'#EXT-X-MAP:.*?URI="([^"]+)"', mediatxt)
            if m and time.monotonic() < hard:
                try:
                    iu = urljoin(base_url, m.group(1))
                    with _open(iu, timeout) as ir:
                        init = ir.read(400000)
                    c2, w2, h2 = parse_mp4_video(init)
                    if h2 > 0:
                        codec, _w, _h = (codec or c2), w2, h2
                except Exception:
                    pass
            # ② TS 里这一片恰好没有 SPS(IDR 稀疏/首片被切)：换清单里下一片再试一次
            if not _h:
                for nxt, _d in _more_segments(mediatxt, base_url, 2):
                    if time.monotonic() >= hard:
                        break
                    try:
                        with _open(nxt, timeout) as nr:
                            nb = nr.read(600000)
                        c3, w3, h3 = (parse_mp4_video(nb)
                                      if (nb[:4] == b"\x00\x00\x00" or b"ftyp" in nb[:64])
                                      else parse_ts_video(nb))
                        if h3 > 0:
                            codec, _w, _h = (codec or c3), w3, h3
                            break
                        if c3 and not codec:
                            codec = c3
                    except Exception:
                        continue
        if codec:
            e["codec"] = codec
        if not res_h and _h > 0:
            res_h = _h
        if _w and _h:
            e["res_wh"] = (_w, _h)
        return True, ttfb, "", mbps, res_h, speed
    except Exception:
        return False, 0, "不可达", 0.0, 0, 0.0

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


# 位置基准：频道所属区域优先匹配的源标签(用于「区域是否对口」判定)
REGION_TAG = {
    "香港": {"kelvin", "org_hk", "epg_hk"},
    "澳门": {"org_mo", "epg_mo"},
    "台湾": {"org_tw", "epg_tw"},
    "国内": {"cn_org", "yang"},
}


# 画质判据（按用户 2026-10-20 三次实测结论定，别再自己发明）：
#   ①「码率越高图像质量越好」—— 标着 1080P 却只有 1.4 Mbps 的源满街都是，标称不可信；
#   ②「分辨率和码率都要看」—— 码率高但分辨率低、或分辨率高但码率低，画面都不行；
#   ③ 用户给的门槛原话：「分辨率 1080P 以上，码率 2M 以上，图像质量就很清晰」；
#   ④ 流畅度另算：「网络(下载吞吐) 400KB/s 以上，看着不卡顿」(400KB/s ≈ 3.2 Mbps)。
# 所以：清晰 = 实测分辨率 ≥1080P 且 实测码率 ≥2 Mbps；流畅 = 实测吞吐 ≥400KB/s。
CLARITY_HEIGHT = 1000          # ≥1000 像素算高清分辨率(1080P 及以上)
CLARITY_MBPS = 2.0             # 用户给的码率门槛：2 Mbps
SMOOTH_KBPS = 400.0            # 用户给的流畅门槛：400 KB/s(≈3.2 Mbps)
MB_TIERS = ((9.0, 4, "超清"), (5.0, 3, "高清"), (2.5, 2, "标准"), (1.0, 1, "一般"))
RES_LEVELS = ((2000, 4.0, "4K"), (1000, 3.0, "1080P"), (620, 2.0, "720P"), (400, 1.0, "480P"))
# 央视频道的官方说法（台标上印的那几个字），频道名统一按这个写
CCTV_OFFICIAL = {
    "1": "综合", "2": "财经", "3": "综艺", "4": "中文国际", "5": "体育",
    "5+": "体育赛事", "6": "电影", "7": "国防军事", "8": "电视剧", "9": "纪录",
    "10": "科教", "11": "戏曲", "12": "社会与法", "13": "新闻", "14": "少儿",
    "15": "音乐", "16": "奥林匹克", "17": "农业农村", "4k": "超高清", "8k": "超高清",
}


def mbps_tier(mbps):
    """按实测码率分档，返回 (等级 0-4, 名称)；0 且名称为空 = 没测到码率。
    4=超清(≥9M) 3=高清(≥5M) 2=标准(≥2.5M) 1=一般(≥1M) 0(<1M 或未知)"""
    try:
        m = float(mbps or 0)
    except Exception:
        m = 0.0
    if m <= 0:
        return 0, ""
    for cut, lv, nm in MB_TIERS:
        if m >= cut:
            return lv, nm
    return 0, "低码率"


def mbps_level(mbps):
    """码率等级(数值 0.3~4)：没测到返回 None。"""
    lv, nm = mbps_tier(mbps)
    if not nm:
        return None
    return float(lv) if lv > 0 else 0.3


def res_level(res_h):
    """分辨率等级(数值 0.3~4)：没测到返回 None。"""
    try:
        rh = int(res_h or 0)
    except Exception:
        rh = 0
    if rh <= 0:
        return None
    for cut, lv, _nm in RES_LEVELS:
        if rh >= cut:
            return lv
    return 0.3


def res_label(res_h):
    """分辨率档的显示名(4K/1080P/720P/480P/低分辨率)，没测到返回空串。"""
    lv = res_level(res_h)
    if lv is None:
        return ""
    for cut, clv, nm in RES_LEVELS:
        if lv == clv:
            return nm
    return "低分辨率"


def official_cctv_name(name):
    """央视频道统一成"台标上的官方名字"（CCTV-1 综合 / CCTV-2 财经 / CCTV-9 纪录 /
    CCTV-5+ 体育赛事 / CCTV-4K 超高清），用户照着台标就能对上号。
    不是央视(或对不上号)返回空串，调用方保持原样。"""
    n = (name or "").strip()
    m = re.match(r"^cctv[\-\s]?(\d{1,2})(\+)?(.*)$", n, re.I)
    if not m:
        return ""
    num = m.group(1)
    plus = "+" if m.group(2) else ""
    tail = (m.group(3) or "").strip().lower()
    key = num + plus
    if ("4k" in tail or "8k" in tail or tail.startswith("k")) and num in ("4", "8"):
        key = num + "k"                      # cctv-4k超高清 / CCTV8K
    suffix = CCTV_OFFICIAL.get(key)
    if not suffix:
        return ""
    region = ""
    for kw, cn in (("asia", "亚洲"), ("europe", "欧洲"), ("america", "美洲")):
        if kw in tail:
            region = "（%s）" % cn
            break
    head = "CCTV-%s%s" % (num, plus)
    if key in ("4k", "8k"):
        head = "CCTV-%sK" % num
    return head + " " + suffix + region


# 非央视频道的展示名修正(2026-10-20 用户要求"名字统一")：精确匹配才替换，
# 替换后原名存 aka，搜索仍能命中旧写法。
NAME_FIXES = {
    "内蒙少儿": "内蒙古少儿",          # 图库/官方都叫"内蒙古少儿"
    "TVBPearl": "TVB Pearl",         # 连写不易读，加空格
    "凤凰香港台": "香港台",           # 台标写"香港台"，频道名跟着台标走
}

# 台标图库别名：这些频道在图库里的文件名跟频道名对不上(差个"频道"后缀/写法不同)，
# 自动解析会 miss，这里点名直查。值为 (库, 图库内路径)。
LOGO_ALIASES = {
    "CCTV-4 欧洲": ("cachemiao", "tv/CCTV4欧洲.png"),
    "CCTV4 Europe": ("cachemiao", "tv/CCTV4欧洲.png"),   # 兼容旧缓存名
    "CCTV-4 中文国际（欧洲）": ("cachemiao", "tv/CCTV4欧洲.png"),
    "CCTV-4 中文国际（美洲）": ("cachemiao", "tv/CCTV4美洲.png"),
    "内蒙古少儿": ("cachemiao", "tv/内蒙古少儿频道.png"),
    "浙江教科影视": ("cachemiao", "tv/浙江科教影视.png"),
    # 图库文件名跟频道名对不上，逐个点名
    "凤凰中文台": ("cachemiao", "tv/凤凰卫视中文台.png"),
    "凤凰资讯台": ("cachemiao", "tv/凤凰卫视资讯台.png"),
    "凤凰香港": ("wanglindl", "img/Phoenix3.png"),
    "香港台": ("wanglindl", "img/Phoenix3.png"),
    "优漫卡通": ("cachemiao", "tv/江苏优漫卡通.png"),
    "黑龙江卫视": ("cachemiao", "tv/黑龙江卫视.png"),
    "大湾区卫视": ("cachemiao", "tv/广东大湾区卫视.png"),
    "金鹰纪实": ("cachemiao", "tv/湖南金鹰纪实.png"),
    # cachemiao 里也有一张"翡翠台"，但是 180x187 的近方图，跟列表里其他横版台标不统一。
    # 这里点名锁 CCSH 那张 300x180 横版的，避免图库扩容后被近方图顶掉。
    "翡翠台": ("other", "翡翠台.png"),
    "翡翠台 HD": ("other", "翡翠台.png"),
    # 电影台锁用户提供的那张(已去白边、透明底、300x180)。不锁的话：
    # ① 图库扩容后 cachemiao 一旦出现"电影台.png"就会顶掉它；
    # ② other 那张万一丢了，宽松匹配会误配到"靖天电影台/凤凰卫视电影台"。
    "电影台": ("other", "电影台.png"),
    # Channel 13（泰国）：wanglindl 那张是已去白底的透明版(209x135)，
    # other 库原先用的是带白底的 392x227，白底图被判 white → 界面上灰化成一块灰块。
    # 这里锁别的库那张透明版，防止以后又被白底图盖回去。
    "Channel 13": ("other", "Channel 13.png"),
    # Channel One Europa：四个图库都没有，是自己画的(深蓝底白字 300x180)。
    # 锁住，免得将来图库更新时被近似的 "Channel One" / "CH1" 之类的图误配顶掉。
    "Channel One Europa": ("other", "Channel One Europa.png"),
}


def quality_label(mbps, res_h):
    """一句话画质结论(界面上的角标)：严格按用户的门槛判，不猜。"""
    try:
        rh = int(res_h or 0)
    except Exception:
        rh = 0
    try:
        mb = float(mbps or 0)
    except Exception:
        mb = 0.0
    if rh >= 1800 and mb >= CLARITY_MBPS:
        return "4K超清"
    if rh >= CLARITY_HEIGHT and mb >= CLARITY_MBPS:
        return "高清"
    if rh >= CLARITY_HEIGHT and mb > 0:
        return "低码率"
    if 620 <= rh < CLARITY_HEIGHT:
        return "720P"
    if 0 < rh < 620:
        return "低分辨率"
    if rh == 0 and mb >= CLARITY_MBPS:
        return "未测分辨率"
    return "未测"


def clear_enough(mbps, res_h):
    """是否达到用户说的"清晰"：分辨率 ≥1080P 且 码率 ≥2 Mbps。"""
    try:
        rh = int(res_h or 0)
    except Exception:
        rh = 0
    try:
        mb = float(mbps or 0)
    except Exception:
        mb = 0.0
    return rh >= CLARITY_HEIGHT and mb >= CLARITY_MBPS


def _src_quality(s, ch):
    """综合画质分(越高越好)：分辨率定档，码率决定这一档能拿到多少。
    - 分辨率档(4:≥4K 3:1080P 2:720P 1:480P) × 码率达标度(≥2M 满分) 为主项；
    - 再加一点码率余量分(最多 +5)，让同为 1080P 时高码率的排前面；
    - 没测到分辨率时按 720P 记(不虚高也不打死)，并留旧逻辑对"确实没数据"的少量源兜底。"""
    try:
        mb = float(s.get("mbps") or 0)
    except Exception:
        mb = 0.0
    rh = s.get("res") or 0
    rs = res_level(rh)
    if mb > 0:
        adequate = min(1.0, mb / CLARITY_MBPS)
        bonus = min(1.0, mb / 10.0) * 5.0
        base = rs if rs is not None else 2.0
        return round(base * 10 * (0.55 + 0.45 * adequate) + bonus, 2)
    # 一个数字都没测到(极少数)：只按标称做排序兜底，不当画质结论
    if rs is not None:
        return round(rs * 10 * 0.35, 2)
    u = (s.get("url") or "").lower()
    if re.search(r"4k|2160|uhd|8k", u):
        return 3.0
    if re.search(r"1080|1920|fhd|超高清|蓝光", u):
        return 2.0
    if re.search(r"720|\bhd\b|高清", u):
        return 1.5
    q = ch.get("quality")
    if q == "1080P":
        return 1.2
    if q == "HD":
        return 0.8
    return 0.5


# 上一轮每个频道在用的最佳地址；本轮只要它还活着就继续用，
# 免得同一频道每轮换个源、用户感觉"参差不齐"。
PREV_BEST = set()


def pick_best_source(ch):
    """程序权威筛选：在已验证可用的源中，按「画质(实测分辨率+码率双维度) > 人工精选 > 沿用上一轮 >
    位置基准 > 链接速度」选出唯一最佳源。返回被选中的源(dict)；无可用源返回 None。
    该最佳源即为写入 M3U 的唯一地址(不列备选)。"""
    live = [s for s in ch["sources"] if s.get("live") and s.get("url")]
    if not live:
        return None
    region = REGION_TAG.get(ch["group"], set())

    def score(s):
        q = _src_quality(s, ch)                       # 画面质量：实测分辨率与码率的短板决定上限
        cur = 1 if s.get("tag") == "curated" else 0   # 人工核对过的源，同档时优先用
        keep = 1 if s.get("url") in PREV_BEST else 0  # 上一轮就在用且现在仍然可用：同档时别换来换去
        loc = 1 if s["tag"] in region else 0          # 位置基准：源的区域标签是否对口
        ttfb = s.get("ttfb") or 9999                  # 链接速度：首包延迟(越低越好)
        mbps = s.get("mbps") or 0                     # 码率
        spd = max(0.0, (2000 - ttfb) / 500.0) + min(mbps, 40) * 0.5
        return (q, cur, keep, loc, spd)
    return max(live, key=score)


# ---------------------------------------------------------------- 台标解析

# 图标库模板({name} 为 URL 编码后的中文台名)；均为 2026-10 实测用户网络可达
LOGO_TPLS = [
    # 用户 2026-10-20 给的台标站：4 万枚图，按频道名直取，支持别名匹配，比下面几个 GitHub
    # 图库全得多(央视、卫视、地方台、港澳台都有)，放第一位，取不到再退回下面几个
    "https://v.999.team/logo.php?name={name}",
    # 同样的图站在国内快一些(jsDelivr)，raw 兜底
    "https://cdn.jsdelivr.net/gh/CCSH/IPTV@main/logo/{name}.png",
    "https://cdn.jsdelivr.net/gh/fanmingming/live@main/tv/{name}.png",
    "https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/logo/{name}.png",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/{name}.png",
]
LOGO_TTL = 7 * 86400          # 台标实测结果缓存 7 天

# ---- 台标来源白名单(2026-10-20 用户要求：所有台标来源必须统一) ----
# 只允许这两个 GitHub 图库。混用别的图库时同一批频道会出现"白底/彩底/黑底"
# 三种风格混在一起，列表里看着很乱；央视那几个台尤其明显(CCTV2 之前就是
# 从 CCSH 拿的图，跟旁边的 cachemiao 完全不是一套)。
# 因此这里做一道硬闸：不管台标是从哪条路进来的(抓源自带的 tvg-logo、自动解析、
# 读缓存)，只要不是这两个库，一律丢弃留空——宁可没图标，也不要风格打架。
LOGO_OK_HOSTS = ("cachemiao/m3u-logos", "wanglindl/TVlogo",
                 # 两个主库都没有的冷门台(黄金翡翠/电影台这类)，从别的中文图库单独补的几张，
                 # 同样随包发行 logos_lib/other/，取图还是走本机
                 "CCSH/IPTV@main/logo", "fanmingming/live@main/tv")

def _filter_logo(u):
    """台标来源闸口：白名单内的原样返回，其它一律清空返回 ""。"""
    u = (u or "").strip()
    if not u:
        return ""
    return u if any(h in u for h in LOGO_OK_HOSTS) else ""
_LOGO_CACHE = {}              # url -> [unix_ts, ok]
_LOGO_KIND = {}               # url -> white/dark/color（台标配色，决定要不要垫深色底）
_LOGO_HASH = {}               # url -> 8×8 分桶指纹（发现"两个台用了同一张图"的错配）
_LOGO_FP = {}                 # url -> 16×16 灰度细指纹（同一桶内再精确比对）
_LOGO_BYTES = {}              # url -> (content_type, bytes)  台标本地中转缓存(最多 600 张)
_LOGO_BYTES_MAX = 600
LOGO_DIR = BASE / "logos"      # 台标图片本地留档：程序重启后 /logo 也不用再出网

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

def _png_pixels(data, ncol=32):
    """极简 PNG 解码：只认 8 位的灰/RGB/调色板/RGBA(台标库实际就这几种)，
    产出 (宽, 高, [(r,g,b,a), ...] 采样后的像素)。解不动返回 None。
    用来判断台标是不是"透明底白图"——那种图放在浅色界面上等于看不见。"""
    import zlib
    if not data.startswith(b"\x89PNG"):
        return None
    i = 8
    w = h = bitd = ctype = inter = 0
    idat = bytearray()
    plte = b""
    trns = b""
    while i + 8 <= len(data):
        ln = int.from_bytes(data[i:i + 4], "big")
        typ = data[i + 4:i + 8]
        body = data[i + 8:i + 8 + ln]
        if typ == b"IHDR":
            w, h = int.from_bytes(body[0:4], "big"), int.from_bytes(body[4:8], "big")
            bitd, ctype = body[8], body[9]
            inter = body[12]
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body              # 调色板透明表：央视那批"白字透明底"就靠它
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        i += 12 + ln
    if not w or not h or inter != 0:
        return None
    if ctype == 3:
        if bitd not in (1, 2, 4, 8):
            return None
        ch = 1
        stride = (w * bitd + 7) // 8
    elif ctype in (0, 2, 4, 6) and bitd in (8, 16):
        ch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
        stride = w * ch * (2 if bitd == 16 else 1)
    else:
        return None
    try:
        raw = zlib.decompress(bytes(idat))
    except Exception:
        return None
    bs = 2 if bitd == 16 else 1          # 16 位图只取高字节
    bpp = max(1, ch * bs)                # PNG 滤波按字节/像素算
    prev = bytearray(stride)
    out = []
    step = max(1, w // ncol)
    p = 0
    for y in range(h):
        if p >= len(raw):
            break
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        if len(line) < stride:
            break
        p += stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 0xFF
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif f == 3:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 0xFF
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b2 = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                pp = a + b2 - c
                pa, pb, pc = abs(pp - a), abs(pp - b2), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b2 if pb <= pc else c)
                line[x] = (line[x] + pr) & 0xFF
        for x in range(0, w, step):
            o = x * ch * bs if ctype != 3 else 0
            if ctype == 0:
                g = line[x * bs]
                px = (g, g, g, 255)
            elif ctype == 4:
                g, a = line[x * 2 * bs], line[x * 2 * bs + bs]
                px = (g, g, g, a)
            elif ctype == 2:
                px = (line[x * 3 * bs], line[x * 3 * bs + bs], line[x * 3 * bs + 2 * bs], 255)
            elif ctype == 6:
                px = (line[x * 4 * bs], line[x * 4 * bs + bs],
                      line[x * 4 * bs + 2 * bs], line[x * 4 * bs + 3 * bs])
            else:                                    # 调色板 ctype=3
                if bitd == 8:
                    idx = line[x]
                else:
                    bitpos = x * bitd
                    idx = (line[bitpos >> 3] >> (8 - bitd - (bitpos & 7))) & ((1 << bitd) - 1)
                a = trns[idx] if idx < len(trns) else 255
                o2 = idx * 3
                if o2 + 2 < len(plte):
                    px = (plte[o2], plte[o2 + 1], plte[o2 + 2], a)
                else:
                    px = (0, 0, 0, 0)
            out.append(px)
        prev = line
    return w, h, out


# 台标配色强制覆盖：自动检测容易误判的少数台标，按 URL 关键字强制指定
_LOGO_KIND_OVERRIDE = {
    "Phoenix3.png": "color",             # 凤凰香港台：橙色凤凰+白字
    "%E9%BB%84%E9%87%91%E7%BF%A1%E7%BF%A0": "color",  # 黄金翡翠：myTV SUPER 白字台标
    "%E4%BA%9A%E6%B4%B2%E5%89%A7": "color",           # 亚洲剧：Asia Digital Media 彩标
}

# 频道名强制覆盖：上游数据源的频道名跟台标/实际称呼不一致时，在此统一
_CHANNEL_NAME_OVERRIDE = {
    "凤凰香港台": "香港台",
}

# 台标 URL 强制覆盖：M3U 源自带的 tvg-logo 指向的台标不对时，在此强制指定正确的台标 URL
# 键是频道 key（如"凤凰香港"），值是完整的台标 URL
_LOGO_URL_OVERRIDE = {
    "凤凰香港": "https://raw.githubusercontent.com/wanglindl/TVlogo/master/img/Phoenix3.png",
    "香港台": "https://raw.githubusercontent.com/wanglindl/TVlogo/master/img/Phoenix3.png",
}

def logo_hash(data):
    """粗指纹(8×8 灰度 aHash)：用来发现"两个不同频道用了同一张图"的错配。
    上游图库确实有这种错误 —— 2026-10-21 用户报「黄金翡翠和亚洲剧台标一致」，
    实测 CCSH 库里这两个名字是同一张 myTV SUPER 的图(字节不同、画面一模一样)。
    8×8 只能用来分桶(央视那套"CCTV x"长得都像，光靠它会互相误伤)，细比看 logo_fp。
    解不出(JPEG 等)返回 ""，这类跳过比对。"""
    try:
        got = _png_pixels(data, ncol=64)
    except Exception:
        return ""
    return _hash_from_px(got) if got else ""


def _gray_grid(got, nw, nh, bg=128):
    """把解码后的像素采成 n×n 的灰度网格，返回 (总宽, 网格)。

    透明部分按**中灰(128)**合成，不按白底：台标大半是"透明底白字"，按白底合成后
    整张图只剩一片 255，两张不同的白字台标指纹就一模一样了(实测会把"江苏苏州文化生活"
    和"法治天地"判成同一张，然后被去重逻辑误杀)。中灰底让白字有对比度，彩色台标不受影响。"""
    w, _h, out = got
    if not out or not w:
        return 0, []
    step = max(1, w // 64)
    cols = len(range(0, w, step))
    if cols <= 0:
        return 0, []
    rows = len(out) // cols
    if rows <= 0:
        return 0, []
    grid = []
    for gy in range(nh):
        y = min(rows - 1, gy * rows // nh)
        for gx in range(nw):
            x = min(cols - 1, gx * cols // nw)
            r, g, b, a = out[y * cols + x]
            bgc = bg * (255 - a)
            grid.append(((r * a + bgc) // 255 * 299 // 1000
                         + (g * a + bgc) // 255 * 587 // 1000
                         + (b * a + bgc) // 255 * 114 // 1000))
    return w, grid


def _hash_from_px(got):
    """8×8 aHash：把灰度网格按中位数二值化成 64 位，用于分桶。"""
    _w, gray = _gray_grid(got, 8, 8)
    if not gray:
        return ""
    avg = sum(gray) // len(gray)
    bits = 0
    for v in gray:
        bits = (bits << 1) | (1 if v > avg else 0)
    return "%016x" % bits


def logo_fp(data):
    """细指纹(32×16 灰度值)：判"两张图是不是同一张画面"。解不出返回 ()。
    采样密度必须够 —— 央视那套 CCTV1/2/3 只有小号数字不同，用 8×8/16×16 会全部判成同一张。"""
    try:
        got = _png_pixels(data, ncol=64)
    except Exception:
        return ()
    if not got:
        return ()
    _w, grid = _gray_grid(got, 32, 16)
    return tuple(grid)


def _same_art(a, b):
    """两枚指纹是不是同一张画面。阈值定得很紧，因为要的是"同一张图"而不是"长得像"：
    实测(304 张随包台标)−−
      同一张图(黄金翡翠 / 亚洲剧，上游把一张图挂了两个名字)：max=0   mean=0.00
      不同频道(CCTV1 / CCTV2 只有小号数字不同)：          max=36  mean=1.12
      CCTV1 / CCTV6：                                    max=40  mean=1.37
    所以只有 max≤8 且平均差≤1.5 才算同一张：漏判只是不拦(不影响显示)，
    误判会白掉正确台标，宁可漏不可错。"""
    if not a or not b or len(a) != len(b):
        return False
    total = 0
    for x, y in zip(a, b):
        d = x - y if x > y else y - x
        if d > 8:
            return False
        total += d
    return total / len(a) <= 1.5


def _name_related(a, b):
    """两个频道名是不是"同一类"(同台不同写法、同城兄弟台)。基于名字相似度判断。
    实测随包台标里被判"同一张图"的 9 组，除 黄金翡翠/亚洲剧 之外全都是同城兄弟台
    (江苏苏州文化生活/生活资讯、浙江新闻/浙江公共新闻…)，它们的图本来就该一样，
    所以相似度够高的直接放过，只拦"名字毫不相干、图却一模一样"的错配。"""
    import difflib
    na = a.replace(" ", "")
    nb = b.replace(" ", "")
    if not na or not nb:
        return True
    if na in nb or nb in na:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= 0.3


def logo_props(data, url=""):
    """一次解码同时拿到 (配色, 分桶指纹, 细指纹)：每张图只解一遍。"""
    kind = ""
    if url:
        for _kw, _v in _LOGO_KIND_OVERRIDE.items():
            if _kw in url:
                kind = _v
                break
    try:
        got = _png_pixels(data)
    except Exception:
        got = None
    if not got:
        return kind, "", ()
    return ((kind or _kind_from_px(got)), _hash_from_px(got),
            tuple(_gray_grid(got, 32, 16)[1]))


def logo_kind(data, url=""):
    """台标配色归类：white=透明底白图(浅色界面上看不见，得垫深色)、
    dark=深色图形、color=彩图、""=判不出来(PNG 解不动/JPEG 等)。"""
    if url:
        for _kw, _v in _LOGO_KIND_OVERRIDE.items():
            if _kw in url:
                return _v
    got = _png_pixels(data)
    if not got:
        return ""
    return _kind_from_px(got)


def _kind_from_px(got):
    if not got:
        return ""
    _w, _h, px = got
    tot = white = dark = colored = 0
    for r, g, b, a in px:
        if a < 64:
            continue
        tot += 1
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum >= 205:
            white += 1
        elif lum <= 70:
            dark += 1
        # 明显彩色：通道差大(非灰阶)。官方台标常见"白底/白字+彩色图形"(翡翠台、山西卫视)，
        # 只看亮度会把它们整张判成 white 然后被前端灰化，彩色就没了——
        # 所以只要有足量彩色像素，一律按彩图对待
        if max(r, g, b) - min(r, g, b) >= 45:
            colored += 1
    if not tot:
        return "white"          # 全透明：按白图处理
    # 阈值取 8%：纯白单色标(CCTV)彩色是 0 不误判；"白字+少量彩色点缀"的标
    # (如亚洲剧 NYJTV 白字+小彩条 colored 5.8%)按白图处理垫深色底，浅色界面才看得清；
    # 而彩色确是主体的官方标(翡翠台三色球 21.7%、山西卫视 17.6%)都在 8% 以上，保留彩色
    if colored / tot >= 0.08:
        return "color"
    if white / tot >= 0.45:
        return "white"
    if dark / tot >= 0.45:
        return "dark"
    return "color"


def _enc_url(u):
    """把 URL 里的非 ASCII 字符(中文台名等)做百分号编码后才能真正发出请求。

    urllib 碰到路径里带中文会直接 UnicodeEncodeError('ascii', ...)，请求根本发不出去，
    表现就是"这一批台标一个都加载不出来"。已编码的 %XX 保持不变，避免二次编码成 %25XX。
    """
    try:
        u.encode("ascii")
        return u                      # 纯 ASCII，原样返回
    except (UnicodeEncodeError, AttributeError):
        pass
    return quote(u, safe=":/?#[]@!$&'()*+,;=%~-._")


def _check_logo(url, timeout=2):
    """HTTP 200 且响应头几个字节为 PNG/JPEG 魔数才认定为可用台标(防 JSON/HTML 冒充)。
    顺手把图片字节留在内存里，页面走 /logo 直接用，不用第二次出网。
    白名单两库的 URL 先查离线整库：本地有图直接判定可用，不出网(国内拉 GitHub 基本超时)。"""
    try:
        p0 = _logo_lib_path_for_url(url)
        if p0 is not None and p0.exists() and p0.stat().st_size > 200:
            body = p0.read_bytes()
            if len(_LOGO_BYTES) > _LOGO_BYTES_MAX:
                _LOGO_BYTES.clear()
            _LOGO_BYTES[url] = ("image/png", body)
            _k, _hs, _fp = logo_props(body, url)
            if _k:
                _LOGO_KIND[url] = _k
            if _hs:
                _LOGO_HASH[url] = _hs
            if _fp:
                _LOGO_FP[url] = _fp
            try:
                LOGO_DIR.mkdir(parents=True, exist_ok=True)
                (LOGO_DIR / _logo_file(url)).write_bytes(body)
            except OSError:
                pass
            return True
        with urllib.request.urlopen(urllib.request.Request(_enc_url(url), headers=UA),
                                    timeout=timeout, context=_SSL_CTX) as r:
            ctype = r.headers.get("Content-Type") or "image/png"
            body = r.read(400 * 1024)
        if not (body.startswith(b"\x89PNG") or body.startswith(b"\xff\xd8\xff")
                or body.startswith(b"GIF8") or body[:4] == b"RIFF"):
            return False
        if len(_LOGO_BYTES) > _LOGO_BYTES_MAX:
            _LOGO_BYTES.clear()
        _LOGO_BYTES[url] = (ctype, body)
        _k, _hs, _fp = logo_props(body, url)
        if _k:
            _LOGO_KIND[url] = _k
        if _hs:
            _LOGO_HASH[url] = _hs
        if _fp:
            _LOGO_FP[url] = _fp
        try:
            LOGO_DIR.mkdir(parents=True, exist_ok=True)
            (LOGO_DIR / _logo_file(url)).write_bytes(body)
        except OSError:
            pass
        return True
    except Exception:
        return False

def _logo_file(url):
    import hashlib
    return hashlib.sha1(url.encode("utf-8")).hexdigest() + ".img"


def _logo_from_disk(url):
    """磁盘缓存里直接读（有就直接用，不用管图标站现在还能不能访问）。
    白名单两库的 URL 还可以退到离线整库 logos_lib/ 里按原始路径找——
    也就是台标展示永远有本机兜底，GitHub 抽风也不影响画面。"""
    for p in (LOGO_DIR / _logo_file(url), _logo_lib_path_for_url(url)):
        if p is None:
            continue
        try:
            if not (p.exists() and p.stat().st_size > 200):
                continue
            body = p.read_bytes()
            if body.startswith(b"\x89PNG"):
                return ("image/png", body)
            if body.startswith(b"\xff\xd8\xff"):
                return ("image/jpeg", body)
            if body.startswith(b"GIF8"):
                return ("image/gif", body)
            if body[:4] == b"RIFF":
                return ("image/webp", body)
        except OSError:
            continue
    return None


def _logo_lib_path_for_url(url):
    """从白名单 URL 解析出离线整库里的文件路径；不是两库的 URL 返回 None。"""
    from urllib.parse import unquote as _uq   # 提到最外层：URL 不匹配任何 host 时
    try:                                      # 下面 other 兜底还要用它，放循环里会 NameError
        u = (url or "").split("#")[0]
        for host in ("cachemiao/m3u-logos", "wanglindl/TVlogo", "fanmingming/live"):
            i = u.find(host)
            if i < 0:
                continue
            rest = u[i + len(host):].lstrip("/")          # main/tv/xxx.png 或 img/xxx.png
            rest = re.sub(r"^[^/]+/", "", rest, count=1)  # 去掉 branch 段(main/master/@main)
            rel = _uq(rest)
            if rel.lower().endswith(".png") and "/" in rel:
                return _lib_root() / host.split("/")[0] / rel.replace("/", os.sep)
    except Exception:
        pass
    # 补充图库(other)：文件名就是频道名，本地有这张图就算这台有了
    try:
        bn = _uq(url.rstrip("/").rsplit("/", 1)[-1])
        if bn.lower().endswith(".png"):
            p = _lib_root() / "other" / bn
            if p.exists() and p.stat().st_size > 200:
                return p
    except Exception:
        pass
    return None


_LOGO_VER_CACHE = {}


def _logo_version(url):
    """台标内容指纹(8位md5)。把它作为版本号拼进 /logo 的 URL：图一变指纹就变，
    浏览器按 URL 缓存，必然重新拉取，根治『改了图却因长缓存(7天)显示旧图』。"""
    import hashlib
    v = _LOGO_VER_CACHE.get(url)
    if v:
        return v
    try:
        p = _logo_lib_path_for_url(url)
        if p is not None and p.exists() and p.stat().st_size > 200:
            v = hashlib.md5(p.read_bytes()).hexdigest()[:8]
    except Exception:
        v = None
    if not v:
        try:
            data = _LOGO_BYTES.get(url) or _logo_from_disk(url)
            if data:
                v = hashlib.md5(data[1]).hexdigest()[:8]
        except Exception:
            v = None
    if not v:
        v = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    _LOGO_VER_CACHE[url] = v
    return v


def _lib_root():
    """离线台标库根目录。打包后优先读 exe 内置的那份(sys._MEIPASS)，
    其次才是数据目录下的 logos_lib(用户自己补的图也算)。"""
    root = None
    try:
        import sys
        if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
            root = Path(sys._MEIPASS) / "logos_lib"
    except Exception:
        pass
    base = LOGO_DIR.parent / "logos_lib"
    return root if (root and root.is_dir()) else base


def _lib_file(rel_lib, rel_path):
    """本地图库文件全路径。整库已随包发行(pyinstaller 解压到 sys._MEIPASS)。"""
    p = _lib_root() / rel_lib / rel_path
    return p if p.exists() and p.stat().st_size > 200 else None


def _alias_url(al):
    """别名表条目 -> 对应的白名单 URL。支持 cachemiao / other(CCSH) / wanglindl 三个库。"""
    lib, rel = al[0], al[1]
    if lib == "cachemiao":
        return "https://raw.githubusercontent.com/cachemiao/m3u-logos/main/%s" % rel
    if lib == "other":
        return "https://cdn.jsdelivr.net/gh/CCSH/IPTV@main/logo/%s" % quote(rel)
    return "https://raw.githubusercontent.com/wanglindl/TVlogo/main/%s" % rel


_LIB_STEMS_CACHE = {}


def _lib_stems(rel_lib, sub):
    """图库子目录里所有 png 的文件名(去掉扩展名)，带缓存，供宽松匹配使用。"""
    key = (rel_lib, sub)
    if key in _LIB_STEMS_CACHE:
        return _LIB_STEMS_CACHE[key]
    stems = set()
    try:
        d = _lib_root() / rel_lib / sub
        if d.is_dir():
            for f in d.iterdir():
                if f.name.lower().endswith(".png"):
                    stems.add(f.name[:-4])
    except Exception:
        pass
    _LIB_STEMS_CACHE[key] = stems
    return stems


# 太通用的频道名不做宽松匹配，否则"新闻综合"会被配到某个省的新闻综合台
_FUZZY_BLOCK = {"新闻综合", "综合频道", "新闻", "公共", "生活", "影视", "经济", "科教",
                "文体", "都市", "娱乐", "电影", "电影台", "电视剧", "少儿", "卡通",
                "导视", "综合", "电视台", "新闻频道", "卫视"}


def _lib_fuzzy(rel_lib, sub, cands, url_tpl):
    """精确匹配失败后的兜底：图库文件名以频道名开头或结尾，或包含频道名。
    例如"余姚新闻综合"能命中"浙江余姚新闻综合"。取长度最接近的候选，减少误配。"""
    stems = _lib_stems(rel_lib, sub)
    if not stems:
        return ""
    cores = set()
    for v in cands:
        if not v or v in _FUZZY_BLOCK or len(v) < 3:
            continue
        cores.add(v)
    if not cores:
        return ""
    best, best_d = None, 10 ** 9
    for stem in stems:
        for core in cores:
            if not (stem.endswith(core) or stem.startswith(core)
                    or (len(core) >= 4 and core in stem)):
                continue
            d = abs(len(stem) - len(core))
            if d < best_d:
                best_d, best = d, stem
    return url_tpl % quote(best) if best else ""


# 简体 -> 繁体（只收频道名里真会用到的字）。港台频道在图库、台标站里大多只有繁体名：
# "亚洲剧"在简体名下拿到的是 myTV SUPER 的通用标，改成"亞洲劇台"才是这一台自己的标。
_TRAD_S2T = {
    "亚": "亞", "剧": "劇", "黄": "黃", "卫": "衛", "视": "視", "东": "東", "凤": "鳳",
    "龙": "龍", "广": "廣", "贵": "貴", "济": "濟", "庆": "慶", "云": "雲", "苏": "蘇",
    "华": "華", "辽": "遼", "宁": "寧", "陕": "陝", "晋": "晉", "内": "內", "粤": "粵",
    "赣": "贛", "闽": "閩", "鲁": "魯", "沪": "滬", "琼": "瓊", "湾": "灣", "财": "財",
    "经": "經", "纪": "紀", "录": "錄", "农": "農", "业": "業", "军": "軍", "综": "綜",
    "艺": "藝", "戏": "戲", "儿": "兒", "动": "動", "画": "畫", "闻": "聞", "乐": "樂",
    "体": "體", "务": "務", "车": "車", "产": "產", "装": "裝", "游": "遊", "钓": "釣",
    "鱼": "魚", "宠": "寵", "养": "養", "资": "資", "讯": "訊", "线": "線", "网": "網",
    "员": "員", "术": "術", "铁": "鐵", "银": "銀", "铜": "銅", "阳": "陽", "阴": "陰",
    "门": "門", "问": "問", "长": "長", "张": "張", "马": "馬", "鸟": "鳥", "飞": "飛",
    "轮": "輪", "红": "紅", "绿": "綠", "蓝": "藍", "镇": "鎮", "乡": "鄉", "县": "縣",
    "区": "區", "园": "園", "书": "書", "学": "學", "汉": "漢", "语": "語", "说": "說",
    "读": "讀", "讲": "講", "带": "帶", "时": "時", "间": "間", "钟": "鐘", "点": "點",
    "号": "號", "毕": "畢", "兴": "興", "举": "舉", "办": "辦", "际": "際", "陆": "陸",
    "岛": "島", "峡": "峽", "湾": "灣", "视": "視", "众": "眾", "亿": "億", "价": "價",
    "传": "傳", "侨": "僑", "俩": "倆", "仓": "倉", "伞": "傘", "伦": "倫", "伟": "偉",
}


def _trad(s):
    """简体名 -> 繁体名（没有对应字的原样保留）。"""
    if not s:
        return s
    return "".join(_TRAD_S2T.get(c, c) for c in s)


def _logo_cands(name):
    """频道名 -> 图库里可能用的文件名候选。返回 (cands, n, n2, n3, n4)。
    央视官方名(CCTV-1 综合)在图库里是 CCTV1.png 这一套；带 HD/台/频道的写法也要试。"""
    n = (name or "").strip()
    cands = [n]
    # 央视官方名 -> 图库文件名。台里改名叫"CCTV-1 综合"了，图库里还是 CCTV1.png 这一套
    mc = re.match(r"^cctv[-\s]?(\d{1,2})\s*(\+)?\s*([k])?\s*(.*)$", n, re.I)
    if mc:
        num, plus, k = mc.group(1), mc.group(2) or "", (mc.group(3) or "").upper()
        cands.append("CCTV%s%s%s" % (num, plus, k))
        cands.append("CCTV-%s%s%s" % (num, plus, k))
    # 图库里带前缀/后缀的写法：兵器科技 -> CCTV兵器科技；内蒙古少儿 -> 内蒙古少儿频道
    for b in list(cands):
        for suf in ("频道", "台", "卫视"):
            if not b.endswith(suf):
                cands.append(b + suf)
        for pre in ("CCTV",):
            cands.append(pre + b)
    n2 = re.sub(r"\s*[hH][dD4kK8kK]*\s*$", "", n).strip()
    n3 = re.sub(r"(电视台|频道|台)$", "", n).strip()
    n4 = n.replace(" ", "").replace("-", "")
    for v in (n2, n3, n4):
        if v and v not in cands:
            cands.append(v)
    # 繁体写法再补一轮：港台频道在台标站/图库里基本只收繁体名（亚洲剧 -> 亞洲劇台）
    for b in list(cands):
        t = _trad(b)
        if t != b and t not in cands:
            cands.append(t)
    return cands, n, n2, n3, n4


def _resolve_logo_local(name):
    """在离线图库里按频道名找台标：命中本地文件 = 100% 可用，零出网。
    返回白名单 URL 或空串。顺序：别名表 -> 原名 -> 常见变体 -> 宽松兜底。"""
    if not name:
        return ""
    lib = "cachemiao"          # 离线图库目录名
    host = "cachemiao/m3u-logos"
    cands, n, n2, n3, n4 = _logo_cands(name)
    # 别名表也参与变体匹配(原名带 HD/后缀时精确查会 miss，如"凤凰香港 HD"->凤凰香港)
    for v in cands:
        al = LOGO_ALIASES.get(v)
        if al and _lib_file(al[0], al[1]):
            return _alias_url(al)
    seen = set()
    for v in cands:
        if not v or v in seen:
            continue
        seen.add(v)
        for qn in (v, v.upper(), v.lower()):
            p = _lib_file(lib, "tv/%s.png" % qn)
            if p:
                return "https://raw.githubusercontent.com/%s/main/tv/%s.png" % (host, quote(qn))
    # 冷门台：别的中文图库单独补的几张，放 logos_lib/other/<频道名>.png
    for v in [n] + cands[:1]:
        for qn in (v, n2, n3, n4):
            if not qn:
                continue
            p = _lib_file("other", "%s.png" % qn)
            if p:
                return "https://cdn.jsdelivr.net/gh/CCSH/IPTV@main/logo/%s.png" % quote(qn)
    # 另一个图库(英文命名)再试一遍
    for v in cands:
        for qn in (v, v.upper(), v.lower()):
            p = _lib_file("wanglindl", "img/%s.png" % qn)
            if p:
                return "https://raw.githubusercontent.com/wanglindl/TVlogo/main/img/%s.png" % quote(qn)
    # fanmingming/live 图库(933 张)：港澳台和台湾频道(民视/TVBS/中天)最全，
    # 放最后兜底——前两个库都命中不了的大多是这类台
    for v in cands:
        for qn in (v, v.upper(), v.lower()):
            p = _lib_file("fanmingming", "tv/%s.png" % qn)
            if p:
                return "https://cdn.jsdelivr.net/gh/fanmingming/live@main/tv/%s.png" % quote(qn)
    # 宽松兜底：图库文件名常带省/市前缀(如"浙江余姚新闻综合")，而频道名只有后半段。
    # 精确匹配配不上时用前缀/后缀/包含再找一次，能补回几十个地方台台标
    u = _lib_fuzzy("cachemiao", "tv", cands,
                   "https://raw.githubusercontent.com/cachemiao/m3u-logos/main/tv/%s.png")
    if u:
        return u
    u = _lib_fuzzy("fanmingming", "tv", cands,
                   "https://cdn.jsdelivr.net/gh/fanmingming/live@main/tv/%s.png")
    if u:
        return u
    return ""


# 本地图库里没有的台标，按名字去这三个白名单库再要一次（实测 200 + 图片魔数才用）。
# 用户 2026-10-21 报「云南卫视台标不显示」的根因就是：离线库是某次同步的快照，
# 新出现的频道本地没文件，而当时没有"按名字上网要一次"的兜底，于是一直空着。
# 命中后 _check_logo 会把图存进 LOGO_DIR，下次直接走本地，不用再出网。
LOGO_NET_TPLS = (
    # 用户 2026-10-21 给的台标站（4 万枚，带别名匹配：给"亞洲劇台"能直接对上"亚洲剧"）
    "https://v.999.team/logo.php?name={n}",
    "https://cdn.jsdelivr.net/gh/cachemiao/m3u-logos@main/tv/{n}.png",
    "https://cdn.jsdelivr.net/gh/CCSH/IPTV@main/logo/{n}.png",
    "https://cdn.jsdelivr.net/gh/fanmingming/live@main/tv/{n}.png",
    "https://raw.githubusercontent.com/cachemiao/m3u-logos/main/tv/{n}.png",
    "https://raw.githubusercontent.com/wanglindl/TVlogo/main/img/{n}.png",
)
_LOGO_MISS = {}               # 频道名 -> 第一次全库都没找到的时间(6 小时内不再重复找)
LOGO_MISS_TTL = 6 * 3600
# 一轮更新里最多出网试这么多次：实测不设上限时，缺图的 100 多个台会把台标这一步
# 从 2 秒拖到 260 秒(整轮 167s -> 388s)。缺的图每轮补一点，几轮之后就都进本地库了。
_LOGO_NET_BUDGET = [0]
LOGO_NET_MAX = 90


def _resolve_logo_net(name):
    """离线库没有时，按名字去白名单图库要一次。返回可用的白名单 URL 或 ""。
    结果走 _LOGO_CACHE(7 天)，失败记 _LOGO_MISS(6 小时)，避免每轮对着同几个台反复出网。"""
    if not name:
        return ""
    miss = _LOGO_MISS.get(name)
    if miss and time.time() - miss < LOGO_MISS_TTL:
        return ""
    cands, _n, n2, n3, n4 = _logo_cands(name)
    # 只试最像的几个写法 + 前三个模板(台标站 + 两个 jsDelivr，国内都可达)，别把整张表跑一遍。
    # 繁体写法必须带上：港台频道在台标站里只认繁体名。
    probe = []
    for v in cands[:3] + [_trad(name), _trad(name) + "台"]:
        if v and v not in probe:
            probe.append(v)
    probe = probe[:5]
    for v in probe:
        for tpl in LOGO_NET_TPLS[:3]:
            if _LOGO_NET_BUDGET[0] >= LOGO_NET_MAX:
                return ""
            u = tpl.format(n=quote(v))
            ent = _LOGO_CACHE.get(u)
            if ent:
                if time.time() - ent[0] < LOGO_TTL:
                    if ent[1]:
                        return u
                    continue
            _LOGO_NET_BUDGET[0] += 1
            ok = _check_logo(u, timeout=1.2)
            _LOGO_CACHE[u] = [time.time(), ok]
            if ok:
                return u
    _LOGO_MISS[name] = time.time()
    return ""


def _logo_alt(name, avoid_fps):
    """给"跟别的台共用同一张画面"的频道另找一张图：按繁体/别名写法逐个试台标站。
    avoid_fps 里已有的画面一律不收。找到返回 (url, kind)，找不到返回 ("", "")。
    用户 2026-10-21 报「黄金翡翠和亚洲剧台标一致」：简体的"亚洲剧"在库里就是通用
    myTV SUPER 标，繁体"亞洲劇台"才是这一台自己的标。"""
    if not name:
        return "", ""
    cands, _n, _n2, _n3, _n4 = _logo_cands(name)
    probe = []
    for v in [_trad(name), _trad(name) + "台", _trad(name) + "頻道"] + cands[:2]:
        if v and v not in probe:
            probe.append(v)
    for v in probe[:5]:
        for tpl in LOGO_NET_TPLS[:2]:
            if _LOGO_NET_BUDGET[0] >= LOGO_NET_MAX:
                return "", ""
            u = tpl.format(n=quote(v))
            got = _logo_from_disk(u)
            if got is None:
                _LOGO_NET_BUDGET[0] += 1
                if not _check_logo(u, timeout=1.5):
                    continue
                got = _logo_from_disk(u)
            if got is None:
                continue
            kind, hsum, fp = logo_props(got[1], u)
            if not fp or not hsum:
                continue
            if any(_same_art(fp, x) for x in avoid_fps):
                continue
            _LOGO_KIND[u] = kind or ""
            _LOGO_HASH[u] = hsum
            _LOGO_FP[u] = fp
            return u, kind or ""
    return "", ""


def resolve_logo(name, src_logo):
    """台标候选链：离线图库(名字直查，零出网) -> 图库别名 -> 源自带的白名单图。
    全部只出白名单两库，结果必须可验证(本地文件在/网络实测 200)才采用。"""
    # 图库别名：图库文件名跟频道名对不上的(写法差异)，点名直查
    al = LOGO_ALIASES.get((name or "").strip())
    if al:
        u = _alias_url(al)
        rel = al[1]
        if _lib_file(al[0], rel):
            return u
        ent = _LOGO_CACHE.get(u)
        if ent and time.time() - ent[0] < LOGO_TTL:
            if ent[1]:
                return u
        else:
            ok = _check_logo(u)
            _LOGO_CACHE[u] = [time.time(), ok]
            if ok:
                return u
    # 1) 离线图库直查(优先，秒回且永不出错)
    u = _resolve_logo_local(name)
    if u:
        return u
    # 1.5) 离线库没有这个台：按名字去白名单图库要一次，命中就存盘，下次走本地
    u = _resolve_logo_net(name)
    if u:
        return u
    # 2) 源自带的台标：只接受白名单两库，且必须能从本地磁盘或网络验证
    if src_logo and _filter_logo(src_logo):
        if _logo_from_disk(src_logo):
            return src_logo
        ent0 = _LOGO_CACHE.get(src_logo)
        if ent0 and not ent0[1] and (time.time() - ent0[0]) < LOGO_TTL:
            pass  # 已知彻底失效
        else:
            return src_logo
    return ""


# 判定为「网页/中转页」的地址记下来，短期内不再重复探测(也避免重复触发杀软)
BLOCK_HOSTS = {"live.iill.top", "www.iill.top", "zby.lskk.top", "lskk.top"}
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
            if key == "curated":
                # 内置精选源：不走网络，直接用内嵌的 M3U 文本
                es = [e for e in parse_m3u(CURATED_M3U, key) if keep_entry(e, cfg)]
                with lock:
                    per_source[key] = (name, region, es, "builtin", True)
                    self.state["source_stats"][key] = {
                        "name": name, "region": region, "ok": True, "count": len(es),
                        "ms": 0, "url": "builtin", "fallback": False,
                        "live_ratio": None, "sample": 0, "sample_ok": 0,
                    }
                log("源[%s] 内置 %d 条" % (name, len(es)))
                return
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

            def _grab(u):
                try:
                    with urllib.request.urlopen(urllib.request.Request(u, headers=UA),
                                                timeout=8, context=_SSL_CTX) as r:
                        t = r.read().decode("utf-8", "ignore")
                    return t if (t and "#EXTINF" in t) else None
                except Exception:
                    return None

            # 前三条候选并发抢，谁先回来用谁：原来是一条一条等，不通的地址每个白等 8 秒，
            # 一个源就能磨掉半分钟(用户反馈"更新太慢"主要就耗在这里和探测上)。
            if len(plan) > 1:
                got = {}
                _ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(plan)))
                try:
                    futs = {_ex.submit(_grab, u): i for i, u in enumerate(plan[:3])}
                    for f in concurrent.futures.as_completed(futs):
                        try:
                            r_ = f.result()
                        except Exception:
                            r_ = None
                        if r_:
                            got[futs[f]] = r_
                            if futs[f] == 0:
                                break      # 第一个候选就通了，剩下的不用等
                finally:
                    _ex.shutdown(wait=False)
                for i in sorted(got):
                    text, used = got[i], plan[i]
                    break
            for u in plan:
                if text:
                    break
                if len(plan) > 1 and u in plan[:3]:
                    continue           # 前三候选已经在上面抢过了
                r_ = _grab(u)
                if r_:
                    text, used = r_, u
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


        # 同域复用(参考 Guovin 的 speed_test_filter_host)：同一个 host:port 上
        # - 连着两个地址都不通、且一次都没成功 → 整站判死，后面同域的直接跳过
        # - 已经有一个地址成功过 → 后面的只做"能不能出画面"的快速确认(0.35s 窗口)
        host_fail, host_ok, host_speed = {}, set(), {}

        durs = []                      # 每个地址花了多久(排查"更新太慢"用)

        def work(u):
            _t = time.monotonic()
            recs = by_url[u]
            hp = hp_of(u)
            with lock:
                dead = host_fail.get(hp, 0) >= 2 and hp not in host_ok
                hint = host_speed.get(hp)
            if dead:
                for sl in recs:
                    sl["live"], sl["ttfb"], sl["note"] = False, 0, "同服务器整批不通，已跳过"
                with lock:
                    counter[0] += 1
                    self.state["done"] = counter[0]
                return
            ok, ttfb, note, mbps, res_h, speed = probe_stream(
                recs[0], timeout=2.5, budget=(0.35 if hint else 1.5),
                want_res=not recs[0].get("res"))
            if hint and (not speed or speed < hint):
                speed = hint
            with lock:
                if ok:
                    host_ok.add(hp)
                    host_speed[hp] = max(host_speed.get(hp, 0), speed or 0)
                elif note.startswith(("不可达", "连接被", "超时", "timed")):
                    host_fail[hp] = host_fail.get(hp, 0) + 1
            if not ok and note.startswith("返回网页"):
                mark_bad_url(u)
            # 能连上但吞吐低到 0.5 Mbps 以下，播起来必然卡：直接当不能用，别让它挤掉好线路
            if ok and speed and speed < 0.5:
                ok, note = False, "下载速度过慢(%.2f Mbps)" % speed
            for sl in recs:
                sl["live"], sl["ttfb"], sl["note"] = ok, ttfb, note
                if ok:
                    if mbps:
                        sl["mbps"] = mbps
                    if speed:
                        sl["speed"] = speed
                    if res_h:
                        sl["res"] = res_h
                    if recs[0].get("codec"):
                        sl["codec"] = recs[0]["codec"]
            with lock:
                counter[0] += 1
                self.state["done"] = counter[0]
                durs.append((time.monotonic() - _t, ok))

        # 一个线程池跑完：分批建池会让每批都重新起几百个线程，白白多花十几秒
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(work, todo))

        # 精选源(人工核对过的)第一次没连上，多半是慢启动，不是不能用：
        # 放宽到 8 秒再试一次(只在少数地址上，不影响整轮速度)
        slow = [u for u in todo
                if not by_url[u][0].get("live")
                and any(s.get("tag") == "curated" for s in by_url[u])]
        if slow:
            t1 = time.monotonic()
            def work2(u):
                recs = by_url[u]
                ok, ttfb, note, mbps, res_h, speed = probe_stream(
                    recs[0], timeout=8, budget=2.5, want_res=not recs[0].get("res"))
                if ok:
                    for sl in recs:
                        sl["live"], sl["ttfb"], sl["note"] = True, ttfb, ""
                        if mbps:
                            sl["mbps"] = mbps
                        if speed:
                            sl["speed"] = speed
                        if res_h:
                            sl["res"] = res_h
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(16, len(slow))) as ex:
                list(ex.map(work2, slow))
            log("精选源补测: %d 个地址，救回 %d 个(%.0fs)"
                % (len(slow), sum(1 for u in slow if by_url[u][0].get("live")), time.monotonic() - t1))

        # 上一轮还在用的地址这次没连上，多半是抖动：放宽到 8 秒补测一次，
        # 否则频道会一轮有一轮没有(用户看到的"参差不齐"主要就是这个)。
        retry = [u for u in todo
                 if not by_url[u][0].get("live") and u in PREV_BEST]
        if retry:
            t2 = time.monotonic()
            def work3(u):
                recs = by_url[u]
                ok, ttfb, note, mbps, res_h, speed = probe_stream(
                    recs[0], timeout=8, budget=2.0, want_res=not recs[0].get("res"))
                if ok:
                    for sl in recs:
                        sl["live"], sl["ttfb"], sl["note"] = True, ttfb, ""
                        if mbps:
                            sl["mbps"] = mbps
                        if speed:
                            sl["speed"] = speed
                        if res_h:
                            sl["res"] = res_h
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(64, len(retry))) as ex:
                list(ex.map(work3, retry))
            log("上轮在用的地址补测: %d 个，救回 %d 个(%.0fs)"
                % (len(retry), sum(1 for u in retry if by_url[u][0].get("live")), time.monotonic() - t2))

        n_ok = sum(1 for u in order if by_url[u][0]["live"])
        log("探测完成: %d 个地址里 %d 个能出画面(%.0fs；跳过 %d 个已知不通的、%d 个上次在用)"
            % (len(order), n_ok, time.monotonic() - t0, n_skip, len(prev & set(order))))
        if durs:
            _dt = sorted(d for d, _o in durs)
            _p = lambda q: _dt[min(len(_dt) - 1, int(len(_dt) * q))]   # noqa: E731
            _slow = sum(1 for d, _o in durs if d >= 2.5)
            log("  单地址耗时: 中位 %.1fs / 90%% %.1fs / 最慢 %.1fs；%d 个超过 2.5s(失败居多)"
                % (_p(0.5), _p(0.9), _dt[-1], _slow))
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
        _LOGO_NET_BUDGET[0] = 0         # 每轮给"上网补缺台标"一个额度，防止把整轮拖慢
        cnt = [0]

        def one(item):
            _, ch = item
            try:
                ch["logo"] = _filter_logo(resolve_logo(ch["name"], ch.get("logo", "")))
            except Exception:
                pass
            cnt[0] += 1
            self.state["done"] = cnt[0]

        t_logo0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            list(ex.map(one, todo))
        _save_logo_cache()
        # 台标配色：透明底白图在浅色界面上等于看不见，要把底垫深（缓存里没有就现解一遍）
        for _, ch in todo:
            u = ch.get("logo") or ""
            if not u:
                continue
            kind = _LOGO_KIND.get(u)
            if not kind:
                got = _logo_from_disk(u)
                if got is None:
                    # 磁盘里没有(台标是缓存命中直接返回的地址，当初没落过盘)：
                    # 现抓一次，顺手写盘 + 记 kind，下次就不再来这一趟
                    _check_logo(u)
                    kind = _LOGO_KIND.get(u)
                else:
                    kind, hsum, hfp = logo_props(got[1], u)
                    if kind:
                        _LOGO_KIND[u] = kind
                    if hsum:
                        _LOGO_HASH[u] = hsum
                    if hfp:
                        _LOGO_FP[u] = hfp
            ch["logo_kind"] = kind or ""
        # 错配拦截：上游图库会把别的台的图挂到这个名字上(实测 CCSH 库里"亚洲剧"和
        # "黄金翡翠"是同一张 myTV SUPER 的图，字节不同、画面一模一样)。两个不同频道
        # 用了同一张画面时，只留名字更完整的那个，另一个宁可不显示(界面会退回文字方块)，
        # 也不显示错的台标。先用 8×8 分桶，再在桶内用 16×16 细指纹确认是不是同一张。
        items = []
        for _k, ch in todo:
            u = ch.get("logo") or ""
            if not u:
                continue
            hsum, hfp = _LOGO_HASH.get(u), _LOGO_FP.get(u)
            if not hfp:
                got = _logo_from_disk(u)
                if got is not None:
                    _k2, hsum2, hfp2 = logo_props(got[1], u)
                    hsum = hsum or hsum2
                    if hsum2:
                        _LOGO_HASH[u] = hsum2
                    if hfp2:
                        _LOGO_FP[u] = hfp2
                        hfp = hfp2
            if hfp:
                items.append((ch, hsum, hfp))
        kept = {}
        n_dup = 0
        blanked = []
        for ch, hsum, hfp in sorted(items, key=lambda it: (-len(it[0]["name"]), it[0]["name"])):
            bucket = kept.setdefault(hsum, [])
            hit = None
            for ch_b, fp_b in bucket:
                if not _same_art(hfp, fp_b):
                    continue
                # 同一个台的不同写法(翡翠台 / 翡翠台HD、同城兄弟台)共用一张图是对的
                if _name_related(ch["name"], ch_b["name"]):
                    continue
                hit = ch_b
                break
            if hit is None:
                bucket.append((ch, hfp))
                continue
            # 先别急着清空：换成繁体/别名再找一次，能拿到"不是同一画面"的真台标就留着
            avoid = [fp_b for _x2, fp_b in bucket] + [hfp]
            u2, k2 = _logo_alt(ch["name"], avoid)
            if u2:
                ch["logo"], ch["logo_kind"] = u2, k2
                got2 = _logo_from_disk(u2)
                fp2 = _LOGO_FP.get(u2)
                if not fp2 and got2 is not None:
                    _k3, _h3, fp2 = logo_props(got2[1], u2)
                if fp2:
                    bucket.append((ch, fp2))
                    continue
            # 名字毫不相干却共用同一张画面 —— 这张图对这俩来说都是错的，
            # 两边都不显示(界面退回"黄"这种文字方块)，比显示别人的台标强。
            for _x in (ch, hit):
                if _x.get("logo"):
                    _x["logo"], _x["logo_kind"] = "", ""
                    blanked.append(_x["name"])
            if hit in bucket:
                bucket.remove(hit)
            n_dup = len(blanked)
        if blanked:
            log("台标去重: %s(同一张图挂了多个台，宁可不显示)" % "、".join(blanked[:6]))
        n_logo = sum(1 for _, ch in todo if ch["logo"])
        log("台标解析完成: %d/%d 频道有台标(%.0fs%s%s)"
            % (n_logo, len(todo), time.monotonic() - t_logo0,
               "，本轮补图 %d 次" % _LOGO_NET_BUDGET[0] if _LOGO_NET_BUDGET[0] else "",
               "，拦下 %d 个重复台标" % n_dup if n_dup else ""))

    # ---------- 组装 ----------
    @staticmethod
    def finalize(merged, backups):
        out = {}
        for k, ch in merged.items():
            live = sorted((s for s in ch["sources"] if s["live"]),
                          key=lambda s: (-_src_quality(s, ch), (s.get("ttfb") or 9999)))
            best = pick_best_source(ch)   # 程序权威筛选的唯一最佳源(画质=实测分辨率+实测码率)
            q = ch["quality"] or ""
            qlv, qlabel = 0.0, ""
            if best:
                rh = best.get("res") or 0
                mb = best.get("mbps") or 0
                res_est = False
                if not rh:
                    # 这个源的码流读不出分辨率(被加扰/私有封装)：同一个频道的其它源读出来了就借过来，
                    # 同一个台基本不会换分辨率；界面上标"≈"提醒是推断值，不是这条源实测的
                    alt = max((int(s.get("res") or 0) for s in ch["sources"]), default=0)
                    if alt > 0:
                        rh, res_est = alt, True
                rl, ml = res_level(rh), mbps_level(mb)
                known = [x for x in (rl, ml) if x is not None]
                qlv = min(known) if known else 0.0
                # 角标按用户门槛给结论：清晰 = 分辨率≥1080P 且 码率≥2M；不足的直说缺什么
                qlabel = quality_label(mb, rh)
                rtxt = res_label(rh)
                if rtxt and clear_enough(mb, rh):
                    q = rtxt
                elif rtxt:
                    q = rtxt + " · " + qlabel
                elif qlabel:
                    q = qlabel
            out[k] = {
                "key": k, "name": ch["name"], "group": ch["group"],
                "quality": q, "logo": ch["logo"],
                "mbps": round(float((best or {}).get("mbps") or 0), 2),
                "res": int(rh if best else 0),
                "res_est": bool(res_est) if best else False,
                "codec": (best or {}).get("codec") or "",
                "speed": round(float((best or {}).get("speed") or 0), 2),
                "clear": clear_enough((best or {}).get("mbps") or 0, rh if best else 0),
                "qlv": qlv, "qlabel": qlabel,
                "sources": live[:backups], "live_count": len(live),
                "playable": bool(best and best.get("url", "").startswith("http")),
                "best": best,
            }
        return out

    # ---------- 同一频道不同叫法的合并 ----------
    @staticmethod
    def merge_same_name(channels):
        """把"翡翠台 / TVB翡翠台 HD"、"TVBS亚洲 / TVBS亚洲台"这种同一个台的不同叫法
        合成一条（源合并、只留一个名字），免得列表里堆一堆重复、还互相抢排序。"""
        noise = re.compile(r"(tvb|hd|高清|超清|蓝光|4k|uhd|sd|标清|流畅|频道|电视台|卫视)")
        # 央视的"官方后缀"：CCTV2 财经 / CCTV-2 财经 / CCTV2 都指同一个频道，统一收成 CCTV2
        cctv_suffix = re.compile(
            r"^cctv[\-\s]?(\d{1,2})\s*(综合|财经|中文国际|综艺|体育|电影|军事农业|国防军事|"
            r"农业农村|电视剧|纪录|科教|戏曲|社会与法|新闻|少儿|音乐|体育赛事|奥林匹克|"
            r"世界地理|怀旧剧场|第一剧场|风云剧场|风云音乐|风云足球|兵器科技|女性时尚|"
            r"文化精品|卫生健康|央视台球|高尔夫网球|央视文化精品)?$")

        def norm(name):
            n = unicodedata.normalize("NFKC", name).lower()
            # 4K/8K 频道单独成键：不然 "cctv-4k超高清" 会被噪声词剥成 "cctv"，
            # 跟 8K 甚至别的 cctv 残名撞成一个桶，两条频道被合成一条
            mk = re.match(r"^cctv[\-\s]?(\d{1,2})\s*k", n.strip())
            if mk:
                return "cctv" + mk.group(1) + "k"
            m = cctv_suffix.match(n.strip())
            if m:
                n = "cctv" + m.group(1)      # 只按频道号归一，后缀丢掉
            n = noise.sub("", n)
            n = re.sub(r"[\s·・\-_/()（）\[\]【】]+", "", n)
            n = n.rstrip("台") or n
            return n

        buckets = {}
        for k, ch in channels.items():
            buckets.setdefault(norm(ch.get("name") or k), []).append((k, ch))
        out = dict(channels)
        merged = 0
        for group in buckets.values():
            if len(group) < 2:
                continue
            def rank(item):
                ch = item[1]
                best = ch.get("best") or {}
                # 人工核对过的精选源名字优先(凤凰资讯台/凤凰中文台 这类，
                # 聚合源的叫法可能是错的，别让它把精选源的名字顶掉)
                cur = 1 if any(s3.get("tag") == "curated" for s3 in (ch.get("sources") or [])) else 0
                # 同名多条时，留实测数据更全、画质(分辨率+码率短板)更高的那一条
                return (cur, 1 if best.get("res") else 0,
                        round(_src_quality(best, ch), 2) if best else 0,
                        ch.get("live_count") or 0,
                        1 if (ch.get("quality") or "").endswith("P") or ch.get("quality") == "4K" else 0,
                        -len(ch.get("name") or ""))
            group.sort(key=rank, reverse=True)
            keep_k, keep = group[0]
            seen = {(s2.get("url") or "") for s2 in (keep.get("sources") or [])}
            for k2, ch2 in group[1:]:
                for s2 in (ch2.get("sources") or []):
                    u = s2.get("url") or ""
                    if u and u not in seen:
                        seen.add(u)
                        keep.setdefault("sources", []).append(s2)
                out.pop(k2, None)
                merged += 1
            keep["live_count"] = len(keep.get("sources") or [])
            best = pick_best_source(keep)
            keep["best"] = best
            keep["playable"] = bool(best and (best.get("url") or "").startswith("http"))
        if merged:
            log("同名频道合并: 去掉 %d 个重复叫法" % merged)
        return out

    # ---------- 同一地址的去重 ----------
    @staticmethod
    def dedupe_by_url(channels):
        """同一个播放地址被拆成好几个频道时(典型: TVBS亚洲台 / TVBS Asia / TVBS亚洲)
        只保留一个 —— 用户在列表里看到的重复项大多来自这里。"""
        def rank(c):
            curated = any(s.get("tag") == "curated" for s in (c.get("sources") or []) if s.get("live"))
            nm = c.get("name") or ""
            return (0 if curated else 1, len(nm), nm)

        seen = {}
        out = {}
        for k, ch in channels.items():
            u = (ch.get("best") or {}).get("url") or ""
            if not u:
                out[k] = ch
                continue
            prev = seen.get(u)
            if prev is None:
                seen[u] = k
                out[k] = ch
            elif rank(ch) < rank(channels[prev]):
                out.pop(prev, None)
                seen[u] = k
                out[k] = ch
        return out

    # ---------- 完整更新 ----------
    def run_once(self):
        if self.state["updating"]:
            return False
        self.state.update(updating=True, error="", done=0, total=0)
        t0 = time.time()
        tray_busy(True)          # 托盘图标切"方块"：一眼看出正在更新
        try:
            global PREV_BEST
            self.prev_live = set()
            PREV_BEST = set()
            for ch in (self.channels or {}).values():
                for s in ch.get("sources") or ():
                    if s.get("live"):
                        self.prev_live.add(s["url"])
                b = ch.get("best") or {}
                if b.get("url"):
                    self.prev_live.add(b["url"])
                    PREV_BEST.add(b["url"])
            entries = self.fetch_all()
            log("共获取 %d 条原始记录" % len(entries))
            merged = self.merge(entries)
            log("去重后 %d 个频道" % len(merged))
            self.verify(merged)
            channels = self.finalize(merged, self.cfg["backups"])
            # 央视名称统一成台标上的官方写法（CCTV-1 综合 / CCTV-2 财经 / CCTV-4K 超高清）：
            # 用户拿台标一对就能找到台。原始名字留在 aka，搜索仍能按旧写法命中。
            # 必须放在"同名合并"之前：改名之后 "CCTV1" 与 "CCTV-1" 才会归成同一条，不然会出两条同名。
            for ch in channels.values():
                nm = official_cctv_name(ch.get("name") or "")
                if not nm:
                    nm = NAME_FIXES.get(ch.get("name") or "", "")
                if nm and nm != ch.get("name"):
                    ch["aka"] = ch["name"]
                    ch["name"] = nm
            n_before = len(channels)
            channels = self.merge_same_name(channels)
            channels = self.dedupe_by_url(channels)
            if len(channels) != n_before:
                log("同一地址合并: 去掉 %d 个重复频道" % (n_before - len(channels)))
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
            # 列表先给用户看，吞吐复测放后台补(不挡界面)：整轮 64 路并发摊薄了带宽，
            # 测出来的吞吐普遍偏低，复测完再把速度徽标刷新成真实值
            threading.Thread(target=self.net_pass, args=(channels,), daemon=True).start()
            return True
        except Exception as e:
            self.state["error"] = str(e)
            log("更新失败: %s" % e)
            tray_notify("更新失败", str(e)[:120])
            return False
        finally:
            tray_busy(False)     # 不管成功失败，都换回"三角"
            self.state["updating"] = False

    def net_pass(self, channels):
        """更新完再补一轮"只看吞吐"的实测：整轮探测是 64 路并发跑的，
        每路分到的带宽被摊薄，测出来的吞吐普遍偏低(实测同一地址单跑 1126KB/s、
        并发里只有 161KB/s)。这里只挑"看着可疑"的(source speed<400KB/s 或没测到)，
        8 路并发、每路 1.5 秒，把结果写回 best["speed"] 并落盘。"""
        targets = []
        for ch in channels.values():
            b = ch.get("best") or {}
            if not b.get("live") or not b.get("url"):
                continue
            try:
                sp = float(b.get("speed") or 0)
            except Exception:
                sp = 0.0
            if sp * 125 < SMOOTH_KBPS:          # 只有可疑的才复测，够快的不再折腾
                targets.append(ch)
        if not targets:
            return
        targets.sort(key=lambda c: -_src_quality(c.get("best") or {}, c))
        log("吞吐复测: %d 个频道(8 路并发)" % len(targets))
        done = [0]
        lock = threading.Lock()

        def one(ch):
            b = ch["best"]
            ok, sp, _res = probe_speed({"url": b.get("url")}, 6)
            if ok and sp > 0:
                b["speed"] = max(sp, float(b.get("speed") or 0))
                # 复测出来的吞吐就是"能不能顺畅播"的硬指标：顺手记一下判据结果
                b["smooth"] = b["speed"] * 125 >= SMOOTH_KBPS
            with lock:
                done[0] += 1
                self.state["net_done"] = done[0]

        self.state["net_total"] = len(targets)
        self.state["net_done"] = 0
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(one, targets))
        except Exception as e:
            log("吞吐复测出错: %s" % e)
        self.save_cache(channels)
        log("吞吐复测完成: %d/%d 达到 %d KB/s" % (
            sum(1 for c in targets if (c["best"].get("speed") or 0) * 125 >= SMOOTH_KBPS),
            len(targets), int(SMOOTH_KBPS)))

    # 注意：本函数不使用实例状态，必须是 staticmethod。
    # 之前漏写 @staticmethod，导致 load_cache() 里 self.compute_stats(self.channels)
    # 抛 TypeError -> 缓存被判定"读取失败" -> 每次启动都误触发全量更新并重探测几百条直播流。
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
            # 频道名强制覆盖（台标/实际称呼与上游数据源不一致时统一）
            for _old, _new in _CHANNEL_NAME_OVERRIDE.items():
                if _old in channels:
                    ch = channels.pop(_old)
                    ch["name"] = _new
                    channels[_new] = ch
            # 台标 URL 强制覆盖（M3U 自带的台标不对时，强制指定正确的台标）
            for _key, _url in _LOGO_URL_OVERRIDE.items():
                if _key in channels:
                    channels[_key]["logo"] = _url
            CACHE_PATH.write_text(json.dumps({
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "channels": channels,
                "source_stats": self.state.get("source_stats") or {},   # 上次各源抓到多少条，重启后还要显示
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
            # 频道名强制覆盖（加载时就改，避免旧缓存名残留）
            for _old, _new in _CHANNEL_NAME_OVERRIDE.items():
                if _old in self.channels:
                    ch = self.channels.pop(_old)
                    ch["name"] = _new
                    self.channels[_new] = ch
            # 台标 URL 强制覆盖（加载时就改，确保台标正确）
            for _key, _url in _LOGO_URL_OVERRIDE.items():
                if _key in self.channels:
                    self.channels[_key]["logo"] = _url
            # 读盘后再过一次来源闸口：老缓存里可能残留第三方图库的台标，
            # 不过滤的话网页列表立刻就又会变得跟 M3U 不一致
            _n = 0
            for _ch in self.channels.values():
                _kept = _filter_logo(_ch.get("logo"))
                if _kept != (_ch.get("logo") or ""):
                    _ch["logo"] = _kept
                    _n += 1
            if _n:
                log("台标来源统一：读缓存时清掉 %d 个非白名单图库的台标" % _n)
            self.state["stats"] = self.compute_stats(self.channels)
            self.state["last_update"] = saved.strftime("%Y-%m-%d %H:%M:%S")
            if data.get("source_stats"):
                self.state["source_stats"] = data["source_stats"]   # 别让设置页在重启后显示"未抓取"
            self.state["next_update"] = time.time() + max(0, self.cfg["interval_hours"] - age_h) * 3600
            log("已加载缓存: %d 频道(%.1f 小时前更新)" % (len(self.channels), age_h))
            # 台标库扩容补漏：图库加新图后，老缓存里"可用但没台标"的频道
            # 按新图库离线再查一遍(纯本地文件查找，零出网秒回)，不用等下一轮更新
            _n2 = 0
            for _ch in self.channels.values():
                _nm = _ch.get("name") or ""
                # 别名表点名的频道(如翡翠台锁 CCSH 那张横版图)：一律以别名为准，
                # 免得图库扩容后被别的库里的近方/竖版图顶掉
                _al = LOGO_ALIASES.get(_nm.strip())
                if _al and _lib_file(_al[0], _al[1]):
                    _want = _alias_url(_al)
                    if _ch.get("logo") != _want:
                        _ch["logo"] = _want
                        _n2 += 1
                    try:                      # 配色也按别名那张图重判
                        _pp = _logo_lib_path_for_url(_want)
                        if _pp and _pp.exists():
                            _k2 = logo_kind(_pp.read_bytes(), _want)
                            if _k2 and _ch.get("logo_kind") != _k2:
                                _ch["logo_kind"] = _k2
                                _n2 += 1
                    except Exception:
                        pass
                    continue
                # 已有台标的：本地重判一遍配色。判定阈值更新后旧结论会过时
                # (如"亚洲剧"白字+小彩条，旧阈值判成彩图不垫底，浅色界面看不清)
                if _ch.get("logo"):
                    try:
                        _pp = _logo_lib_path_for_url(_ch["logo"])
                        if _pp and _pp.exists():
                            _k2 = logo_kind(_pp.read_bytes(), _ch["logo"])
                            if _k2 and _ch.get("logo_kind") != _k2:
                                _ch["logo_kind"] = _k2
                                _n2 += 1
                    except Exception:
                        pass
                    continue
                if not (_ch.get("best") or {}).get("live"):
                    continue
                _u = _resolve_logo_local(_nm)
                if _u:
                    _ch["logo"] = _u
                    try:
                        _p = _logo_lib_path_for_url(_u)
                        if _p:
                            _ch["logo_kind"] = logo_kind(_p.read_bytes(), _u)
                    except Exception:
                        pass
                    _n2 += 1
            if _n2:
                log("台标库扩容补漏: 按新图库找到 %d 个频道的台标" % _n2)
                self.save_cache(self.channels)
            return True
        except Exception as e:
            log("缓存加载失败: %s" % e)
            return False

    # ---------- M3U 写出(每频道只写程序筛选出的唯一最佳源，不列备选) ----------
    def write_m3u(self, path, keys=None, logo_via=None):
        """logo_via: 局域网订阅(/list.m3u)时传本机中转前缀(如 "http://192.168.1.5:8902/logo?u=")，
        tvg-logo 会被改写成经由本机 /logo 取图。原因：台标库在 raw.githubusercontent.com，
        电视端播放器直连基本拉不下来，台标全是纯文字；而图片已全量缓存在本机 logos/ 目录，
        局域网内从本机拿图稳定且不出网。网页/桌面导出不传，仍写图库原始地址。"""
        with self.lock:
            channels = self.channels
        if not channels:
            log("无频道数据，跳过 M3U 写出(保留原文件)")
            return 0, 0
        lines = ["#EXTM3U"]
        if self.cfg["epg_url"]:
            lines[0] += ' x-tvg-url="%s"' % self.cfg["epg_url"]
        lines.append("# 由 %s v%s 生成于 %s" % (APP_NAME, VERSION, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        n_src = n_ch = n_skip = 0
        n_urls = max(1, min(10, int(self.cfg.get("urls_per_channel") or 3)))
        lines.append("# 筛选标准：画质=实测分辨率+实测码率(两个指标谁弱谁定上限，短板优先) > 区域基准 > 链路速度；"
                     "每个频道最多写 %d 条实测可用线路" % n_urls)
        present = sorted({ch["group"] for ch in channels.values()},
                         key=lambda g: (GROUP_RANK.index(g) if g in GROUP_RANK else 50, g))
        for g in present:
            # 组内按画质分(分辨率+码率短板)排，同分再按码率与首包速度
            gch = sorted((c for c in channels.values() if c["group"] == g),
                         key=lambda c: (-_src_quality(c.get("best") or {}, c),
                                        -((c.get("best") or {}).get("mbps") or 0),
                                        (c.get("best") or {}).get("ttfb") or 9999, c["name"]))
            for ch in gch:
                if keys is not None and ch["key"] not in keys:
                    continue
                best = ch.get("best")
                if not best or not best.get("live") or not best.get("url"):
                    if keys is None:
                        n_skip += 1
                    continue
                if self.cfg.get("hide_local", True) and ch.get("group") == "地方台":
                    n_skip += 1
                    continue
                mm = float(self.cfg.get("min_mbps") or 0)
                if mm and (best.get("mbps") or 0) < mm:
                    n_skip += 1
                    continue
                # 同一频道所有实测可用线路按画质分排序(分辨率+码率短板)，写前 n_urls 条当备份
                cand = []
                for sl in (ch.get("sources") or []):
                    if not (sl.get("live") and sl.get("url")):
                        continue
                    _m = sl.get("mbps") or 0
                    if mm and _m and _m < mm:
                        continue
                    cand.append(sl)
                cand.sort(key=lambda sl: (-_src_quality(sl, ch), -(sl.get("mbps") or 0),
                                          (sl.get("ttfb") or 9999)))
                seen_url, urls = set(), []
                for sl in cand:
                    if sl["url"] in seen_url:
                        continue
                    seen_url.add(sl["url"])
                    urls.append(sl["url"])
                    if len(urls) >= n_urls:
                        break
                if not urls:
                    urls = [best["url"]]
                n_ch += 1
                n_src += len(urls)
                for _u in urls:
                    # 写出前再过一次来源闸口(就算内存里还有脏台标也不会进 M3U)
                    _lg = _filter_logo(ch["logo"])
                    if _lg and logo_via:      # 局域网订阅：台标走本机中转，电视端必能显示
                        _lg = logo_via + quote(_lg, safe="")
                    lines.append('#EXTINF:-1 tvg-name="%s" tvg-logo="%s" group-title="%s",%s'
                                 % (esc_attr(ch["name"]), esc_attr(_lg), g, ch["name"]))
                    lines.append(_u)
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
  --bg:#e4e7ea; --bg1:#f4f6f8; --card:#fff; --txt:#1b1f24; --sub:#6b7280; --line:#e4e8ef;
  --ok:#16a34a; --warn:#d97706; --bad:#dc2626;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 8px 24px -12px rgba(16,24,40,.18);
  --r:14px;
}
html[data-theme="dark"]{
  --bg:#0d1015; --bg1:#161b23; --card:#181d25; --txt:#e8eaee; --sub:#9aa2ae; --line:#252b35;
  --accent-l:#3a1218; --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -14px rgba(0,0,0,.7);
}
*{box-sizing:border-box}
/* 底色：顶部近白、往下淡蓝灰，比原来的一片平灰更有层次（卡片仍是纯白，对比更清楚） */
body{margin:0;background:var(--bg);background-image:linear-gradient(180deg,var(--bg1) 0,var(--bg) 420px);
  background-repeat:no-repeat;background-attachment:fixed;color:var(--txt);
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
main{max-width:1120px;margin:0 auto;padding:12px 18px 62px;display:flex;flex-direction:column;min-height:calc(100vh - 62px)}
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
.list{margin-top:10px;overflow:hidden;flex:1 1 auto;display:flex;flex-direction:column;min-height:0}
.thead,.tr{display:grid;grid-template-columns:30px 104px minmax(0,1fr) 80px 180px minmax(0,1fr);align-items:center;gap:8px;padding:0 10px}
.thead{height:32px;font-size:12px;color:var(--sub);border-bottom:1px solid var(--line);background:var(--card)}
.tbody{flex:1 1 auto;min-height:200px;overflow:auto}   /* 列表拉伸填充，随窗口高度自适应 */
.tr{height:72px;border-bottom:1px solid color-mix(in srgb,var(--line) 60%,transparent)}
.tr:hover{background:color-mix(in srgb,var(--accent) 4%,transparent)}
.tr.dead{opacity:.45}
.nm{display:flex;align-items:center;gap:9px;min-width:0}
/* 台标统一排版：所有台标（彩图直显 / 白图垫底）都进同一个 104x40 画框，
   object-fit:contain 居中——横版(300x180)、竖版(507x597)、宽条(294x77)
   都完整显示且视觉大小一致，不再撑爆行宽也不被裁切 */
.nm img{height:40px;width:auto;max-width:104px;min-width:32px;border-radius:5px;
  object-fit:contain;background:transparent;flex:0 0 auto}
.lgcol{display:flex;align-items:center;justify-content:center;min-width:0;overflow:hidden}
/* 表头"台标"两个字与下方居中的台标图对齐 */
.hlg{text-align:center}
/* 表头"频道"两个字整体向右内缩一点，避免紧贴台标列显得拥挤 */
.hch{padding-left:14px}
.lg{display:flex;align-items:center;justify-content:center;width:104px;height:40px;
  max-width:104px;min-width:104px;border-radius:6px;flex:0 0 auto;overflow:hidden;padding:0 3px}
.lg img{width:100%;height:100%;object-fit:contain}
/* 透明底白图（央视全系、湖北卫视这类）：直接放白卡上等于看不见。
   统一垫一块深色底，白字/彩标都清楚；不做灰度/降低透明度，否则会"发灰看不清" */
.lg.dk{background:#2b3240;box-shadow:inset 0 0 0 1px rgba(255,255,255,.06)}
.lg.dk img{filter:none;opacity:1;padding:2px 0}
.ph{width:26px;height:26px;border-radius:4px;background:transparent;color:#9aa4b2;flex:0 0 auto;
  display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700}
.nm .t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1 1 auto;min-width:0}
.nsrc{font-size:11px;color:var(--sub);background:var(--bg);border-radius:6px;padding:0 5px;flex:0 0 auto}
.grp{font-size:12.5px;color:var(--sub)}
.qa{display:flex;align-items:center;gap:6px;font-size:12.5px;min-width:0;flex-wrap:nowrap}
.tag{font-size:11px;font-weight:700;padding:1px 6px;border-radius:6px;background:var(--bg);color:var(--sub);border:1px solid var(--line);flex:0 0 auto}
.tag.q4{color:#7c3aed;border-color:#ddd6fe;background:#f5f3ff}
.tag.q3{color:#0369a1;border-color:#bae6fd;background:#f0f9ff}
.tag.q2{color:#4d7c0f;border-color:#d9f99d;background:#f7fee7}
.tag.q1{color:#9a3412;border-color:#fed7aa;background:#fff7ed}
.tag.q0{color:#b91c1c;border-color:#fecaca;background:#fef2f2}
.spd{font-size:11px;color:var(--sub);font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cd{font-size:10px;font-weight:700;color:#6b7280;background:var(--bg);border:1px solid var(--line);
  border-radius:4px;padding:0 4px;flex:0 0 auto;margin-left:2px}
.net{font-size:10.5px;font-variant-numeric:tabular-nums;border-radius:5px;padding:0 4px;flex:0 0 auto}
.net.ok{color:#15803d;background:#f0fdf4;border:1px solid #bbf7d0}
.net.slow{color:#b91c1c;background:#fef2f2;border:1px solid #fecaca}
.host{font-size:12px;color:var(--sub);display:flex;align-items:center;gap:6px;min-width:0}
.host .h{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mini{opacity:0;height:22px;padding:0 8px;border-radius:7px;border:1px solid var(--line);
  background:var(--card);font-size:11.5px;color:var(--sub);transition:.15s;flex:0 0 auto}
.tr:hover .mini{opacity:1}
.mini:hover{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
.lowb{font-size:10.5px;color:#b45309;background:#fffbeb;border:1px solid #fde68a;
  border-radius:5px;padding:0 4px;flex:0 0 auto}
.lowr{font-size:10.5px;color:#1d4ed8;background:#eff6ff;border:1px solid #bfdbfe;
  border-radius:5px;padding:0 4px;flex:0 0 auto}
input[type=checkbox]{width:16px;height:16px;accent-color:var(--accent);cursor:pointer}
.empty{padding:36px 16px;text-align:center;color:var(--sub);font-size:13px}

/* 底栏 */
footer{position:fixed;left:0;right:0;bottom:0;z-index:40;background:color-mix(in srgb,var(--card) 94%,transparent);
  backdrop-filter:blur(10px);border-top:1px solid var(--line)}
.foot{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;flex-wrap:wrap;
  margin-top:auto;margin-bottom:0;text-align:center;font-size:11.5px;color:var(--sub);
  min-height:34px;padding:4px 0;line-height:1.4}
.foot a{color:var(--sub);text-decoration:none}
.foot a:hover{color:var(--accent);text-decoration:underline}
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

/* 首次运行的合规提示条：只声明"不含内容"，一句就能看懂 */
.legal{display:flex;gap:14px;align-items:center;background:#fff7ed;border:1px solid #fed7aa;
  border-radius:12px;padding:11px 14px;margin-bottom:12px}
.legal .lt{font-weight:600;font-size:13px;color:#7c2d12;white-space:nowrap}
.legal .ld{flex:1;font-size:12px;line-height:1.55;color:#9a3412}
.legal .btn{flex:0 0 auto}

/* toast */
#toast{position:fixed;left:50%;bottom:84px;transform:translateX(-50%) translateY(14px);z-index:70;
  background:#1b1f24;color:#fff;font-size:13px;padding:10px 16px;border-radius:10px;opacity:0;
  pointer-events:none;transition:.22s;max-width:88vw;box-shadow:0 12px 30px -10px rgba(0,0,0,.6)}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
@media(max-width:820px){
  .cards{grid-template-columns:1fr 1fr}
  #fname{width:110px}
}

/* ---------- 平板 ---------- */
@media(max-width:900px){
  .hbar{flex-wrap:wrap;row-gap:6px}
  .hbar .brand span{display:none}
  .fbar{gap:6px}
  .dlg{width:min(94vw,720px);max-height:92vh}
  .grid2{grid-template-columns:1fr 1fr}
  .thead,.tr{grid-template-columns:30px 96px minmax(0,1fr) 80px 160px 0;gap:6px;padding:0 6px}
  .thead>div:nth-child(6),.tr>*:nth-child(6){display:none}
}

/* ---------- 手机 ---------- */
@media(max-width:600px){
  .hbar{padding:6px 10px;gap:8px}
  .logo{width:30px;height:30px}
  .brand b{font-size:15px}
  .pill{font-size:11px;padding:3px 8px}
  #verPill{display:none}
  .hbar .btn{padding:0 10px;height:30px;font-size:12.5px}
  main{padding:10px 10px 96px}
  .cards{grid-template-columns:1fr 1fr;gap:8px}
  .stat{padding:6px 10px}
  .stat b{font-size:17px}
  .stat span{font-size:11px}
  .toolbar{padding:8px 10px;gap:6px;flex-wrap:wrap}
  .search{flex:1 1 100%;min-width:0}
  .sortsel,.toolbar .btn{flex:0 0 auto}
  .chips{overflow-x:auto;flex-wrap:nowrap;padding-bottom:2px;-webkit-overflow-scrolling:touch}
  .chips::-webkit-scrollbar{display:none}
  .chip{flex:0 0 auto}
  /* 手机只留：勾选 + 台标 + 频道名 + 速率；分组/首选源隐藏 */
  .thead,.tr{grid-template-columns:30px 60px minmax(0,1fr) 74px;gap:6px;padding:0 6px}
  /* 手机上只留速率，"1080P"这类画质标签和数字挤在一起会换行 */
  .tr .qa>span:first-child{display:none}
  .thead>div:nth-child(4),.thead>div:nth-child(6),
  .tr>*:nth-child(4),.tr>*:nth-child(6){display:none}
  .tr .qa .spd{font-size:11.5px}
  .tr{height:auto;min-height:46px;padding-top:6px;padding-bottom:6px}
  .nm{white-space:normal;line-height:1.3}
  .tbody{max-height:none;overflow:visible}
  .fbar{padding:6px 10px 8px;gap:6px}
  .fbar .cnt{flex:1 1 100%}
  #outdir,#fname,#btnBrowse,#btnFolder{display:none}
  .fbar .sel{flex:1 1 100%}
  .fbar .btn{flex:1 1 100%;height:38px;font-size:14px}
  .fbar .btn.primary{flex:1 1 100%;height:40px;font-size:15px}
  .dlg{width:100vw;max-width:100vw;height:100vh;max-height:100vh;border-radius:0}
  .mask{align-items:stretch;justify-content:stretch}
  .dbody{max-height:none;flex:1 1 auto}
  .dfoot{padding:10px 12px}
  .grid2,.srcs{grid-template-columns:1fr}
  .legal{flex-direction:column;align-items:stretch}
  .legal .btn{align-self:flex-end}
  .dfoot{position:sticky;bottom:0;background:var(--card);border-top:1px solid var(--line)}
  .dlg{display:flex;flex-direction:column}
}

/* ---------- 小屏手机 ---------- */
@media(max-width:430px){
  .brand b{font-size:14px}
  .hbar .btn{height:28px;padding:0 8px;font-size:12px}
  .stat b{font-size:16px}
  .thead,.tr{grid-template-columns:30px 56px minmax(0,1fr) 70px}
}
.legal[hidden]{display:none !important}
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
  <div class="legal" id="legalBar" hidden>
    <div class="lt">本程序只整理公开链接，不含任何节目内容</div>
    <div class="ld">它不提供、不托管、不转发任何直播流，也不解除任何付费或加密限制。能不能播放、内容是否合规，取决于你所在地区和那些公开来源本身；请自行确认当地法律法规与来源授权，仅供个人自用。</div>
    <button class="btn" id="btnLegal">我已了解</button>
  </div>
  <div class="cards">
    <div class="card stat"><b id="sChan">-</b><span id="sChanLb">实测可用频道</span></div>
    <div class="card stat"><b id="sSrc">-</b><span>频道总数</span></div>
    <div class="card stat"><b id="sHkmt">-</b><span>港澳台频道</span></div>
    <div class="card stat"><b id="sTime">-</b><span>上次更新</span></div>
  </div>

  <div class="card toolbar">
    <div class="row">
      <input class="search" id="q" placeholder="搜索频道名，例如 CCTV5 / 翡翠台 / 湖南卫视">
      <select class="field sortsel" id="sort" title="排序方式">
        <option value="hot">常用优先（CCTV · 卫视 · 港澳台在前）</option>
        <option value="quality">画质优先（实测分辨率 × 码率）</option>
        <option value="bitrate">码率优先</option>
        <option value="speed">网络最快优先（不卡）</option>
        <option value="group">按分组</option>
        <option value="name">按名称</option>
      </select>
      <button class="btn" id="btnAll">全选</button>
      <button class="btn" id="btnInv">反选</button>
    </div>
    <div class="row chips" id="chips"></div>
    <div class="row chips" id="chipsQ">
      <button class="chip" data-f="pass" title="用户的标准：分辨率 ≥1080P、码率 ≥2 Mbps、下载吞吐 ≥400 KB/s，三条全满足">达标（1080P+ 清晰不卡）</button>
      <button class="chip" data-f="ok" title="分辨率 ≥1080P 且 码率 ≥2 Mbps（只看画面清晰，不管网络速度）">仅看清晰</button>
      <button class="chip" data-s="1" title="实测下载吞吐 ≥400 KB/s（≈3.2 Mbps）—— 达到这个速度看着不卡">网络 400KB/s+</button>
      <span class="qsep"></span>
      <button class="chip" data-r="4" title="实测分辨率 4K（≥2000 像素）">4K</button>
      <button class="chip" data-r="3" title="实测分辨率 1080P">1080P</button>
      <button class="chip" data-r="2" title="实测分辨率 720P">720P</button>
      <span class="qsep"></span>
      <button class="chip" data-q="4" title="实测码率 ≥9 Mbps">码率≥9M</button>
      <button class="chip" data-q="3" title="实测码率 ≥5 Mbps">码率≥5M</button>
      <button class="chip" data-q="2" title="实测码率 ≥2.5 Mbps">码率≥2.5M</button>
      <button class="chip" data-q="low" title="实测码率不到 2 Mbps（用户：这个码率画面就一般了）">码率不足2M</button>
      <button class="chip" data-q="lowr" title="实测分辨率不到 720P，码率再高画面也细不了">分辨率偏低</button>
      <span class="qsep"></span>
      <button class="chip" data-qk="alive">仅可用</button>
    </div>
  </div>

  <div class="card list">
    <div class="thead"><div><input type="checkbox" id="ckAll"></div><div class="hlg">台标</div><div class="hch">频道</div><div>分组</div><div>画质（分辨率·码率）</div><div>首选源</div></div>
    <div class="tbody" id="rows"><div class="empty">点右上角「立即更新」开始检测直播源。<br><span class="hint">每一轮都会重新实测，不会沿用上次的结果。</span></div></div>
  </div>

  <div class="foot"><span>LIVE直播源 · 作者 海风（kele551）</span>
    <a href="https://github.com/kele551/LiveIPTV" target="_blank" rel="noopener">github.com/kele551/LiveIPTV</a></div>
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
    <div class="f">最低码率 Mbps（低于此值不显示、不导出，0=不限）
      <input type="number" id="c_min" min="0" max="50" step="0.5"></div>
          <div class="f">EPG 节目单地址（可留空）<input type="text" id="c_epg" placeholder="http://…/epg.xml"></div>
          <div class="f">保存位置<input type="text" id="c_out" placeholder="M3U 输出路径"></div>
        </div>
        <div class="grid2" style="margin-top:10px">
          <label class="f ck"><input type="checkbox" id="c_sd">保留标清频道</label>
          <label class="f ck"><input type="checkbox" id="c_tv">只保留电视台频道（白名单，列表更干净）</label>
          <label class="f ck"><input type="checkbox" id="c_junk">过滤非电视频道（DJ / 相声 / 助眠等）</label>
        <label class="f ck"><input type="checkbox" id="c_lo">隐藏地级市/县级台（只留大台，列表更短）</label>
        <label class="f"><span>每个频道写入几条线路</span><input class="in" id="c_urls" type="number" min="1" max="10" step="1" value="3"></label>
        <label class="f ck"><input type="checkbox" id="c_lan">允许手机/平板在局域网访问（手机导入用）</label>
        <div class="f hint" id="lanHint" style="grid-column:1/-1"></div>
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
var CH=[], sel=new Set(), grp="", rf="", qf="", qk="", sf="", q="", sk="hot", lastLoaded="", timer=null, dirty=false;
var fresh=false, wasUpdating=false;   // fresh=本次打开后跑完过一轮更新，才把频道列出来
var GORDER=["央视","卫视","香港","澳门","台湾","体育","电影","少儿","游戏","国际·综合","地方台","其他"];
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

// 画质判据（与后端 _src_quality / quality_label 同一套口径，按用户 2026-10-20 给的门槛）：
//   清晰 = 实测分辨率 ≥1080P 且 实测码率 ≥2 Mbps；
//   流畅 = 实测下载吞吐 ≥400 KB/s（≈3.2 Mbps，不够就会转圈/卡顿）。
// 界面上两个指标都亮出来，别只给一个数字让用户猜。
var REST=[[2000,4,"4K"],[1000,3,"1080P"],[620,2,"720P"],[400,1,"480P"]];
var CLARITY_H=1000, CLARITY_MB=2.0, SMOOTH_KB=400;
function resLv(r){ r=r||0; if(r<=0) return 0; for(var i=0;i<REST.length;i++){ if(r>=REST[i][0]) return REST[i][1] } return 0.3 }
function mbLv(m){ m=m||0; if(m<=0) return 0; if(m>=9) return 4; if(m>=5) return 3; if(m>=2.5) return 2; if(m>=1) return 1; return 0.3 }
function resName(r){ var l=resLv(r); if(!l) return ""; if(l<1) return "低分辨率";
  for(var i=0;i<REST.length;i++){ if(l===REST[i][1]) return REST[i][2] } return "" }
// 吞吐：后端 speed 单位是 Mbps，换算成 KB/s 更接近用户看的播放器数字
function kbps(c){ var b=c.best||{}; return (b.speed||0)*125 }
function mbpsTxt(m){ return (m||0).toFixed(1)+"M" }
function qScore(c){
  var b=c.best||{}, m=b.mbps||0, rs=resLv(b.res||0);
  if(!(m>0)) return rs?(rs*10*0.35):2.0;
  var adequate=Math.min(1, m/CLARITY_MB);
  var bonus=Math.min(1, m/10)*5;
  var base=rs||2.0;                      // 没测到分辨率按 720P 记，不虚高也不打死
  return base*10*(0.55+0.45*adequate)+bonus;
}
function clearEnough(c){ var b=c.best||{}; return (b.res||0)>=CLARITY_H && (b.mbps||0)>=CLARITY_MB }
function smoothEnough(c){ return kbps(c)>=SMOOTH_KB }
function lowBit(c){ var m=(c.best||{}).mbps||0; return m>0 && m<CLARITY_MB }
function lowRes(c){ var r=(c.best||{}).res||0; return r>0 && r<620 }
// 画质列：分辨率档 + 实测码率，两个数字并排，缺哪个标哪个
function detailText(c){
  // 鼠标悬停看这一路的全部实测细节：分辨率(像素)、编码、码率、我这边的下载速度、首包延迟
  var b=c.best||{}, p=[];
  if(b.res_wh&&b.res_wh[0]) p.push("实测分辨率 "+b.res_wh[0]+"×"+b.res_wh[1]);
  else if(b.res) p.push("分辨率 "+(c.res_est?"≈":"")+b.res+"p"+(c.res_est?"(借同频道其它源)":""));
  if(b.codec) p.push("编码 "+b.codec);
  if(b.mbps) p.push("码率 "+b.mbps+" Mbps");
  if(b.speed) p.push("下载 "+Math.round(kbps(c))+" KB/s");
  if(b.ttfb) p.push("首包 "+b.ttfb+" ms");
  p.push("可用线路 "+(c.live_count||(c.sources||[]).length)+" 条");
  return p.join(" · ");
}
function spd(c){
  var b=c.best||{}, rn=resName(b.res||0), m=b.mbps||0;
  if(rn && c.res_est) rn="≈"+rn;      // 这个源的码流读不出分辨率，借同频道其它源的实测值
  var parts=[];
  if(rn) parts.push(rn); else if(b.live) parts.push("分辨率未测");
  if(m>0) parts.push("码率"+mbpsTxt(m)); else if(b.live) parts.push("码率未测");
  if(!parts.length) return c.quality||"";
  return parts.join(" · ");
}
function tagCls(c){
  var b=c.best||{};
  if(!b.live) return "tag";
  if(clearEnough(c)) return ((b.res||0)>=1800?"tag q4":"tag q3");
  if(lowBit(c)) return "tag q1";                       // 分辨率够、码率不够(湖南卫视那种)
  if(lowRes(c)) return "tag q1";                       // 码率够、分辨率不够
  if((b.res||0)>=620) return "tag q2";
  return "tag";
}
function host(u){ try{ return new URL(u).host; }catch(e){ return u||"" } }
function isHkmt(c){ return ["香港","澳门","台湾"].indexOf(c.group)>=0 }

function gidx(g){ var i=GORDER.indexOf(g); return i<0?90:i }
// CCTV 频道按编号排(CCTV1..CCTV17 整齐)，其余归到 99
function cnum(n){ var m=(n||"").match(/cctv[-\s]*(\d{1,2})/i); return m?+m[1]:99 }
// 同号里把"标准台"排前面(CCTV4 在 CCTV4K / CCTV-4 Europe 之前)
function cbase(n){ return /^cctv[-\s]?\d{1,2}$/i.test((n||"").trim())?0:1 }
function mb(c){ var b=c.best||{}; return b.speed||b.mbps||0 }
function mbbr(c){ var b=c.best||{}; return b.mbps||0 }
function filtered(){
  var kw=q.trim().toLowerCase();
  var list=CH.filter(function(c){
    if(grp && c.group!==grp) return false;
    var b=c.best||{};
    if(rf && String(resLv(b.res||0))!==rf) return false;           // 按实测分辨率筛
    if(sf && !smoothEnough(c)) return false;                       // 网络 ≥400KB/s
    if(qf==="pass" && !(clearEnough(c) && smoothEnough(c))) return false;   // 用户标准：清晰+不卡
    if(qf==="ok" && !clearEnough(c)) return false;                 // 清晰：分辨率+码率都达标
    if(qf==="low" && !lowBit(c)) return false;                     // 码率不足 2M
    if(qf==="lowr" && !lowRes(c)) return false;                    // 分辨率偏低
    if(qf && "01234".indexOf(qf)>=0){
      var m=b.mbps||0;
      if(!(m>0)) return false;
      if(String(mbLv(m))!==qf) return false;                       // 按实测码率档筛
    }
    if(qk==="hkmt" && !isHkmt(c)) return false;
    if(qk==="alive" && !(c.best&&c.best.live)) return false;
    if(kw && ((c.name||"")+" "+(c.aka||"")).toLowerCase().indexOf(kw)<0) return false;
    return true;
  });
  list.sort(function(a,b){
    if(sk==="quality"){                    // 画质优先：分辨率+码率短板算出来的综合分
      var d=qScore(b)-qScore(a);
      if(d) return d;
      var g4=gidx(a.group)-gidx(b.group);
      if(g4) return g4;
    }
    if(sk==="hot"||sk==="group"){
      var g=gidx(a.group)-gidx(b.group);   // 常看的组在前(CCTV/卫视/港澳台)
      if(g) return g;
      var ca=cnum(a.name), cb=cnum(b.name);   // CCTV1..CCTV17 按编号排整齐
      if(ca!==cb) return ca-cb;
      var ba=cbase(a.name), bb=cbase(b.name);
      if(ba!==bb) return ba-bb;
      if(sk==="hot"){ var d0=qScore(b)-qScore(a); if(d0) return d0 }
    }
    if(sk==="bitrate"){                    // 纯按实测码率排(带宽有限时用)
      var d1=(mbbr(b)-mbbr(a));
      if(d1) return d1;
      var g5=gidx(a.group)-gidx(b.group);
      if(g5) return g5;
    }
    if(sk==="speed"){
      var d=mb(b)-mb(a);
      if(d) return d;                      // 实测快的排前面
      var g2=gidx(a.group)-gidx(b.group);
      if(g2) return g2;
    }
    return (a.name||"").localeCompare(b.name||"","zh");
  });
  return list;
}

function renderChips(){
  var gs=[], seen={};
  CH.forEach(function(c){ if(!seen[c.group]){seen[c.group]=1;gs.push(c.group)} });
  var order=GORDER;
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
function logoTile(name){
  // 没有台标图片时补一个"字母牌"：按名字取稳定颜色 + 头 2~3 个字，整列看起来是齐的
  var n = (name||"?").replace(/\s+/g,"");
  // 取最有辨识度的一段：CCTV2 财经 → 财经；CCTV-4 Europe → Eur
  var parts = (name||"").split(/[\s\-—·]+/).filter(function(x){return x});
  var tail = parts.length ? parts[parts.length-1] : n;
  var isCJK = /[\u4e00-\u9fa5]/.test(tail);
  var ch = isCJK ? tail.slice(0,3) : tail.slice(0,3).toUpperCase();
  var h = 0;
  for (var i=0;i<n.length;i++) h = (h*31 + n.charCodeAt(i)) % 360;
  return '<span class="ph" style="background:hsl('+h+',58%,46%);color:#fff;font-size:10px;'+
         'display:flex;align-items:center;justify-content:center;overflow:hidden;padding:0 2px">'+
         esc(ch)+'</span>';
}
function esc(s){
  return String(s==null?"":s).replace(/[&<>"']/g,function(m){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m];
  });
}
function renderQ(){
  [].forEach.call($("chipsQ").querySelectorAll(".chip"),function(b){
    var on;
    if(b.dataset.r!==undefined) on = (rf===b.dataset.r);
    else if(b.dataset.q!==undefined) on = (qf===b.dataset.q);
    else on = (qk===b.dataset.qk);
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
      +'<div class="lgcol">'+(c.logo?('<span class="lg'+(c.logo_kind==="white"?" dk":"")+'"><img loading="lazy" src="'+esc(c.logo)+'" onerror="this.style.visibility=\'hidden\'"></span>'):logoTile(c.name))+'</div>'
      +'<div class="nm"><span class="t">'+esc(c.name)+'</span>'+(n>1?'<span class="nsrc">'+n+' 源</span>':'')+'</div>'
      +'<div class="grp">'+esc(c.group)+'</div>'
      +'<div class="qa" title="'+esc(alive?detailText(c):"这一路没连上")+'"><span class="'+tagCls(c)+'">'+esc((c.qlabel||spd(c))||"未知")+'</span>'
      +'<span class="spd">'+esc(alive?(spd(c)||"已实测"):"不可用")+'</span>'
      +(alive&&c.best&&c.best.codec?'<span class="cd" title="实测编码">'+esc(c.best.codec)+'</span>':'')+'</div>'
      +'<div class="host"><span class="h">'+esc(alive?host(c.best.url).split(":")[0]:"—")+'</span>'
      +((alive&&kbps(c)>0)?('<span class="net'+(smoothEnough(c)?" ok":" slow")+'" title="实测下载吞吐：'+
          (smoothEnough(c)?"达到 400 KB/s，看着不卡":"不到 400 KB/s，可能转圈/卡顿")+'">'+
          Math.round(kbps(c))+' KB/s</span>'):'')
      +((alive&&lowBit(c))?'<span class="lowb" title="码率不到 2 Mbps：用户实测这个码率画面就一般了">码率不足</span>':'')
      +((alive&&lowRes(c))?'<span class="lowr" title="实测分辨率不到 720P，码率再高画面也细不了">分辨率低</span>':'')
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
  // 列表可能比"实测可用"少(隐藏了地级台/低码率)，卡片跟着列表走，避免数字对不上
  if(CH.length){ $("sChan").textContent=CH.length; $("sChanLb").textContent="列表内可用频道"; }
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
    if(s.legal_ack===0 && $("legalBar")) $("legalBar").hidden=false;
    if(s.save_path && !$("outdir").value){
      var sp=String(s.save_path), i=Math.max(sp.lastIndexOf("\\"), sp.lastIndexOf("/"));
      if(i>0){
        $("outdir").value=sp.slice(0,i);
        // 文件名也跟着实际保存位置走，否则「保存」会另写一份(桌面出现两个 m3u)
        if(!window.__fnInit){ $("fname").value=sp.slice(i+1)||"直播源.m3u"; window.__fnInit=1; }
      }
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
  if(b.dataset.r!==undefined){
    rf=(rf===b.dataset.r)?"":b.dataset.r;
    qf=""; sf="";                                   // 分辨率筛与"清晰/码率"互斥，免得筛出 0 条
  } else if(b.dataset.q!==undefined){
    qf=(qf===b.dataset.q)?"":b.dataset.q; rf=""; sf="";
  } else if(b.dataset.s!==undefined){
    sf=sf?"":"1"; rf=""; qf="";
  } else {
    qk=(qk===b.dataset.qk)?"":b.dataset.qk;
  }
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
    $("c_lo").checked=c.hide_local!==false;
    $("c_urls").value=(c.urls_per_channel===undefined?3:c.urls_per_channel);
    $("c_lan").checked=!!c.lan;
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
      $("lanHint").innerHTML = s.lan
        ? ('手机/电视盒导入地址：<b>'+(s.lan_url||"（没拿到局域网 IP）")+'</b>　（填到播放器的"添加 M3U 订阅"里，同一 Wi-Fi 下可用）')
        : '想用手机看：勾上上面这项并保存，程序会重启一次，然后把这里给出的地址填进手机播放器。';
      var st=s.source_stats||{};
      $("c_srcs").innerHTML=SRCS.map(function(x){
        var e=st[x.key];
        var on=!!c.sources[x.key];
        var col=!on?"var(--sub)":(!e?"var(--sub)":(e.ok?"var(--ok)":"var(--bad)"));
        var meta;
        if(!on) meta="已关闭";
        else if(!e) meta="上次没参与";
        else if(e.ok) meta="<b>"+e.count+"</b> 条 · "+e.ms+"ms"+(e.fallback?" · 备选":"");
        else meta="抓取失败";
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
      hide_local:$("c_lo").checked,
      urls_per_channel:(parseInt($("c_urls").value,10)||3),
      lan:$("c_lan").checked,
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

// 打开页面直接显示"最近一次更新"的结果(后台跑完也会自动落到这里)，但一个都不勾选，
// 由用户自己挑；真正没有任何结果时才显示空提示。
loadChannels(); loadStatus(); $("btnLegal").addEventListener("click",function(){
  fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({legal_ack:1})}).then(function(){ $("legalBar").hidden=true; });
});
setInterval(loadStatus,2000);
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
        if path == "/logo":
            q = parse_qs(urlsplit(self.path).query)
            u = (q.get("u") or [""])[0]
            if not u.startswith(("http://", "https://")):
                self.send_error(400, "bad logo url")
                return
            data = _LOGO_BYTES.get(u) or _logo_from_disk(u)
            if data is None:
                # 内存/磁盘都没有：现取一次（带缓存落盘），拿不到就 404，绝不崩溃成 500
                try:
                    _check_logo(u)
                except Exception:
                    pass
                data = _LOGO_BYTES.get(u) or _logo_from_disk(u)
            if data is None:
                self.send_error(404, "logo not available")
                return
            self.send_response(200)
            self.send_header("Content-Type", data[0])
            self.send_header("Content-Length", str(len(data[1])))
            self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            self.wfile.write(data[1])
            return
        if path == "/list.m3u":
            with self.updater.lock:
                chs = list(self.updater.channels.values())
            tmp = Path(tempfile.gettempdir()) / "live_iptv_lan.m3u"
            try:
                # 局域网订阅的台标必须走本机中转：raw.githubusercontent 电视端直连拉不下来。
                # 用请求自带 Host(播放器访问哪个 IP 就回哪个 IP)，拿不到再退 _lan_ip()。
                _host = (self.headers.get("Host") or "").strip()
                if not _host:
                    _ip = _lan_ip()
                    _host = "%s:%d" % (_ip, _SERVER.server_address[1]) if _ip else \
                            "127.0.0.1:%d" % _SERVER.server_address[1]
                self.updater.write_m3u(tmp, logo_via="http://%s/logo?u=" % _host)
                body = tmp.read_bytes()
            except Exception as e:
                body = ("#EXTM3U\n# 生成失败: %s\n" % e).encode("utf-8")
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "audio/x-mpegurl; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="LiveIPTV.m3u"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
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
            "legal_ack": int(self.cfg.get("legal_ack") or 0),
            "lan": bool(self.cfg.get("lan")),
            "lan_url": ("http://%s:%d/list.m3u" % (_lan_ip(), _SERVER.server_address[1])
                        if self.cfg.get("lan") and _lan_ip() else ""),
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
            # 默认不列地级市/县级台(用户：这些台就别出现了)，需要的话在设置里打开
            if self.cfg.get("hide_local", True):
                channels = [c for c in channels if c.get("group") != "地方台"]
            channels.sort(key=lambda c: (GROUP_RANK.index(c["group"]) if c["group"] in GROUP_RANK else 50,
                                         cctv_num(c["name"]), cctv_base(c["name"]),
                                         -_src_quality(c["best"], c),
                                         -((c["best"].get("mbps") or 0) or (c["best"].get("speed") or 0)),
                                         c["name"]))
            # 台标一律走本机中转：图标站有防盗链/跨域，直连在浏览器里就是一个个灰方块
            out = []
            for c in channels:
                c2 = dict(c)
                # 网页列表同样过来源闸口，跟 M3U 保持一套
                lg = _filter_logo(c2.get("logo"))
                c2["logo"] = ("/logo?u=" + quote(lg, safe="") + "&v=" + _logo_version(lg)) if lg.startswith(("http://", "https://")) else ""
                out.append(c2)
            channels = out
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
                new = {k: data[k] for k in ("interval_hours", "backups", "keep_sd", "filter_junk", "only_tv", "min_mbps", "hide_local", "urls_per_channel", "lan",
                                            "legal_ack",
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


def _verify_manifest(raw, sig):
    """Ed25519 验签：raw=version.json 原始字节；sig 可以是 64 字节二进制，也可以是十六进制文本。"""
    try:
        if isinstance(sig, str):
            txt = "".join(sig.split())
            # 优先当十六进制解析；不是十六进制(比如读到了二进制签名)就按 latin-1 取回字节
            try:
                sig = bytes.fromhex(txt)
            except ValueError:
                sig = sig.encode("latin-1", "ignore")
        sig = bytes(sig)
        pk = bytes.fromhex(UPDATE_PUBKEY_HEX)
        if len(sig) != 64:
            # 有些发布工具会把 64 字节签名存成 96/128 位十六进制文本
            hexed = "".join(chr(b) for b in sig if 48 <= b <= 57 or 97 <= b <= 102 or 65 <= b <= 70)
            if len(hexed) >= 64:
                sig = bytes.fromhex(hexed[:128])
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
        # raw.githubusercontent 走 CDN，可能"清单是旧提交、签名是新提交"→ 必然验签失败。
        # 所以：两个 CDN(raw + jsDelivr)各试两轮，每个来源都加时间戳，只认能验签通过的那一对。
        base = cfg["update_url"]
        bases = []
        if "raw.githubusercontent.com/" in base:
            try:
                tail = base.split("raw.githubusercontent.com/", 1)[1]
                owner_repo, rest = tail.split("/", 1)
                repo, rest = rest.split("/", 1)
                branch, path = rest.split("/", 1)
                # 按"提交号"取文件：同一提交的 version.json 和 .sig 一定配套，
                # 也不会被 CDN 的 5 分钟缓存搞成"一半新一半旧"
                try:
                    info = json.loads(_fetch_bytes(
                        "https://api.github.com/repos/%s/%s/commits/%s" % (owner_repo, repo, branch), 12
                    ).decode("utf-8", "ignore"))
                    sha = str(info.get("sha") or "")
                    if len(sha) >= 7:
                        bases.append("https://raw.githubusercontent.com/%s/%s/%s/%s"
                                     % (owner_repo, repo, sha, path))
                except Exception:
                    pass
                bases.append(base)   # 分支地址兜底（CDN 刷新后就一致了）
                bases.append("https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % (owner_repo, repo, branch, path))
            except Exception:
                pass
        if not bases:
            bases = [base]
        raw, sig, data = None, b"", None
        for attempt in range(4):
            for b in bases:
                sep = "&" if "?" in b else "?"
                bust = "%st=%d" % (sep, int(time.time() * 1000) + attempt)
                try:
                    raw = _fetch_bytes(b + bust)
                    sig = _fetch_bytes(b + ".sig" + bust, 15)   # 64 字节二进制或十六进制文本都吃
                except Exception:
                    continue
                try:
                    data = json.loads(raw.decode("utf-8", "ignore"))
                except Exception:
                    continue
                if not cfg.get("require_sig", True) or _verify_manifest(raw, sig):
                    break
                if attempt >= 1:
                    log("升级源签名校验未通过(CDN 可能还没刷新)，换个来源再试")
            else:
                continue
            break
        if raw is None or data is None:
            log("读取升级源失败")
            return None
        if cfg.get("require_sig", True):
            if not (sig.strip() if isinstance(sig, (bytes, str)) else sig):
                log("升级源缺少签名文件(version.json.sig)，按安全策略拒绝升级")
                return None
            if not _verify_manifest(raw, sig):
                log("升级源签名校验失败，拒绝升级(升级源可能被篡改)")
                return None
        elif sig and not _verify_manifest(raw, sig):
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
            host = "0.0.0.0" if cfg.get("lan") else "127.0.0.1"
            httpd = ThreadingHTTPServer((host, p), Handler)
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

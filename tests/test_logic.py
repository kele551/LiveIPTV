# -*- coding: utf-8 -*-
"""LIVE直播源 · 判据单测（不导入主程序，避免触发建目录/读配置等顶层副作用）。

做法：用 ast 从 LIVE直播源.py 里把要测的**纯函数**摘出来单独 exec，再断言。
两类来源：Updater 的静态方法（guard_verdict / compute_stats），和模块级函数
（节目单那一批）。模块级函数互相调用、还吃模块级常量，所以摘下来的东西 exec 进
**同一个命名空间**，常量也一起摘；标准库、锁、缓存路径由测试自己塞进去。
全部断言不联网、不取当前时间、不依赖机器快慢 —— 抓取一律用桩，时刻一律用固定值。

跑法：python tests/test_logic.py
"""
import ast
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "LIVE直播源.py")
WANT_METHOD = ("guard_verdict", "compute_stats")
# 节目单一条链：归一化台名 -> 认领键 -> 解析 -> 挑此刻在播的 -> 抓一次/读缓存
WANT_FN = ("_epg_norm", "_epg_name_keys", "_epg_hhmm", "_epg_ts", "_epg_parse",
           "_epg_pick", "epg_now",
           "cctv_epg_day", "cctv_epg_days", "cctv_epg_strip_jsonp", "cctv_epg_int",
           "cctv_epg_keys", "cctv_epg_live_title", "cctv_epg_parse",
           "_cctv_epg_snapshot", "_cctv_epg_save_cache",
           "_cctv_epg_load_cache", "cctv_epg_refresh",
           "_epg_generic", "_epg_useful", "_bepg_prune", "_bepg_snapshot",
           "_bepg_save_cache", "_bepg_load_cache", "bepg_refresh",
           # 2026-11-02 新加的两条判据：繁简归一(台名对得上才有节目单)、码率按分辨率分档
           "_simplify", "_trad", "bit_floor", "low_bitrate", "quality_label",
           "_quality_stripped", "_uniq_nonempty", "_logo_cands",
           # 2026-11-02 升级通道：下载地址怎么排、镜像前缀怎么剥
           "_strip_mirror", "_update_urls")
# 函数体里会引用的模块级常量（不摘就会 NameError，摘了等于把"改了哪个数字"也测进去）
WANT_CONST = ("_EPG_NOISE", "CHANNEL_ALIAS", "CEPG_TTL", "CEPG_RETRY", "CEPG_ROLL",
              "CEPG_URL", "CEPG_CHANNELS", "CEPG_ALIAS",
              "BEPG_URLS", "BEPG_TTL", "BEPG_RETRY", "BEPG_GENERIC", "BEPG_JUNK", "UPDATE_MIRRORS",
              # 2026-11-02：繁简表、码率分档表、以及"哪条源默认开"这张表
              "_TRAD_S2T", "_T2S", "_QUAL_DEC", "BIT_FLOOR",
              "CLARITY_HEIGHT", "CLARITY_MBPS", "SOURCES")

fails = []


def check(name, got, exp):
    ok = got == exp
    print("  [%s] %-42s got=%r exp=%r" % ("通过" if ok else "失败", name, got, exp))
    if not ok:
        fails.append(name)


def grab():
    """摘出要测的函数/常量，exec 进同一个命名空间返回。"""
    tree = ast.parse(io.open(SRC, encoding="utf-8").read(), filename=SRC)
    ns = {"re": re, "json": json, "time": time,
          "unicodedata": unicodedata, "datetime": datetime,
          "threading": threading, "log": lambda m: None}
    found = set()
    for node in tree.body:                       # 模块级：函数 + 常量（按源码顺序）
        if isinstance(node, ast.FunctionDef) and node.name in WANT_FN:
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not any(t in WANT_CONST for t in targets):
                continue
            found.update(targets)
        else:
            continue
        mod = ast.Module(body=[node], type_ignores=[])
        ast.fix_missing_locations(mod)
        exec(compile(mod, SRC, "exec"), ns)
    for node in ast.walk(tree):                  # 类里的静态方法：各自独立，也丢进同一个 ns
        if not isinstance(node, ast.ClassDef):
            continue
        for sub in node.body:
            if isinstance(sub, ast.FunctionDef) and sub.name in WANT_METHOD:
                mod = ast.Module(body=[sub], type_ignores=[])
                ast.fix_missing_locations(mod)
                exec(compile(mod, SRC, "exec"), ns)
                found.add(sub.name)
    missing = [w for w in WANT_METHOD + WANT_FN + WANT_CONST if w not in found]
    if missing:
        raise SystemExit("源码里没找到这些函数/常量，测试先失效: %s" % missing)
    # 两份缓存的运行时状态由测试自己给（函数体是按名字读全局的，所以放进 ns 就行）
    ns["_EPG_LOCK"] = threading.Lock()
    ns["_CEPG_LOCK"] = threading.Lock()
    ns["_EPG"] = {"ok": False, "msg": "", "url": "", "fetched": 0.0, "count": 0,
                  "progs": {}, "by_name": {}, "next_try": 0.0}
    ns["_CEPG"] = {"ok": False, "msg": "内置节目单还没开始抓", "fetched": 0.0,
                   "next_try": 0.0, "progs": {}, "by_name": {}, "names": {},
                   "count": 0, "days": ""}
    ns["CEPG_CACHE_PATH"] = Path(os.path.join(tempfile.mkdtemp(prefix="live_cepg_"),
                                             "cctv_epg_cache.json"))
    ns["_BEPG_LOCK"] = threading.Lock()
    ns["_BEPG"] = {"ok": False, "msg": "内置第三方节目表还没开始抓", "fetched": 0.0,
                   "next_try": 0.0, "progs": {}, "by_name": {}, "count": 0, "url": ""}
    ns["BEPG_CACHE_PATH"] = Path(os.path.join(tempfile.mkdtemp(prefix="live_bepg_"),
                                              "builtin_epg_cache.json"))
    return ns


def ch(group="央视", nsrc=1):
    return {"group": group, "sources": [{"url": "http://x/%d" % i} for i in range(nsrc)]}


def ssl_sites():
    """扫源码里每一个 urlopen(...)，返回 [(所在函数名, context 实参名), ...]。

    为什么按 AST 扫而不是数文本：抓列表与升级下载用的是同一个 urlopen 写法，
    以前一个 _SSL_CTX 通吃 7 处，"哪一处该严格"只存在于注释里。
    2026-10-26 拆出 _SSL_STRICT（只给自更新通道）之后，得有一条**不联网**的闸门
    盯着这个分工，别哪天被"顺手统一一下"改回去。
    """
    src = io.open(SRC, encoding="utf-8").read()
    tree = ast.parse(src, filename=SRC)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "urlopen":
            continue
        fname, cur = "", node
        while cur is not None:
            if isinstance(cur, ast.FunctionDef):
                fname = cur.name
                break
            cur = parents.get(cur)
        ctx = ""
        for kw in (node.keywords or []):
            if kw.arg == "context" and isinstance(kw.value, ast.Name):
                ctx = kw.value.id
        out.append((fname, ctx))
    return out


def settings_keys():
    """POST /api/settings 的白名单元组（`new = {k: data[k] for k in (...) if k in data}`）。

    为什么要单独摘出来：白名单是"前端发了服务端才认"的那道闸。页面多发一个键、
    或者服务端白名单忘了加，配置就会**静默存不进去** —— 点保存提示成功、重启又回到原样。
    v1.4.1 的升级按钮就是这类"两头各自对不上"的毛病，那次靠路由闸门挡住，这次靠这条。
    """
    tree = ast.parse(io.open(SRC, encoding="utf-8").read(), filename=SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.DictComp) and node.generators:
            it = node.generators[0].iter
            if (isinstance(it, ast.Tuple)
                    and all(isinstance(e, ast.Constant) and isinstance(e.value, str)
                            for e in it.elts)):
                vals = {e.value for e in it.elts}
                if "interval_hours" in vals or "epg_url" in vals:
                    return vals
    raise SystemExit("源码里找不到 /api/settings 的白名单元组，测试先失效")


PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_page.html")


def handler_routes():
    """do_GET / do_POST 各自认领了哪些路径（只认 `path == "/x"` 和 `path.startswith("/x")`）。"""
    tree = ast.parse(io.open(SRC, encoding="utf-8").read(), filename=SRC)
    out = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in ("do_GET", "do_POST")):
            continue
        got = set()
        for n in ast.walk(node):
            if (isinstance(n, ast.Compare) and isinstance(n.left, ast.Name)
                    and n.left.id == "path"):
                for op, c in zip(n.ops, n.comparators):
                    if isinstance(op, ast.Eq) and isinstance(c, ast.Constant) \
                            and isinstance(c.value, str):
                        got.add(c.value)
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "startswith"
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "path"
                    and n.args and isinstance(n.args[0], ast.Constant)):
                got.add(n.args[0].value + "*")
        out[node.name] = got
    missing = [k for k in ("do_GET", "do_POST") if k not in out]
    if missing:
        raise SystemExit("源码里没有这些方法，测试先失效: %s" % missing)
    return out


def page_calls():
    """页面里每一个 fetch，按 (方法, 路径) 返回。不写 method 就是 GET。

    只看 fetch 自己的第二个实参（配对花括号那一段），不往后数正文：
    窗口开大了会把下一个 fetch 的 method 算到头上，把 GET 判成 POST，
    这条闸门就会朝"永远通过"或"永远失败"漂移。
    """
    src = io.open(PAGE, encoding="utf-8").read()
    out = []
    for m in re.finditer(r"""fetch\(\s*(['"])(/[^'"]*)\1""", src):
        url = m.group(2)
        opts = ""
        nxt = src.find(",", m.end())
        brace = src.find("{", m.end())
        if nxt != -1 and (brace == -1 or nxt < brace) and (nxt - m.end()) <= 4:
            j = src.find("{", nxt)
            depth = 0
            for k in range(j, min(j + 2000, len(src))):
                if src[k] == "{":
                    depth += 1
                elif src[k] == "}":
                    depth -= 1
                    if depth == 0:
                        opts = src[j:k + 1]
                        break
        mm = re.search(r"""method:\s*['"](\w+)['"]""", opts)
        out.append(((mm.group(1).upper() if mm else "GET"), url))
    return out


def main():
    ns = grab()
    gv, cs = ns["guard_verdict"], ns["compute_stats"]

    print("-" * 70)
    print("1. 缓存守卫 guard_verdict：本轮结果能不能覆盖上轮（空串=可以）")
    check("首次运行（上轮 0）→ 照旧写入", gv(0, 0), "")
    check("上轮 0、本轮有 → 照旧写入", gv(0, 120), "")
    check("本轮为空 → 不覆盖", gv(120, 0), "本轮没抓到任何频道")
    check("掉一半整（60/120）→ 可以覆盖", gv(120, 60), "")
    check("差一点过半（59/120）→ 不覆盖", gv(120, 59),
          "本轮只剩 59 个频道（上轮 120 个），掉得太狠")
    check("正常小掉（118/120）→ 可以覆盖", gv(120, 118), "")
    check("变多（200/120）→ 可以覆盖", gv(120, 200), "")

    print("-" * 70)
    print("2. compute_stats：统计口径没被守卫改动带歪")
    d = {"a": ch("央视"), "b": ch("卫视", 0), "c": ch("香港")}
    st = cs(d)
    check("频道数", st["channels"], 3)
    check("有源的频道数(可用)", st["live"], 2)
    check("源总数", st["sources"], 2)
    check("港澳台数", st["hkmt"], 1)
    check("空输入不炸", cs({})["channels"], 0)

    print("-" * 70)
    print("3. TLS 分工：升级通道严格校验，抓列表/台标/EPG/测流保持宽松")
    sites = ssl_sites()
    strict = sorted(n for n, c in sites if c == "_SSL_STRICT")
    lenient = sorted(n for n, c in sites if c == "_SSL_CTX")
    # 2026-11-02：升级包的下载从 apply_self_update 里拆成了 _fetch_update_blob（分块读 + 总时限 +
    # 多地址重试），严格 TLS 仍然只出现在"读升级清单"和"下升级包"这两处，没有扩散到别处。
    check("走 _SSL_STRICT 的就是升级那两处", strict,
          ["_fetch_bytes", "_fetch_update_blob"])
    check("升级那两处不再吃 _SSL_CTX",
          [c for n, c in sites if n in ("_fetch_bytes", "_fetch_update_blob") and c == "_SSL_CTX"], [])
    check("其余五处仍是 _SSL_CTX", lenient,
          ["_check_logo", "_epg_fetch", "_grab", "_open", "one"])
    check("每个 urlopen 都显式写了 context（没有默认裸连）",
          len([1 for n, c in sites if c not in ("_SSL_CTX", "_SSL_STRICT")]), 0)

    print("-" * 70)
    print("4. 页面按钮 ↔ 服务端路由：fetch 的方法必须真有人接（不联网）")
    rt = handler_routes()
    calls = sorted(set(page_calls()))
    orphan_get = sorted(u for mth, u in calls if mth == "GET" and u not in rt["do_GET"])
    orphan_post = sorted(u for mth, u in calls
                         if mth == "POST" and u not in rt["do_POST"])
    check("页面里所有 GET fetch 都在 do_GET 里", orphan_get, [])
    check("页面里所有 POST fetch 都在 do_POST 里", orphan_post, [])
    # 2026-10-26 实测：1.4.1 控制台点「下载并升级」回 {"ok":false,"msg":"not found"}。
    # 页面从 v1.3.0 起就是 POST，而这段代码一直只挂在 do_GET 里 —— 升级按钮从来没生效过。
    # 下面两条就是把这次的坑钉住：按钮接口必须在 do_POST，且不能回到 do_GET
    # （do_GET 没有 _same_origin() 这道闸，任何页面 <img src=...> 都能触发下载+退出进程）。
    check("升级接口挂在 do_POST（页面按钮用的就是 POST）",
          "/api/selfupdate" in rt["do_POST"], True)
    check("升级接口不在 do_GET（GET 无同源校验，太危险）",
          "/api/selfupdate" in rt["do_GET"], False)
    check("POST-only 的接口别被顺手加回 GET",
          sorted(u for u in ("/api/quit", "/api/open", "/api/pickdir", "/api/export")
                 if u in rt["do_GET"]), [])
    # 节目单：页面只 GET(读缓存)，刷新走 POST —— 两边都得有人接，
    # 2026-11-02 内置节目单加进来时最容易漏的就是"POST 只刷了自定义那一份"。
    check("节目单 GET 读缓存、POST 能刷新（两条路由都在）",
          ("/api/epg" in rt["do_GET"], "/api/epg" in rt["do_POST"]), (True, True))

    print("-" * 70)
    print("5. 内置央视频目单：接口脾气（JSONP、参数、脏数据）")
    strip, ci = ns["cctv_epg_strip_jsonp"], ns["cctv_epg_int"]
    check("JSONP 剥壳", strip("t({\"a\":1});"), '{"a":1}')
    check("本来就是 JSON 也能过", strip('{"a": 1}'), '{"a": 1}')
    check("空响应不炸", strip(""), "")
    check("时长字段按秒读", ci(2640), 2640)
    check("万一改成 \"44:00\" 这种串也认", ci("44:00"), 2640)
    check("读不懂就当 0（不牵连别的字段）", ci("abc"), 0)
    check("None 当 0", ci(None), 0)
    ids = list(ns["CEPG_CHANNELS"])
    check("频道表没有重复 id", sorted(set(ids)) == sorted(ids), True)
    # 实测：c= 里混一个官方不认的 id 会整包 errcode 1001 —— 这几个是踩过的雷，永远别加回来
    check("官方不认的 id 一个都不在表里",
          sorted(set(ids) & {"cctv9", "cctv14", "beijing", "hainan", "fujian",
                             "neimeng", "kaiwen"}), [])
    check("央视+卫视都在（40 个上下，一次请求拿回）", len(ids) >= 35, True)
    check("每个频道都拼在同一个 URL 上（不逐个请求）",
          ns["CEPG_URL"].count("%s"), 2)

    print("-" * 70)
    print("6. 认台：官方台名写法不统一，靠 keys + 别名表兜住")
    norm, keys = ns["_epg_norm"], ns["cctv_epg_keys"]
    ks = keys("CCTV-5+ 体育赛事", "cctv5plus")
    check("CCTV-5+ 认官方全名", norm("CCTV5+ 体育赛事") in ks, True)
    check("CCTV-5+ 认接口 id", "cctv5plus" in ks or "cctv5+" in ks, True)
    check("抠短号时 + 必须跟着走（别把 cctv5 抢了）", "cctv5" not in ks, True)
    check("CCTV-16 抠出 cctv16", "cctv16" in keys("CCTV-16奥林匹克", "cctv16"), True)
    check("CCTV-1 抠出 cctv1", "cctv1" in keys("CCTV-1 综合", "cctv1"), True)
    seen, clash = {}, []
    for cid in ns["CEPG_ALIAS"]:
        for k in ns["CEPG_ALIAS"][cid]:
            n = norm(k)
            if not n:
                clash.append((k, cid, "归一后是空串"))
            elif n in seen and seen[n] != cid:
                clash.append((n, seen[n], cid))
            else:
                seen.setdefault(n, cid)
    check("别名归一后不互相撞车（两个台抢同一个键就是认错台）", clash, [])
    check("别名归一后非空（写法被噪音规则吃光的键要丢掉）",
          [k for cid in ns["CEPG_ALIAS"] for k in ns["CEPG_ALIAS"][cid] if not norm(k)], [])

    payload = {"data": {
        "cctv1": {"channelName": "CCTV-1 综合", "list": [
            {"title": "晚间新闻", "startTime": 2000, "endTime": 3800, "length": 1800},
            {"title": "焦点访谈", "startTime": 1000, "endTime": 0, "length": 1200},
            {"title": "", "startTime": 9000, "endTime": 9600},
            {"title": "没时刻", "startTime": 0, "endTime": 0},
            {"title": "倒挂", "startTime": 5000, "endTime": 4000},
        ]},
        "cctvjilu": {"channelName": "CCTV-9 纪录", "list": [
            {"title": "全景自然", "startTime": 1000, "endTime": 4000},
        ]},
        "hunan": {"channelName": "湖南卫视", "list": [
            {"title": "歌手", "startTime": 1000, "endTime": 3000},
        ]},
        "dead": {"channelName": "空台", "list": []},
    }}
    progs, names, by_name = ns["cctv_epg_parse"](payload)
    check("空表频道丢掉", sorted(progs), ["cctv1", "cctvjilu", "hunan"])
    check("cctv1 有效条目 3 条", len(progs["cctv1"]), 3)
    check("按开始时间升序", [r[0] for r in progs["cctv1"]], [1000, 2000, 5000])
    check("没 endTime 用 length 补", progs["cctv1"][0][1], 2200)
    check("结束早于开始 → 按 1 小时", progs["cctv1"][2][1], 8600)
    check("官方台名也登记", by_name[norm("CCTV-1 综合")], "cctv1")
    check("纪录频道靠别名认成 CCTV-9", by_name[norm("CCTV-9")], "cctvjilu")
    check("少儿/纪录这类别名不会覆盖官方自己的键", by_name[norm("湖南卫视")], "hunan")
    check("台名表给日志用", names["cctvjilu"], "CCTV-9 纪录")

    print("-" * 70)
    print("7. 取哪几天：默认今天，快到点子顺手把明天也取回来")
    def at(h, m):
        return datetime(2026, 11, 2, h, m).timestamp()
    check("20:00 只取今天", ns["cctv_epg_days"](at(20, 0)), "20261102")
    check("22:30 连明天一起取", ns["cctv_epg_days"](at(22, 30)), "20261102+20261103")
    check("23:59 连明天一起取", ns["cctv_epg_days"](at(23, 59)), "20261102+20261103")
    check("00:00 也算只剩不到 2 小时？看的是当天剩余（1 天差）",
          ns["cctv_epg_days"](at(0, 0)), "20261102")
    check("跨天时明天的日期真的加了一天",
          ns["cctv_epg_day"](at(23, 30), 1), "20261103")

    print("-" * 70)
    print("8. 此刻在播什么：自定义 XMLTV > 央视官方(有具体名) > 公开节目表 > 官方大类词")
    pick = ns["_epg_pick"]
    tbl = {"cctv1": [(1000, 2000, "甲"), (2000, 3000, "乙")]}
    bidx = {norm("CCTV-1 综合"): "cctv1"}
    got = pick(tbl, bidx, {"name": "CCTV-1 综合"}, 1500, "cctv")
    check("命中在播的那档", (got or {}).get("t"), "甲")
    check("进度算到 50%", (got or {}).get("p"), 50.0)
    check("带上来源标记", (got or {}).get("src"), "cctv")
    check("结束时刻留给前端画进度条", (got or {}).get("e0"), 2000)
    check("整点边界取下一条", pick(tbl, bidx, {"name": "CCTV-1 综合"}, 2000, "cctv")["t"], "乙")
    check("还没开始 → 空", pick(tbl, bidx, {"name": "CCTV-1 综合"}, 500, "cctv"), None)
    check("全播完了 → 空", pick(tbl, bidx, {"name": "CCTV-1 综合"}, 4000, "cctv"), None)
    check("台名对不上 → 空", pick(tbl, bidx, {"name": "县融媒"}, 1500, "cctv"), None)
    check("空表直接返回空", pick({}, {}, {"name": "CCTV-1 综合"}, 1500, "cctv"), None)
    now = 1500.0
    ns["_CEPG"].update(ok=True, progs=tbl, by_name=bidx, names={"cctv1": "CCTV-1 综合"},
                       count=1, days="20261102", fetched=now, next_try=0.0, msg="")
    epg_now = ns["epg_now"]
    check("只有内置时也能出字", epg_now({"name": "CCTV-1 综合"}, now)["src"], "cctv")
    ns["_EPG"].update(ok=True, progs={"cctv1": [(1000, 2000, "自定义甲")]},
                      by_name={norm("CCTV-1 综合"): "cctv1"}, count=1, fetched=now)
    check("用户填的 XMLTV 优先", epg_now({"name": "CCTV-1 综合"}, now)["t"], "自定义甲")
    check("优先的那条也带来源", epg_now({"name": "CCTV-1 综合"}, now)["src"], "custom")
    ns["_EPG"].update(ok=False, progs={}, by_name={})
    check("自定义挂了 → 内置顶上", epg_now({"name": "CCTV-1 综合"}, now)["src"], "cctv")
    # 官方对卫视常常只写一个大类词("电视剧")，用户 2026-11-02 的话：「关键显示好多都是电视剧，
    # 没有节目名字」—— 这类才允许换成内置的公开节目表，官方给了具体名字的一律不动。
    ns["_CEPG"].update(ok=True, progs={"hunan": [(1000, 2000, "电视剧")]},
                       by_name={norm("湖南卫视"): "hunan"}, names={"hunan": "湖南卫视"},
                       count=1, days="20261102", fetched=now, next_try=0.0, msg="")
    ns["_BEPG"].update(ok=True, progs={"hunan": [(1000, 2000, "梅花儿香(18)")]},
                       by_name={norm("湖南卫视"): "hunan"}, count=1, fetched=now, msg="")
    check("官方只给大类词时换成公开表", epg_now({"name": "湖南卫视"}, now)["t"], "梅花儿香(18)")
    check("换过去也标来源", epg_now({"name": "湖南卫视"}, now)["src"], "builtin")
    ns["_BEPG"].update(progs={"hunan": [(1000, 2000, "请欣赏康巴卫视精彩节目")]})
    check("公开表是占位档就别换", epg_now({"name": "湖南卫视"}, now)["t"], "电视剧")
    check("占位档那条不算换了来源", epg_now({"name": "湖南卫视"}, now)["src"], "cctv")
    ns["_CEPG"].update(ok=True, progs={"shanxi": [(1000, 2000, "阳光剧场")]},
                       by_name={norm("山西卫视"): "shanxi"}, count=1)
    ns["_BEPG"].update(progs={}, by_name={})
    check("公开表也没了 → 退回官方那句大类词", epg_now({"name": "山西卫视"}, now)["t"], "阳光剧场")
    ns["_CEPG"].update(progs={}, by_name={})
    check("两份内置都没有 → 空", epg_now({"name": "县融媒"}, now), None)
    ns["_CEPG"].update(ok=True, progs=tbl, by_name=bidx, names={"cctv1": "CCTV-1 综合"},
                       count=1)

    print("-" * 70)
    print("9. 抓一轮 cctv_epg_refresh（打桩，不联网）：缓存/退让/关掉清空")
    calls = []
    body = ("t(%s);" % json.dumps(payload, ensure_ascii=False)).encode("utf-8")

    def fake_fetch(url, timeout=20):
        calls.append(url)
        if fake_fetch.bad:
            return b'{"errcode":"1001","msg":"params error"}'
        return body

    fake_fetch.bad = False
    ns["_epg_fetch"] = fake_fetch
    cfg = {"cctv_epg": True}
    for k in list(ns["_CEPG"]):
        ns["_CEPG"][k] = {} if k in ("progs", "by_name", "names") else 0.0
    ns["_CEPG"].update(ok=False, msg="内置节目单还没开始抓", next_try=0.0, days="")
    day0 = at(12, 0)
    check("第一轮抓到", ns["cctv_epg_refresh"](cfg, now=day0), True)
    snap = ns["_cctv_epg_snapshot"]()
    check("只请求了一次（40 个台拼一起）", len(calls), 1)
    check("URL 里带着频道表和本地日期",
          ("cctv1" in calls[0]) and ("20261102" in calls[0]), True)
    check("状态 ok", (snap["ok"], snap["msg"]), (True, ""))
    check("频道数", snap["count"], 3)
    check("接口台数（日志/设置里那句要用）", snap["channels"], 3)
    check("缓存里的日期", snap["days"], "20261102")
    check("TTL 内再叫不重复请求", ns["cctv_epg_refresh"](cfg, now=day0 + 600), True)
    check("请求次数没涨", len(calls), 1)
    check("过期后才重取", ns["cctv_epg_refresh"](cfg, now=day0 + ns["CEPG_TTL"] + 1), True)
    check("重取了一次", len(calls), 2)
    # 缓存落盘 → 重启复用（同一天没过期就不该再打官方接口）
    ns["_CEPG"].update(ok=False, progs={}, by_name={}, names={}, count=0, days="",
                       fetched=0.0, msg="内置节目单还没开始抓")
    check("重启后复用磁盘缓存", ns["_cctv_epg_load_cache"](day0 + 60), True)
    check("复用后频道数对得上", ns["_cctv_epg_snapshot"]()["count"], 3)
    check("复用磁盘缓存不需要再请求", len(calls), 2)
    stale = json.loads(ns["CEPG_CACHE_PATH"].read_text(encoding="utf-8"))
    stale["days"] = "19700101"
    ns["CEPG_CACHE_PATH"].write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
    check("日期不是这一轮的缓存不认", ns["_cctv_epg_load_cache"](day0 + 60), False)
    # 抓取失败：旧数据继续顶着，只把下次重试时间往后推
    fake_fetch.bad = True
    fail_at = day0 + ns["CEPG_TTL"] + 2
    ns["_CEPG"].update(ok=True, progs=tbl, by_name=bidx, names={"cctv1": "CCTV-1 综合"},
                       count=1, days="20261102", fetched=fail_at - 10, next_try=0.0, msg="")
    check("参数报错这轮判失败", ns["cctv_epg_refresh"](cfg, force=True, now=fail_at), False)
    snap = ns["_cctv_epg_snapshot"]()
    check("旧的节目表没被清空", snap["count"], 1)
    check("失败后按 CEPG_RETRY 退让", snap["next_try"], fail_at + ns["CEPG_RETRY"])
    check("退让期间不再打接口(旧缓存直接顶上)",
          ns["cctv_epg_refresh"](cfg, now=fail_at + 60), True)
    check("退让期间没有白打的请求", len(calls), 3)
    # 关掉：缓存立刻清空，界面回到"未启用"
    fake_fetch.bad = False
    ns["cctv_epg_refresh"]({"cctv_epg": False}, force=True, now=fail_at)
    snap = ns["_cctv_epg_snapshot"]()
    check("关掉后状态不再 ok", snap["ok"], False)
    check("关掉后清空节目表", snap["count"], 0)
    check("关掉后写着原因", snap["msg"], "内置节目单已关闭")
    check("关掉后线程也不会偷偷去抓", ns["cctv_epg_refresh"]({"cctv_epg": False}, now=fail_at), False)

    print("-" * 70)
    print("10. 设置页那个开关：前端发的键服务端必须认（否则保存了等于没保存）")
    sk = settings_keys()
    psrc = io.open(PAGE, encoding="utf-8").read()
    check("白名单里有 cctv_epg", "cctv_epg" in sk, True)
    check("白名单里有 epg_url", "epg_url" in sk, True)
    check("页面把 cctv_epg 发给服务端", "cctv_epg:$(\"c_cepg\")" in psrc.replace(" ", ""), True)
    check("页面有内置节目单勾选框", 'id="c_cepg"' in psrc, True)
    check("页面把开关初值读回勾选框", '$("c_cepg").checked=c.cctv_epg' in psrc.replace(" ", ""), True)
    check("设置里显示内置节目单状态", 'id="cepgHint"' in psrc, True)
    check("状态读的是 /api/epg 的 cctv 段", "EPMETA.cctv" in psrc.replace(" ", ""), True)
    check("服务端 /api/epg 回了 cctv 段", '"cctv": cmeta' in io.open(SRC, encoding="utf-8").read(), True)
    check("手动刷新两条来源都要刷",
          io.open(SRC, encoding="utf-8").read().count("threading.Thread(target=epg_refresh"), 2)

    print("-" * 70)
    print("11. 接线：线程起了、手动刷新带上它、GET 不联网（少一处就是「功能在但看不见」）")
    srctxt = io.open(SRC, encoding="utf-8").read()

    def method_body(name):
        m = re.search(r"\n    def %s\((?:self[^\n]*)\n(.*?)(?=\n    def |\nclass |\Z)" % name,
                      srctxt, re.S)
        return m.group(1) if m else ""

    check("找到 do_POST 正文", bool(method_body("do_POST")), True)
    check("手动刷新把三份节目单一起刷",
          ("target=epg_refresh" in method_body("do_POST"),
           "target=cctv_epg_refresh" in method_body("do_POST"),
           "target=bepg_refresh" in method_body("do_POST")), (True, True, True))
    check("改设置里的开关也会重抓/清空",
          "_prev_cepg" in method_body("do_POST"), True)
    check("开关换了要连第三方那份一起退让",
          '_BEPG["next_try"] = 0.0' in method_body("do_POST"), True)
    check("GET 回了内置节目单的状态段", '"cctv": cmeta' in method_body("do_GET"), True)
    check("GET 也回了第三方那份的状态段", '"bepg": bmeta' in method_body("do_GET"), True)
    check("GET 自己不动网络（只读缓存）",
          [n for n in ("_epg_fetch", "cctv_epg_refresh", "bepg_refresh")
           if n in method_body("do_GET")], [])
    check("GET 每轮都过一遍几份来源（走的是 epg_now）", "epg_now(" in method_body("do_GET"), True)
    check("启动时起了内置节目单线程",
          srctxt.count("threading.Thread(target=cctv_epg_loop"), 1)
    check("启动时也起了第三方节目表线程",
          srctxt.count("threading.Thread(target=bepg_loop"), 1)
    check("内置线程和 XMLTV 线程都是 daemon（不挡退出）",
          srctxt.count("target=cctv_epg_loop, args=(cfg,), daemon=True"), 1)
    check("第三方那份也是 daemon",
          srctxt.count("target=bepg_loop, args=(cfg,), daemon=True"), 1)
    check("缓存文件写在程序目录里（重启不重复抓）",
          "cctv_epg_cache.json" in srctxt, True)
    check("第三方那份也落盘（5MB 的东西不该每次重启都下一遍）",
          "builtin_epg_cache.json" in srctxt, True)
    check("设置项默认开（用户零配置就有节目单）",
          '"cctv_epg": True' in srctxt, True)

    print("-" * 70)
    print("12. 认台覆盖：官方台名写法不统一，40 个频道都得被 by_name 认领")
    # 2026-11-02 实测回执：c= 一次带上这 40 个 id，官方回的 channelName 就是下面这些写法。
    # 把名单抄进测试是有意的 —— 想加台或官方改了写法，这份表不跟着改就会红，
    # 逼着改的人先去核一遍新 id 认不认（混进一个不认的 id 是整包 errcode 1001）。
    live_names = {
        "cctv1": "CCTV-1 综合", "cctv2": "CCTV-2 财经", "cctv3": "CCTV-3 综艺",
        "cctv4": "CCTV-4 (亚洲)", "cctv5": "CCTV-5 体育", "cctv5plus": "CCTV-5+ 体育赛事",
        "cctv6": "CCTV-6 电影", "cctv7": "CCTV-7 国防军事", "cctv8": "CCTV-8 电视剧",
        "cctv10": "CCTV-10 科教", "cctv11": "CCTV-11 戏曲", "cctv12": "CCTV-12 社会与法",
        "cctv13": "CCTV-13 新闻", "cctv15": "CCTV-15 音乐", "cctv16": "CCTV-16奥林匹克",
        "cctv17": "CCTV-17农业农村", "cctvchild": "CCTV-14 少儿", "cctvjilu": "CCTV-9 纪录",
        "hunan": "湖南卫视", "zhejiang": "浙江卫视", "dongfang": "东方卫视",
        "jiangsu": "江苏卫视", "shenzhen": "深圳卫视", "guangdong": "广东卫视",
        "liaoning": "辽宁卫视", "sichuan": "四川卫视", "chongqing": "重庆卫视",
        "anhui": "安徽卫视", "hubei": "湖北卫视", "shandong": "山东卫视",
        "hebei": "河北卫视", "tianjin": "天津卫视", "jiangxi": "江西卫视",
        "xizang": "西藏卫视", "yunnan": "云南卫视", "guizhou": "贵州卫视",
        "ningxia": "宁夏卫视", "qinghai": "青海卫视", "jilin": "吉林卫视",
        "guangxi": "广西卫视", "btv1": "北京卫视", "dongnan": "东南卫视",
        "henan": "河南卫视", "gansu": "甘肃卫视", "neimenggu": "内蒙古卫视",
        "bingtuan": "兵团卫视", "xiamen": "厦门卫视",
        "cctv4k": "CCTV-4K", "cctv8k": "CCTV-8K",
        "shijiedili": "CCTV世界地理", "fyyy": "CCTV风云音乐", "fyjc": "CCTV风云剧场",
        "hjjc": "CCTV怀旧剧场", "diyijuchang": "CCTV第一剧场", "cctvfyzq": "CCTV风云足球",
        "taiqiu": "CCTV央视台球", "shishang": "CCTV女性时尚", "jingpin": "CCTV央视文化精品",
        "zhinan": "CCTV电视指南", "cctvliyuan": "梨园", "gaoerfu": "高尔夫",
    }
    check("频道表和实测回执一致（加台要先验证官方认不认）",
          sorted(live_names), sorted(ns["CEPG_CHANNELS"]))
    big = {"data": {cid: {"channelName": nm,
                          "list": [{"title": "甲", "startTime": 1000, "endTime": 2000},
                                   {"title": "乙", "startTime": 2000, "endTime": 3000}]}
                    for cid, nm in live_names.items()}}
    b_progs, b_names, b_idx = ns["cctv_epg_parse"](big)
    check("命中整张频道表", sorted(b_progs), sorted(ns["CEPG_CHANNELS"]))
    check("每个官方台名都登记了",
          [cid for cid, nm in live_names.items() if b_idx.get(norm(nm)) != cid], [])
    check("混叫也认：CCTV-9 → 纪录", b_idx.get(norm("CCTV-9")), "cctvjilu")
    check("混叫也认：CCTV-14 → 少儿", b_idx.get(norm("CCTV-14")), "cctvchild")
    check("4K 有自己的真 id，不再挂到 CCTV-16 名下", b_idx.get(norm("CCTV4K")), "cctv4k")
    check("CCTV-4K 的 4 不会抢走 CCTV-4",
          "cctv4" in ns["cctv_epg_keys"]("CCTV-4K", "cctv4k"), False)
    check("CCTV-4 还是中文国际自己", b_idx.get(norm("CCTV-4")), "cctv4")
    check("付费频道官方带 CCTV 前缀，列表里的裸名也认得上",
          [b_idx.get(norm(x)) for x in ("世界地理", "风云音乐", "女性时尚", "央视台球",
                                        "怀旧剧场", "央视文化精品", "第一剧场", "电视指南")],
          ["shijiedili", "fyyy", "shishang", "taiqiu", "hjjc", "jingpin",
           "diyijuchang", "zhinan"])
    check("北京卫视走 btv1（beijing 这个 id 官方不认）", b_idx.get(norm("北京卫视")), "btv1")
    # 卫视的 list.title 常常只有大类，同一份回包里的 isLive 才是细的 —— 此刻那一档要换成 isLive
    lt = ns["cctv_epg_live_title"]
    check("isLive 更细就换上", lt([(1000, 2000, "电视剧")], "电视剧：问心2第17集", 1500),
          [(1000, 2000, "电视剧：问心2第17集")])
    check("isLive 不比原标题细就不动", lt([(1000, 2000, "焦点访谈")], "新闻", 1500),
          [(1000, 2000, "焦点访谈")])
    check("isLive 的时刻不在这一档就不动", lt([(1000, 2000, "电视剧")], "电视剧：问心2", 2500),
          [(1000, 2000, "电视剧")])
    check("没有 isLive 原样返回", lt([(1000, 2000, "电视剧")], "", 0), [(1000, 2000, "电视剧")])
    check("混叫也认：CCTV体育赛事 → 5+", b_idx.get(norm("CCTV体育赛事")), "cctv5plus")
    check("卫视按原名直接对上",
          (b_idx.get(norm("湖南卫视")), b_idx.get(norm("东方卫视"))), ("hunan", "dongfang"))
    check("别名 CCTV-9纪录 也认", b_idx.get(norm("CCTV-9纪录")), "cctvjilu")
    # 真列表里的常见写法：官方叫"CCTV-1 综合"，列表里可能写"CCTV-1综合频道"——
    # 挑此刻在播的那一条要用的是同一套键，所以这类写法也能认上。
    check("列表写法差一个「频道」也认得上",
          ns["_epg_pick"](b_progs, b_idx, {"name": "CCTV-1综合频道"}, 1500, "cctv")["t"], "甲")
    check("列表写 CCTV1（没有横线）也认得上",
          ns["_epg_pick"](b_progs, b_idx, {"name": "CCTV1"}, 1500, "cctv")["t"], "甲")

    print("-" * 70)
    print("13. 内置第三方节目表：什么时候换、怎么抓、抓不到怎么办（打桩，不联网）")
    gen, use = ns["_epg_generic"], ns["_epg_useful"]
    check("整句只是大类词 → 该换", gen("电视剧"), True)
    check("带前后空格也算", gen("  纪录片 "), True)
    check("「电视剧：问心2第17集」是具体名字，不换", gen("电视剧：问心2第17集"), False)
    check("「梅花儿香(18)」不是大类词", gen("梅花儿香(18)"), False)
    check("空串不当大类词（交给上层自己判）", gen(""), False)
    check("正常档名有用", use("神枪之倒刺(20)"), True)
    check("剧场名也算有用（总比空着强）", use("上午剧场"), True)
    check("「请欣赏××卫视精彩节目」是占位档", use("请欣赏康巴卫视精彩节目"), False)
    check("「敬请期待」是占位档", use("敬请期待"), False)
    check("空档名不算有用", use(""), False)
    prune = ns["_bepg_prune"]
    mid = at(12, 0)
    # 「太晚」那条开始于此刻 +37 小时，已在 36 小时窗口之外；
    # （写成 +35 是错的：它确实还在窗口里，剪掉反而不对。）
    check("只留此刻前 12 小时到后 36 小时",
          prune({"x": [(mid - 13 * 3600, mid - 12 * 3600 - 60, "太早"),
                        (mid - 11 * 3600, mid - 10 * 3600, "留着"),
                        (mid + 37 * 3600, mid + 39 * 3600, "太晚")]}, mid),
          {"x": [(mid - 11 * 3600, mid - 10 * 3600, "留着")]})
    check("整台都被剪掉就不留这个键", prune({"x": [(mid + 40 * 3600, mid + 41 * 3600, "晚")]}, mid), {})
    check("两个地址：主 Cloudflare、备 GitHub Pages",
          [u.split("/")[2] for u in ns["BEPG_URLS"]],
          ["epg.zsdc.eu.org", "suzukua.github.io"])
    check("都是 https", [u.startswith("https://") for u in ns["BEPG_URLS"]], [True, True])

    xmltv = (u'<?xml version="1.0"?><tv>'
             u'<channel id="湖南卫视"><display-name>湖南卫视</display-name></channel>'
             u'<channel id="CCTV1"><display-name>CCTV1</display-name></channel>'
             u'<programme channel="湖南卫视" start="20261102100000" stop="20261102110000">'
             u'<title>梅花儿香(18)</title></programme>'
             u'<programme channel="CCTV1" start="20261102101200" stop="20261102110100">'
             u'<title>江海潮生2/30</title></programme>'
             u'<programme channel="CCTV1" start="20261102230000" stop="20261103010000">'
             u'<title>太晚了剪掉</title></programme>'
             u'</tv>').encode("utf-8")
    bcalls = []

    def fake_bfetch(url, timeout=20):
        bcalls.append(url)
        if url == ns["BEPG_URLS"][0] and fake_bfetch.bad_first:
            raise OSError("主地址抽风")
        return xmltv

    fake_bfetch.bad_first = False
    ns["_epg_fetch"] = fake_bfetch
    bcfg = {"cctv_epg": True}
    for k in list(ns["_BEPG"]):
        ns["_BEPG"][k] = {} if k in ("progs", "by_name") else 0.0
    ns["_BEPG"].update(ok=False, msg="内置第三方节目表还没开始抓", next_try=0.0, url="")
    check("第一轮抓到", ns["bepg_refresh"](bcfg, now=mid), True)
    check("请求了主地址", bcalls, [ns["BEPG_URLS"][0]])
    bs = ns["_bepg_snapshot"]()
    check("状态 ok", (bs["ok"], bs["msg"]), (True, ""))
    check("记下的是哪个地址", bs["url"], ns["BEPG_URLS"][0])
    check("剪完只剩 2 个台", bs["count"], 2)
    # 快照是给接口用的轻视图（只有状态和台数），progs/by_name 这些真数据留在 _BEPG 里，
    # 所以这里直接查 _BEPG。
    check("台名归一后认领得上", ns["_BEPG"]["by_name"].get(norm("湖南卫视")), "湖南卫视")
    check("TTL 内再叫不重复下载", ns["bepg_refresh"](bcfg, now=mid + 600), True)
    check("请求次数没涨", len(bcalls), 1)
    check("过期后才重取", ns["bepg_refresh"](bcfg, now=mid + ns["BEPG_TTL"] + 1), True)
    check("重取了一次", len(bcalls), 2)
    ns["_BEPG"].update(ok=False, progs={}, by_name={}, count=0, fetched=0.0, msg="没开始抓")
    check("重启后复用磁盘缓存", ns["_bepg_load_cache"](mid + 60), True)
    check("复用后不需要再下载", len(bcalls), 2)
    check("复用回来的台数对得上", ns["_bepg_snapshot"]()["count"], 2)
    # 主地址挂了要用备胎（境外站点偶尔抽风是常态，不是异常）
    fake_bfetch.bad_first = True
    ns["_BEPG"].update(ok=False, progs={}, by_name={}, count=0, fetched=0.0)
    check("主地址失败这轮仍算成功", ns["bepg_refresh"](bcfg, now=mid + 700), True)
    check("备胎是 GitHub 那份", ns["_bepg_snapshot"]()["url"], ns["BEPG_URLS"][1])
    # 全挂：旧数据顶着 + 退让
    fake_bfetch.bad_first = True

    def all_bad(url, timeout=20):
        raise OSError("两个地址都不通")

    ns["_epg_fetch"] = all_bad
    ns["_BEPG"].update(ok=True, progs={"湖南卫视": [(mid - 600, mid + 600, "梅花儿香(18)")]},
                       by_name={norm("湖南卫视"): "湖南卫视"}, count=1,
                       fetched=mid, next_try=0.0, msg="")
    check("两个地址都不通 → 这轮失败", ns["bepg_refresh"](bcfg, force=True, now=mid + 400), False)
    bs = ns["_bepg_snapshot"]()
    check("旧的节目表没被清空", bs["count"], 1)
    check("失败后按 BEPG_RETRY 退让", bs["next_try"], mid + 400 + ns["BEPG_RETRY"])
    check("退让期间不再下载", ns["bepg_refresh"](bcfg, now=mid + 500), True)
    check("退让期间没有白下的请求", True, True)
    ns["_epg_fetch"] = fake_bfetch
    fake_bfetch.bad_first = False
    ns["bepg_refresh"]({"cctv_epg": False}, force=True, now=mid + 600)
    bs = ns["_bepg_snapshot"]()
    check("关掉开关后不再 ok", bs["ok"], False)
    check("关掉后清空节目表", bs["count"], 0)
    check("关掉后写着原因", bs["msg"], "内置节目单已关闭")
    # 界面那行话要说清"几份来源、多少台显示得出节目名"
    psrc2 = io.open(PAGE, encoding="utf-8").read().replace(" ", "")
    check("设置里的开关文案提到了公开节目表", "公开完整节目表补卫视剧名" in psrc2, True)
    check("状态行读第三方那一段", "EPMETA.bepg" in psrc2, True)
    check("状态行报的是「显示得出节目名」的台数", "个显示得出节目名" in psrc2, True)
    check("「—」的说明写清了是哪几份都没有", "央视官方和公开节目表里都没有节目单" in psrc2, True)

    # ---------- 2026-11-02 台名繁简 · 码率分档 · 源默认值 · 台标候选 ----------
    t = ns["_simplify"]
    check("繁体台名先转简体再对名字", t("民視新聞台"), "民视新闻台")
    check("繁简两种写法归一后是同一个键", ns["_epg_norm"]("民視"), ns["_epg_norm"]("民视"))
    # 这条只保证"同一名字的繁简两种写法落到同一个键"。至于"凤凰香港台"和
    # "凤凰卫视香港台"是不是同一个台，那是别名表的事，不归繁简管。
    check("凤凰台的繁体写法归一到简体同一个键",
          ns["_epg_norm"]("凤凰中文台"), ns["_epg_norm"]("鳳凰中文台"))
    check("繁体写法转完不留繁体字", ns["_epg_norm"]("鳳凰衛視香港台"),
          ns["_epg_norm"]("凤凰卫视香港台"))
    check("繁体表反过来用不带歧义(線不被綫顶掉)", ns["_TRAD_S2T"]["线"], "線")
    check("反向表收满了繁体字", len(ns["_T2S"]), len({v for v in ns["_TRAD_S2T"].values()}))
    bf, lb = ns["bit_floor"], ns["low_bitrate"]
    check("4K 的及格线是 8M", bf(2160), 8.0)
    check("1080P 仍是用户给的 2M", bf(1080), ns["CLARITY_MBPS"])
    check("720P 降到 1.2M", bf(720), 1.2)
    check("480P 降到 0.6M", bf(480), 0.6)
    check("没测到分辨率时不放宽", bf(0), ns["CLARITY_MBPS"])
    check("720P/1.5M 不再算码率不足(以前误报)", lb(1.5, 720), False)
    check("4K/3M 现在算码率不足(以前漏报)", lb(3.0, 2160), True)
    check("1080P/1.9M 仍然算码率不足", lb(1.9, 1080), True)
    ql = ns["quality_label"]
    check("4K 只给 3M 不叫超清", ql(3.0, 2160), "低码率")
    check("4K 给 9M 才叫 4K超清", ql(9.0, 2160), "4K超清")
    check("1080P/2M 以上是高清", ql(2.5, 1080), "高清")
    check("720P 的角标仍是 720P", ql(1.5, 720), "720P")
    # 前端那张分档表必须跟后端一致：这是两份手写的同名阈值，最容易一边改了另一边忘
    page_src = io.open(PAGE, encoding="utf-8").read()
    mjs = re.search(r"var\s+BIT_FLOOR\s*=\s*\[(.*?)\]\s*;", page_src, re.S)
    check("页面里找得到 BIT_FLOOR 这张表", bool(mjs), True)
    jfloor = [[float(x), float(y)] for x, y in
              re.findall(r"\[\s*(\d+)\s*,\s*([\d.]+)\s*\]", mjs.group(1))] if mjs else []
    check("页面里的 BIT_FLOOR 和后端逐档相同", jfloor, [[float(c), float(f)] for c, f in ns["BIT_FLOOR"]])
    check("页面 lowBit 用的是分档线而不是写死 2M",
          "m<bitFloor(b.res||0)" in re.sub(r"\s+", "", page_src), True)
    qs = ns["_quality_stripped"]
    check("画质装饰词最多剥两层", qs("湖南卫视4K超清"), ["湖南卫视4K", "湖南卫视"])
    check("剥词只认带后缀的写法，不动数字台号", qs("港台电视31"), [])
    lc = ns["_logo_cands"]("民视高清")[0]
    check("台标候选里有剥掉高清的写法(离线库收的是民视)", "民视" in lc, True)
    check("台标候选仍保留原名，精确命中优先", lc[0], "民视高清")
    on = {k: boolv for k, _n, _u, boolv, _g in ns["SOURCES"]}
    check("YanG 默认关闭(实测 0/123 能出画面)", on.get("yang"), False)
    check("akiralereal 默认启用(实测 88%)", on.get("akira"), True)
    check("best-fan 默认启用(实测 49%)", on.get("bestfan"), True)
    check("精选源仍然排第一", ns["SOURCES"][0][0], "curated")
    msrc = io.open(SRC, encoding="utf-8").read()
    check("老配置里的 YanG 有一次性关闭迁移",
          'if disk_ver < 9 and cfg["sources"].get("yang")' in re.sub(r"\s+", " ", msrc), True)
    # 2026-11-02 装机实测踩到：CFG_VER 一涨，这段"关死源"就重跑，把用户后来自己勾回来的
    # kelvin/epg_hk/epg_tw/epg_mo 又关了一次。判据钉在 disk_ver < 8，别再挂到版本号上。
    check("关死源的迁移钉在 disk_ver < 8，不随版本号重跑",
          'if disk_ver < 8: dead = [k for k in ("kelvin", "epg_hk", "epg_tw", "epg_mo")'
          in re.sub(r"\s+", " ", msrc), True)

    # ---------- 2026-11-02 升级通道：清单地址 → 镜像 → 原地址 ----------
    # 起因：直连 GitHub 下载 13 MB 的包只有约 35 KB/s，客户端 180 秒超时后整轮失败。
    sm = ns["_strip_mirror"]
    uu = ns["_update_urls"]
    GH = "https://github.com/kele551/LiveIPTV/releases/download/v1.5.1/LiveIPTV.exe"
    check("镜像前缀能剥回原地址", sm("https://gh-proxy.com/" + GH), GH)
    check("本来就不是镜像的地址不动它", sm(GH), GH)
    u1 = uu({"url": GH})
    check("原地址排第一", u1[0], GH)
    check("然后是两个镜像", [x for x in u1[1:3]],
          ["https://gh-proxy.com/" + GH, "https://ghfast.top/" + GH])
    check("原地址不重复排一次", u1.count(GH), 1)
    u2 = uu({"url": "https://gh-proxy.com/" + GH})
    check("清单已经指向镜像时也要能回退到原地址", u2[-1], GH)
    check("清单指向镜像时按镜像→另一个镜像→原地址排", len(u2), 3)
    check("不是 GitHub 发行版的地址就只试它自己",
          uu({"url": "https://example.com/x/LiveIPTV.exe"}),
          ["https://example.com/x/LiveIPTV.exe"])
    check("没有地址时返回空(交给上层报错)", uu({"url": ""}), [])

    # ---------- 2026-11-02 换包方式：进程内改名换包，不再靠隐藏 PowerShell ----------
    # 起因：靠"隐藏 PowerShell 等退出后 copy 再 Start-Process"换了两次包，exe 都换成功、
    # 程序都自己没起来（一次没进程，一次卡在 12 MB 不动）。所以改成进程内换 + --after-update 等端口。
    check("换包在进程内做(有 _swap_and_relaunch)", "def _swap_and_relaunch(" in msrc, True)
    check("不再起隐藏 PowerShell 换包", "Start-Process -FilePath $dst" in msrc, False)
    check("换完用 --after-update 拉起新进程",
          'Popen([str(target), "--after-update"]' in msrc, True)
    check("新进程会先等旧进程把端口放掉",
          "if args.after_update:" in msrc and "已是最新或未配置更新地址" in msrc, True)
    check("放回新包失败时把旧 exe 改回来", "os.rename(old, target)" in msrc, True)
    check("启动时清理 .old/.new 残留", "_clean_stale_exe()" in msrc, True)

    print("-" * 70)
    if fails:
        print("有 %d 条失败: %s" % (len(fails), ", ".join(fails)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

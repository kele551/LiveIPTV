# -*- coding: utf-8 -*-
"""LIVE直播源 —— 线上升级链路验真（只读，什么都不发）

为什么要有这个文件
    这个项目的升级源只挂在 GitHub 一个平台上，而本机到 GitHub 的路时通时断；
    v1.4.x 那几次"发了但用户升不上来"的教训，全部出在这条链的某个环节：
    CDN 给了半新半旧的清单、签名与清单不是同一批字节、清单里的 sha256 与附件对不上、
    老版本里那个升级按钮本身就是坏的。
    所以把客户端 check_self_update 的判据原样复刻成一条命令：发版后立刻跑一次，
    用户报"升级失败"时先跑一次。全绿才叫"用户能升级"。

它按客户端的口径逐条走：
    ① 先问 api.github.com 要 main 当前的**提交号**，再用提交号去取 version.json / .sig
       （按分支名取会被 CDN 缓存坑成"清单是新的、签名是旧的"，验签必挂 —— 客户端就是这么防的）；
    ② 对 version.json 的**原始字节**做 Ed25519 验签，公钥直接取源码里的 UPDATE_PUBKEY_HEX；
    ③ 线上那份与仓库里这份逐字节比一下（顺手给"只差换行符"的判定，防 autocrlf 假红）；
    ④ 按清单 url 把发行附件下载回来，比对真实 sha256 与 size；
       下载页路由抽风时改走 api.github.com 的 assets 二进制口（同一批字节，不是换个来源验）；
    ⑤ 版本比较：清单版本 > 已装版本，用户才会看到"有新版本"（--from 传用户手上那个版本号）。

用法
    python tools/verify_release.py                # 验源码 VERSION 对应的那一版
    python tools/verify_release.py --from 1.4.2   # 顺带回答"装着 1.4.2 的人升不升得动"

退出码：全过 = 0；任何一条硬失败 = 1（网络取不到也算失败，因为用户此刻就是取不到）。
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = (os.path.dirname(HERE), HERE)
REPO = next(p for p in _CANDIDATES
            if os.path.exists(os.path.join(p, 'LIVE直播源.py')))
SRC = os.path.join(REPO, 'LIVE直播源.py')
# 本机裸连 GitHub 时不时 10060，取不到就借狐径的本地代理 8787 再试一轮。
# 这只影响**这台维护机**怎么把字节拿回来，不改变线上用户走的路，也不影响字节比对。
PROXY = os.environ.get('LIVE_VERIFY_PROXY') or 'http://127.0.0.1:8787'

results = []


def say(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('  [%s] %s%s' % ('PASS' if ok else 'FAIL', name, ('  ' + detail) if detail else ''))
    return ok


SOCK_TMO = int(os.environ.get('LIVE_SOCK_TMO') or 60)        # 一次 recv 的上限：链路断了 60 s 内报错，不用干等十五分钟
DEADLINE_BIG = int(os.environ.get('LIVE_DEADLINE_BIG') or 900)   # 大附件的**总时长**预算（本机走代理实测 ~48 KB/s，十几兆要五六分钟）


def fetch(url, timeout=SOCK_TMO, tries=3, headers=None, token=None, deadline=None,
          expect=0, label=''):
    """严格 TLS（默认上下文：校验证书链 + 主机名），与客户端自更新通道同一口径。

    ⚠ `timeout` 只管一次 recv，`deadline` 才是总时长 —— 以前只写 timeout=900 再
    `r.read()` 一把梭，只要有零碎字节在动就永远不会超时，一次验真拖到没人分得清
    是在跑还是卡死（2026-10-26 热点那边就是这么烧掉二十分钟的）。
    """
    hd = {'User-Agent': 'LiveIPTV-verify', 'Accept-Encoding': 'identity'}
    hd.update(headers or {})
    if token:
        hd['Authorization'] = 'token ' + token
    err = ''
    for i in range(tries):
        op = urllib.request.build_opener(
            urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
            if i else urllib.request.ProxyHandler({}))
        t0 = time.time()
        nxt = 15
        try:
            with op.open(urllib.request.Request(url, headers=hd), timeout=timeout) as r:
                if getattr(r, 'status', 200) != 200:
                    err = 'HTTP %s' % r.status
                    time.sleep(2)
                    continue
                buf = bytearray()
                over = False
                while True:
                    # read1：有多少取多少。read(n) 会一直等到凑满 n 字节或连接关闭 ——
                    # 那种慢链路下 deadline 永远轮不到（2026-10-26 那 15 MB 就是这么空转到没人知道在跑还是卡死）。
                    chunk = (r.read1(262144) if hasattr(r, "read1") else r.read(262144))
                    if not chunk:
                        break
                    buf += chunk
                    spent = time.time() - t0
                    if spent >= nxt:
                        print('    … %s 已取回 %.1f MB / %.1f MB（%.0f KB/s，%d s）'
                              % (label or url.split('//')[-1][:52], len(buf) / 1048576.0,
                                 expect / 1048576.0 if expect else 0,
                                 len(buf) / max(spent, 1) / 1024.0, int(spent)))
                        sys.stdout.flush()
                        nxt = spent + 15
                    if deadline and spent > deadline:
                        err = '总时长预算 %d s 用尽（只取回 %d B / 需 %d B）' % (
                            deadline, len(buf), expect)
                        over = True
                        break
                if over:
                    return None, err
                if buf:
                    return bytes(buf), ''
        except Exception as e:
            err = '%s: %s' % (type(e).__name__, str(e)[:110])
        time.sleep(2)
    return None, err


def gh_token():
    """本机 gh.exe 登录态里的令牌（可选）。没有就匿名跑，匿名也能取公开仓库附件。"""
    for exe in (os.environ.get('LIVE_GH'), r'F:\Harness\toolchain\gh\bin\gh.exe', 'gh'):
        if not exe:
            continue
        try:
            r = subprocess.run([exe, 'auth', 'token'], capture_output=True, text=True, timeout=20)
            t = (r.stdout or '').strip()
            if r.returncode == 0 and t:
                return t
        except Exception:
            continue
    return ''


def get_asset(owner_repo, url):
    """把清单 url 指向的附件取回来。先按 url 直取；路由抽风就改走 API 的二进制口。

    附件名一律**从清单里读**，不在这里二次硬编码 —— 名字差一个字，老用户就是 404。
    """
    import urllib.parse
    name = os.path.basename(urllib.parse.urlsplit(url).path)
    blob, err = fetch(url, deadline=DEADLINE_BIG, label='清单 url 附件')
    if blob is not None:
        return name, blob, '清单 url'
    # 兜底：api.github.com 的 assets 口（Accept: octet-stream）给的是同一批存储字节，
    # 换的只是取数路径，不是"换个来源自己夸自己"。
    tok = gh_token()
    tag = 'v' + url.split('/releases/download/')[1].split('/')[0] if '/releases/download/' in url else ''
    meta, err2 = fetch('https://api.github.com/repos/%s/releases/tags/%s' % (owner_repo, tag),
                       30, headers={'Accept': 'application/vnd.github+json'}, token=tok)
    if meta is None:
        return name, None, '%s / 回退也失败: %s' % (err, err2)
    try:
        assets = json.loads(meta.decode('utf-8', 'ignore')).get('assets') or []
    except Exception:
        return name, None, '发行版元数据不是 JSON'
    for a in assets:
        if a.get('name') != name:
            continue
        blob, err3 = fetch(a.get('url') or '', deadline=DEADLINE_BIG,
                           headers={'Accept': 'application/octet-stream'}, token=tok,
                           expect=a.get('size') or 0, label='api assets/%s' % a.get('id'))
        return (name, blob, 'api assets/%s' % a.get('id')) if blob is not None else (name, None, err3)
    return name, None, '发行版里没有 %s（附件名要和清单一致）' % name


def ver_tuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', str(v) or '')[:3])


def main():
    ap = argparse.ArgumentParser(add_help=True, description='LIVE直播源线上升级链路验真（只读）')
    ap.add_argument('--from', dest='installed', default='', help='用户已装的版本号')
    a = ap.parse_args()

    sys.path.insert(0, REPO)
    import _ed25519

    src = io.open(SRC, encoding='utf-8').read()

    def _const(pat, label):
        m = re.search(pat, src, re.M)
        if not m:
            say('源码里能解析出 %s' % label, False, '按 %s 没找到' % pat)
            raise SystemExit(1)
        return m.group(1)

    pub_hex = _const(r'^UPDATE_PUBKEY_HEX\s*=\s*"([0-9a-fA-F]{64})"', 'UPDATE_PUBKEY_HEX')
    ver_src = _const(r'^VERSION\s*=\s*"([^"]+)"', 'VERSION')
    feed = _const(r'"update_url"\s*:\s*"(https://[^"]+version\.json)"', 'update_url')
    m = re.search(r'raw\.githubusercontent\.com/([^/]+/[^/]+)/', feed)
    owner_repo = m.group(1)
    print('源码 VERSION=%s  内置公钥=%s…  升级源=%s' % (ver_src, pub_hex[:16], feed))
    say('内置公钥格式正确（64 个十六进制字符）', len(pub_hex) == 64)

    # ① 提交号（客户端就是这么防 CDN 半新半旧的）
    j, err = fetch('https://api.github.com/repos/%s/commits/%s' % (owner_repo, 'main'), 30)
    if not j:
        say('能取到 main 分支的提交号', False, err)
        return 1
    sha = json.loads(j.decode('utf-8', 'ignore')).get('sha')
    if not sha or len(sha) < 7:
        say('能取到 main 分支的提交号', False, repr(sha))
        return 1
    say('能取到 main 分支的提交号（清单与签名按同一提交定位）', True, sha[:12] + '…')

    base = 'https://raw.githubusercontent.com/%s/%s/' % (owner_repo, sha)
    raw, e1 = fetch(base + 'version.json')
    sigraw, e2 = fetch(base + 'version.json.sig')
    if raw is None or sigraw is None:
        say('按提交号能取到 version.json 与 .sig', False, e1 or e2)
        return 1
    d = json.loads(raw.decode('utf-8-sig'))
    print('   线上清单: version=%s  size=%s  sha256=%s…' % (
        d.get('version'), d.get('size'), (d.get('sha256') or '')[:16]))

    # ② 验签（.sig 允许 64 字节裸签名或 128 位十六进制文本，与客户端同口径）
    pub = bytes.fromhex(pub_hex)
    ok = None
    if len(sigraw) == 64:
        try:
            ok = _ed25519.checkvalid(sigraw, raw, pub)
        except Exception as e:
            ok = '异常 %s' % type(e).__name__
    else:
        txt = ''.join(chr(b) for b in sigraw if 32 <= b < 127).strip()
        try:
            ok = _ed25519.checkvalid(bytes.fromhex(txt), raw, pub)
        except Exception as e:
            ok = '异常 %s' % type(e).__name__
    if not say('%s 线上 version.json 用内置公钥验签通过' % owner_repo, ok is True,
               '.sig %d 字节' % len(sigraw)):
        return 1

    # ③ 线上那份 == 仓库这份
    local_raw = io.open(os.path.join(REPO, 'version.json'), 'rb').read()
    say('线上 version.json 与仓库这份逐字节一致',
        raw == local_raw or raw.replace(b'\r\n', b'\n') == local_raw.replace(b'\r\n', b'\n'),
        '线上 %d B / 本地 %d B' % (len(raw), len(local_raw)))

    # ④ 附件真下载回来
    name, blob, how = get_asset(owner_repo, d.get('url') or '')
    if blob is None:
        say('发行附件 %s 能下载回来' % name, False, how)
    else:
        real = hashlib.sha256(blob).hexdigest()
        say('附件真实 sha256 == 清单写的（取数路径: %s）' % how, real == (d.get('sha256') or '').lower(),
            '%s… vs %s…' % (real[:16], (d.get('sha256') or '')[:16]))
        say('附件真实大小 == 清单写的', len(blob) == d.get('size'),
            '%d B vs %s B' % (len(blob), d.get('size')))

    # ⑤ 源码 VERSION 与线上清单是否同一版（发版漏改/漏推会在这里露出来）
    say('源码 VERSION == 线上清单 version', str(ver_src) == str(d.get('version')),
        '源码=%s 线上=%s' % (ver_src, d.get('version')))

    if a.installed:
        say('已装 %s 的用户看得见 %s（按元组比，不按字符串）' % (a.installed, d.get('version')),
            ver_tuple(d.get('version')) > ver_tuple(a.installed),
            '%s vs %s' % (ver_tuple(a.installed), ver_tuple(d.get('version'))))

    bad = [n for n, o in results if not o]
    print()
    print('验真结果: %s（%d 项，失败 %d 项）' % ('PASS' if not bad else 'FAIL', len(results), len(bad)))
    for n in bad:
        print('   FAIL -> %s' % n)
    return 0 if not bad else 1


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    sys.exit(main())

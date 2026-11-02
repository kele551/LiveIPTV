<div align="center">
<img src="docs/icon.png" alt="LIVE直播源" height="120" width="120">

<h1>LIVE直播源</h1>

<a href="https://github.com/kele551/LiveIPTV/releases" title="点击去下载（各平台发行版合计 · 实时）"><img alt="Downloads" src="https://img.shields.io/endpoint?url=https%3A%2F%2Fkele551-badge.kele551.workers.dev%2F%3Frepo%3DLiveIPTV%26kind%3Ddownloads&style=flat-square" height="30"></a>
<a href="https://github.com/kele551/LiveIPTV" title="浏览量 · 各平台访问计数合计 · 实时"><img alt="浏览量" src="https://img.shields.io/endpoint?url=https%3A%2F%2Fkele551-badge.kele551.workers.dev%2F%3Frepo%3DLiveIPTV%26kind%3Dviews&style=flat-square" height="30"></a>

<a href="https://github.com/kele551/LiveIPTV/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square"></a>
<img alt="Platform" src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square">
<a href="https://github.com/kele551/LiveIPTV/releases"><img alt="Release" src="https://img.shields.io/github/v/release/kele551/LiveIPTV?style=flat-square&label=release&color=blue"></a>
<img alt="Last Commit" src="https://img.shields.io/github/last-commit/kele551/LiveIPTV?style=flat-square&label=last%20commit&color=blue">

<a href="https://github.com/kele551/LiveIPTV/stargazers"><img alt="GitHub Star" src="https://img.shields.io/github/stars/kele551/LiveIPTV?style=flat-square&logo=github&label=GitHub%20Star&color=gold"></a>
<a href="https://github.com/kele551/LiveIPTV/network/members"><img alt="GitHub Fork" src="https://img.shields.io/github/forks/kele551/LiveIPTV?style=flat-square&label=GitHub%20Fork&color=blue"></a>
<a href="https://github.com/kele551"><img alt="Follow Author" src="https://img.shields.io/github/followers/kele551?style=flat-square&logo=github&label=follow%20author&color=blue"></a>

<img alt="Category" src="https://img.shields.io/badge/分类-应用软件-blue?style=flat-square">
<img alt="Single File" src="https://img.shields.io/badge/形态-单文件exe-blue?style=flat-square">
<img alt="Free" src="https://img.shields.io/badge/费用-免费无广告-brightgreen?style=flat-square">
<img alt="No Tracking" src="https://img.shields.io/badge/用户数据-不采集不上传-green?style=flat-square">

<a href="https://github.com/kele551/LiveIPTV/releases"><img alt="Download from GitHub" src="https://img.shields.io/badge/%F0%9F%93%A5_%E4%B8%8B%E8%BD%BD-GitHub%E4%B8%BB%E6%BA%90-24292f?style=flat-square&logo=github&logoColor=white&labelColor=3d4552"></a>
<a href="https://github.com/kele551/LiveIPTV"><img alt="GitHub source" src="https://img.shields.io/badge/%F0%9F%90%99_%E6%BA%90%E7%A0%81-GitHub%E4%BB%93%E5%BA%93-24292f?style=flat-square&logo=github&logoColor=white&labelColor=3d4552"></a>
<a href="https://github.com/kele551/LiveIPTV/issues"><img alt="Issues" src="https://img.shields.io/badge/%F0%9F%90%9E_%E5%8F%8D%E9%A6%88-%E6%8F%90Issue-0969da?style=flat-square&labelColor=3d4552"></a>
<a href="#支持项目"><img alt="Sponsor" src="https://img.shields.io/badge/%E2%98%95_%E8%B5%9E%E8%B5%8F-%E8%AF%B7%E5%96%9D%E5%92%96%E5%95%A1-ff69b4?style=flat-square&labelColor=3d4552"></a>

<p>📺 <b>直播源整理与可用性检测工具</b>　·　一键跑出一条自己能播的 M3U</p>

<p>作者 <b>海风（kele551）</b>　·　<a href="https://github.com/kele551/LiveIPTV">GitHub（主）</a>　·　<a href="docs/README_EN.md">English</a></p>
</div>

<details>
<summary>📊 <b>仓库数据一览</b>（点击展开）</summary>

<p align="center">
<img alt="Release Date" src="https://img.shields.io/github/release-date/kele551/LiveIPTV?style=flat-square&label=release%20date">
<img alt="Commit Activity" src="https://img.shields.io/github/commit-activity/y/kele551/LiveIPTV?style=flat-square&label=commits%2Fyear">
<img alt="Contributors" src="https://img.shields.io/github/contributors/kele551/LiveIPTV?style=flat-square&label=contributors">
<a href="https://github.com/kele551/LiveIPTV/issues"><img alt="Issues" src="https://img.shields.io/github/issues/kele551/LiveIPTV?style=flat-square&label=issues"></a>
<img alt="Resolved" src="https://img.shields.io/github/issues-closed/kele551/LiveIPTV?style=flat-square&label=resolved">
<img alt="Language" src="https://img.shields.io/github/languages/top/kele551/LiveIPTV?style=flat-square">
<img alt="Code Size" src="https://img.shields.io/github/languages/code-size/kele551/LiveIPTV?style=flat-square&label=code%20size">
<a href="https://github.com/kele551/LiveIPTV/blob/main/docs/CONTRIBUTING.md"><img alt="PRs Welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square"></a>
</p>

</details>

---

## 这是什么

网上的直播源列表有很多，但**大多已经失效**：一个 m3u 里几十上百条，能播的可能只有几条，还得一条条去试。

这个小工具就干一件事：**把若干个公开的直播源列表抓下来，合并去重，实测哪些真的能播、画质到底多少，然后挑出最好的一条，导出成一个干净的 M3U**。导出的文件丢给 PotPlayer / VLC / IPTV 播放器 / 电视盒子都能直接用。

它自己**不提供、不存储、不转发任何直播内容**，只是把公开可访问的链接整理一遍、测一测（见 [合规声明](docs/COMPLIANCE.md)）。

> ⚠️ **用之前请看清楚这三句**
>
> 1. 本程序**不含任何节目内容**，只整理别人公开发布的链接；能不能播、内容是否合规，取决于你所在地区**和那些来源本身**。
> 2. 它**不解除任何付费、加密、鉴权限制**，也不提供"看某个频道"的服务——它只回答"这条链接此刻通不通、码率多少"。
> 3. 请自行确认当地法律法规与来源授权，**仅供个人自用**；整理结果不要用于公开播放、转播、再分发或售卖。如果不确定某个来源，直接在「设置 → 数据源」里关掉它（可以全部关掉，只用你自己的列表）。

---

## 三步上手

| 步骤 | 做什么 |
|---|---|
| **① 下载** | 去 [Releases](https://github.com/kele551/LiveIPTV/releases) 拿 `LiveIPTV.exe`，双击即可（单文件，免安装）。发行页上的附件名是 `LiveIPTV.exe`，和本机打包出来的 `LIVE直播源.exe` 是同一个程序，改不改名都能跑 |
| **② 更新** | 首次启动会自动跑一次体检；浏览器自动打开控制台 `http://127.0.0.1:8899` |
| **③ 导出** | 勾选想要的频道（或点「全选」）→ 点「保存 M3U」→ 把生成的 `直播源.m3u` 拖进播放器 |

下次打开直接用上次的结果（默认每 6 小时自动更新一次，可关）。

---

## 它到底做了什么

```
抓取 9 个公开源  →  按频道名合并去重  →  按源实测可用率排序
      ↓                                          ↓
 每个地址只测一次（去重）  →  连通性 + 是否返回网页  →  拉一段真实分片测速
      ↓                                          ↓
 每个频道挑一条最好的（画质优先、再看速度）  →  写 M3U（UTF-8 BOM，播放器不挑）
```

几个关键点：

- **同一地址只测一次**。不同源里大量重复地址，去重后要探测的数量能少一半以上。
- **按源的可信度排序**。先抽样 20 条算出每个源「大概有几成能播」，能播的源优先用，不行的源只留一条兜底。
- **上次在用的地址优先复测**。日常更新只复测上一轮真能播的那些地址，其余频道没有可播源时才去探新地址 —— 所以第二次以后的更新明显更快。
- **会认「假直播」**。有些地址连得上，但返回的其实是频道网页/中转页，这类一律判失效（也顺手记下来，下次不再访问）。
- **画质是解析视频流实测出来的**（v1.4.0 起）。直接解 TS 分片里 H.264 / HEVC 的 SPS、fMP4 的 `moov`、
  MPEG-2 的序列头，拿到**真实像素宽高**，再按分片字节数 ÷ 时长算**真实码率**；不是拿主清单里标称的
  `RESOLUTION` 猜，也不看频道名。实测覆盖率约 97%。
- **判定用两条**（用户实测口径）：分辨率 ≥1080P **且** 码率 ≥2 Mbps 才算清晰；下载吞吐 ≥400 KB/s 才算不卡。
  只测到一项时会标出缺的那项（"低码率" / "分辨率低"），点开能看到具体数值。
- **「码率不足」这个角标按分辨率分档**（2026-11-02 起）：4K 要 8 Mbps、1080P 要 2 Mbps、
  720P 要 1.2 Mbps、480P 要 0.6 Mbps。以前全场只有一条 2 Mbps 的线，720P/1.5 Mbps 这种正常源被误挂角标、
  4K/3 Mbps 的虚标源反而没人管。
- **「正在播出」不用填地址**：内置两档节目单——央视官方接口（61 个台 id 一次批量，秒级）与一份公开完整
  节目表（往后 5 天、往前 7 天，卫视那批能给到具体剧名）。优先级钉死：你自己填的 XMLTV > 央视官方（给了具体
  节目名的）> 公开节目表 > 官方只给的大类词；"请欣赏××卫视精彩节目""敬请期待"这类占位档一律不用。
  抓取都在后台线程，界面只读内存缓存，首屏不受影响；抓不到就显示「—」，其它功能照常。
- **台标自带离线库**：随包 394 张（约 4 MB，按实际显示尺寸存），第一次打开就有图，不用等从 GitHub 拉；
  本地没有的台会去台标站补（`v.999.team`，约 4 万枚，简繁两种写法都试），补到就存进本地库。
  透明的白字台标垫深色底显示，央视那批不会再"白字压白底看不见"；同一张图挂在多个不相干的台上会被拦下，
  宁可显示名字方块也不显示错标（v1.4.1 起）。

---

## 界面

<p align="center"><img src="docs/screenshot.png" alt="控制台界面" width="880"></p>

控制台就一页：

- 顶部：状态、进度、「立即更新」「设置」「退出」
- 四个数字：可用频道 / 在线直播源 / 港澳台 / 上次更新
- 中间：搜索、按分组筛（央视 / 卫视 / 港澳台 / 地方台 …）、按画质筛（4K / 1080P / 高清 / 仅港澳台 / 仅可用）
- 底部：已选数量、保存目录、文件名、「保存 M3U」「打开目录」

快捷键：`Ctrl+S` 保存、`Ctrl+F` 搜索、`Esc` 关弹窗。

右下角托盘图标：左键打开控制台，右键菜单有「打开控制台 / 立即更新频道 / 打开 M3U 所在文件夹 / 退出程序」；每次更新完会弹一条气泡告诉你结果。

---

## 数据源与实测可信度

内置的公开源分三类（国内聚合 / 港澳台 / 可选国际台），默认只开下面这些
（可用率是 2026-11-02 在本机实测抽样，会随网络和时间变化）：

| 源 | 覆盖 | 抽样可用 | 默认 |
|---|---|---|---|
| 精选源（内置人工核对，走源码不联网） | 央视、卫视、港澳台 | 10/17 | ✅ |
| best-fan·`cn_all.m3u8` | 国内聚合 | 14/20 | ✅ |
| akiralereal·`IPTV.m3u` | 国内为主 + 少量海外体育 | 14/14 | ✅ |
| CCSH·全量源 `live.m3u` | 央视、卫视、港澳台、地方台 | 8/20 | ✅ |
| Guovin·IPTV-API | 国内为主 | 7/20 | ✅ |
| ChinaIPTV·自动更新 | 央视、卫视为主 | 3/20 | ✅ |
| iptv-org（中国 / 香港 / 台湾 / 澳门） | 境外整理的国内与港澳台 | 2/20、0/1、2/10、0 条 | ✅ |
| YanG·Gather | 国内聚合 | 全量 123 条 **0 条出画面** | ❌ 默认关 |
| CCSH·平台源 `live_platforms.m3u` | 是网络直播间清单，不是电视台 | — | ❌ 默认关 |
| kelvin（旧列表） | 香港 | 0/15 | ❌ 默认关 |
| epg.pw（港/澳/台） | 港澳台 | 1/5、7/17、0 条 | ❌ 默认关 |

> YanG·Gather 的那份列表里，咪咕要签名 URL、ttvb 的代理已 404，全量 123 条实测一条都出不了画面，
> 所以默认关掉（老配置升级时会替你关一次，之后你自己勾选照样算数）。
> epg.pw 那几份列表里的流都指向同一个中转域名，本机连不上，所以默认关掉；想试可以在「设置 → 数据源」里重新打开。
> 抓取时会自动走 `jsdelivr` / `gh-proxy` 这类**公开 CDN 镜像**（原地址连不上时才会用），你也可以自己换。

---

## 设置里能改什么

| 分组 | 项 |
|---|---|
| 更新 | 自动更新间隔、每个频道保留几条备用、节目单（内置，也可填自己的 XMLTV 地址）、保存位置、是否保留标清、启动时是否打开网页 |
| 程序 | 托盘图标、开机自启、计划任务（后台定时更新）、检查新版本、**必须校验签名**、自动下载新版本、升级源地址、检查间隔 |
| 数据源 | 每个源的开关、状态点、抓到的条数、抽样可用率 |

「计划任务」注册的是 `LIVE直播源自动更新`，用它可以在不开窗口的情况下定时跑一次（托盘和计划任务二选一，一般用托盘就够了）。

---

## 升级与签名

- 升级源是一份 `version.json` + 一份 `version.json.sig`。
- 程序内置 **Ed25519 公钥**，每次检查更新都会验签；**签名对不上或没有签名，一律拒绝升级**（可在设置里关掉，但不建议）。
- 下载完的新版本还会再核对 `sha256` 和字节数，三样都过才提示你替换。
- 因为程序是单文件 exe、运行时无法覆盖自己，新版本会下载到数据目录，提示你手动替换（或按提示操作）。

私钥不随仓库分发，签名流程见 [CODE_SIGNING_POLICY.md](docs/CODE_SIGNING_POLICY.md)。

---

## 常见问题

<details><summary><b>导出的 m3u 播放器不认？</b></summary>

文件是 UTF-8 带 BOM 的 `#EXTM3U`，PotPlayer、VLC、MX Player、Kodi、各类 IPTV 盒子都能直接读；如果播放器要求 http 链接，可以把文件放到本地 http 服务再填地址。
</details>

<details><summary><b>为什么有些频道没出现？</b></summary>

只输出「实测能拉出画面」的频道。判失效的三种情况：连不上、返回的是网页、能连上但拉不到数据。想放宽可以把「备用源数」调大，或在设置里关掉「保留标清」的限制。
</details>

<details><summary><b>为什么更新有时候要一两分钟？</b></summary>

第一轮要把几百上千个地址都测一遍；之后是增量更新，只复测上一轮能用的地址，一般快得多。也可以在设置里调低「并发探测数」、调小「备用源数」来缩短时间。
</details>

<details><summary><b>杀软报毒？</b></summary>

单文件 Python 打包的 exe 常被启发式误报。程序**只做两件事**：访问你启用的那些公开列表地址、把结果写进自己的数据目录 `%APPDATA%\LIVE直播源`。源码完全公开，可自行 `pyinstaller` 编译。
</details>

<details><summary><b>端口被占用？</b></summary>

默认 8899，被占会自动往后找 10 个；地址会打印在日志和数据目录里。
</details>

---

## 从源码运行

```bash
# 需要 Python 3.9+，只用标准库，不用装任何第三方包
python LIVE直播源.py              # 打开控制台（默认 http://127.0.0.1:8899）
python LIVE直播源.py --once       # 只更新一次就退出（适合计划任务）
python LIVE直播源.py --no-tray --no-browser --port 9000
```

打包：

```bash
python build_exe.py               # 产物在 builds/v<版本>/LIVE直播源.exe（打包前自动过一致性检查）
python tools/check_page.py --strict-src   # 自检：页面与 _page.html 一致、src 未漂移、语法能过
python tests/test_logic.py        # 判据单测（缓存守卫、统计口径）
```

数据目录：默认 `%APPDATA%\LIVE直播源`；设环境变量 `LIVE_DATA` 可以指到别处（便携 / 测试用）。

---

## 合规与免责

- **免费、无广告、不收费**；**不采集、不上传任何用户数据**：没有账号系统、没有统计上报、没有广告，运行数据只写本机数据目录。
- 程序**不含任何直播内容**，不存储、不转发、不二次分发；只整理公开可访问的链接并做可用性测试。
- 所有频道、台标、节目内容的权利归各自权利人；本工具与任何电视台、平台、运营商**没有隶属关系**，也不代表其认可。
- 内容来自第三方公开列表，其合法性、稳定性、画质不由本工具保证；请遵守所在地法律法规，仅作个人学习与自用。
- 权利人若认为某个来源不宜被整理，可通过 [Issues](https://github.com/kele551/LiveIPTV/issues) 告知，我会把该来源从默认列表里移除。

完整说明见 [COMPLIANCE.md](docs/COMPLIANCE.md)。

## 第三方组件与许可

**零第三方依赖**：只用 Python 标准库（`http.server`、`urllib`、`concurrent.futures`、`ctypes` 等）。
Ed25519 验签为自行实现的 `_ed25519.py`（RFC 8032 参考实现思路，MIT）。
本项目以 [MIT](LICENSE) 许可发布，Copyright (C) 2026 HaiFeng (kele551)。

## 支持项目

如果它帮你省了点折腾时间，可以请我喝杯咖啡 ☕ —— 完全自愿，不影响任何功能。

<p align="center"><img src="docs/sponsor.png" alt="赞赏码" width="220"></p>

---

<p align="center"><sub>作者 <b>海风（kele551）</b>　·　<a href="https://github.com/kele551/LiveIPTV">github.com/kele551/LiveIPTV</a></sub></p>

# -*- coding: utf-8 -*-
# 作者: 海风（kele551）   https://gitee.com/kele551/hotnews
"""Ed25519 纯 Python 实现（签名 + 验签），零第三方依赖。

【为什么自己写】这台机器上 cryptography / nacl / rsa 一个都没有装，
而"升级通道签名"又不值得为了它把一个几十兆的加密库塞进 exe。
Ed25519 的参考实现很短（Bernstein 等人论文附带的 Python 版），只用 hashlib，
验签一次几十毫秒，完全够用。

用途：
  · 发布端（tools/publish.py）：用私钥给 version.json 签名
  · 客户端（updater.py）：用内置公钥验签，**验不过就拒绝升级**

这样即便 Gitee 账号被盗、有人推了恶意 version.json + 恶意 exe，
没有私钥就签不出合法签名，客户端会直接拒绝。

正确性由 tests_ed25519.py 用 RFC 8032 官方测试向量验证。
"""
import hashlib

b = 256
q = 2 ** 255 - 19
l = 2 ** 252 + 27742317777372353535851937790883648493


def H(m):
    return hashlib.sha512(m).digest()


def expmod(b_, e, m):
    if e == 0:
        return 1
    t = expmod(b_, e // 2, m) ** 2 % m
    if e & 1:
        t = (t * b_) % m
    return t


def inv(x):
    return expmod(x, q - 2, q)


d = -121665 * inv(121666)
I = expmod(2, (q - 1) // 4, q)


def xrecover(y):
    xx = (y * y - 1) * inv(d * y * y + 1)
    x = expmod(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * I) % q
    if x % 2 != 0:
        x = q - x
    return x


By = 4 * inv(5)
Bx = xrecover(By)
B = [Bx % q, By % q]


def edwards(P, Q):
    x1, y1 = P[0], P[1]
    x2, y2 = Q[0], Q[1]
    x3 = (x1 * y2 + x2 * y1) * inv(1 + d * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * inv(1 - d * x1 * x2 * y1 * y2)
    return [x3 % q, y3 % q]


def scalarmult(P, e):
    if e == 0:
        return [0, 1]
    Q = scalarmult(P, e // 2)
    Q = edwards(Q, Q)
    if e & 1:
        Q = edwards(Q, P)
    return Q


def encodepoint(P):
    x, y = P[0], P[1]
    bits = [(y >> i) & 1 for i in range(b - 1)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(b // 8))


def bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1


def publickey(sk):
    h = H(sk)
    a = 2 ** (b - 2) + sum(2 ** i * bit(h, i) for i in range(3, b - 2))
    A = scalarmult(B, a)
    return encodepoint(A)


def signature(m, sk):
    """用 32 字节私钥给消息 m（bytes）签名，返回 64 字节签名。"""
    h = H(sk)
    a = 2 ** (b - 2) + sum(2 ** i * bit(h, i) for i in range(3, b - 2))
    r = int.from_bytes(H(h[b // 8:b // 4] + m), "little")
    R = scalarmult(B, r)
    S = (r + int.from_bytes(H(encodepoint(R) + publickey(sk) + m), "little") * a) % l
    return encodepoint(R) + S.to_bytes(32, "little")


def isoncurve(P):
    x, y = P[0], P[1]
    return (-x * x + y * y - 1 - d * x * x * y * y) % q == 0


def decodepoint(s):
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = xrecover(y)
    if (x & 1) != ((s[31] >> 7) & 1):
        x = q - x
    P = [x, y]
    if not isoncurve(P):
        raise ValueError("点不在曲线上")
    return P


def is_small_order(P):
    """P 是否落在 8 阶小子群里（含单位点 [0,1]）。

    【为什么需要】Ed25519 的公开密钥是 32 字节编码、共 8 个点的小子群（阶为 8）。
    如果公钥恰好是这类点，那么**任何人都能对任意消息伪造一个能验过的签名**
    （签名验证只做 [S]B == R + [h]A，A 落在小子群时 h 的贡献被"吃掉"）。
    本项目的公钥是内置固定值、不是这类点，但验签器是通用实现，必须按规范拒绝。
    """
    return scalarmult(P, 8) == [0, 1]


def checkvalid(sig, m, pk):
    """验签：sig(64) / m(bytes) / pk(32)。通过返回 True，不通过返回 False。

    【2026-10-09 修 低-2】按 RFC 8032 §5.1.7 的实现要求补两条校验：
      · S 必须 < l（群阶）。签名是对 l 取模算出来的，所以 S、S+l、S+2l… 都能验过 ——
        不拦住就等于"同一个签名有无数个等价变形"，会让幂等/去重类的上层判断失效；
      · 公钥不得是小阶点（含单位点）。理由见 is_small_order 的说明。
    本项目的公钥是内置常量、签名来自维护者离线私钥，两条都不会被触发，
    属于"按实现规范补齐"，对正常签名没有任何影响。
    """
    try:
        if len(sig) != 64 or len(pk) != 32:
            return False
        S = int.from_bytes(sig[32:], "little")
        if S >= l:                      # 规范要求：S < l
            return False
        A = decodepoint(pk)
        if is_small_order(A):           # 规范要求：拒绝小阶/单位点公钥
            return False
        R = decodepoint(sig[:32])
        h = int.from_bytes(H(sig[:32] + pk + m), "little")
        return scalarmult(B, S) == edwards(R, scalarmult(A, h))
    except Exception:
        return False

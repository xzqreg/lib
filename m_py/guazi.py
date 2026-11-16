# -*- coding: utf-8 -*-
"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '4K影视',
  lang: 'hipy'
})
"""
"""
4K影视 (com.kqkd.sgjm.az) TVBox / hipy 源

transport v3 协议自实现：
  P-256 ECDH 握手 -> HKDF 派生会话密钥 -> AES-GCM 加密业务 protobuf

依赖：requests, pycryptodome（hipy 环境一般自带）
"""
import sys
import os
import json
import time
import zlib
import hmac
import tempfile
import hashlib
import random

import requests

try:
    from Crypto.Cipher import AES
except Exception:  # pragma: no cover
    AES = None


# --------------------------------------------------------------------------- 常量
HOST = "103.236.60.72"
PORT = 19987
BASE = "/app/bn"
KEY_IDS = "83e093e7caf460c8de4bd75f1faf22d77383f62165d48ed2011eaf227f59e06e"
CLIENT_VERSION = "6.0.6"
DEVICE_ID = "d1d4721f28a0b5ee"          # 16 字符；服务端用 sha256(它) 校验
ACCOUNT = "3574628454"
PASSWORD = "Qqboy@362421"

# 模块 / 动作
M_USER, M_VOD = 2, 3
A_LOGIN = 30
A_LIST = 61        # 列表/搜索
A_DETAIL = 62      # 详情
A_PLAY = 69        # 播放地址

CHANNELS = [
    ("电视剧", "1"),
    ("动漫", "2"),
    ("电影", "3"),
    ("综艺", "4"),
    ("直播", "5"),
]

SORTS = [
    ("热播榜", "vod_hits_week"),
    ("最新", "time"),
    ("高分", "vod_score"),
]

# 服务端线路代号 -> 安卓端显示名（按详情里 f75 的顺序）
LINE_NAMES = {
    "BBA": "AG蓝光",
    "co": "KF蓝光",
    "zijianm3u8": "臻彩4K",
    "SH4K": "臻享4K",
    "shvip": "SH蓝光",
    "vod_1080": "CK蓝光",
    "zy1080_01": "CK1蓝光",
    "zy1080_02": "CK2蓝光",
    "youku": "YK蓝光",
}

CACHE_FILE = os.path.join(tempfile.gettempdir(), "4kys_session.json")


# --------------------------------------------------------------------------- P-256
class P256:
    P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
    A = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFC
    B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
    N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
    GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
    GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5

    @classmethod
    def _add(cls, p, q):
        if p is None:
            return q
        if q is None:
            return p
        x1, y1 = p
        x2, y2 = q
        if x1 == x2 and (y1 + y2) % cls.P == 0:
            return None
        if p == q:
            lam = (3 * x1 * x1 + cls.A) * pow(2 * y1, cls.P - 2, cls.P) % cls.P
        else:
            lam = (y2 - y1) * pow(x2 - x1, cls.P - 2, cls.P) % cls.P
        x3 = (lam * lam - x1 - x2) % cls.P
        y3 = (lam * (x1 - x3) - y1) % cls.P
        return (x3, y3)

    @classmethod
    def _mul(cls, k, p):
        r = None
        while k:
            if k & 1:
                r = cls._add(r, p)
            p = cls._add(p, p)
            k >>= 1
        return r

    @classmethod
    def gen(cls):
        d = random.randrange(1, cls.N)
        pub = cls._mul(d, (cls.GX, cls.GY))
        raw = b"\x04" + pub[0].to_bytes(32, "big") + pub[1].to_bytes(32, "big")
        return d, raw

    @classmethod
    def shared_x(cls, d, peer_raw):
        px = int.from_bytes(peer_raw[1:33], "big")
        py = int.from_bytes(peer_raw[33:65], "big")
        s = cls._mul(d, (px, py))
        return s[0].to_bytes(32, "big")


# --------------------------------------------------------------------------- protobuf
def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _tag(no, wt):
    return _varint((no << 3) | wt)


def f_var(no, val):
    return _tag(no, 0) + _varint(val)


def f_bytes(no, data):
    return _tag(no, 2) + _varint(len(data)) + data


def _read_varint(b, i):
    v = 0
    sh = 0
    while i < len(b):
        x = b[i]
        i += 1
        v |= (x & 0x7F) << sh
        sh += 7
        if not (x & 0x80):
            return v, i
    return None, i


def pb_parse(b):
    """返回 [(field_no, wire_type, value)]，value 对 varint 是 int，对 2 是 bytes"""
    out = []
    i = 0
    while i < len(b):
        tag, i = _read_varint(b, i)
        if tag is None or tag == 0:
            break
        wt, fn = tag & 7, tag >> 3
        if wt == 0:
            v, i = _read_varint(b, i)
            if v is None:
                break
            out.append((fn, 0, v))
        elif wt == 2:
            ln, i = _read_varint(b, i)
            if ln is None or i + ln > len(b):
                break
            out.append((fn, 2, b[i:i + ln]))
            i += ln
        elif wt == 5:
            out.append((fn, 5, b[i:i + 4]))
            i += 4
        elif wt == 1:
            out.append((fn, 1, b[i:i + 8]))
            i += 8
        else:
            break
    return out


def pb_get(b, no, default=None):
    for fn, wt, v in pb_parse(b):
        if fn == no:
            return v
    return default


def pb_all(b, no):
    return [v for fn, wt, v in pb_parse(b) if fn == no]


def _txt(v):
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8")
        except Exception:
            return ""
    return str(v)


# --------------------------------------------------------------------------- 传输
class Transport(object):
    def __init__(self):
        self.s = requests.Session()
        self.s.trust_env = False          # 忽略环境里的 HTTP_PROXY 等变量
        self.s.headers.update({
            "User-Agent": "okhttp/3.12.13",
            "Content-Type": "application/x-protobuf",
            "Accept-Encoding": "identity",
            "X-Transport-Key-Ids": KEY_IDS,
        })
        self.device_hdr = hashlib.sha256(DEVICE_ID.encode()).hexdigest()
        self.seq = 0
        self.session_id = None
        self.master = None
        self.user_token = None
        self._logging_in = False
        if not self._load_cache():          # 复用会话，省掉握手+登录（TVBox 每次请求可能新起进程）
            self.handshake()

    # 会话缓存：TVBox 每次调用常常是独立进程，缓存可把首屏耗时从数秒降到一次 RPC
    def _load_cache(self):
        try:
            raw = open(CACHE_FILE, "r", encoding="utf-8").read()
            obj = json.loads(raw)
            if time.time() - obj.get("ts", 0) > 12 * 3600:
                return False
            if obj.get("dev") != DEVICE_ID:
                return False
            master = bytes.fromhex(obj["master"])
            if len(master) != 32:
                return False
            self.session_id = obj["sid"]
            self.master = master
            self.user_token = obj.get("tok")
            return True
        except Exception:
            return False

    def _save_cache(self):
        try:
            json.dump({"sid": self.session_id, "master": self.master.hex(),
                       "tok": self.user_token, "ts": time.time(), "dev": DEVICE_ID},
                      open(CACHE_FILE, "w", encoding="utf-8"))
        except Exception:
            pass

    def _url(self, path):
        return "http://%s:%d%s%s" % (HOST, PORT, BASE, path)

    def handshake(self):
        d, pub = P256.gen()
        caps = f_var(1, 1) + f_var(3, 1)
        req = f_bytes(1, pub) + f_bytes(2, CLIENT_VERSION.encode()) + f_bytes(3, caps)
        last = None
        for attempt in range(4):
            r = self.s.post(self._url("/v3/handshake"), data=req,
                            headers={"X-Transport-Device": self.device_hdr}, timeout=20)
            if r.status_code == 200:
                break
            last = r.status_code
            if r.status_code == 429:
                # 握手有限流：短退避（引擎 15s 超时，不能睡太久）
                time.sleep(1 + attempt)
                continue
            raise Exception("handshake HTTP %d" % r.status_code)
        else:
            raise Exception("handshake HTTP %s (rate limited)" % last)
        body = r.content
        sid = pb_get(body, 1)
        spub = pb_get(body, 2)
        if not sid or not spub or len(spub) != 65:
            raise Exception("handshake response invalid")
        self.session_id = _txt(sid)
        shared = P256.shared_x(d, spub)
        prk = hmac.new(sid, shared, hashlib.sha256).digest()
        self.master = hmac.new(prk, b"v3-session" + b"\x01", hashlib.sha256).digest()
        self._save_cache()

    def _deflate(self, data):
        co = zlib.compressobj(6, zlib.DEFLATED, -15)
        return co.compress(data) + co.flush()

    def _inflate(self, data):
        for wbits in (-15, 15, 47):
            try:
                return zlib.decompress(data, wbits)
            except Exception:
                pass
        return data

    def _gcm_enc(self, plain):
        iv = bytes(random.getrandbits(8) for _ in range(12))
        c = AES.new(self.master, AES.MODE_GCM, nonce=iv)
        c.update(b"v3-request")
        ct, tag = c.encrypt_and_digest(plain)
        return iv + ct + tag

    def _gcm_dec(self, blob):
        iv, ct, tag = blob[:12], blob[12:-16], blob[-16:]
        c = AES.new(self.master, AES.MODE_GCM, nonce=iv)
        c.update(b"v3-response")
        return c.decrypt_and_verify(ct, tag)

    def login(self, account=None, password=None):
        account = account or ACCOUNT
        password = password or PASSWORD
        pl = f_bytes(1, account.encode()) + f_bytes(2, password.encode())
        self._logging_in = True
        try:
            resp = self._rpc_once(M_USER, A_LOGIN, pl)
        finally:
            self._logging_in = False
        payload = pb_get(resp, 4) or b""
        tok = pb_get(payload, 2)
        self.user_token = _txt(tok) if tok else None
        self._save_cache()
        return self.user_token

    def rpc(self, module, action, payload=b""):
        try:
            return self._rpc_once(module, action, payload)
        except Exception as e:
            msg = str(e)
            # 只有会话失效/网络类错误才值得重新握手；业务错误直接抛出
            if not any(k in msg for k in ("session", "transport", "rpc HTTP", "Connection",
                                          "timed out", "Max retries", "unnel")):
                raise
            self.user_token = None
            self.handshake()
            try:
                self.login()
            except Exception:
                pass
            return self._rpc_once(module, action, payload)

    def _rpc_once(self, module, action, payload=b""):
        # 不在这里自动登录：首页/分类/详情/搜索/播放都不需要用户态，
        # 少一次往返，避免触发引擎 15s 超时
        self.seq += 1
        rid = int(time.time() * 1000) * 1000 + self.seq
        core = (f_var(1, rid) + f_var(2, module) + f_var(3, action)
                + f_bytes(4, DEVICE_ID.encode()))
        if self.user_token:
            core += f_bytes(5, self.user_token.encode())
        if payload:
            core += f_bytes(6, payload)
        core += f_var(7, int(time.time() * 1000))

        cipher = self._gcm_enc(self._deflate(core))
        frame = f_var(1, rid) + f_bytes(2, cipher)
        r = self.s.post(self._url("/v3"), data=frame,
                        headers={"X-Session-Id": self.session_id,
                                 "X-Transport-Device": self.device_hdr}, timeout=20)
        if r.status_code != 200:
            raise Exception("rpc HTTP %d" % r.status_code)
        body = r.content
        blob = None
        for fn, wt, v in pb_parse(body):
            if fn == 2 and wt == 2:
                blob = v
        if blob is None:
            # 服务端明文错误
            st = pb_get(body, 3)
            raise Exception("rpc error: %s" % (_txt(st) if st else body[:80]))
        plain = self._inflate(self._gcm_dec(blob))
        st = pb_get(plain, 3)
        if st and _txt(st) != "ok":
            raise Exception("api: %s" % _txt(st))
        return plain


# --------------------------------------------------------------------------- 解析
def parse_items(payload):
    """列表 payload -> [{...}]"""
    out = []
    for raw in pb_all(payload, 1):
        if not isinstance(raw, bytes):
            continue
        item = {
            "vod_id": str(pb_get(raw, 1) or ""),
            "vod_name": _txt(pb_get(raw, 3) or b""),
            "vod_pic": _txt(pb_get(raw, 13) or pb_get(raw, 6) or pb_get(raw, 7) or b""),
            "vod_remarks": _txt(pb_get(raw, 11) or pb_get(raw, 9) or b""),
            "vod_year": _txt(pb_get(raw, 18) or b"")[:4] or str(pb_get(raw, 2) or ""),
            "vod_area": _txt(pb_get(raw, 16) or pb_get(raw, 28) or b""),
            "vod_content": _txt(pb_get(raw, 20) or pb_get(raw, 21) or b""),
            "vod_actor": ",".join(_txt(x) for x in pb_all(raw, 14) if x),
            "vod_director": _txt(pb_get(raw, 15) or b""),
        }
        if item["vod_name"]:
            out.append(item)
    return out


def parse_detail(payload):
    d = {
        "id": pb_get(payload, 1),
        "name": _txt(pb_get(payload, 5) or b""),
        "pic": _txt(pb_get(payload, 13) or pb_get(payload, 6) or b""),
        "desc": _txt(pb_get(payload, 21) or pb_get(payload, 71) or b""),
        "remarks": _txt(pb_get(payload, 22) or b""),
        "area": _txt(pb_get(payload, 28) or pb_get(payload, 16) or b""),
        "year": _txt(pb_get(payload, 30) or pb_get(payload, 2) or b""),
        "director": _txt(pb_get(payload, 18) or b""),
        "actors": ",".join(_txt(x) for x in pb_all(payload, 17) if x and b":" not in x),
        "groups": [],
    }
    # f75: 线路组 {f1: 线路名, f2: repeated {f3: token, f4: 集号}}
    for grp in pb_all(payload, 75):
        if not isinstance(grp, bytes):
            continue
        gname = _txt(pb_get(grp, 1) or b"") or "线路"
        eps = []
        for ep in pb_all(grp, 2):
            if not isinstance(ep, bytes):
                continue
            tok = pb_get(ep, 3)
            if not tok:
                continue
            eps.append({
                "name": _txt(pb_get(ep, 4) or b"") or _txt(tok),
                "token": _txt(tok),
                "idx": pb_get(ep, 1) or 0,
            })
        if eps:
            d["groups"].append({"name": gname, "episodes": eps})
    return d


# --------------------------------------------------------------------------- Spider
_TP = None

REGIONS = ["全部", "中国", "中国香港", "中国台湾", "美国", "韩国", "日本", "泰国", "英国", "新加坡"]
LANGS = ["全部", "国语", "粤语", "英语", "日语", "韩语", "闽南语", "其它"]
YEARS = ["全部"] + [str(y) for y in range(2026, 2009, -1)] + ["更早"]
GENRES = ["全部", "剧情", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻",
          "历史", "悬疑", "爱情", "都市", "武侠", "科幻", "恐怖", "惊悚", "冒险", "动画",
          "热血", "玄幻", "真人秀", "综艺", "音乐", "纪录片", "运动", "儿童", "教育", "军事"]


def _opts(names):
    out = [{"n": "全部", "v": ""}]
    for n in names:
        if n != "全部":
            out.append({"n": n, "v": n})
    return out


class Spider(object):
    def __init__(self, query_params=None, t4_api=None):
        self.t = None
        self.extend = ""

    def getName(self):
        return "4K影视"

    def init(self, extend=""):
        self.extend = extend or ""
        return None

    def _tp(self):
        global _TP
        if _TP is not None:
            return _TP
        if self.t is None:
            self.t = Transport()
            _TP = self.t
        return self.t

    def _cat(self, channel, page, sort_key="time", area="", lang="", year="", genre="", keyword=b""):
        f5 = f_bytes(3, channel.encode())          # 1电视剧 2动漫 3电影 4综艺 5直播
        if genre:
            f5 += f_bytes(8, genre.encode())       # 类型
        if area:
            f5 += f_bytes(6, area.encode())
        if lang:
            f5 += f_bytes(7, lang.encode())
        if year:
            f5 += f_bytes(9, year.encode())
        f5 += f_var(17, 30) + f_bytes(18, sort_key.encode()) + f_var(19, 1)
        pl = f_bytes(1, keyword) + f_var(2, page) + f_var(3, 30) + f_bytes(5, f5)
        resp = self._tp().rpc(M_VOD, A_LIST, pl)
        return parse_items(pb_get(resp, 4) or b"")

    # ---------------- TVBox / hipy 接口（返回 dict）
    def homeContent(self, filter=False):
        cats = [{"type_name": name, "type_id": tid} for name, tid in CHANNELS]
        filters = {}
        for _, tid in CHANNELS:
            if tid == "5":
                continue
            filters[tid] = [
                {"key": "sort", "name": "排序", "value": [{"n": n, "v": v} for n, v in SORTS]},
                {"key": "genre", "name": "类型", "value": _opts(GENRES)},
                {"key": "area", "name": "地区", "value": _opts(REGIONS)},
                {"key": "year", "name": "年份", "value": _opts(YEARS)},
                {"key": "lang", "name": "语言", "value": _opts(LANGS)},
            ]
        result = {"class": cats, "filters": filters}
        try:
            result["list"] = self._cat(CHANNELS[0][1], 1)
        except Exception as e:
            result["list"] = []
            result["msg"] = str(e)
        return result

    def homeVideoContent(self):
        try:
            return {"list": self._cat(CHANNELS[0][1], 1)}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1
        channel = tid if tid in [c for _, c in CHANNELS] else CHANNELS[0][1]
        ext = extend if isinstance(extend, dict) else {}
        try:
            vlist = self._cat(channel, page,
                              sort_key=ext.get("sort") or "time",
                              genre=ext.get("genre") or "",
                              area=ext.get("area") or "",
                              lang=ext.get("lang") or "",
                              year=ext.get("year") or "")
        except Exception:
            vlist = []
        return {"list": vlist, "page": page, "pagecount": 9999,
                "limit": 30, "total": 999999}

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, (list, tuple)) else ids
        resp = self._tp().rpc(M_VOD, A_DETAIL, f_var(1, int(vod_id)))
        d = parse_detail(pb_get(resp, 4) or b"")

        froms, urls = [], []
        for gi, g in enumerate(d["groups"]):
            code = g["name"] or ""
            gname = LINE_NAMES.get(code) or code or ("线路%d" % (gi + 1))
            if gname in froms:
                gname = "%s-%d" % (gname, gi + 1)
            froms.append(gname)
            urls.append("#".join("%s$%s" % (e["name"], e["token"]) for e in g["episodes"]))

        vod = {
            "vod_id": vod_id,
            "vod_name": d["name"],
            "vod_pic": d["pic"],
            "vod_year": d["year"],
            "vod_area": d["area"],
            "vod_remarks": d["remarks"],
            "vod_actor": d["actors"],
            "vod_director": d["director"],
            "vod_content": d["desc"],
            "vod_play_from": "$$$".join(froms) if froms else "默认",
            "vod_play_url": "$$$".join(urls) if urls else "",
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg=1):
        try:
            page = int(pg)
        except Exception:
            page = 1
        pl = (f_bytes(1, key.encode()) + f_var(2, page) + f_var(3, 30)
              + f_bytes(5, f_var(17, 30) + f_bytes(18, b"vod_hits_week") + f_var(19, 1)))
        try:
            resp = self._tp().rpc(M_VOD, A_LIST, pl)
            vlist = parse_items(pb_get(resp, 4) or b"")
        except Exception:
            vlist = []
        return {"list": vlist}

    def playerContent(self, flag, pid, vipFlags=None):
        pid = pid or ""
        header = {"User-Agent": "okhttp/3.12.13"}
        url = ""
        # f1 是源/清晰度序号，每条线路不一样，逐个重试；直播频道（zb-xxx）固定 7
        order = (7, 1, 2, 3, 4, 5, 6, 8) if pid.startswith("zb-") else (2, 1, 3, 4, 5, 6, 7, 8, 0)
        for q in order:
            try:
                resp = self._tp().rpc(M_VOD, A_PLAY, f_var(1, q) + f_bytes(2, pid.encode()))
                payload = pb_get(resp, 4) or b""
                url = _txt(pb_get(payload, 2) or b"")
                if url:
                    break
            except Exception:
                continue
        if url:
            return {"parse": 0, "playUrl": "", "url": url, "header": header}
        # 接口没给地址、但本身是网页链接（如 youku）时，交给外部解析
        if pid.startswith("http://") or pid.startswith("https://"):
            return {"parse": 1, "playUrl": "", "url": pid, "header": header}
        return {"parse": 0, "playUrl": "", "url": "", "header": header}

    def localProxy(self, params):
        return [404, "text/plain", ""]

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False


if __name__ == "__main__":
    sp = Spider()
    print(sp.homeContent()["class"])
    print(len(sp.categoryContent("1", 1, False, {"area": "中国"})["list"]))

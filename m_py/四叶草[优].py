# -*- coding: utf-8 -*-
"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '四叶草',
  lang: 'hipy'
})
"""
"""
四叶草 (com.minivideo.app) TVBox / hipy 源

协议要点（逆向自 2.1.0 版 APK）：
  * 设备注册：ECDH P-256 换 device_secret；本文件直接内置已注册设备的 device_secret
  * 业务请求：HMAC-SHA256 签名 + AES-256-GCM 加密请求体/响应
    签名串 = ts|nonce|deviceId|path|query|bodyHash
    请求头 = X-TS / X-Nonce / X-Device-Id / X-Client-Type / User-Agent / X-Sign
    响应 = {"encrypted":true,"data":"<b64(iv|ct|tag)>"} 或普通 JSON
  * 播放接口需要登录：账号写在下方 ACCOUNT 里，token 缓存 30 天

依赖：requests, pycryptodome
"""
import os
import re
import sys
import json
import time
import uuid
import hmac
import base64
import hashlib
import tempfile
import urllib.parse

import requests

try:
    from Crypto.Cipher import AES
except Exception:  # pragma: no cover
    AES = None

# 兼容 Pyramid / Chaquopy（安卓4.4 机顶盒）引擎：必须继承 base.spider.Spider
sys.path.append("..")
try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object


# --------------------------------------------------------------------------- 常量
BASE = "http://103.109.20.117:7777/api/"
BOOTSTRAP = "https://yzysap.oss-cn-hangzhou.aliyuncs.com/xzl.txt"
UA = "MiniVideo/2.1.0 (Android; Mobile)"
DEVICE_ID = "TANq0FVZbPDaAAxrurGpOg"
DEVICE_SECRET = "E15tEHt513B5gB0CEhaR2mwSa10FBKNT650nVEGGfvY="   # base64(32B)
ACCOUNT = ("qqboy", "Qqboy@362421")
PAGE_SIZE = 20
TIMEOUT = (6, 20)

# 金牌(jp://)客户端解析：app 自带，不走服务端
JPYS_BASE = "https://y2s52n7.com"
JPYS_KEY = "cb808529bae6b6be45ecfab29a4889bc"
JPYS_UA = ("Mozilla/5.0 (Linux; Android 12; M2012K10C) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
_JPYS = {"base": JPYS_BASE, "key": JPYS_KEY}

TOKEN_FILE = os.path.join(tempfile.gettempdir(), "syc_token.json")
BASE_FILE = os.path.join(tempfile.gettempdir(), "syc_base.json")
JPYS_FILE = os.path.join(tempfile.gettempdir(), "syc_jpys.json")

ORDERS = [("最新", "new"), ("评分", "score"), ("最热", "hot")]


class _Client(object):
    def __init__(self):
        self.token = ""
        self.exp = 0
        self.base = BASE
        self._load()

    # ---------------- 基础
    def _load(self):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if d.get("token") and d.get("exp", 0) > time.time():
                self.token = d["token"]
                self.exp = d["exp"]
        except Exception:
            pass
        try:
            with open(BASE_FILE, "r", encoding="utf-8") as f:
                b = json.load(f)
            if b.get("base"):
                self.base = b["base"]
        except Exception:
            pass
        try:
            with open(JPYS_FILE, "r", encoding="utf-8") as f:
                b = json.load(f)
            if b.get("jpys_base"):
                _JPYS["base"] = b["jpys_base"]
            if b.get("jpys_key"):
                _JPYS["key"] = b["jpys_key"]
        except Exception:
            pass

    def save_base_config(self, d):
        try:
            with open(JPYS_FILE, "w", encoding="utf-8") as f:
                json.dump(d, f)
        except Exception:
            pass

    def _save(self):
        try:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump({"token": self.token, "exp": self.exp}, f)
        except Exception:
            pass

    @staticmethod
    def _key():
        return base64.b64decode(DEVICE_SECRET)

    def _enc(self, plain):
        iv = os.urandom(12)
        c = AES.new(self._key(), AES.MODE_GCM, nonce=iv)
        ct, tag = c.encrypt_and_digest(plain)
        return base64.b64encode(iv + ct + tag).decode()

    def _dec(self, b64):
        raw = base64.b64decode(b64)
        c = AES.new(self._key(), AES.MODE_GCM, nonce=raw[:12])
        return c.decrypt_and_verify(raw[12:-16], raw[-16:])

    def _sign(self, ts, nonce, path, query, body_hash):
        msg = "|".join([ts, nonce, DEVICE_ID, path, query, body_hash])
        return hmac.new(self._key(), msg.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _q(params):
        if not params:
            return ""
        return "&".join("%s=%s" % (k, urllib.parse.quote(str(v)))
                        for k, v in params.items() if v not in (None, ""))

    # ---------------- 请求
    def call(self, method, path, params=None, body=None, retry=True):
        if AES is None:
            raise RuntimeError("缺少 pycryptodome")
        query = self._q(params)
        url = self.base + path + (("?" + query) if query else "")
        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        path_full = "/api/" + path
        body_bytes = b""
        body_hash = ""
        if body is not None:
            body_bytes = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            body_hash = hashlib.sha256(body_bytes).hexdigest()
        headers = {
            "X-TS": ts, "X-Nonce": nonce, "X-Device-Id": DEVICE_ID,
            "X-Client-Type": "android_app", "User-Agent": UA, "Accept": "application/json",
            "X-Sign": self._sign(ts, nonce, path_full, query, body_hash),
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = None
        if body is not None:
            data = json.dumps({"encrypted": True, "data": self._enc(body_bytes)},
                              separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
            headers["X-Body-Hash"] = body_hash
            headers["X-Encrypt"] = "1"
        r = requests.request(method, url, data=data, headers=headers, timeout=TIMEOUT)
        try:
            j = r.json()
        except Exception:
            return {"code": -1, "message": "bad json: %s" % r.text[:120], "data": None}
        if isinstance(j, dict) and j.get("encrypted") and j.get("data"):
            try:
                j = json.loads(self._dec(j["data"]))
            except Exception:
                return {"code": -1, "message": "解密失败", "data": None}
        if retry and isinstance(j, dict) and j.get("code") in (401, 4429):
            if j.get("code") == 401:
                self.token = ""
                self.exp = 0
                if self.login():
                    return self.call(method, path, params, body, retry=False)
        return j

    def login(self):
        u, p = ACCOUNT
        j = self.call("POST", "auth/login", None, {"username": u, "password": p}, retry=False)
        d = j.get("data") or {}
        tok = d.get("token") or ""
        if not tok:
            return False
        self.token = tok
        self.exp = time.time() + max(3600, int(d.get("expires_in") or 86400))
        self._save()
        return True

    def ensure_token(self):
        if not self.token and not self.login():
            return False
        return True


_C = _Client()


# --------------------------------------------------------------------------- 工具
def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


_TAGS = re.compile(r"<[^>]+>")


def _plain(s):
    s = _fmt(s)
    s = _TAGS.sub("", s)
    s = (s.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
         .replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " "))
    return s


def _item(v):
    return {
        "vod_id": v.get("vod_id"),
        "vod_name": _fmt(v.get("vod_name")),
        "vod_pic": _fmt(v.get("vod_pic")),
        "vod_remarks": _fmt(v.get("vod_remarks")),
        "vod_year": _fmt(v.get("vod_year")),
        "vod_area": _fmt(v.get("vod_area")),
        "vod_actor": _fmt(v.get("vod_actor")),
        "vod_director": _fmt(v.get("vod_director")),
        "vod_content": _plain(v.get("vod_content")),
    }


def _page_list(res):
    d = res.get("data") or {}
    items = [_item(v) for v in (d.get("list") or [])]
    return items, int(d.get("total") or 0), int(d.get("page") or 1), int(d.get("total_pages") or 1)


def _opts(names):
    out = [{"n": "全部", "v": ""}]
    for n in names or []:
        if n and n not in [x["v"] for x in out]:
            out.append({"n": n, "v": n})
    return out


# --------------------------------------------------------------------------- 金牌(jp://)解析
def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _sha1(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _jpys_refresh():
    """配置轮换时从 app/config 拉最新的 jpys 地址与 key。"""
    try:
        d = (_C.call("GET", "app/config") or {}).get("data") or {}
        base = (d.get("jpys_base") or "").strip()
        key = (d.get("jpys_key") or "").strip()
        if base.startswith("http") and len(key) >= 16:
            _JPYS["base"] = base.rstrip("/")
            _JPYS["key"] = key
            _C.save_base_config({"jpys_base": _JPYS["base"], "jpys_key": key})
            return True
    except Exception:
        pass
    return False


def _jpys_parse(url):
    raw = url or ""
    for _ in range(2):
        if raw.startswith("jp://"):
            raw = raw[5:]
    raw = raw.split("?", 1)[0]
    parts = [p for p in raw.split("/") if p]
    if len(parts) < 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        return ""
    vid, nid = parts[0], parts[1]

    def once():
        base, key = _JPYS["base"], _JPYS["key"]
        t = str(int(time.time() * 1000))
        sign = _sha1(_md5("id=%s&nid=%s&key=%s&t=%s" % (vid, nid, key, t)))
        api = "%s/api/mw-movie/anonymous/v2/video/episode/url?id=%s&nid=%s" % (base, vid, nid)
        h = {"sign": sign, "T": t, "Deviceid": "Deviceid", "User-Agent": JPYS_UA,
             "Accept": "application/json", "Origin": base, "Referer": base + "/"}
        r = requests.get(api, headers=h, timeout=(6, 15))
        if r.status_code in (401, 403):
            raise PermissionError("jpys auth")
        lst = ((r.json() or {}).get("data") or {}).get("list") or []
        best = None
        for it in lst:
            u = _fmt(it.get("url")).strip()
            if not u:
                continue
            res = it.get("resolution") or 0
            if best is None or res > best[0]:
                best = (res, u)
        return best[1] if best else ""

    try:
        return once()
    except PermissionError:
        if _jpys_refresh():
            try:
                return once()
            except Exception:
                return ""
    except Exception:
        return ""
    return ""


_URL_RE = re.compile(r"https?://[^\s\"'<>\\]+")


def _extract_play(body, ua=""):
    body = (body or "").strip()
    if not body:
        return ""
    try:
        j = json.loads(body)
    except Exception:
        j = None
    if isinstance(j, dict):
        for k in ("url", "play_url", "playurl", "playUrl"):
            v = j.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        d = j.get("data")
        if isinstance(d, dict):
            for k in ("url", "play_url", "playurl", "playUrl"):
                v = d.get(k)
                if isinstance(v, str) and v.startswith("http"):
                    return v
        elif isinstance(d, str) and d.startswith("http"):
            return d
    cands = [u.replace("&amp;", "&") for u in _URL_RE.findall(body)]
    if not cands:
        return ""
    for u in cands:
        if ".m3u8" in u or ".mp4" in u:
            return u
    return cands[0]


def _client_parse(parse_field, url, ua=""):
    """server_parse=0 的线路：用 parse 里配置的 JSON 解析前缀自己拼 URL 再取地址。"""
    prefixes = [p.strip() for p in (parse_field or "").split("|") if p.strip()]
    ua = ua or JPYS_UA
    for p in prefixes:
        if not p.startswith("http"):
            continue
        try:
            r = requests.get(p + url, headers={"User-Agent": ua}, timeout=(6, 12))
            if r.status_code != 200:
                continue
            play = _extract_play(r.text, ua)
            if play:
                return play
        except Exception:
            continue
    return ""


# --------------------------------------------------------------------------- Spider
_CATEGORIES = None
_OPTIONS_CACHE = {}


class Spider(_BaseSpider):
    def __init__(self, query_params=None, t4_api=None):
        self.t = None

    def getName(self):
        return "四叶草"

    def init(self, extend=""):
        return None

    # ---------------- 首页 / 分类
    def _cats(self):
        global _CATEGORIES
        if _CATEGORIES:
            return _CATEGORIES
        res = _C.call("GET", "videos/categories")
        cats = [{"type_name": _fmt(c.get("type_name")), "type_id": str(c.get("type_id"))}
                for c in (res.get("data") or [])]
        if cats:
            _CATEGORIES = cats
        return cats

    def homeContent(self, filter=False):
        cats = self._cats()
        filters = {}
        for c in cats:
            tid = c["type_id"]
            op = self._options(tid)
            filters[tid] = [
                {"key": "order", "name": "排序", "value": [{"n": n, "v": v} for n, v in ORDERS]},
                {"key": "class", "name": "类型", "value": _opts(op.get("classes"))},
                {"key": "area", "name": "地区", "value": _opts(op.get("areas"))},
                {"key": "year", "name": "年份", "value": _opts(op.get("years"))},
                {"key": "lang", "name": "语言", "value": _opts(op.get("langs"))},
            ]
        out = {"class": cats, "filters": filters}
        try:
            out["list"] = self.homeVideoContent()["list"]
        except Exception:
            out["list"] = []
        return out

    def _options(self, tid):
        key = str(tid)
        if key in _OPTIONS_CACHE:
            return _OPTIONS_CACHE[key]
        try:
            res = _C.call("GET", "videos/filter-options", {"type_id": tid})
            op = res.get("data") or {}
        except Exception:
            op = {}
        if op:
            _OPTIONS_CACHE[key] = op
        return op

    def homeVideoContent(self):
        try:
            res = _C.call("GET", "videos/recommend", {"limit": 12})
            groups = (res.get("data") or {}).get("groups") or []
            out, seen = [], set()
            for g in groups:
                for v in g.get("videos") or []:
                    if v.get("vod_id") in seen:
                        continue
                    seen.add(v.get("vod_id"))
                    out.append(_item(v))
            return {"list": out}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1
        ext = extend if isinstance(extend, dict) else {}
        tid = str(tid)
        order = ext.get("order") or "new"
        params = {"type_id": tid, "page": page, "page_size": PAGE_SIZE}
        filt = {k: ext.get(k) for k in ("class", "area", "year", "lang") if ext.get(k)}
        try:
            if filt:
                params.update(filt)
                params["order"] = order
                res = _C.call("GET", "videos/filter", params)
            else:
                params["order"] = order
                res = _C.call("GET", "videos/list", params)
            items, total, cur, pages = _page_list(res)
        except Exception:
            items, total, cur, pages = [], 0, page, 1
        return {"list": items, "page": cur or page,
                "pagecount": max(pages, page + (1 if items and not total else 0)),
                "limit": PAGE_SIZE, "total": total}

    # ---------------- 搜索 / 详情
    def searchContent(self, key, quick, pg=1):
        try:
            page = int(pg)
        except Exception:
            page = 1
        try:
            res = _C.call("GET", "videos/search",
                          {"keyword": key, "page": page, "page_size": PAGE_SIZE})
            items, total, cur, pages = _page_list(res)
        except Exception:
            items, total, cur, pages = [], 0, page, 1
        return {"list": items, "page": cur or page, "pagecount": pages,
                "limit": PAGE_SIZE, "total": total}

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, (list, tuple)) else ids
        res = _C.call("GET", "videos/detail/%s" % vod_id)
        d = res.get("data") or {}
        froms, urls = [], []
        for gi, src in enumerate(d.get("play_sources") or []):
            pi = src.get("player_info") or {}
            name = _fmt(pi.get("show") or src.get("source") or ("线路%d" % (gi + 1)))
            eps = src.get("episodes") or []
            if not eps:
                continue
            if name in froms:
                name = "%s-%d" % (name, gi + 1)
            parse = _fmt(pi.get("parse"))
            sp = _fmt(pi.get("server_parse") or 1)
            ua = _fmt(pi.get("user_agent"))
            froms.append(name)
            urls.append("#".join("%s$%s|%s|%s|%s|%s" % (
                _fmt(e.get("name")), _fmt(e.get("url")), _fmt(e.get("token")),
                parse, sp, ua) for e in eps))
        vod = _item(d)
        vod.update({
            "vod_id": vod_id,
            "vod_play_from": "$$$".join(froms) if froms else "默认",
            "vod_play_url": "$$$".join(urls),
        })
        return {"list": [vod]}

    # ---------------- 播放
    def playerContent(self, flag, pid, vipFlags=None):
        pid = pid or ""
        parts = pid.rsplit("|", 4)
        if len(parts) != 5:
            return {"parse": 0, "url": "", "header": {}}
        url, token, parse, sp, ua = parts
        header = {"User-Agent": ua} if ua else {}

        # 1) 金牌 jp:// —— 客户端解析（跟 App 一样）
        if sp == "2" or url.startswith("jp://"):
            play = _jpys_parse(url)
            if play:
                header = {"User-Agent": JPYS_UA}
            return {"parse": 0, "playUrl": "", "url": play, "header": header}

        # 2) server_parse=1 —— 服务端解析
        play = ""
        if sp != "0" and _C.ensure_token():
            for attempt in range(3):
                try:
                    res = _C.call("POST", "player/parse", None,
                                  {"parse_api": parse, "url": url, "token": token})
                    d = res.get("data") or {}
                    play = d.get("url") or d.get("proxy_url") or ""
                    if play or res.get("code") != 429:
                        break
                except Exception:
                    play = ""
                time.sleep(0.8 + 0.8 * attempt)

        # 3) server_parse=0 或服务端没给 —— 用 parse 配置的 JSON 接口自己解
        if not play and sp != "1" and parse.startswith("http"):
            play = _client_parse(parse, url, ua)

        return {"parse": 0, "playUrl": "", "url": play, "header": header}

    def localProxy(self, params):
        return [404, "text/plain", ""]

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False


if __name__ == "__main__":
    sp = Spider()
    cats = sp.homeContent()["class"]
    print("cate:", cats[:3])
    lst = sp.categoryContent(cats[0]["type_id"], 1, False, {})["list"]
    print("list:", len(lst), lst[0]["vod_name"] if lst else None)
    s = sp.searchContent("凡人修仙传", False, 1)["list"]
    print("search:", len(s), s[0]["vod_name"] if s else None)
    vod = sp.detailContent([lst[0]["vod_id"]])["list"][0]
    print("detail:", vod["vod_name"], "froms:", len(vod["vod_play_from"].split("$$$")))
    url = ""
    for frm, plist in zip(vod["vod_play_from"].split("$$$"), vod["vod_play_url"].split("$$$")):
        pid = plist.split("#")[0].split("$", 1)[1]
        play = sp.playerContent(frm, pid)
        print("play", frm, "->", play["url"][:80])
        url = play["url"] or url
        if url:
            break
    assert url, "no play url"

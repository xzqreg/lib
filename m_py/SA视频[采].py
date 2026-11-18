"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: 'SA视频',
  lang: 'hipy',
})
导航:   https://www.qiushui.vip   
           https://www.qiushuitv.cn
           https://www.qiushuiying.cn
由「影视py源生成器」自动生成 2026-09-17 21:05
站点: https://www.lsjys11.com
"""
import json
import time
import uuid
import re
import os
import gzip
import base64
import hashlib
import hmac
from urllib.parse import urljoin

import requests

try:
    from Crypto.Cipher import AES as _AES
except ImportError:
    _AES = None

try:
    from base.spider import Spider as _BaseSpider
except ImportError:
    class _BaseSpider(object):
        pass


def _unquote_html(s):
    return re.sub(r"<[^>]+>", "", s or "")


class Spider(_BaseSpider):
    name = "SA视频"
    base_url = "https://www.lsjys11.com"
    site_url = "https://www.lsjys11.com"
    api_url = "https://www.lsjys11.com/api"
    KEY = b"x3t8rvtaescfe38s"
    EP_FILTER = "/movie/filter"
    EP_SEARCH = "/search/movie"
    EP_DETAIL = "/movie/detail"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.lsjys11.com/",
        "Origin": "https://www.lsjys11.com",
    }
    timeout = 15
    page_size = "24"
    class_name = ["电影", "连续剧", "综艺", "短剧", "动漫", "纪录片"]
    class_url = ["13", "12", "11", "16", "14", "15"]
    _device_id = ("oct" + uuid.uuid4().hex)[:20]
    _session = None
    _filter_data = None
    _filter_ts = 0.0

    def getName(self):
        return self.name

    def init(self, extend=""):
        self._extend = extend or ""
        ext = {}
        if isinstance(extend, str) and extend.strip():
            try:
                ext = json.loads(extend)
            except Exception:
                ext = {}
        elif isinstance(extend, dict):
            ext = dict(extend)
        if isinstance(ext, dict):
            k = str(ext.get("key") or "")
            if k:
                self.KEY = k.encode()
            h = str(ext.get("host") or "").rstrip("/")
            if h.startswith("http"):
                self.base_url = h
                self.site_url = h
                self.api_url = h + "/api"
                self.headers["Referer"] = h + "/"
                self.headers["Origin"] = h
        return ""

    def getHeaders(self):
        return self.headers

    def _get_session(self):
        if self._session is None:
            s = _PowSession()
            s.trust_env = False
            s.verify = False
            s.headers.update(self.headers)
            self._session = s
        return self._session

    def _gen_key(self, rid):
        return hmac.new(self.KEY, bytes.fromhex(rid.replace("-", "")),
                        hashlib.sha256).digest()

    def _api(self, path, data, retries=2):
        if _AES is None:
            print(f"[{self.name}] 缺少 pycryptodome，无法使用加密接口: "
                  f"pip install pycryptodome")
            return None
        sess = self._get_session()
        for i in range(retries + 1):
            rid = str(uuid.uuid4())
            body = {"data": data, "token": "", "deviceId": self._device_id}
            raw = gzip.compress(json.dumps(body, separators=(",", ":")).encode())
            pad = 16 - len(raw) % 16
            raw += bytes([pad]) * pad
            iv = os.urandom(16)
            try:
                payload = base64.b64encode(
                    iv + _AES.new(self._gen_key(rid), _AES.MODE_CBC,
                                  iv).encrypt(raw)).decode()
                r = sess.post(
                    self.api_url + path, data=payload,
                    headers={"Content-Type": "text/plain",
                             "time": str(int(time.time() * 1000))[:11],
                             "version": "1.0.0", "deviceType": "web",
                             "requestId": rid, "language": "zh-cn",
                             "Accept": "application/json"},
                    timeout=self.timeout)
                if r.status_code != 200 or not r.text:
                    raise ValueError("http %s" % r.status_code)
                er = base64.b64decode(r.text.strip())
                pt = _AES.new(self._gen_key(rid), _AES.MODE_CBC,
                              er[:16]).decrypt(er[16:])
                pt = pt[:-pt[-1]]
                return json.loads(gzip.decompress(pt).decode())
            except Exception as e:
                print(f"[{self.name}] 接口异常({i + 1}/{retries + 1}) {path}: {e}")
                time.sleep(0.4)
        return None

    def _load_filters(self, force=False):
        now = time.time()
        if self._filter_data is not None and not force and now - self._filter_ts < 1800:
            return self._filter_data
        r = self._api(self.EP_FILTER, {})
        data = {}
        if isinstance(r, dict) and r.get("status") == "y" and isinstance(r.get("data"), dict):
            d = r["data"]
            cats = (d.get("category") or {})
            cat_items = [x for x in (cats.get("items") or []) if str(x.get("value") or "")]

            def block(field, items, name):
                vals = [{"n": _unquote_html(x.get("name")), "v": str(x.get("value") or "")}
                        for x in (items or [])]
                return {"key": field, "name": name, "value": vals} if vals else None

            for c in cat_items:
                tid = str(c.get("value") or "")
                blocks = []
                tags = ((c.get("filters") or {}).get("items")) or []
                b = block("tag_id", [t for t in tags if str(t.get("value") or "")], "标签")
                if b:
                    blocks.append(b)
                for field, fname in (("area", "地区"), ("language", "语言"),
                                     ("year", "年份"), ("series_status", "状态"),
                                     ("update_status", "状态"), ("sort", "排序")):
                    dim = d.get(field) or {}
                    b = block(dim.get("field") or field,
                              [x for x in (dim.get("items") or [])
                               if str(x.get("value") or "")],
                              fname)
                    if b:
                        blocks.append(b)
                data[tid] = blocks
        if data:
            self._filter_data = data
            self._filter_ts = now
        return self._filter_data or {}

    def homeContent(self, filter=False):
        result = {"class": [], "filters": {}, "list": []}
        classes = []
        r = self._api(self.EP_FILTER, {})
        if isinstance(r, dict) and isinstance(r.get("data"), dict):
            for c in ((r["data"].get("category") or {}).get("items") or []):
                tid = str(c.get("value") or "")
                if tid:
                    classes.append({"type_id": tid,
                                    "type_name": _unquote_html(c.get("name"))})
        if not classes and self.class_name:
            classes = [{"type_id": u, "type_name": n}
                       for n, u in zip(self.class_name, self.class_url)]
        result["class"] = classes
        if filter:
            result["filters"] = self._load_filters()
        r2 = self._api(self.EP_SEARCH, {"page": 1, "page_size": self.page_size,
                                        "order_direction": "desc",
                                        "position": "movie"})
        if isinstance(r2, dict) and isinstance((r2.get("data") or {}).get("data"), list):
            result["list"] = [self._brief(x) for x in r2["data"]["data"][:30]]
        return result

    def homeVideoContent(self):
        r = self._api(self.EP_SEARCH, {"page": 1, "page_size": "12",
                                       "order_direction": "desc",
                                       "position": "movie"})
        if isinstance(r, dict) and isinstance((r.get("data") or {}).get("data"), list):
            items = r["data"]["data"]
            if items:
                b = self._brief(items[0])
                b["vod_content"] = _unquote_html(str(items[0].get("description") or ""))
                return b
        return {}

    @staticmethod
    def _brief(item):
        return {
            "vod_id": str(item.get("id") or ""),
            "vod_name": _unquote_html(str(item.get("name") or "")),
            "vod_pic": str(item.get("img") or ""),
            "vod_remarks": str(item.get("duration") or ""),
            "vod_year": str(item.get("issue_year") or ""),
        }

    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = int(pg) if str(pg).isdigit() and int(pg) > 0 else 1
        result = {"list": [], "page": page, "pagecount": 1,
                  "limit": int(self.page_size), "total": 0}
        ext = {}
        if isinstance(extend, str) and extend.strip():
            try:
                ext = json.loads(extend)
            except Exception:
                ext = {}
        if isinstance(extend, dict):
            ext = dict(extend)
        body = {"page": page, "page_size": self.page_size,
                "order_direction": "desc", "position": "movie"}
        if str(tid):
            body["cat_id"] = str(tid)
        for k in ("tag_id", "area", "language", "year", "update_status",
                  "series_status", "order"):
            v = str(ext.get(k) or "")
            if v:
                body[k] = v
        r = self._api(self.EP_SEARCH, body)
        if isinstance(r, dict) and isinstance(r.get("data"), dict):
            d = r["data"]
            items = d.get("data") or []
            result["list"] = [self._brief(x) for x in items]
            try:
                result["total"] = int(d.get("total") or 0)
                result["pagecount"] = int(d.get("last_page") or 1)
            except Exception:
                pass
        return result

    def detailContent(self, ids):
        result = {"list": []}
        try:
            vid = str(ids[0])
            r = self._api(self.EP_DETAIL, {"id": vid})
            d = ((r or {}).get("data") or {}).get("data") or {}
            vod_name = _unquote_html(str(d.get("name") or ""))
            tags = [str(t.get("name") or "") for t in (d.get("tags") or [])
                    if t.get("name")]
            play_links = d.get("play_links") or []
            line_names = [str(x.get("name") or x.get("code") or "线路")
                          for x in play_links] or ["默认线路"]
            eps_groups = d.get("links") or []
            line_urls = []
            for _ln in line_names:
                eps = []
                for g in eps_groups:
                    for it in (g.get("items") or []):
                        lid = str(it.get("id") or "")
                        if lid:
                            eps.append("%s$%s|%s" % (
                                _unquote_html(str(it.get("name") or "")), vid, lid))
                if not eps:
                    eps.append("正片$%s|%s" % (vid, str(d.get("lid") or "")))
                line_urls.append("#".join(eps))
            vod = {
                "vod_id": vid,
                "vod_name": vod_name,
                "vod_pic": str(d.get("img") or ""),
                "vod_year": str(d.get("issue_year") or ""),
                "vod_area": str(d.get("area") or ""),
                "vod_actor": _unquote_html(str(d.get("actor") or "")),
                "vod_director": _unquote_html(str(d.get("director") or "")),
                "vod_type": ",".join(tags),
                "vod_remarks": str(d.get("links_tips") or ""),
                "vod_content": _unquote_html(str(d.get("description") or "")),
                "vod_play_from": "$$$".join(line_names),
                "vod_play_url": "$$$".join(line_urls),
            }
            result["list"].append(vod)
        except Exception as e:
            print(f"[{self.name}] 详情异常: {e}")
        return result

    def searchContent(self, key, quick=None, pg="1"):
        page = int(pg) if str(pg).isdigit() and int(pg) > 0 else 1
        result = {"list": [], "page": page, "pagecount": 1,
                  "limit": int(self.page_size), "total": 0}
        if not key:
            return result
        r = self._api(self.EP_SEARCH, {"page": page, "page_size": self.page_size,
                                       "keywords": str(key),
                                       "order_direction": "desc"})
        if isinstance(r, dict) and isinstance(r.get("data"), dict):
            d = r["data"]
            items = d.get("data") or []
            result["list"] = [self._brief(x) for x in items]
            try:
                result["total"] = int(d.get("total") or 0)
                result["pagecount"] = int(d.get("last_page") or 1)
            except Exception:
                pass
        return result

    def playerContent(self, flag, id, vipFlags=None):
        try:
            vid, _, lid = str(id).partition("|")
            line = str(flag or "")
            r = self._api(self.EP_DETAIL, {"id": vid, "lid": lid})
            d = ((r or {}).get("data") or {}).get("data") or {}
            url = ""
            for x in (d.get("play_links") or []):
                if (str(x.get("name") or "") == line
                        or str(x.get("code") or "") == line or not line):
                    url = str(x.get("m3u8_url") or "")
                    if url:
                        break
            if not url and (d.get("play_links") or []):
                url = str(d["play_links"][0].get("m3u8_url") or "")
            if url and not url.startswith("http"):
                url = urljoin(self.base_url + "/", url)
            if url:
                return {"parse": 0, "url": url,
                        "header": {"User-Agent": self.headers["User-Agent"],
                                   "Referer": self.base_url + "/"}}
            return {"parse": 1, "url": self.base_url + "/", "header": {}}
        except Exception as e:
            print(f"[{self.name}] 播放解析异常: {e}")
            return {"parse": 1, "url": self.base_url + "/", "header": {}}

    def isVideoFormat(self, url):
        return any(t in url for t in (".m3u8", ".mp4", ".flv", ".mkv"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            if self._session is not None:
                self._session.close()
        except Exception:
            pass

    def localProxy(self, param):
        return None


import requests as _rq
from urllib.parse import urlparse as _up


def _pow_params(text):
    if not text:
        return None
    if not ("正在验证您的浏览器" in text or "__cdn_pow" in text):
        return None
    import re as _re
    m = _re.search(r'var\s+TS\s*=\s*"([^"]+)"\s*,\s*SIG\s*=\s*"([^"]+)"\s*,'
                   r'\s*DIFF\s*=\s*"([^"]+)"\s*(?:,\s*MODE\s*=\s*"([^"]*)")?',
                   text)
    if not m:
        return None
    mc = _re.search(r'var\s+POW\s*=\s*"([^"]+)"', text)
    return {"ts": m.group(1), "sig": m.group(2),
            "diff": m.group(3) or "0000", "mode": m.group(4) or "auto",
            "cookie": mc.group(1) if mc else "__cdn_pow"}


def _pow_solve(sig, diff, mx=4000000):
    import hashlib as _hl
    import time as _t
    t0 = _t.time()
    n = 0
    while n < mx:
        if _hl.sha256((sig + str(n)).encode()).hexdigest().startswith(diff):
            return n
        n += 1
        if n % 50000 == 0 and _t.time() - t0 > 8:
            return None
    return None


try:
    class _PowSession(_rq.Session):

        def request(self, method, url, *a, **kw):
            r = _rq.Session.request(self, method, url, *a, **kw)
            try:
                txt = r.text or ""
            except Exception:
                return r
            for _i in range(2):
                p = _pow_params(txt)
                if not p:
                    break
                n = _pow_solve(p["sig"], p["diff"])
                if n is None:
                    break
                self.cookies.set(p["cookie"],
                                 "%s_%s_%s_%s" % (p["ts"], p["mode"], n, p["sig"]),
                                 domain=_up(url).netloc, path="/")
                r = _rq.Session.request(self, method, url, *a, **kw)
                try:
                    txt = r.text or ""
                except Exception:
                    break
            return r
except Exception:
    _PowSession = _rq.Session
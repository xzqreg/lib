import re
import time
import json
import requests
from urllib.parse import quote

try:
    from base.spider import Spider as BaseSpider
    RUN_IN_TVBOX = True
except ImportError:
    RUN_IN_TVBOX = False
    class BaseSpider:
        def init(self, extend=""): pass
        def getName(self): return "mock"

PC_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
         "AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/120.0.0.0 Safari/537.36")
MOBILE_UA = ("Mozilla/5.0 (Linux; Android 13; V2049A Build/TP1A.220624.014; wv) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36")

LXY_API = "https://jx.lxyy.club/public.php"
LXY_CALLER = "https://4k.pianku.online/"
LXY_BROWSER = "0123456789abcdef0123456789abcdef"

LXY_CODES = {"tx": "qq", "iq": "qiyi", "mg": "mgtv", "yk": "youku"}
MAX_IFACE_LINES = 99

_IFACE_CACHE = {}
_IFACE_CACHE_TTL = 5 * 60


def _lxyy_request(page_url, code="qq", iface=""):
    try:
        r = requests.post(
            LXY_API,
            json={
                "url": page_url, "code": code,
                "browser": LXY_BROWSER, "interface": iface,
                "excluded": [], "caller": LXY_CALLER,
            },
            headers={
                "User-Agent": PC_UA,
                "Referer": "https://jx.lxyy.club/",
                "Origin": "https://jx.lxyy.club",
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
            },
            timeout=15,
        )
        data = r.json()
        if data.get("success"):
            return (
                True, data.get("url", ""), data.get("format", "hls"),
                data.get("interfaces") or [],
            )
        print(f"[lxyy] 失败 code={code} iface={iface}: {data.get('message', '')}")
    except Exception as e:
        print(f"[lxyy] 异常 code={code}: {e}")
    return False, "", "", []


def lxyy_resolve(page_url, code="qq", iface=""):
    ok, url, fmt, _ = _lxyy_request(page_url, code, iface)
    return (url, fmt) if ok else (None, None)


def lxyy_get_interfaces(page_url, code="qq"):
    if not page_url:
        return []
    now = time.time()
    cache_key = (code, page_url)
    if cache_key in _IFACE_CACHE:
        ts, ifaces = _IFACE_CACHE[cache_key]
        if now - ts < _IFACE_CACHE_TTL:
            print(f"[lxyy] 接口列表命中缓存 code={code} ({len(ifaces)} 条)")
            return ifaces

    ok, _, _, ifaces_raw = _lxyy_request(page_url, code, "")
    if not ok:
        return []

    result = []
    for it in ifaces_raw:
        if it.get("type") == "json" and it.get("id"):
            result.append({
                "id": it["id"],
                "name": it.get("name") or it["id"][:8],
            })

    if result:
        _IFACE_CACHE[cache_key] = (now, result)
    return result


# ============================================================
# 腾讯
# ============================================================
class TxAdapter:
    SITE = "tx"
    SITE_NAME = "腾讯"
    CLASSES = [
        ("1", "电影"), ("2", "连续剧"), ("3", "综艺"),
        ("4", "动漫"), ("5", "少儿"), ("6", "纪录片"), ("7", "短剧"),
    ]
    HOSTS = [
        "https://cj.10010888.xyz",
        "https://tianwei.qzz.io",
        "http://cj.tianwe.cn",
        "http://tianwei.qzz.io",
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": PC_UA})

    def _req(self, path):
        for host in self.HOSTS:
            try:
                r = self.session.get(host + path, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, dict) and data.get("list"):
                        return data
            except Exception:
                continue
        return {}

    def category(self, cid, pg, ext=None):
        ext = ext or {}
        path = (f"/api.php/provide/vod/?ac=detail&from=qq&t={cid}&pg={pg}"
                f"&year={ext.get('year', '')}"
                f"&area={ext.get('area', '')}"
                f"&by={ext.get('by', '')}")
        return self._req(path).get("list", [])

    def detail(self, vid):
        lst = self._req(f"/api.php/provide/vod/?ac=detail&ids={vid}").get("list", [])
        return lst[0] if lst else {}

    def search(self, key, pg):
        path = f"/api.php/provide/vod/?ac=detail&wd={quote(key)}&pg={pg}"
        return self._req(path).get("list", [])

    def get_filter_objects(self, cid):
        year = [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2014, -1)]
        area = [{"n": "全部", "v": ""}] + [{"n": n, "v": n} for n in
                                            ["大陆", "香港", "台湾", "美国", "韩国", "日本", "泰国"]]
        sort = [{"n": "最新", "v": "time"}, {"n": "最热", "v": "hits"}, {"n": "评分", "v": "score"}]
        return [
            {"key": "year", "name": "年份", "value": year},
            {"key": "area", "name": "地区", "value": area},
            {"key": "by", "name": "排序", "value": sort},
        ]


# ============================================================
# 爱奇艺
# ============================================================
class IqiyiAdapter:
    SITE = "iq"
    SITE_NAME = "爱奇艺"
    CLASSES = [
        ("2", "电视剧"), ("35", "短剧"), ("1", "电影"), ("6", "综艺"),
        ("15", "少儿"), ("4", "动漫"), ("37", "漫剧"), ("3", "纪录片"), ("31", "知识"),
    ]
    HOST = "https://pcw-api.iqiyi.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": PC_UA,
            "Referer": "https://www.iqiyi.com/",
            "Origin": "https://www.iqiyi.com",
        })

    def category(self, cid, pg, ext=None):
        try:
            url = f"{self.HOST}/search/recommend/list?channel_id={cid}&data_type=1&page_id={pg}&ret_num=24"
            r = self.session.get(url, timeout=10)
            data = r.json()
            return (data.get("data") or {}).get("list") or []
        except Exception:
            return []

    def detail_info(self, vid):
        try:
            url = (f"{self.HOST}/video/video/videoinfowithuser/{vid}"
                   f"?agent_type=1&authcookie=&subkey={vid}&subscribe=1")
            r = self.session.get(url, timeout=10)
            return r.json().get("data", {})
        except Exception:
            return {}

    def episodes(self, album_id):
        try:
            all_eps, page = [], 1
            while page <= 10:
                url = f"{self.HOST}/albums/album/avlistinfo?aid={album_id}&size=200&page={page}"
                r = self.session.get(url, timeout=10)
                data = r.json().get("data", {})
                eps = data.get("epsodelist", [])
                all_eps.extend(eps)
                total = data.get("total", 0)
                if len(all_eps) >= total or len(eps) < 200:
                    break
                page += 1
            return all_eps
        except Exception:
            return []

    def episode_url(self, ep):
        return ep.get("playUrl", "")

    def search(self, key, pg):
        try:
            url = (f"https://search.video.iqiyi.com/o?if=html5&key={quote(key)}"
                   f"&pageNum={pg}&pos=1&pageSize=24&site=iqiyi")
            r = self.session.get(url, timeout=10)
            return r.json().get("data", {}).get("docinfos", [])
        except Exception:
            return []

    def get_filter_objects(self, cid):
        year = [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2014, -1)]
        area = [{"n": "全部", "v": ""}] + [{"n": n, "v": n} for n in
                                            ["大陆", "香港", "台湾", "美国", "韩国", "日本"]]
        sort = [{"n": "最热", "v": "1"}, {"n": "最新", "v": "4"}, {"n": "评分", "v": "7"}]
        return [
            {"key": "year", "name": "年份", "value": year},
            {"key": "area", "name": "地区", "value": area},
            {"key": "sort", "name": "排序", "value": sort},
        ]


# ============================================================
# 芒果
# ============================================================
class MgtvAdapter:
    SITE = "mg"
    SITE_NAME = "芒果"
    CLASSES = [
        ("2", "电视剧"), ("3", "电影"), ("1", "综艺"), ("50", "动漫"),
        ("51", "纪录片"), ("115", "教育"), ("10", "少儿"),
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": PC_UA,
            "Referer": "https://www.mgtv.com/",
        })

    def category(self, cid, pg, ext=None):
        ext = ext or {}
        try:
            url = (f"https://pianku.api.mgtv.com/rider/list/pcweb/v3"
                   f"?platform=pcweb&channelId={cid}&pn={pg}&pc=20&hudong=1"
                   f"&_support=10000000&kind=a1&area=a1"
                   f"&year={ext.get('year', 'all')}"
                   f"&sort={ext.get('sort', 'all')}"
                   f"&chargeInfo={ext.get('chargeInfo', 'all')}")
            r = self.session.get(url, timeout=10)
            return r.json().get("data", {}).get("hitDocs", [])
        except Exception:
            return []

    def detail_info(self, vid):
        try:
            url = f"https://pcweb.api.mgtv.com/episode/list?page=1&size=50&video_id={vid}"
            r = self.session.get(url, timeout=10)
            return r.json().get("data", {})
        except Exception:
            return {}

    def episodes(self, vid):
        data = self.detail_info(vid)
        return data.get("list", []) or data.get("series", [])

    def episode_url(self, ep):
        u = ep.get("url", "")
        if u and not u.startswith("http"):
            u = "https://www.mgtv.com" + u
        return u

    def search(self, key, pg):
        try:
            url = f"https://mobileso.bz.mgtv.com/pc/search/v1?q={quote(key)}&pn={pg}&pc=10"
            r = self.session.get(url, timeout=10)
            return r.json().get("data", {}).get("contents", [])
        except Exception:
            return []

    def get_filter_objects(self, cid):
        year = [{"n": "全部", "v": "all"}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2004, -1)]
        sort = [{"n": "最新", "v": "c1"}, {"n": "最热", "v": "c2"}, {"n": "高分", "v": "c4"}]
        charge = [{"n": "全部", "v": "all"}, {"n": "免费", "v": "b1"},
                  {"n": "VIP", "v": "b2"}, {"n": "用券", "v": "b3"}]
        return [
            {"key": "year", "name": "年份", "value": year},
            {"key": "sort", "name": "排序", "value": sort},
            {"key": "chargeInfo", "name": "付费", "value": charge},
        ]


# ============================================================
# 优酷
# ============================================================
class YoukuAdapter:
    SITE = "yk"
    SITE_NAME = "优酷"
    CLASS_NAMES = {
        "1": "电视剧", "2": "电影", "3": "综艺", "4": "动漫",
        "5": "少儿", "6": "纪录片", "7": "文化", "8": "亲子",
        "9": "教育", "10": "搞笑", "11": "生活", "12": "体育",
        "13": "音乐", "14": "游戏",
    }
    CLASSES = [(k, v) for k, v in CLASS_NAMES.items()]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": PC_UA,
            "Referer": "https://www.youku.com/",
        })

    def category(self, cid, pg, ext=None):
        ext = ext or {}
        try:
            params = {
                "type": self.CLASS_NAMES.get(cid, "电视剧"),
                "main_area": ext.get("main_area", ""),
                "tags": ext.get("tags", ""),
                "year": ext.get("year", ""),
                "status": ext.get("status", ""),
                "pay_type": ext.get("pay_type", ""),
                "sort": ext.get("sort", ""),
                "tag_label_name": ext.get("tag_label_name", ""),
            }
            params_str = quote(json.dumps(params, ensure_ascii=False))
            url = f"https://www.youku.com/category/data?optionRefresh=1&pageNo={pg}&params={params_str}"
            r = self.session.get(url, timeout=10)
            return r.json().get("data", {}).get("filterData", {}).get("listData", [])
        except Exception:
            return []

    def detail_info(self, vid):
        try:
            url = f"https://search.youku.com/api/search?appScene=show_episode&showIds={vid}"
            r = self.session.get(url, timeout=10)
            return r.json()
        except Exception:
            return {}

    def episodes(self, vid):
        return self.detail_info(vid).get("serisesList", [])

    def episode_url(self, ep):
        vid = ep.get("videoId", "")
        return f"https://v.youku.com/v_show/id_{vid}.html" if vid else ""

    def search(self, key, pg):
        try:
            url = f"https://search.youku.com/api/search?pg={pg}&keyword={quote(key)}"
            r = self.session.get(url, timeout=10)
            return r.json().get("pageComponentList", [])
        except Exception:
            return []

    def get_filter_objects(self, cid):
        year = [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2014, -1)]
        area = [{"n": "全部", "v": ""}] + [
            {"n": "内地", "v": "中国内地"}, {"n": "香港", "v": "中国香港"},
            {"n": "台湾", "v": "中国台湾"}, {"n": "美国", "v": "美国"},
            {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"},
        ]
        sort = [{"n": "综合", "v": ""}, {"n": "最热", "v": "7"},
                {"n": "最新", "v": "1"}, {"n": "好评", "v": "3"}]
        return [
            {"key": "year", "name": "年份", "value": year},
            {"key": "main_area", "name": "地区", "value": area},
            {"key": "sort", "name": "排序", "value": sort},
        ]


# ============================================================
# 主 Spider
# ============================================================
class Spider(BaseSpider):
    PAGE_SIZE = 20
    MAX_PAGECOUNT = 999

    def init(self, extend=""):
        self.adapters = {
            "tx": TxAdapter(),
            "iq": IqiyiAdapter(),
            "mg": MgtvAdapter(),
            "yk": YoukuAdapter(),
        }

    def destroy(self):
        for a in self.adapters.values():
            try:
                a.session.close()
            except Exception:
                pass

    @staticmethod
    def _safe_dict(v):
        if v is None: return {}
        if isinstance(v, dict): return v
        if isinstance(v, str):
            s = v.strip()
            if not s: return {}
            try:
                d = json.loads(s)
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _safe_list(v):
        if v is None: return []
        if isinstance(v, list): return v
        if isinstance(v, tuple): return list(v)
        if isinstance(v, str): return [v] if v else []
        return [str(v)]

    @staticmethod
    def _iq_pic(url):
        if not url: return ""
        try: return str(url).replace(".jpg", "_390_520.jpg?caplist=jpg,webp")
        except: return ""

    @staticmethod
    def _iq_remarks(it):
        try:
            cid = it.get("channelId")
            score_raw = it.get("score")
            score = (str(score_raw) + "分") if score_raw else ""
            if cid == 1:
                return score or str(it.get("duration", "") or "")
            if cid in (2, 4, 35, 15, 37):
                latest = it.get("latestOrder") or ""
                total = it.get("videoCount") or ""
                score_p = (score + " ") if score else ""
                if total and latest and str(latest) == str(total):
                    return score_p + str(total) + "集全"
                if total and latest:
                    return score_p + f"{latest}/{total}集"
                if latest:
                    return f"更新至{latest}集"
                return str(it.get("focus", "") or "")
            if cid == 6:
                period = it.get("period") or ""
                return f"{period}期" if period else ""
            return str(it.get("focus", "") or "")
        except Exception:
            return ""

    # ========== 首页 ==========
    def homeContent(self, filter=False):
        classes, filters = [], {}
        for site in ["tx", "iq", "mg", "yk"]:
            adapter = self.adapters[site]
            for cid, cname in adapter.CLASSES:
                tid = f"{site}_{cid}"
                classes.append({"type_id": tid, "type_name": f"{adapter.SITE_NAME}·{cname}"})
                filters[tid] = adapter.get_filter_objects(cid)
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        try:
            items = self.adapters["tx"].category("2", 1)
            return {"list": [{
                "vod_id": f"tx_{it.get('vod_id', '')}",
                "vod_name": it.get("vod_name", ""),
                "vod_pic": it.get("vod_pic", ""),
                "vod_remarks": it.get("vod_remarks", ""),
            } for it in items[:30]]}
        except Exception:
            return {"list": []}

    # ========== 分类 ==========
    def categoryContent(self, tid="1", pg="1", filter=False, extend=None):
        tid = str(tid or "1")
        try: pg_num = int(pg or 1)
        except: pg_num = 1
        ext = self._safe_dict(extend)

        if "_" not in tid:
            return {"list": [], "page": pg_num, "pagecount": 1, "limit": 0, "total": 0, "filters": {}}
        site, cid = tid.split("_", 1)
        adapter = self.adapters.get(site)
        if not adapter:
            return {"list": [], "page": pg_num, "pagecount": 1, "limit": 0, "total": 0, "filters": {}}

        videos = []
        try:
            items = adapter.category(cid, pg_num, ext)
            if site == "tx":
                for it in items:
                    videos.append({
                        "vod_id": f"tx_{it.get('vod_id', '')}",
                        "vod_name": it.get("vod_name", ""),
                        "vod_pic": it.get("vod_pic", ""),
                        "vod_remarks": it.get("vod_remarks", ""),
                    })
            elif site == "iq":
                for it in items:
                    try:
                        vid = it.get("albumId") or it.get("tvId") or ""
                        if not vid: continue
                        videos.append({
                            "vod_id": f"iq_{vid}",
                            "vod_name": it.get("name", "") or "",
                            "vod_pic": self._iq_pic(it.get("imageUrl", "")),
                            "vod_remarks": self._iq_remarks(it),
                        })
                    except Exception:
                        continue
            elif site == "mg":
                for it in items:
                    ppid = it.get("playPartId")
                    if not ppid: continue
                    videos.append({
                        "vod_id": f"mg_{ppid}",
                        "vod_name": it.get("title", ""),
                        "vod_pic": it.get("img", ""),
                        "vod_remarks": it.get("updateInfo", "")
                                         or (it.get("rightCorner") or {}).get("text", ""),
                    })
            elif site == "yk":
                for it in items:
                    link = it.get("videoLink", "")
                    m = re.search(r'id_([A-Za-z0-9=]+)', link)
                    if not m: continue
                    videos.append({
                        "vod_id": f"yk_{m.group(1)}",
                        "vod_name": it.get("title", ""),
                        "vod_pic": it.get("img", ""),
                        "vod_remarks": it.get("subTitle", ""),
                    })
        except Exception as e:
            print(f"[{site}] categoryContent 异常: {e}")

        has_next = len(videos) >= self.PAGE_SIZE
        pagecount = min(pg_num + 1 if has_next else pg_num, self.MAX_PAGECOUNT)
        filters_dict = {o["key"]: o["value"] for o in adapter.get_filter_objects(cid)}

        return {
            "list": videos, "page": pg_num,
            "pagecount": pagecount,
            "limit": self.PAGE_SIZE,
            "total": pagecount * self.PAGE_SIZE,
            "filters": filters_dict,
        }

    # ========== 详情 ==========
    def detailContent(self, ids=None):
        ids = self._safe_list(ids)
        if not ids: return {"list": []}
        full_id = str(ids[0])
        if "_" not in full_id: return {"list": []}
        site, real_id = full_id.split("_", 1)
        try:
            if site == "tx": return self._detail_tx(real_id)
            if site == "iq": return self._detail_iq(real_id)
            if site == "mg": return self._detail_mg(real_id)
            if site == "yk": return self._detail_yk(real_id)
        except Exception as e:
            print(f"[{site}] detailContent 异常: {e}")
        return {"list": []}

    def _build_multi_line_detail(self, site, real_id, vod_meta, ep_items):
        if not ep_items:
            return {"list": []}

        first_url = ep_items[0][1]
        code = LXY_CODES.get(site, "qq")
        interfaces = []
        if first_url:
            try:
                interfaces = lxyy_get_interfaces(first_url, code=code)
                if interfaces:
                    print(f"[{site}] 拿到 {len(interfaces)} 个接口: {[i['name'] for i in interfaces]}")
            except Exception as e:
                print(f"[{site}] 拿接口列表异常: {e}")

        play_from_list = ["自动"]
        auto_eps = [f"{name}${site}_{real_id}_{i}_auto" for i, (name, _) in enumerate(ep_items)]
        play_url_list = ["#".join(auto_eps)]

        for iface in interfaces[:MAX_IFACE_LINES]:
            iface_id = iface["id"]
            label = iface.get("name", iface_id[:8])
            line_eps = [f"{name}${site}_{real_id}_{i}_{iface_id}"
                        for i, (name, _) in enumerate(ep_items)]
            play_from_list.append(label)
            play_url_list.append("#".join(line_eps))

        vod = dict(vod_meta)
        vod["vod_id"] = f"{site}_{real_id}"
        vod["vod_play_from"] = "$$$".join(play_from_list)
        vod["vod_play_url"] = "$$$".join(play_url_list)
        return {"list": [vod]}

    def _detail_tx(self, real_id):
        v = self.adapters["tx"].detail(real_id)
        if not v: return {"list": []}
        lines = v.get("vod_play_url", "").split("$$$")
        eps = lines[0].split("#") if lines else []
        ep_items = []
        for ep in eps:
            parts = ep.split("$")
            if len(parts) >= 2:
                ep_items.append((parts[0], parts[1]))
        meta = {
            "vod_name": v.get("vod_name", ""),
            "vod_pic": v.get("vod_pic", ""),
            "vod_year": v.get("vod_year", ""),
            "vod_actor": v.get("vod_actor", ""),
            "vod_director": v.get("vod_director", ""),
            "vod_content": v.get("vod_content", ""),
            "vod_remarks": v.get("vod_remarks", ""),
        }
        return self._build_multi_line_detail("tx", real_id, meta, ep_items)

    def _detail_iq(self, real_id):
        info = self.adapters["iq"].detail_info(real_id)
        if not info: return {"list": []}
        album_id = info.get("albumId", real_id)
        eps = self.adapters["iq"].episodes(album_id)
        ep_items = []
        for i, ep in enumerate(eps):
            name = ep.get("shortTitle") or f"第{ep.get('order', i + 1)}集"
            url = self.adapters["iq"].episode_url(ep)
            ep_items.append((name, url))
        cats = info.get("categories") or []
        type_name = ",".join([c.get("name", "") for c in cats if c.get("name")])
        meta = {
            "vod_name": info.get("name", ""),
            "vod_pic": (info.get("imageUrl") or "").replace(".jpg", "_390_520.jpg"),
            "vod_content": info.get("description", ""),
            "vod_remarks": info.get("subtitle", "") or "",
            "type_name": type_name,
        }
        return self._build_multi_line_detail("iq", album_id, meta, ep_items)

    def _detail_mg(self, real_id):
        data = self.adapters["mg"].detail_info(real_id)
        if not data: return {"list": []}
        eps = data.get("list", [])
        ep_items = []
        for i, ep in enumerate(eps):
            name = ep.get("t4") or f"第{i + 1}集"
            url = self.adapters["mg"].episode_url(ep)
            ep_items.append((name, url))
        series = data.get("series") or [{}]
        info = data.get("info") or {}
        vod_name = (
            (series[0].get("name") if series else "")
            or info.get("name")
            or (eps[0].get("t1") if eps else "")
            or (eps[0].get("t3") if eps else "")
            or f"芒果_{real_id}"
        )
        meta = {
            "vod_name": vod_name,
            "vod_pic": info.get("image") or (eps[0].get("img") if eps else ""),
            "vod_content": info.get("desc") or "",
            "vod_remarks": (series[0].get("desc") if series else "") or "",
        }
        return self._build_multi_line_detail("mg", real_id, meta, ep_items)

    def _detail_yk(self, real_id):
        data = self.adapters["yk"].detail_info(real_id)
        if not data: return {"list": []}
        eps = data.get("serisesList", [])
        ep_items = []
        for i, ep in enumerate(eps):
            name = ep.get("displayName") or ep.get("title") or f"第{i + 1}集"
            url = self.adapters["yk"].episode_url(ep)
            ep_items.append((name, url))
        src_name = data.get("sourceName", "优酷")
        meta = {
            "vod_name": eps[0].get("title", "") if eps else "",
            "vod_pic": eps[0].get("thumbUrl", "") if eps else "",
            "vod_content": "",
            "vod_remarks": src_name,
        }
        return self._build_multi_line_detail("yk", real_id, meta, ep_items)

    # ========== 搜索 ==========
    def searchContent(self, key="", quick=False, pg="1"):
        if not key: return {"list": []}
        try: pg_num = int(pg or 1)
        except: pg_num = 1
        results = []

        try:
            for it in self.adapters["tx"].search(key, pg_num):
                results.append({
                    "vod_id": f"tx_{it.get('vod_id', '')}",
                    "vod_name": it.get("vod_name", ""),
                    "vod_pic": it.get("vod_pic", ""),
                    "vod_remarks": it.get("vod_remarks", ""),
                })
        except Exception: pass

        try:
            for it in self.adapters["iq"].search(key, pg_num):
                info = it.get("albumDocInfo", {})
                if not info.get("albumId"): continue
                results.append({
                    "vod_id": f"iq_{info['albumId']}",
                    "vod_name": info.get("albumTitle", ""),
                    "vod_pic": info.get("albumVImage", ""),
                    "vod_remarks": info.get("tvFocus", ""),
                })
        except Exception: pass

        try:
            for it in self.adapters["mg"].search(key, pg_num):
                data = it.get("data", {}) or {}
                sources = data.get("sourceList")
                if not sources:
                    years = data.get("yearList") or []
                    sources = years[0].get("sourceList") if years else None
                if not sources: continue
                pic = data.get("pic") or (data.get("yearList", [{}])[0].get("pic", "") if data.get("yearList") else "")
                title = data.get("title") or (data.get("yearList", [{}])[0].get("title", "") if data.get("yearList") else "")
                results.append({
                    "vod_id": f"mg_{sources[0].get('vid', '')}",
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": data.get("playTime", ""),
                })
        except Exception: pass

        try:
            for it in self.adapters["yk"].search(key, pg_num):
                cd = it.get("commonData")
                if not cd or not cd.get("showId"): continue
                results.append({
                    "vod_id": f"yk_{cd['showId']}",
                    "vod_name": cd.get("titleDTO", {}).get("displayName", ""),
                    "vod_pic": cd.get("posterDTO", {}).get("vThumbUrl", ""),
                    "vod_remarks": cd.get("stripeBottom", ""),
                })
        except Exception: pass

        return {"list": results, "page": pg_num}

    # ========== 播放 ==========
    def playerContent(self, flag="", id="", vipFlags=None):
        id = str(id or "")
        parts = id.rsplit("_", 3)
        if len(parts) == 4:
            site, real_id, idx_str, iface = parts
        elif len(parts) == 3:
            site, real_id, idx_str = parts
            iface = "auto"
        else:
            return {"parse": 1, "url": "", "msg": "id 格式错误"}
        try: idx = int(idx_str)
        except: idx = 0

        adapter = self.adapters.get(site)
        if not adapter:
            return {"parse": 1, "url": "", "msg": "未知站点"}

        play_page_url = ""
        extra_header = {"User-Agent": PC_UA}

        if site == "tx":
            v = adapter.detail(real_id)
            lines = v.get("vod_play_url", "").split("$$$")
            eps = lines[0].split("#") if lines else []
            if idx >= len(eps):
                return {"parse": 1, "url": "", "msg": "集数越界"}
            raw = eps[idx].split("$")[1] if "$" in eps[idx] else ""
            if ".m3u8" in raw or ".mp4" in raw:
                return {"parse": 0, "url": raw,
                        "header": {"User-Agent": PC_UA, "Referer": "https://m.v.qq.com/"}}
            play_page_url = raw
            extra_header = {"User-Agent": PC_UA, "Referer": "https://m.v.qq.com/"}

        elif site == "iq":
            eps = adapter.episodes(real_id)
            if idx >= len(eps):
                return {"parse": 1, "url": "", "msg": "集数越界"}
            play_page_url = adapter.episode_url(eps[idx])
            extra_header = {"User-Agent": PC_UA, "Referer": "https://www.iqiyi.com/"}

        elif site == "mg":
            eps = adapter.episodes(real_id)
            if idx >= len(eps):
                return {"parse": 1, "url": "", "msg": "集数越界"}
            play_page_url = adapter.episode_url(eps[idx])
            extra_header = {"User-Agent": MOBILE_UA, "Referer": "https://www.mgtv.com/"}

        elif site == "yk":
            eps = adapter.episodes(real_id)
            if idx >= len(eps):
                return {"parse": 1, "url": "", "msg": "集数越界"}
            play_page_url = adapter.episode_url(eps[idx])
            extra_header = {"User-Agent": PC_UA, "Referer": "https://v.youku.com/"}

        if not play_page_url:
            return {"parse": 1, "url": "", "msg": "无法获取播放页 URL"}

        if ".m3u8" in play_page_url or ".mp4" in play_page_url:
            return {"parse": 0, "url": play_page_url, "header": extra_header}

        # ★★★ 只改这里：自动线路 → parse:0 + jx:1 弹框 ★★★
        if iface == "auto":
            print(f"[{site}] 第{idx}集 [自动] → 本地解析器（弹框）")
            return {
                "parse": 0,
                "jx": 1,
                "url": play_page_url,
                "header": extra_header,
            }

        # 指定接口 → lxyy 直链（保持原样）
        code = LXY_CODES.get(site, "qq")
        print(f"[{site}] 第{idx}集 [{iface[:8]}] → lxyy 直链")
        m3u8, fmt = lxyy_resolve(play_page_url, code=code, iface=iface)
        if m3u8:
            return {"parse": 0, "url": m3u8, "header": extra_header}

        # lxyy 指定接口失败 → 降级 auto
        m3u8, fmt = lxyy_resolve(play_page_url, code=code, iface="")
        if m3u8:
            return {"parse": 0, "url": m3u8, "header": extra_header}

        # lxyy 全失败 → 也弹框让用户选
        print(f"[{site}] lxyy 全失败 → 本地解析器（弹框）")
        return {
            "parse": 0,
            "jx": 1,
            "url": play_page_url,
            "header": extra_header,
        }


# ============================================================
# Termux 测试
# ============================================================
if __name__ == "__main__":
    spider = Spider()
    spider.init()
    try:
        hc = spider.homeContent(True)
        print(f"0. homeContent: {len(hc['class'])} 分类")

        res = spider.categoryContent("tx_2", "1", True, {})
        if res["list"]:
            vid = res["list"][0]["vod_id"]
            detail = spider.detailContent([vid])
            if detail["list"]:
                d = detail["list"][0]
                play_froms = d["vod_play_from"].split("$$$")
                play_urls = d["vod_play_url"].split("$$$")
                print(f"\n[tx] {d['vod_name']}, 线路数={len(play_froms)}")
                for i, (f, u) in enumerate(zip(play_froms, play_urls)):
                    print(f"   线路{i+1}: {f}, 集数={len(u.split('#'))}")

                # 测自动
                ep_id = play_urls[0].split("#")[0].split("$")[1]
                pc = spider.playerContent(play_froms[0], ep_id)
                print(f"\n   [自动] 返回字段: {pc}")
    finally:
        spider.destroy()
# coding: utf-8

"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: 'mock',
  lang: 'hipy',
})
"""

import re
import json
import hashlib
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


class Spider(BaseSpider):
    host = "https://www.duse0.com"
    IMG_HOST = "https://vres.wkcyvs.cn"
    PAGE_SIZE = 24
    MAX_PAGECOUNT = 999
    DEFAULT_SORT = "3"

    APP_ONLY_LINES = {"4K", "8K", "蓝光4K", "蓝光4K-1", "超高清"}
    FALLBACK_PRIORITY = ["超清2", "超清", "蓝光1", "蓝光", "FF线路", "HN线路"]

    GENRES = ["剧情", "喜剧", "动作", "爱情", "恐怖", "惊悚", "犯罪", "科幻",
              "悬疑", "奇幻", "冒险", "战争", "历史", "古装", "家庭", "传记",
              "武侠", "歌舞", "短片", "动画", "儿童", "职场"]
    AREAS = [("大陆", "中国大陆"), ("香港", "中国香港"), ("台湾", "中国台湾"),
             ("美国", "美国"), ("日本", "日本"), ("韩国", "韩国"), ("英国", "英国"),
             ("法国", "法国"), ("德国", "德国"), ("印度", "印度"), ("泰国", "泰国"),
             ("丹麦", "丹麦"), ("瑞典", "瑞典"), ("巴西", "巴西"), ("加拿大", "加拿大"),
             ("俄罗斯", "俄罗斯"), ("意大利", "意大利"), ("比利时", "比利时"),
             ("爱尔兰", "爱尔兰"), ("西班牙", "西班牙"), ("澳大利亚", "澳大利亚"), ("其他", "其他")]
    LANGS = ["国语", "粤语", "英语", "日语", "韩语", "法语", "其他"]
    YEARS = [("2026", "2026"), ("2025", "2025"), ("2024", "2024"), ("2023", "2023"),
             ("2022", "2022"), ("2021", "2021"), ("2020", "2020"),
             ("10年代", "2010_2019"), ("00年代", "2000_2009"),
             ("90年代", "1990_1999"), ("80年代", "1980_1989"), ("更早", "0_1979")]
    SORTS = [("综合", "1"), ("最新", "2"), ("最热", "3"), ("评分", "4")]

    def init(self, extend=""):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
        })

    def destroy(self):
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

    # ================= CDNDefend 破解 =================
    def _solve_cdndefend(self, c):
        n1 = int(c[0], 16)
        for i in range(100000):
            s = hashlib.sha1((c + str(i)).encode()).digest()
            if s[n1] == 0xb0 and s[n1 + 1] == 0xb:
                return i
        return -1

    def _get(self, url, **kwargs):
        # ★ 回退到原版请求方式，不加任何自定义头，避免触发站点 WAF
        if "timeout" not in kwargs:
            kwargs["timeout"] = 10
        rsp = self.session.get(url, **kwargs)
        rsp.encoding = "utf-8"
        if rsp.status_code == 850 or "cdndefend" in rsp.text:
            m = re.search(r"([A-F0-9]{40})", rsp.text)
            if m:
                c = m.group(1)
                i = self._solve_cdndefend(c)
                if i >= 0:
                    self.session.cookies.set("cdndefend_js_cookie", f"{c}{i}")
                    rsp = self.session.get(url, **kwargs)
                    rsp.encoding = "utf-8"
        return rsp
    # ==================================================

    def _fix_pic(self, pic):
        if not pic:
            return ""
        if pic.startswith("http://") or pic.startswith("https://"):
            return pic
        if pic.startswith("//"):
            return "https:" + pic
        if pic.startswith("/"):
            return self.IMG_HOST + pic
        return self.IMG_HOST + "/" + pic

    # ---- 筛选 ----
    def _genre_options(self):
        return [{"n": "全部", "v": ""}] + [{"n": g, "v": g} for g in self.GENRES]

    def _area_options(self):
        return [{"n": "全部", "v": ""}] + [{"n": n, "v": v} for n, v in self.AREAS]

    def _lang_options(self):
        return [{"n": "全部", "v": ""}] + [{"n": l, "v": l} for l in self.LANGS]

    def _year_options(self):
        return [{"n": "全部", "v": ""}] + [{"n": n, "v": v} for n, v in self.YEARS]

    def _sort_options(self):
        return [{"n": n, "v": v} for n, v in self.SORTS]

    def _build_filter_objects(self, tid):
        nm = {"type": "类型", "area": "地区", "lang": "语言", "year": "年份", "sort": "排序"}
        opts = {"type": self._genre_options(), "area": self._area_options(),
                "lang": self._lang_options(), "year": self._year_options(),
                "sort": self._sort_options()}
        return [{"key": k, "name": nm[k], "value": opts[k]}
                for k in ["type", "area", "lang", "year", "sort"]]

    def _build_filters_dict(self, tid):
        return {"type": self._genre_options(), "area": self._area_options(),
                "lang": self._lang_options(), "year": self._year_options(),
                "sort": self._sort_options()}

    # ---- 首页 ----
    def homeContent(self, filter=False):
        classes = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "连续剧"},
            {"type_id": "3", "type_name": "动漫"},
            {"type_id": "4", "type_name": "综艺纪录"},
            {"type_id": "6", "type_name": "短剧"},
        ]
        filters = {c["type_id"]: self._build_filter_objects(c["type_id"]) for c in classes}
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        try:
            rsp = self._get(self.host + "/")
            print("[home] status:", rsp.status_code,
                  "| len:", len(rsp.text),
                  "| has_module:", 'class="module-item"' in rsp.text,
                  "| has_detail_a:", 'href="/detail/' in rsp.text)
            videos = self._parse_list(rsp.text)
            if videos:
                return {"list": videos[:50]}
        except Exception as e:
            print("[home] exception:", e)
        try:
            rsp = self._get(self.host + "/show/1------.html")
            print("[home-fallback] status:", rsp.status_code,
                  "| len:", len(rsp.text),
                  "| has_module:", 'class="module-item"' in rsp.text)
            return {"list": self._parse_list(rsp.text)[:50]}
        except Exception as e:
            print("[home-fallback] exception:", e)
            return {"list": []}

    # ---- 分类 ----
    def categoryContent(self, tid="1", pg="1", filter=False, extend=None):
        tid = str(tid or "1")
        try:
            pg_num = int(pg or 1)
        except Exception:
            pg_num = 1
        ext = self._safe_dict(extend)

        genre = str(ext.get("type", "") or "")
        area  = str(ext.get("area", "") or "")
        lang  = str(ext.get("lang", "") or "")
        year  = str(ext.get("year", "") or "")
        sort  = str(ext.get("sort", "") or self.DEFAULT_SORT)

        parts = [tid, quote(genre, safe=''), quote(area, safe=''),
                 quote(lang, safe=''), quote(year, safe=''), sort, str(pg_num)]
        url = f"{self.host}/show/{'-'.join(parts)}.html"

        try:
            rsp = self._get(url)
            html = rsp.text
            videos = self._parse_list(html)

            has_next = bool(re.search(r'class="page-item-next"', html))
            pagecount = min(pg_num + 1 if has_next else pg_num, self.MAX_PAGECOUNT)

            return {
                "list": videos,
                "page": pg_num,
                "pagecount": pagecount,
                "limit": self.PAGE_SIZE,
                "total": pagecount * self.PAGE_SIZE,
                "filters": self._build_filters_dict(tid),
            }
        except Exception:
            return {"list": [], "page": pg_num, "pagecount": 1, "limit": 0, "total": 0}

    # ---- 详情 ----
    def detailContent(self, ids=None):
        ids = self._safe_list(ids)
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = f"{self.host}/detail/{vod_id}.html"
        try:
            rsp = self._get(url)
            html = rsp.text

            if rsp.status_code != 200 or "detail-title" not in html:
                self._get(self.host + "/")
                rsp = self._get(url)
                html = rsp.text

            if "detail-title" not in html:
                return {"list": []}

            name = ""
            m = re.search(r'<div class="detail-title">(.*?)</div>', html, re.S)
            if m:
                strongs = re.findall(r'<strong>([^<]+)</strong>', m.group(1))
                if len(strongs) >= 2:
                    name = strongs[1].strip()
                elif strongs:
                    name = strongs[0].strip()

            pic = ""
            m = re.search(r'<div class="detail-pic">.*?<img[^>]+data-original="([^"]+)"', html, re.S)
            if m:
                pic = self._fix_pic(m.group(1))

            desc = ""
            m = re.search(r'<div class="detail-desc">\s*<p>\s*(.*?)\s*</p>', html, re.S)
            if m:
                desc = re.sub(r'<[^>]+>', '', m.group(1)).strip()

            year = ""
            m = re.search(r'<div class="detail-info-row-side">首映:</div>\s*<div class="detail-info-row-main">([^<]+)', html)
            if m:
                year = m.group(1).strip()[:4]

            director = ""
            m = re.search(r'<div class="detail-info-row-side">导演:</div>\s*<div class="detail-info-row-main">(.*?)</div>', html, re.S)
            if m:
                director = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip()

            actor = ""
            m = re.search(r'<div class="detail-info-row-side">演员:</div>\s*<div class="detail-info-row-main">(.*?)</div>', html, re.S)
            if m:
                actor = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip()

            play_data = self._parse_play_lists(html)

            return {"list": [{
                "vod_id": vod_id,
                "vod_name": name or "未知影片",
                "vod_pic": pic,
                "vod_year": year,
                "vod_actor": actor,
                "vod_director": director,
                "vod_content": desc,
                "vod_play_from": play_data["from"],
                "vod_play_url": play_data["url"],
            }]}
        except Exception:
            return {"list": []}

    def _parse_play_lists(self, html):
        sources = re.findall(r'<span class="source-item-label">([^<]+)</span>', html)
        ep_lists = re.findall(r'<div class="episode-list"[^>]*>([\s\S]*?)</div>', html)

        play_from, play_urls = [], []
        for i, ep_list in enumerate(ep_lists):
            if i >= len(sources):
                break
            line_name = sources[i].strip()
            if line_name in self.APP_ONLY_LINES:
                continue

            items = []
            # 放宽匹配：不依赖 href 与 class 的先后顺序
            for a_tag in re.findall(r'<a[^>]+class="episode-item"[^>]*>.*?</a>', ep_list, re.S):
                href_m = re.search(r'href="(/play/[^"]+)"', a_tag)
                name_m = re.search(r'<span>([^<]+)</span>', a_tag)
                if not href_m or not name_m:
                    continue
                m = re.search(r'/play/(\d+)-([A-Za-z0-9]+)-(\d+)\.html', href_m.group(1))
                if m:
                    vid, pf, idx = m.groups()
                    items.append(f"{name_m.group(1).strip()}${vid}|{pf}|{idx}")

            if items:
                play_from.append(line_name)
                play_urls.append("#".join(items))

        return {"from": "$$$".join(play_from), "url": "$$$".join(play_urls)}

    # ---- 搜索 ----
    def _get_search_token(self):
        try:
            rsp = self._get(self.host + "/")
            m = re.search(r'name="t"\s+value="([^"]+)"', rsp.text)
            return m.group(1) if m else ""
        except Exception:
            return ""

    def searchContent(self, key="", quick=False, pg="1"):
        if not key:
            return {"list": []}
        try:
            pg_num = int(pg or 1)
        except Exception:
            pg_num = 1
        token = self._get_search_token()
        params = {"k": key}
        if token:
            params["t"] = token
        try:
            rsp = self._get(self.host + "/search", params=params)
            return {"list": self._parse_list(rsp.text), "page": pg_num}
        except Exception:
            return {"list": []}

    # ---- 播放（单线路解析，失败返回 None） ----
    def _try_play(self, vod_id, play_from, ep_idx, header):
        play_page = f"{self.host}/play/{vod_id}-{play_from}-{ep_idx}.html"
        try:
            rsp = self._get(play_page)
            html = rsp.text

            for a, b in [("&amp;", "&"), ("&#x2F;", "/"), ("&#47;", "/"),
                         ("\\u002F", "/"), ("\\/", "/")]:
                html = html.replace(a, b)

            m = re.search(r'src\s*:\s*""', html)
            if m:
                return None

            for pat in [r'src\s*:\s*"([^"]+)"', r"src\s*:\s*'([^']+)'"]:
                m = re.search(pat, html)
                if m:
                    u = m.group(1).strip()
                    if u and (".m3u8" in u or ".mp4" in u):
                        if u.startswith("//"): u = "https:" + u
                        elif u.startswith("/"): u = self.host + u
                        return {"parse": 0, "url": u, "header": header}

            for ext in ["m3u8", "mp4"]:
                m = re.search(rf'(https?://[^"\'\s<>]+\.{ext}[^"\'\s<>]*)', html)
                if m:
                    return {"parse": 0, "url": m.group(1), "header": header}
        except Exception:
            pass
        return None

    # ---- 播放（主入口：智能降级） ----
    def playerContent(self, flag="", id="", vipFlags=None):
        id = str(id or "")
        parts = id.split("|")
        if len(parts) != 3:
            return {"parse": 1, "url": "", "msg": "id 格式错误"}
        vod_id, play_from, ep_idx = parts

        header = {
            "User-Agent": self.session.headers["User-Agent"],
            "Referer": self.host + "/",
        }

        result = self._try_play(vod_id, play_from, ep_idx, header)
        if result:
            return result

        try:
            rsp = self._get(f"{self.host}/detail/{vod_id}.html")
            html = rsp.text

            sources = re.findall(r'<span class="source-item-label">([^<]+)</span>', html)
            ep_lists = re.findall(r'<div class="episode-list"[^>]*>([\s\S]*?)</div>', html)

            target_pos = 0
            for i, s in enumerate(sources):
                if s.strip() != play_from or i >= len(ep_lists):
                    continue
                eps = re.findall(r'/play/(\d+)-([A-Za-z0-9]+)-(\d+)\.html', ep_lists[i])
                for pos, (_, _, idx) in enumerate(eps):
                    if idx == ep_idx:
                        target_pos = pos
                        break
                break

            order = []
            for name in self.FALLBACK_PRIORITY:
                for i, s in enumerate(sources):
                    if s.strip() == name and name != play_from and i not in order:
                        order.append(i)
            for i, s in enumerate(sources):
                if s.strip() != play_from and i not in order and s.strip() not in self.APP_ONLY_LINES:
                    order.append(i)

            for i in order:
                if i >= len(ep_lists):
                    continue
                eps = re.findall(r'/play/(\d+)-([A-Za-z0-9]+)-(\d+)\.html', ep_lists[i])
                if not eps:
                    continue
                pos = target_pos if target_pos < len(eps) else 0
                vid2, pf2, idx2 = eps[pos]
                result = self._try_play(vid2, pf2, idx2, header)
                if result:
                    return result
        except Exception:
            pass

        play_page = f"{self.host}/play/{vod_id}-{play_from}-{ep_idx}.html"
        return {"parse": 1, "url": play_page, "header": header}

    # ---- 列表解析 ----
    def _parse_list(self, html):
        videos, seen = [], set()
        blocks = re.split(r'<div class="module-item">', html)[1:]
        for block in blocks:
            id_m = re.search(r'href="/detail/(\d+)\.html"', block)
            if not id_m: continue
            vid = id_m.group(1)
            if vid in seen: continue

            name = ""
            m = re.search(r'<div class="v-item-title">([^<]+)</div>', block)
            if m: name = m.group(1).strip()
            if not name: continue

            covers = re.findall(r'data-original="([^"]+)"', block)
            real = [c for c in covers if 'placeholder' not in c]
            pic = real[0] if real else (covers[1] if len(covers) > 1 else "")
            pic = self._fix_pic(pic)

            rem = ""
            m = re.search(r'<div class="v-item-bottom">\s*<span>\s*([^<]+?)\s*</span>', block)
            if m: rem = m.group(1).strip()

            seen.add(vid)
            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": rem,
            })

        if not videos:
            for m in re.finditer(r'<a[^>]+href="/detail/(\d+)\.html"[^>]*>(.*?)</a>', html, re.S):
                vid = m.group(1)
                if vid in seen: continue
                content = m.group(2)

                name_m = (re.search(r'<div class="v-item-title">([^<]+)</div>', content)
                          or re.search(r'<p[^>]*>([^<]+)</p>', content)
                          or re.search(r'alt="([^"]+)"', content)
                          or re.search(r'title="([^"]+)"', content))
                if not name_m: continue

                pic_m = re.search(r'data-original="([^"]+)"', content)
                pic = self._fix_pic(pic_m.group(1) if pic_m else "")

                rem_m = re.search(r'<div class="v-item-bottom">\s*<span>\s*([^<]+?)\s*</span>', content)
                rem = rem_m.group(1).strip() if rem_m else ""

                seen.add(vid)
                videos.append({
                    "vod_id": vid,
                    "vod_name": name_m.group(1).strip(),
                    "vod_pic": pic,
                    "vod_remarks": rem,
                })

        return videos


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    try:
        print("===== 首页 =====")
        home = spider.homeVideoContent()
        print("0. homeVideoContent:", len(home.get("list", [])))
        if home.get("list"):
            print("   首条封面:", home["list"][0]["vod_pic"])

        print("\n===== 详情诊断 =====")
        rsp = spider._get(spider.host + "/detail/390043.html")
        print("debug status:", rsp.status_code,
              "| len:", len(rsp.text),
              "| has_detail:", "detail-title" in rsp.text)

        d = spider.detailContent(["390043"])
        print("5. detailContent:", len(d.get("list", [])))
        if d.get("list"):
            it = d["list"][0]
            print("   名称:", it["vod_name"])
            print("   封面:", it["vod_pic"])
            print("   线路:", it["vod_play_from"][:120])

    finally:
        spider.destroy()
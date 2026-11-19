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
import requests

# ===== TVBox / Termux 兼容层 =====
try:
    from base.spider import Spider as BaseSpider
    RUN_IN_TVBOX = True
except ImportError:
    RUN_IN_TVBOX = False
    class BaseSpider:
        def init(self, extend=""): pass
        def getName(self): return "mock"
# =================================


class Spider(BaseSpider):
    PAGE_SIZE = 12
    MAX_PAGECOUNT = 999

    # 线路顺序：普通线路优先（电视端默认能播），官方线路放后面
    LINE_ORDER = {"bfzym3u8": 0, "jsm3u8": 1, "covip": 2, "qq": 3}

    def init(self, extend=""):
        self.host = "https://jisuzhuiju.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.line_name_map = {
            "qq": "腾讯官方线路",
            "covip": "自建线路",
            "bfzym3u8": "普通线路二",
            "jsm3u8": "普通线路一",
        }

    def destroy(self):
        # 代理已移除，保留空钩子兼容旧调用
        pass

    def getName(self):
        return "极速追剧"

    def getDependence(self):
        # 本源只依赖 requests（APK 已内置），无需额外声明
        return []

    @staticmethod
    def _safe_dict(v):
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return {}
            try:
                d = json.loads(s)
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _safe_list(v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, tuple):
            return list(v)
        if isinstance(v, str):
            return [v] if v else []
        return [str(v)]

    # ★ 按播放直链域名智能匹配 Referer，解决官方线路电视端防盗链
    def _guess_referer(self, url):
        low = (url or "").lower()
        if "qq.com" in low or "gtimg" in low or "qpic" in low or "tencent" in low:
            return "https://v.qq.com/"
        if "mgtv" in low:
            return "https://www.mgtv.com/"
        if "iqiyi" in low or "qy.net" in low:
            return "https://www.iqiyi.com/"
        if "youku" in low or "ykimg" in low:
            return "https://www.youku.com/"
        if "bilibili" in low or "bilivideo" in low:
            return "https://www.bilibili.com/"
        return self.host + "/"

    # ---------------- 首页分类 + 筛选 ----------------
    def homeContent(self, filter=False):
        classes = [
            {"type_id": "1", "type_name": "电视剧"},
            {"type_id": "2", "type_name": "电影"},
            {"type_id": "3", "type_name": "动漫"},
            {"type_id": "4", "type_name": "综艺"},
            {"type_id": "5", "type_name": "短剧"},
        ]
        filters = {c["type_id"]: self._build_filter_objects(c["type_id"]) for c in classes}
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        try:
            rsp = self.session.get(self.host + "/", timeout=10)
            rsp.encoding = "utf-8"
            videos = self._parse_list(rsp.text)
            if not videos:
                rsp = self.session.get(
                    self.host + "/filter",
                    params={"channel": "1", "sort": "hot", "page": "1"},
                    timeout=10,
                )
                rsp.encoding = "utf-8"
                videos = self._parse_list(rsp.text)
            return {"list": videos[:50]}
        except Exception:
            return {"list": []}

    # ---------------- 筛选构建 ----------------
    def _filter_options(self, key):
        if key == "type":
            return [
                {"n": "全部", "v": ""}, {"n": "剧情", "v": "7"},
                {"n": "古装", "v": "9"}, {"n": "战争", "v": "10"},
                {"n": "谍战", "v": "11"}, {"n": "爱情", "v": "12"},
                {"n": "罪案", "v": "13"}, {"n": "悬疑", "v": "14"},
                {"n": "家庭", "v": "15"}, {"n": "军旅", "v": "16"},
                {"n": "喜剧", "v": "17"}, {"n": "都市", "v": "18"},
                {"n": "武侠", "v": "19"}, {"n": "言情", "v": "20"},
                {"n": "偶像", "v": "21"}, {"n": "青春", "v": "22"},
                {"n": "农村", "v": "23"}, {"n": "穿越", "v": "24"},
                {"n": "奇幻", "v": "25"}, {"n": "历史", "v": "26"},
                {"n": "年代", "v": "27"}, {"n": "科幻", "v": "28"},
                {"n": "生活", "v": "29"}, {"n": "励志", "v": "31"},
                {"n": "婚姻", "v": "32"}, {"n": "警匪", "v": "33"},
                {"n": "犯罪", "v": "34"}, {"n": "推理", "v": "35"},
                {"n": "商战", "v": "36"}, {"n": "宫廷", "v": "37"},
                {"n": "仙侠", "v": "38"}, {"n": "神话", "v": "39"},
                {"n": "动作", "v": "40"}, {"n": "复仇", "v": "41"},
                {"n": "惊悚", "v": "42"},
            ]
        if key == "area":
            return [
                {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"},
                {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"},
                {"n": "美国", "v": "美国"}, {"n": "泰国", "v": "泰国"},
                {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"},
                {"n": "德国", "v": "德国"}, {"n": "印度", "v": "印度"},
                {"n": "其他", "v": "其他"},
            ]
        if key == "year":
            return ([{"n": "全部", "v": ""}]
                    + [{"n": str(y), "v": str(y)} for y in range(2026, 2017, -1)]
                    + [{"n": "其他", "v": "-1"}])
        if key == "sort":
            return [{"n": "热度", "v": "hot"},
                    {"n": "时间", "v": "time"},
                    {"n": "评分", "v": "score"}]
        return []

    def _filter_keys_for(self, tid):
        keys = ["area", "year", "sort"]
        if str(tid) == "1":
            keys.insert(0, "type")
        return keys

    def _build_filter_objects(self, tid):
        name_map = {"type": "类型", "area": "地区", "year": "年份", "sort": "排序"}
        return [
            {"key": k, "name": name_map[k], "value": self._filter_options(k)}
            for k in self._filter_keys_for(tid)
        ]

    def _build_filters_dict(self, tid):
        return {k: self._filter_options(k) for k in self._filter_keys_for(tid)}

    # ---------------- 分类列表 ----------------
    def categoryContent(self, tid="1", pg="1", filter=False, extend=None):
        tid = str(tid or "1")
        try:
            pg_num = int(pg or 1)
        except Exception:
            pg_num = 1
        ext = self._safe_dict(extend)

        params = {
            "channel": tid,
            "type": str(ext.get("type", "") or ""),
            "area": str(ext.get("area", "") or ""),
            "year": str(ext.get("year", "") or ""),
            "sort": str(ext.get("sort", "") or "hot"),
            "page": str(pg_num),
        }
        try:
            rsp = self.session.get(self.host + "/filter", params=params, timeout=10)
            rsp.encoding = "utf-8"
            html = rsp.text
            videos = self._parse_list(html)

            has_next = bool(re.search(r'下一页|下页|尾页', html))
            if not has_next and videos:
                has_next = len(videos) >= self.PAGE_SIZE
            pagecount = pg_num + 1 if has_next else pg_num
            if pagecount > self.MAX_PAGECOUNT:
                pagecount = self.MAX_PAGECOUNT

            return {
                "list": videos,
                "page": pg_num,
                "pagecount": pagecount,
                "limit": self.PAGE_SIZE,
                "total": pagecount * self.PAGE_SIZE,
                "filters": self._build_filters_dict(tid),
            }
        except Exception:
            return {"list": [], "page": pg_num, "pagecount": 1,
                    "limit": 0, "total": 0}

    # ---------------- 详情 ----------------
    def detailContent(self, ids=None):
        ids = self._safe_list(ids)
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        try:
            rsp = self.session.get(f"{self.host}/detail/{vod_id}.html", timeout=10)
            rsp.encoding = "utf-8"
            html = rsp.text

            name = pic = desc = year = actor = director = ""
            m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    for g in data.get("@graph", []):
                        if g.get("@type") == "TVSeries":
                            name = g.get("name", "")
                            pic = g.get("image", "")
                            desc = g.get("description", "")
                            year = g.get("datePublished", "")
                            actor = g.get("actor", "")
                            director = g.get("director", "")
                            break
                except Exception:
                    pass

            play_data = self._parse_play_from_html(html, vod_id)
            if not play_data["url"]:
                try:
                    play_html = self.session.get(
                        f"{self.host}/vodplay/{vod_id}-qq-1.html", timeout=10
                    ).text
                    play_data = self._parse_play_from_html(play_html, vod_id)
                except Exception:
                    pass

            return {"list": [{
                "vod_id": vod_id,
                "vod_name": name or "未知影片",
                "vod_pic": pic,
                "vod_year": year,
                "vod_area": "中国大陆",
                "vod_actor": actor,
                "vod_director": director,
                "vod_content": desc,
                "vod_play_from": play_data["from"],
                "vod_play_url": play_data["url"],
            }]}
        except Exception:
            return {"list": []}

    # ---------------- 搜索 ----------------
    def searchContent(self, key="", quick=False, pg="1"):
        if not key:
            return {"list": []}
        try:
            pg_num = int(pg or 1)
        except Exception:
            pg_num = 1
        params = {"field": "all", "keyword": key}
        if pg_num > 1:
            params["page"] = str(pg_num)
        try:
            rsp = self.session.get(self.host + "/search", params=params, timeout=10)
            rsp.encoding = "utf-8"
            return {"list": self._parse_search(rsp.text), "page": pg_num}
        except Exception:
            return {"list": []}

    def searchContentPage(self, key="", quick=False, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------------- 播放解析 ----------------
    def playerContent(self, flag="", id="", vipFlags=None):
        id = str(id or "")
        try:
            parts = id.split("|")
            if len(parts) != 3:
                return {"parse": 1, "url": "", "msg": "id 格式错误"}
            vod_id, play_from, index = parts
            rsp = self.session.get(
                self.host + "/api/play-url",
                params={"vodId": vod_id, "playFrom": play_from, "index": index},
                timeout=15,
            )
            data = rsp.json()
            play_url = data.get("url") or (data.get("data") or {}).get("url") or ""
            if not play_url:
                return {"parse": 1, "url": "", "msg": "API 未返回播放地址"}

            # ★ 关键：按直链域名给正确的 Referer，官方线路电视端才有可能播
            header = {
                "User-Agent": self.headers["User-Agent"],
                "Referer": self._guess_referer(play_url),
            }

            # ★ 统一 parse=0 直连：不再依赖电视端弱的嗅探，也不走本地代理
            if ".m3u8" in play_url or ".mp4" in play_url:
                return {"parse": 0, "url": play_url, "header": header}
            # 非直链格式（极少见）才退回 parse=1
            return {"parse": 1, "url": play_url, "header": header}
        except Exception as e:
            return {"parse": 1, "url": "", "msg": f"解析失败: {str(e)}"}

    # ---------------- 解析辅助 ----------------
    def _parse_list(self, html):
        videos = []
        seen = set()
        for block in re.split(r'<div class="col-4 col-md-2">', html)[1:]:
            id_m = re.search(r'href="/detail/(\d+)\.html"', block)
            name_m = re.search(r'<p class="vod-title[^"]*">([^<]+)</p>', block)
            pic_m = re.search(r'<img[^>]+src="([^"]+)"', block)
            rem_m = re.search(r'<span class="vod-badge[^"]*">([^<]+)</span>', block)
            if id_m and name_m and id_m.group(1) not in seen:
                seen.add(id_m.group(1))
                videos.append({
                    "vod_id": id_m.group(1),
                    "vod_name": name_m.group(1).strip(),
                    "vod_pic": pic_m.group(1) if pic_m else "",
                    "vod_remarks": rem_m.group(1).strip() if rem_m else "",
                })
        if not videos:
            pattern = re.compile(r'<a[^>]+href="/detail/(\d+)\.html"[^>]*>(.*?)</a>', re.S)
            for m in pattern.finditer(html):
                vid = m.group(1)
                if vid in seen:
                    continue
                content = m.group(2)
                img_m = re.search(r'<img[^>]+src="([^"]+)"', content)
                title_m = (re.search(r'<p class="vod-title[^"]*">([^<]+)</p>', content)
                           or re.search(r'alt="([^"]+)"', content)
                           or re.search(r'title="([^"]+)"', content))
                if title_m:
                    seen.add(vid)
                    videos.append({
                        "vod_id": vid,
                        "vod_name": title_m.group(1).strip(),
                        "vod_pic": img_m.group(1) if img_m else "",
                        "vod_remarks": "",
                    })
        return videos

    def _parse_search(self, html):
        videos = []
        for block in re.split(r'<div class="search-item">', html)[1:]:
            id_m = re.search(r'<a href="/detail/(\d+)\.html"', block)
            name_m = re.search(r'class="search-item-title[^"]*"[^>]*>([^<]+)</a>', block)
            pic_m = re.search(r'<img src="([^"]+)"', block)
            if id_m and name_m:
                videos.append({
                    "vod_id": id_m.group(1),
                    "vod_name": name_m.group(1).strip(),
                    "vod_pic": pic_m.group(1) if pic_m else "",
                })
        return videos

    def _parse_play_from_html(self, html, vod_id):
        pattern = re.compile(
            r'<a[^>]+href="/vodplay/' + re.escape(vod_id) +
            r'-([A-Za-z0-9]+)-(\d+)\.html"[^>]*>([^<]+)</a>',
            re.S,
        )
        groups = {}
        for m in pattern.finditer(html):
            key, index, ep_name = m.group(1), m.group(2), m.group(3).strip()
            groups.setdefault(key, []).append((int(index), ep_name))

        # ★ 普通线路排前、官方线路排后，电视端默认落在能播的线路上
        ordered_keys = sorted(groups.keys(),
                              key=lambda k: self.LINE_ORDER.get(k, 99))

        sources = []
        for key in ordered_keys:
            eps = sorted(groups[key], key=lambda x: x[0])
            episodes = [f"{name}${vod_id}|{key}|{idx}" for idx, name in eps]
            sources.append({
                "name": self.line_name_map.get(key, key),
                "episodes": episodes,
            })
        return {
            "from": "$$$".join(s["name"] for s in sources),
            "url": "$$$".join("#".join(s["episodes"]) for s in sources),
        }


# ================= Termux 本地测试 =================
if __name__ == "__main__":
    spider = Spider()
    spider.init()
    try:
        print("=" * 60)
        print("0. homeVideoContent")
        res = spider.homeVideoContent()
        print("首页影片数:", len(res.get("list", [])))

        print("\n1. homeContent")
        res = spider.homeContent(True)
        print("filters 频道:", list(res.get("filters", {}).keys()))
        print("filters[1] 是 list:", isinstance(res["filters"]["1"], list))

        print("\n2. categoryContent · extend=dict")
        res = spider.categoryContent("1", "1", True, {"area": "大陆", "year": "2025"})
        print("影片数:", len(res.get("list", [])),
              "| pagecount:", res.get("pagecount"),
              "| filters 是 dict:", isinstance(res.get("filters"), dict))

        print("\n3. categoryContent · extend=JSON字符串")
        res = spider.categoryContent("1", "1", True, '{"area":"大陆","year":"2025"}')
        print("影片数:", len(res.get("list", [])), "| pagecount:", res.get("pagecount"))

        print("\n4. categoryContent · extend=None")
        res = spider.categoryContent("1", "1", True, None)
        print("影片数:", len(res.get("list", [])), "| pagecount:", res.get("pagecount"))

        print("\n5. detailContent · ids=list")
        res = spider.detailContent(["561"])
        print("线路:", res["list"][0]["vod_play_from"] if res.get("list") else "空")

        print("\n6. detailContent · ids=字符串")
        res = spider.detailContent("561")
        print("线路:", res["list"][0]["vod_play_from"] if res.get("list") else "空")

        print("\n7. searchContent")
        res = spider.searchContent("兰香", True)
        print("结果数:", len(res.get("list", [])))

        print("\n8. playerContent · 腾讯官方（应 parse=0 直连 + 腾讯 Referer）")
        res = spider.playerContent("腾讯官方线路", "561|qq|1", [])
        print("parse:", res.get("parse"),
              "| Referer:", (res.get("header") or {}).get("Referer"),
              "| url 前缀:", res.get("url", "")[:50])

        print("\n9. playerContent · 普通线路二（应 parse=0 直连）")
        res = spider.playerContent("普通线路二", "561|bfzym3u8|1", [])
        print("parse:", res.get("parse"),
              "| url 前缀:", res.get("url", "")[:50])
    finally:
        spider.destroy()
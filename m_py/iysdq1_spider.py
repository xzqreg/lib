#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════
  影视大全 (iysdq1.com) · 遮天法爬虫 v1.8 (安卓4.x 适配)
  基于苹果CMS V10 · 防御等级 0 (轮海·彼岸)
═══════════════════════════════════════════════════════════════

  v1.8 (安卓 APK 适配):
    ✓ 补 getDependence() / searchContentPage()
    ✓ detailContent / categoryContent 兼容字符串入参
    ✓ categoryContent 参数加默认值
    ✓ pagecount 封顶 MAX_PAGECOUNT = 999
    ✓ TTLCache maxsize 500→100, cache_ttl 300→120
    ✓ 编码判断改用 header charset（去 apparent_encoding 慢探测）
    ✓ m3u8 广告清洗关闭（保留代理只做绝对化 + Referer）
    ✓ HLSProxyServer 保留（普通线路必需）

  v1.7 新增:
    ✓ TTLCache 结果缓存
    ✓ HLSProxyServer 本地代理

  配置开关:
    "cache_ttl": 120          # 缓存秒数, 0 关闭
    "proxy_clean_m3u8": True  # 是否用本地代理转发 m3u8

  TVBox 加载: 导出类名必须为 Spider
  【版本】v1.8 | 【作者】遮天法
"""

import sys
import re
import json
import time
import random
import argparse
import threading
from urllib.parse import quote, unquote, urljoin, urlparse, parse_qs
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        pass

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# ═══════════════════════════════════════════════════════════════
#  配置中心
# ═══════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "name": "影视大全",
    "host": "https://www.iysdq1.com",
    "api_base": "/",

    "endpoints": {
        "home": "/",
        "category": "/vodshow/{tid}-{area}-{by}-{cls}-{lang}-{letter}---{pg}---{year}.html",
        "detail": "/voddetail/{vod_id}.html",
        "search": "/vodsearch/-------------.html",
        "play": "/vodplay/{vod_id}-{sid}-{nid}.html",
    },

    "pagination": {
        "page_size": 40,
        "search_page_size": 20,
    },

    "categories": [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "电视剧"},
        {"type_id": "3", "type_name": "综艺"},
        {"type_id": "4", "type_name": "动漫"},
        {"type_id": "5", "type_name": "短剧"},
    ],

    "filters": {
        "_common": {
            "area": ["", "大陆", "香港", "台湾", "美国", "日本", "韩国", "英国", "法国",
                     "德国", "意大利", "西班牙", "俄罗斯", "加拿大", "印度", "泰国",
                     "其它", "新加坡", "菲律宾", "澳大利亚", "土耳其", "瑞典", "巴西",
                     "荷兰", "印度尼西亚", "挪威", "智利", "爱尔兰", "伊朗", "蒙古"],
            "lang": ["", "国语", "粤语", "闽南语", "英语", "韩语", "日语", "法语", "德语", "其它"],
            "letter": ["", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
                       "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "0-9"],
            "year": [""] + [str(y) for y in range(2026, 1999, -1)],
        },
        "1": {"class": ["", "动作片", "喜剧片", "科幻片", "恐怖片", "爱情片", "剧情片",
                        "战争片", "记录片", "动画片", "惊悚", "犯罪", "悬疑", "冒险",
                        "奇幻", "家庭", "历史", "传记", "古装", "音乐", "同性", "运动",
                        "武侠", "短片", "歌舞", "西部", "儿童", "灾难", "戏曲",
                        "真人秀", "青春"]},
        "2": {"class": ["", "国产剧", "欧美剧", "香港剧", "韩国剧", "台湾剧", "日本剧",
                        "海外剧", "泰国剧", "剧情", "爱情", "喜剧", "悬疑", "犯罪",
                        "古装", "动作", "奇幻", "惊悚", "家庭", "历史"]},
        "3": {"class": ["", "大陆综艺", "港台综艺", "日韩综艺", "欧美综艺",
                        "真人秀", "选秀", "情感", "访谈", "播报", "旅游",
                        "音乐", "美食", "纪实", "曲艺", "游戏", "脱口秀"]},
        "4": {"class": ["", "国产动漫", "日韩动漫", "欧美动漫", "港台动漫", "海外动漫",
                        "动画", "喜剧", "剧情", "奇幻", "冒险", "动作", "科幻",
                        "爱情", "儿童", "家庭", "短片", "悬疑", "运动", "古装"]},
        "5": {"class": ["", "逆袭", "重生", "穿越", "复仇", "甜宠", "虐恋", "悬疑",
                        "古装", "现代", "总裁", "豪门", "都市", "职场", "情感",
                        "权谋", "玄幻", "搞笑", "热血", "恐怖", "家庭", "婚姻",
                        "成长", "励志", "战争", "失忆", "系统"]},
    },

    "headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "sec-ch-ua": "\"Chromium\";v=\"129\", \"Not=A?Brand\";v=\"8\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "Upgrade-Insecure-Requests": "1",
    },

    "ua_pool": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    ],

    "retry": {
        "max_retries": 3,
        "backoff_factor": 1.0,
        "timeout": 15,
    },

    "m3u8_clean": {
        "enabled": False,   # ★ 关闭广告清洗（用户已确认无用）
        "ad_keywords": ["ad", "ads", "advert", "preroll", "片头", "广告", "/gg/",
                        "banner", "promo", "casino", "博彩", "充值", "slot", "sponsor"],
        "min_duration": 1.2,
        "skip_first_n": 12,
    },

    "cache_ttl": 120,           # ★ 300 → 120，减少数据陈旧
    "proxy_clean_m3u8": True,   # 本地代理只做绝对化 + Referer 转发
    "cache_maxsize": 100,       # ★ 500 → 100，降低内存

    "debug": False,
}


# ═══════════════════════════════════════════════════════════════
#  缓存 & 代理
# ═══════════════════════════════════════════════════════════════

class TTLCache:
    """线程安全的 TTL 缓存"""

    def __init__(self, ttl: int = 120, maxsize: int = 100):
        self._cache = {}
        self._lock = threading.Lock()
        self.ttl = ttl
        self.maxsize = maxsize

    def get(self, key):
        if self.ttl <= 0:
            return None
        with self._lock:
            item = self._cache.get(key)
            if not item:
                return None
            value, expire_at = item
            if time.time() > expire_at:
                self._cache.pop(key, None)
                return None
            return value

    def set(self, key, value, ttl: int = None):
        if self.ttl <= 0 and ttl is None:
            return
        with self._lock:
            if len(self._cache) >= self.maxsize:
                now = time.time()
                self._cache = {k: v for k, v in self._cache.items() if v[1] > now}
                if len(self._cache) >= self.maxsize:
                    keys = list(self._cache.keys())[: len(self._cache) // 2]
                    for k in keys:
                        self._cache.pop(k, None)
            expire_at = time.time() + (ttl if ttl is not None else self.ttl)
            self._cache[key] = (value, expire_at)

    def clear(self):
        with self._lock:
            self._cache.clear()

    def size(self):
        with self._lock:
            return len(self._cache)


class HLSProxyServer:
    """本地 HLS 转发（只做绝对化 + Referer，不清洗广告）"""

    _server = None
    _port = 0
    _lock = threading.Lock()

    class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    @classmethod
    def start(cls, config: Dict, port_range: Tuple[int, int] = (9979, 9999)) -> int:
        with cls._lock:
            if cls._server is not None:
                return cls._port
            if not HAS_REQUESTS:
                return 0
            for port in range(port_range[0], port_range[1]):
                try:
                    handler_cls = cls._make_handler(config)
                    server = cls._ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
                    t = threading.Thread(target=server.serve_forever, daemon=True)
                    t.start()
                    cls._server = server
                    cls._port = port
                    return port
                except OSError:
                    continue
                except Exception:
                    continue
            return 0

    @classmethod
    def stop(cls):
        with cls._lock:
            if cls._server is not None:
                try:
                    cls._server.shutdown()
                except Exception:
                    pass
                cls._server = None
                cls._port = 0

    @classmethod
    def _make_handler(cls, config: Dict):
        class Handler(BaseHTTPRequestHandler):
            def _rewrite_master(self, text: str, base_url: str) -> str:
                port = HLSProxyServer._port
                if port <= 0:
                    return text
                out = []
                for line in text.splitlines():
                    s = line.strip()
                    if not s or s.startswith("#"):
                        out.append(line)
                        continue
                    absolute = urljoin(base_url, s)
                    if ".m3u8" in absolute.lower():
                        out.append(f"http://127.0.0.1:{port}/?url={quote(absolute, safe='')}")
                    else:
                        out.append(absolute)
                return "\n".join(out)

            def _do_fetch(self):
                try:
                    parsed = urlparse(self.path)
                    params = parse_qs(parsed.query)
                    target_url = params.get("url", [""])[0]
                    if not target_url:
                        self.send_response(400)
                        self.end_headers()
                        return

                    ua = (config.get("ua_pool") or ["Mozilla/5.0"])[0]
                    headers = {
                        "User-Agent": ua,
                        "Referer": config.get("host", ""),
                        "Accept": "*/*",
                    }
                    r = requests.get(target_url, headers=headers, timeout=15)
                    text = r.text

                    if "#EXT-X-STREAM-INF" in text:
                        text = self._rewrite_master(text, target_url)
                    else:
                        # ★ 只绝对化，不做广告清洗
                        text = JieZiMi.absolutize_m3u8(text, target_url)

                    body = text.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                except Exception:
                    try:
                        self.send_response(502)
                        self.end_headers()
                    except Exception:
                        pass

            def do_GET(self): self._do_fetch()
            def do_HEAD(self): self._do_fetch()
            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")
                self.end_headers()

            def log_message(self, *args): pass

        return Handler


# ═══════════════════════════════════════════════════════════════
#  九秘核心能力库
# ═══════════════════════════════════════════════════════════════

class DouZiMi:
    """斗字秘·战斗解析"""

    @staticmethod
    def clean_text(raw: Any) -> str:
        if not raw:
            return ""
        text = str(raw)
        text = re.sub(r"<[^>]+>", "", text)
        import html as html_module
        text = html_module.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def fix_pic(url: str, host: str = "") -> str:
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/") and host:
            return host.rstrip("/") + url
        if not url.startswith("http") and host:
            return host.rstrip("/") + "/" + url.lstrip("/")
        return url

    @staticmethod
    def parse_video_list(html: str, config: Dict = None) -> List[Dict]:
        cfg = config or DEFAULT_CONFIG
        videos = []
        if not html:
            return videos

        if HAS_BS4:
            try:
                soup = BeautifulSoup(html, "html.parser")
                items = soup.select("div.public-list-box, div.public-pic-b")
                if not items:
                    items = soup.select("div.vodlist-item, div.module-item, div.video-item")
                if not items:
                    items = soup.select("a.module-poster-item, a.vodlist-item")

                for item in items:
                    link_tag = item.select_one("a.public-list-exp") or item.select_one("a")
                    if not link_tag:
                        continue
                    href = link_tag.get("href", "")
                    vid_match = re.search(r"/voddetail/(\d+)\.html", href)
                    if not vid_match:
                        continue
                    vod_id = vid_match.group(1)

                    title = DouZiMi.clean_text(link_tag.get("title", ""))
                    if not title:
                        title_tag = item.select_one("a.time-title")
                        if title_tag:
                            title = DouZiMi.clean_text(
                                title_tag.get("title", "") or title_tag.text
                            )

                    img_tag = item.select_one("img")
                    pic = ""
                    if img_tag:
                        pic = (img_tag.get("data-src")
                               or img_tag.get("data-original")
                               or img_tag.get("src") or "")

                    remark_tag = (item.select_one("span.public-list-prb")
                                  or item.select_one("span.public-prt"))
                    remark = DouZiMi.clean_text(remark_tag.text if remark_tag else "")

                    if vod_id and title:
                        videos.append({
                            "vod_id": vod_id,
                            "vod_name": title,
                            "vod_pic": pic,
                            "vod_remarks": remark,
                        })

                if videos:
                    return videos
            except Exception:
                pass

        patterns = [
            r'<a[^>]*class="public-list-exp"[^>]*href="(/voddetail/(\d+)\.html)"[^>]*title="([^"]+)"[^>]*>.*?<img[^>]*(?:data-src|src)="([^"]+)"',
            r'<a[^>]*href="(/voddetail/(\d+)\.html)"[^>]*title="([^"]+)"[^>]*>.*?<img[^>]*(?:data-src|src)="([^"]+)"',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, html, re.S)
            if matches:
                for m in matches:
                    vod_id = m[1]
                    title = m[2] if len(m) > 2 else ""
                    pic = m[3] if len(m) > 3 else ""
                    if vod_id:
                        videos.append({
                            "vod_id": vod_id,
                            "vod_name": DouZiMi.clean_text(title),
                            "vod_pic": pic,
                            "vod_remarks": "",
                        })
                if videos:
                    return videos

        return videos


class QianZiMi:
    """前字秘·不死天刀（播放地址提取）"""

    PLAYER_PATTERN = r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>'

    @staticmethod
    def extract_player_url(html: str, config: Dict = None) -> Optional[str]:
        if not html:
            return None

        m = re.search(QianZiMi.PLAYER_PATTERN, html, re.S)
        if m:
            try:
                player_data = json.loads(m.group(1))
                url = player_data.get("url", "")
                if url:
                    return url.replace("\\/", "/")
            except json.JSONDecodeError:
                m2 = re.search(r'"url"\s*:\s*"([^"]+)"', m.group(1))
                if m2:
                    return m2.group(1).replace("\\/", "/")

        m = re.search(r'(https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*)', html)
        if m:
            return m.group(1).replace("\\/", "/")

        m = re.search(r'<iframe[^>]*src="[^"]*[?&]url=([^&"\']+)', html)
        if m:
            return unquote(m.group(1))

        return None


class JieZiMi:
    """皆字秘·m3u8 工具"""

    @staticmethod
    def clean_m3u8(text: str, base_url: str = "", config: Dict = None) -> str:
        """保留方法以防外部引用，但 v1.8 默认不调用"""
        cfg = config or DEFAULT_CONFIG
        clean_cfg = cfg.get("m3u8_clean", {})
        if not clean_cfg.get("enabled", False):
            return text

        try:
            lines = text.splitlines()
            if not lines or lines[0].strip() != "#EXTM3U":
                return text

            header_lines, segments = [], []
            current_seg = {"tags": [], "uri": "", "dur": 0}
            in_seg = False
            original_sequence = 0

            for line in lines:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#EXTINF:"):
                    in_seg = True
                    dur_match = re.search(r"#EXTINF:([0-9.]+)", s)
                    current_seg["dur"] = float(dur_match.group(1)) if dur_match else 3.0
                    current_seg["tags"].append(line)
                elif s.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                    seq_match = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", s)
                    if seq_match:
                        original_sequence = int(seq_match.group(1))
                elif s.startswith("#"):
                    if in_seg:
                        current_seg["tags"].append(line)
                    else:
                        header_lines.append(line)
                else:
                    if in_seg:
                        current_seg["uri"] = s
                        segments.append(current_seg)
                        current_seg = {"tags": [], "uri": "", "dur": 0}
                        in_seg = False
                    else:
                        header_lines.append(line)

            if not segments:
                return text

            ad_keywords = clean_cfg.get("ad_keywords", [])
            min_dur = clean_cfg.get("min_duration", 1.2)
            cleaned_segs, removed = [], 0

            for seg in segments:
                uri = seg["uri"]
                is_ad = False
                if any(k in uri.lower() for k in ad_keywords):
                    is_ad = True
                if 0 < seg["dur"] <= min_dur:
                    is_ad = True
                if is_ad:
                    removed += 1
                    continue
                cleaned_segs.extend(seg["tags"])
                cleaned_segs.append(uri)

            out = ["#EXTM3U"]
            out.extend([l for l in header_lines if not l.strip().startswith("#EXTM3U")])
            out.append(f"#EXT-X-MEDIA-SEQUENCE:{original_sequence + removed}")
            out.extend(cleaned_segs)
            out.append("#EXT-X-ENDLIST")
            return "\n".join(out)
        except Exception:
            return text

    @staticmethod
    def absolutize_m3u8(text: str, base_url: str) -> str:
        if not base_url:
            return text
        base = base_url.rsplit("/", 1)[0] + "/"
        lines = []
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                lines.append(urljoin(base, s))
            else:
                lines.append(line)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  爬虫主类
# ═══════════════════════════════════════════════════════════════

class Spider(BaseSpider):
    """影视大全 (iysdq1.com) · v1.8 带缓存 + 代理转发"""

    realm_name = "轮海·彼岸"
    defense_level = 0
    MAX_PAGECOUNT = 999   # ★ pagecount 封顶

    _html_cache: Optional[TTLCache] = None
    _proxy_port: int = 0
    _proxy_lock = threading.Lock()

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.config = DEFAULT_CONFIG
        self.siteUrl = self.config["host"]
        self._session = None

        if Spider._html_cache is None:
            Spider._html_cache = TTLCache(
                ttl=self.config.get("cache_ttl", 120),
                maxsize=self.config.get("cache_maxsize", 100),
            )

    # ── 内部工具 ──

    def _get_session(self):
        if self._session is None:
            if not HAS_REQUESTS:
                return None
            self._session = requests.Session()
            self._session.headers.update(self._build_headers())
        return self._session

    def _build_headers(self, extra: Dict = None) -> Dict:
        h = dict(self.config["headers"])
        h["Referer"] = self.siteUrl + "/"
        h["Origin"] = self.siteUrl
        if extra:
            h.update(extra)
        return h

    def _random_ua(self) -> str:
        return random.choice(self.config["ua_pool"])

    def _get_html(self, url: str, params: Dict = None, retries: int = None) -> Optional[str]:
        if not HAS_REQUESTS:
            return None

        cache_key = url
        if params:
            cache_key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))

        cache = Spider._html_cache
        if cache is not None:
            cached = cache.get(cache_key)
            if cached is not None:
                if self.config.get("debug"):
                    print(f"[{self.realm_name}] 缓存命中: {cache_key}")
                return cached

        session = self._get_session()
        if session is None:
            return None

        retry_cfg = self.config.get("retry", {})
        if retries is None:
            retries = retry_cfg.get("max_retries", 3)
        backoff = retry_cfg.get("backoff_factor", 1.0)
        timeout = retry_cfg.get("timeout", 15)

        last_err = None
        html = None
        for attempt in range(retries):
            try:
                headers = self._build_headers()
                headers["User-Agent"] = self._random_ua()
                r = session.get(url, params=params, headers=headers, timeout=timeout)
                if r.status_code == 200:
                    # ★ 编码判断优化：优先 header charset，兜底 utf-8，避免 apparent_encoding 全量探测
                    ct = (r.headers.get("Content-Type") or "").lower()
                    m = re.search(r"charset=([^\s;]+)", ct)
                    if m:
                        r.encoding = m.group(1).strip('"\'')
                    elif not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
                        r.encoding = "utf-8"
                    html = r.text
                    break
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    if self.config.get("debug"):
                        print(f"[{self.realm_name}] HTTP {r.status_code}: {url}")
                    return None
                last_err = f"HTTP {r.status_code}"
            except requests.Timeout:
                last_err = "timeout"
            except requests.RequestException as e:
                last_err = str(e)
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"

            if attempt < retries - 1:
                delay = backoff * (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(delay)

        if html is None:
            if self.config.get("debug"):
                print(f"[{self.realm_name}] 请求失败({retries}次): {url} — {last_err}")
            return None

        if cache is not None:
            cache.set(cache_key, html)

        return html

    def _ensure_proxy(self) -> int:
        if Spider._proxy_port > 0:
            return Spider._proxy_port
        with Spider._proxy_lock:
            if Spider._proxy_port > 0:
                return Spider._proxy_port
            port = HLSProxyServer.start(self.config)
            Spider._proxy_port = port or 0
            if self.config.get("debug"):
                print(f"[{self.realm_name}] HLS 代理: port={port}")
            return Spider._proxy_port

    # ── TVBox 接口 ──

    def init(self, extend=""):
        try:
            if extend:
                ext = json.loads(extend) if isinstance(extend, str) else extend
                if isinstance(ext, dict) and ext.get("host"):
                    self.siteUrl = ext["host"].rstrip("/")
                    self.config["host"] = self.siteUrl
        except Exception:
            pass

    def getName(self) -> str:
        return self.config.get("name", "影视大全")

    def getDependence(self):
        # 本源只依赖 requests + bs4（APK 内置），无需额外声明
        return []

    def isVideoFormat(self, url: str) -> bool:
        video_exts = ['.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.ts', '.mpg']
        return any(ext in url.lower() for ext in video_exts)

    def manualVideoCheck(self) -> bool:
        return False

    def homeContent(self, filter: bool = False) -> Dict:
        try:
            classes = self.config["categories"]
            filters = {}
            filters_cfg = self.config.get("filters", {})
            common = filters_cfg.get("_common", {})

            def to_options(values):
                return [{"n": v if v else "全部", "v": v} for v in values]

            for cat in classes:
                tid = str(cat["type_id"])
                specific = filters_cfg.get(tid, {})
                items = []
                if specific.get("class"):
                    items.append({"key": "class", "name": "类型",
                                  "value": to_options(specific["class"])})
                if common.get("area"):
                    items.append({"key": "area", "name": "地区",
                                  "value": to_options(common["area"])})
                if common.get("lang"):
                    items.append({"key": "lang", "name": "语言",
                                  "value": to_options(common["lang"])})
                if common.get("letter"):
                    items.append({"key": "letter", "name": "字母",
                                  "value": to_options(common["letter"])})
                if common.get("year"):
                    items.append({"key": "year", "name": "年份",
                                  "value": to_options(common["year"])})
                if items:
                    filters[tid] = items

            return {"class": classes, "filters": filters}
        except Exception as e:
            if self.config.get("debug"):
                print(f"[{self.realm_name}] homeContent 错误: {e}")
            return {"class": self.config["categories"]}

    def homeVideoContent(self) -> Dict:
        try:
            html = self._get_html(self.siteUrl)
            if not html:
                return {"list": []}
            videos = DouZiMi.parse_video_list(html, self.config)
            return {"list": videos[:50]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, extend=None) -> Dict:
        # ★ 兼容 dict / JSON 字符串 / None
        if isinstance(extend, str):
            try:
                extend = json.loads(extend) if extend.strip() else {}
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}

        try:
            pg_num = int(pg or 1)
            area = extend.get("area", "") or ""
            by = extend.get("by", "") or ""
            cls = extend.get("class", "") or ""
            lang = extend.get("lang", "") or ""
            letter = extend.get("letter", "") or ""
            year = extend.get("year", "") or ""

            pg_field = "" if pg_num == 1 else str(pg_num)
            path = (
                f"/vodshow/{tid}"
                f"-{quote(area)}"
                f"-{by}"
                f"-{quote(cls)}"
                f"-{quote(lang)}"
                f"-{quote(letter)}"
                f"---{pg_field}---"
                f"{year}.html"
            )
            url = self.siteUrl.rstrip("/") + path

            if self.config.get("debug"):
                print(f"[{self.realm_name}] 分类URL: {url}")

            html = self._get_html(url)
            if not html:
                return {"list": [], "page": pg_num, "pagecount": 1, "limit": 0, "total": 0}

            videos = DouZiMi.parse_video_list(html, self.config)

            has_next = bool(re.search(r'下一页|下页|尾页', html))
            if not has_next and videos:
                has_next = len(videos) >= self.config["pagination"]["page_size"]

            pagecount = pg_num + 1 if has_next else pg_num
            # ★ 封顶
            if pagecount > self.MAX_PAGECOUNT:
                pagecount = self.MAX_PAGECOUNT
            total = pagecount * self.config["pagination"]["page_size"]

            return {
                "list": videos,
                "page": pg_num,
                "pagecount": pagecount,
                "limit": self.config["pagination"]["page_size"],
                "total": total,
                "filters": self._build_filters(tid),
            }
        except Exception as e:
            if self.config.get("debug"):
                print(f"[{self.realm_name}] categoryContent 错误: {e}")
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 0, "total": 0}

    def _build_filters(self, tid: str) -> Dict:
        try:
            filters_cfg = self.config.get("filters", {})
            if not filters_cfg:
                return {}
            common = filters_cfg.get("_common", {})
            specific = filters_cfg.get(str(tid), {})

            def to_options(values):
                return [{"n": v if v else "全部", "v": v} for v in values]

            result = {}
            if specific.get("class"):
                result["class"] = to_options(specific["class"])
            if common.get("area"):
                result["area"] = to_options(common["area"])
            if common.get("lang"):
                result["lang"] = to_options(common["lang"])
            if common.get("letter"):
                result["letter"] = to_options(common["letter"])
            if common.get("year"):
                result["year"] = to_options(common["year"])
            return result
        except Exception:
            return {}

    def detailContent(self, ids) -> Dict:
        # ★ 兼容字符串入参（安卓壳有时传 "177600" 而非 ["177600"]）
        if isinstance(ids, str):
            ids = [ids] if ids else []
        if not isinstance(ids, (list, tuple)):
            ids = []
        if not ids:
            return {"list": []}

        results = []
        for vod_id in ids:
            if not vod_id:
                continue
            try:
                path = self.config["endpoints"]["detail"].replace("{vod_id}", str(vod_id))
                url = self.siteUrl.rstrip("/") + path
                html = self._get_html(url)
                if not html:
                    continue
                item = self._parse_detail_html(html, vod_id)
                if item:
                    results.append(item)
            except Exception as e:
                if self.config.get("debug"):
                    print(f"[{self.realm_name}] detailContent {vod_id} 错误: {e}")
                continue
        return {"list": results}

    def _parse_detail_html(self, html: str, vod_id: str) -> Optional[Dict]:
        detail = {
            "vod_id": str(vod_id),
            "vod_name": "",
            "vod_pic": "",
            "vod_remarks": "",
            "vod_content": "",
            "vod_year": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_area": "",
            "vod_type": "",
            "vod_score": "",
            "vod_play_from": "",
            "vod_play_url": "",
        }

        if not HAS_BS4:
            m = re.search(r'<div class="this-desc-title">([^<]+)</div>', html)
            if m:
                detail["vod_name"] = DouZiMi.clean_text(m.group(1))
            if not detail["vod_name"]:
                m = re.search(r'<title>(.*?)</title>', html, re.S)
                if m:
                    detail["vod_name"] = DouZiMi.clean_text(m.group(1)).split("_")[0].split("-")[0].strip()
            if not detail["vod_name"]:
                detail["vod_name"] = f"视频_{vod_id}"
            return detail

        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.select_one("div.this-desc-title")
        if title_tag:
            detail["vod_name"] = DouZiMi.clean_text(title_tag.text)

        if not detail["vod_name"]:
            for sel in ["h1.title", "div.detail-title h1", "h1.page-title", "h1"]:
                t = soup.select_one(sel)
                if t:
                    detail["vod_name"] = DouZiMi.clean_text(t.text)
                    if detail["vod_name"]:
                        break
        if not detail["vod_name"]:
            m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html)
            if m:
                detail["vod_name"] = DouZiMi.clean_text(m.group(1))
        if not detail["vod_name"]:
            m = re.search(r'<title>(.*?)</title>', html, re.S)
            if m:
                detail["vod_name"] = DouZiMi.clean_text(m.group(1)).split("_")[0].split("-")[0].strip()

        pic_bj = soup.select_one("div.this-pic-bj")
        if pic_bj:
            style = pic_bj.get("style", "")
            m = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", style)
            if m:
                detail["vod_pic"] = DouZiMi.fix_pic(m.group(1), self.siteUrl)

        if not detail["vod_pic"]:
            for sel in ["img.gen-movie-img", "div.detail-pic img", "img.lazy"]:
                img_tag = soup.select_one(sel)
                if img_tag:
                    detail["vod_pic"] = DouZiMi.fix_pic(
                        img_tag.get("data-src") or img_tag.get("data-original")
                        or img_tag.get("src") or "",
                        self.siteUrl
                    )
                    if detail["vod_pic"]:
                        break

        info_spans = soup.select("div.this-desc-info > span")
        area_list = self.config.get("filters", {}).get("_common", {}).get("area", []) or []
        for span in info_spans:
            text = DouZiMi.clean_text(span.text)
            if not text:
                continue
            if re.fullmatch(r"\d+(\.\d+)?", text):
                if not detail["vod_score"]:
                    detail["vod_score"] = text
                continue
            if re.fullmatch(r"(19|20)\d{2}", text):
                if not detail["vod_year"]:
                    detail["vod_year"] = text
                continue
            if any(k in text for k in ["更新", "完结", "全集", "第"]):
                if not detail["vod_remarks"]:
                    detail["vod_remarks"] = text
                continue
            if text in area_list:
                if not detail["vod_area"]:
                    detail["vod_area"] = text

        actor_tag = soup.select_one("div.this-info a")
        if actor_tag:
            detail["vod_actor"] = DouZiMi.clean_text(actor_tag.text)

        desc_tag = soup.select_one("div.this-desc div.text")
        if desc_tag:
            txt = desc_tag.get_text(strip=True)
            txt = re.sub(r"^描述[:：]\s*", "", txt)
            if txt and txt not in ("暂无简介", "暂无"):
                detail["vod_content"] = DouZiMi.clean_text(txt)

        for li in soup.select("div.info-parameter ul li"):
            text = li.get_text(strip=True)
            if "导演" in text:
                v = self._extract_after_colon(text)
                if v and v != "未知":
                    detail["vod_director"] = v
            elif "主演" in text and not detail["vod_actor"]:
                v = self._extract_after_colon(text)
                if v:
                    detail["vod_actor"] = v
            elif "年份" in text and not detail["vod_year"]:
                v = self._extract_after_colon(text)
                if re.fullmatch(r"(19|20)\d{2}", v):
                    detail["vod_year"] = v
            elif "地区" in text and not detail["vod_area"]:
                v = self._extract_after_colon(text)
                if v:
                    detail["vod_area"] = v
            elif "状态" in text and not detail["vod_remarks"]:
                v = self._extract_after_colon(text)
                if v:
                    detail["vod_remarks"] = v
            elif "类型" in text and not detail["vod_type"]:
                type_as = li.find_all("a")
                if type_as:
                    types = [DouZiMi.clean_text(a.text) for a in type_as]
                    types = [t for t in types if t]
                    if types:
                        detail["vod_type"] = ",".join(types)
                else:
                    v = self._extract_after_colon(text)
                    if v:
                        detail["vod_type"] = v
            elif ("简介" in text or "描述" in text) and not detail["vod_content"]:
                v = self._extract_after_colon(text)
                if v and v not in ("暂无简介", "暂无"):
                    detail["vod_content"] = v

        play_from, play_url = self._parse_play_list(soup, vod_id, html)
        detail["vod_play_from"] = play_from
        detail["vod_play_url"] = play_url

        if not detail["vod_name"]:
            detail["vod_name"] = f"视频_{vod_id}"

        return detail

    def _parse_play_list(self, soup, vod_id: str, html: str = "") -> Tuple[str, str]:
        froms, urls = [], []

        if soup is not None:
            tab_names = []
            tab_container = soup.select_one("div.anthology-tab")
            if tab_container:
                for a in tab_container.select("a.swiper-slide"):
                    tab_names.append(DouZiMi.clean_text(a.get_text()))

            list_container = soup.select_one("div.anthology-list")
            if list_container:
                boxes = list_container.select("div.anthology-list-box")
                for i, box in enumerate(boxes):
                    episodes = []
                    sid = ""
                    for a in box.select("a[href*='/vodplay/']"):
                        href = a.get("href", "")
                        m = re.search(r"/vodplay/\d+-(\d+)-\d+\.html", href)
                        if m and not sid:
                            sid = m.group(1)
                        ep_name = DouZiMi.clean_text(a.text) or f"第{len(episodes) + 1}集"
                        if not href.startswith("http"):
                            href = urljoin(self.siteUrl, href)
                        episodes.append(f"{ep_name}${href}")
                    if episodes:
                        if i < len(tab_names) and tab_names[i]:
                            name = tab_names[i]
                        elif sid:
                            name = f"线路{sid}"
                        else:
                            name = f"线路{i + 1}"
                        froms.append(name)
                        urls.append("#".join(episodes))
                if froms:
                    return "$$$".join(froms), "$$$".join(urls)

        if soup is not None:
            selectors = [
                "div.playlist", "div.vod-playlist", "ul.content_playlist",
                "div.play-list", "div.playlist-content", "div#playlist",
                "div.tab-content", "div.panel-playlist", "div.module-playlist",
            ]
            for sel in selectors:
                try:
                    divs = soup.select(sel)
                except Exception:
                    continue
                if divs:
                    for i, div in enumerate(divs):
                        episodes = []
                        for a in div.select("a"):
                            href = a.get("href", "")
                            ep_name = DouZiMi.clean_text(a.text) or f"第{len(episodes) + 1}集"
                            if "/vodplay/" in href:
                                if not href.startswith("http"):
                                    href = urljoin(self.siteUrl, href)
                                episodes.append(f"{ep_name}${href}")
                        if episodes:
                            froms.append(f"线路{i + 1}")
                            urls.append("#".join(episodes))
                    if froms:
                        return "$$$".join(froms), "$$$".join(urls)

        if html:
            m = re.search(r'vod_play_from\s*[:=]\s*["\']([^"\']+)["\']', html)
            m2 = re.search(r'vod_play_url\s*[:=]\s*["\']([^"\']+)["\']', html)
            if m and m2:
                f_list = m.group(1).split("$$$")
                u_list = m2.group(1).split("$$$")
                if f_list and u_list and len(f_list) == len(u_list):
                    return "$$$".join(f_list), "$$$".join(u_list)

        if html:
            all_links = re.findall(
                r'<a[^>]*href="(/vodplay/' + re.escape(str(vod_id)) + r'-(\d+)-(\d+)\.html)"[^>]*>([^<]*)</a>',
                html
            )
            if all_links:
                groups = defaultdict(list)
                for href, sid, nid, txt in all_links:
                    groups[sid].append((int(nid), href, txt))
                for sid in sorted(groups.keys(), key=int):
                    eps = sorted(groups[sid], key=lambda x: x[0])
                    episodes = []
                    for nid, href, txt in eps:
                        ep_name = DouZiMi.clean_text(txt) or f"第{nid}集"
                        full = urljoin(self.siteUrl, href)
                        episodes.append(f"{ep_name}${full}")
                    froms.append(f"线路{sid}")
                    urls.append("#".join(episodes))
                if froms:
                    return "$$$".join(froms), "$$$".join(urls)

        if html:
            links = re.findall(r'<a[^>]*href="(/vodplay/[^"]+)"[^>]*>([^<]*)</a>', html)
            if links:
                episodes = []
                for i, (href, txt) in enumerate(links):
                    ep_name = DouZiMi.clean_text(txt) or f"第{i + 1}集"
                    full = urljoin(self.siteUrl, href)
                    episodes.append(f"{ep_name}${full}")
                return "默认线路", "#".join(episodes)

        return "", ""

    @staticmethod
    def _extract_after_colon(text: str) -> str:
        parts = re.split(r"[:：]", text, maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else text

    def playerContent(self, flag: str, id: str, vipFlags: str = None) -> Dict:
        try:
            if not id:
                return {"parse": 0, "url": "", "header": {}}

            if id.startswith("http"):
                play_url = id
            elif id.startswith("/"):
                play_url = self.siteUrl.rstrip("/") + id
            elif "/vodplay/" in id:
                play_url = urljoin(self.siteUrl, id)
            else:
                parts = id.split("-")
                if len(parts) >= 3:
                    play_url = f"{self.siteUrl.rstrip('/')}/vodplay/{parts[0]}-{parts[1]}-{parts[2]}.html"
                else:
                    return {"parse": 0, "url": id, "header": {}}

            html = self._get_html(play_url)
            if not html:
                return {"parse": 0, "url": play_url, "header": {}}

            m3u8_url = QianZiMi.extract_player_url(html, self.config)
            if not m3u8_url:
                m = re.search(r'<iframe[^>]*src="([^"]*[?&]url=([^&"]+))', html)
                if m:
                    m3u8_url = unquote(m.group(2))

            if not m3u8_url:
                return {"parse": 0, "url": play_url, "header": {}}

            header = {
                "Referer": self.siteUrl,
                "User-Agent": self._random_ua(),
            }

            # ★ 代理只做绝对化 + Referer 转发，不做广告清洗
            if self.config.get("proxy_clean_m3u8", True) and ".m3u8" in m3u8_url.lower():
                port = self._ensure_proxy()
                if port > 0:
                    proxy_url = f"http://127.0.0.1:{port}/?url={quote(m3u8_url, safe='')}"
                    if self.config.get("debug"):
                        print(f"[{self.realm_name}] 代理URL: {proxy_url[:120]}")
                    return {"parse": 0, "url": proxy_url, "header": header}

            return {"parse": 0, "url": m3u8_url, "header": header}

        except Exception as e:
            if self.config.get("debug"):
                print(f"[{self.realm_name}] playerContent 错误: {e}")
            return {"parse": 0, "url": id, "header": {}}

    def searchContent(self, key: str, quick: str = "1", pg: str = "1") -> Dict:
        try:
            pg_num = int(pg or 1)
            base_path = self.config["endpoints"]["search"]
            url = self.siteUrl.rstrip("/") + base_path
            params = {"wd": key}
            if pg_num > 1:
                params["page"] = pg_num

            html = self._get_html(url, params=params)
            if not html:
                return {"list": [], "page": pg_num, "pagecount": 1}

            videos = DouZiMi.parse_video_list(html, self.config)

            has_next = bool(re.search(r'下一页|下页|尾页', html))
            if not has_next and videos:
                has_next = len(videos) >= self.config["pagination"]["search_page_size"]

            pagecount = pg_num + 1 if has_next else pg_num
            if pagecount > self.MAX_PAGECOUNT:
                pagecount = self.MAX_PAGECOUNT

            return {
                "list": videos,
                "page": pg_num,
                "pagecount": pagecount,
            }
        except Exception as e:
            if self.config.get("debug"):
                print(f"[{self.realm_name}] searchContent 错误: {e}")
            return {"list": [], "page": int(pg or 1), "pagecount": 1}

    def searchContentPage(self, key: str, quick: bool = False, pg: str = "1") -> Dict:
        """★ 安卓 APK 兼容入口"""
        return self.searchContent(key, quick, pg)

    def localProxy(self, param: Dict) -> List:
        try:
            url = unquote(param.get("url", ""))
            kind = param.get("kind", "")
            if not url:
                return [400, "text/plain", b"missing url"]

            session = self._get_session()
            if session is None:
                return [500, "text/plain", b"no session"]

            r = session.get(url, headers=self._build_headers(), timeout=30)

            if kind == "hls" or ".m3u8" in url:
                # ★ 只绝对化，不清洗
                text = JieZiMi.absolutize_m3u8(r.text, url)
                return [200, "application/vnd.apple.mpegurl", text.encode()]

            if kind == "img":
                return [200, r.headers.get("Content-Type", "image/jpeg"), r.content]

            return [200, r.headers.get("Content-Type", "application/octet-stream"), r.content]
        except Exception as e:
            return [500, "text/plain", f"Proxy Error: {e}".encode()]


YiSdqSpider = Spider


# ═══════════════════════════════════════════════════════════════
#  自检 & 命令行（桌面/Termux 用，安卓加载不会触发）
# ═══════════════════════════════════════════════════════════════

def self_test():
    print("█" * 60)
    print("█" + " " * 14 + "影视大全爬虫 v1.8 自检" + " " * 15 + "█")
    print("█" * 60)
    print(f"Python: {sys.version}")
    print(f"requests: {'OK' if HAS_REQUESTS else 'MISSING'}")
    print(f"beautifulsoup4: {'OK' if HAS_BS4 else 'MISSING'}")
    print(f"\nTVBox 入口类: Spider = {Spider}")

    print("\n  [1] TTLCache 测试")
    cache = TTLCache(ttl=2, maxsize=10)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1", "缓存读写失败"
    print(f"    写入+命中: OK")
    time.sleep(2.1)
    assert cache.get("k1") is None, "缓存未过期"
    print(f"    TTL 过期: OK")
    cache.set("k2", "v2")
    cache.clear()
    assert cache.get("k2") is None, "缓存清空失败"
    print(f"    clear(): OK")

    print("\n  [2] HLSProxyServer 测试")
    port = HLSProxyServer.start(DEFAULT_CONFIG)
    if port > 0:
        print(f"    启动成功: port={port}")
    else:
        print(f"    启动失败（沙箱可能禁端口，将回退直链）")

    print("\n  [3] 兼容性测试（不联网）")
    spider = Spider()
    spider.siteUrl = "https://www.iysdq1.com"
    # 3.1 字符串 ids
    try:
        res = spider.detailContent("")
        assert res == {"list": []}, res
        print(f"    detailContent('') → [] : OK")
    except Exception as e:
        print(f"    detailContent('') 失败: {e}")

    # 3.2 字符串 extend
    try:
        # 不真请求，只验证不抛异常
        r1 = spider._safe_test_extend('{"area":"大陆"}')
        print(f"    extend 字符串解析: {r1} : OK")
    except Exception as e:
        print(f"    extend 字符串解析失败: {e}")

    # 3.3 详情页解析
    detail_html = '''
    <html><head><title>《乡镇大亨》-影视大全</title></head>
    <body>
    <div class="this-pic-bj" style="background-image: url('https://cdnv3.daquanz.com/upload/vod/20261013-1/e6585474142634b77d24cd841f56de09.jpg')"></div>
    <div class="this-desc-title">乡镇大亨：从辞职返乡开始</div>
    <div class="this-desc-info">
      <span class="this-desc-score">7.0</span>
      <span>2026</span>
      <span>大陆</span>
      <span>更新全集</span>
    </div>
    <div class="this-info"><strong>演员:</strong><a href="#">刘峰硕&知意</a></div>
    <div class="info-parameter"><ul>
      <li><em>导演：</em>未知</li>
      <li><em>年份：</em>2026</li>
      <li><em>地区：</em>大陆</li>
      <li><em>类型：</em><a href="#">年代穿越</a><a href="#">短剧</a></li>
    </ul></div>
    <div class="anthology-tab"><div class="swiper-wrapper">
      <a class="swiper-slide">2线</a><a class="swiper-slide">3线</a>
    </div></div>
    <div class="anthology-list">
      <div class="anthology-list-box"><ul><li><a href="/vodplay/177600-2-1.html">全集</a></li></ul></div>
      <div class="anthology-list-box"><ul><li><a href="/vodplay/177600-1-1.html">全集</a></li></ul></div>
    </div>
    </body></html>
    '''
    detail = spider._parse_detail_html(detail_html, "177600")
    for k in ["vod_name", "vod_year", "vod_area", "vod_remarks", "vod_actor",
              "vod_type", "vod_score", "vod_play_from"]:
        print(f"    {k}: {detail.get(k)}")

    print("\n  [4] 真实请求缓存命中测试")
    if HAS_REQUESTS:
        url = "https://www.iysdq1.com/"
        t1 = time.time(); h1 = spider._get_html(url); d1 = time.time() - t1
        t2 = time.time(); h2 = spider._get_html(url); d2 = time.time() - t2
        if h1 and h2:
            print(f"    首次: {d1:.2f}s, 缓存: {d2:.3f}s, 命中: {h1 == h2}")
        else:
            print(f"    请求失败（网络问题）")

    HLSProxyServer.stop()
    print("\n" + "█" * 60)
    print("自检完成！")
    print("█" * 60)


# 兼容自检里的 extend 解析测试
def _safe_test_extend(self, extend):
    if isinstance(extend, str):
        try:
            extend = json.loads(extend) if extend.strip() else {}
        except Exception:
            extend = {}
    if not isinstance(extend, dict):
        extend = {}
    return extend

Spider._safe_test_extend = _safe_test_extend


def main():
    parser = argparse.ArgumentParser(description="影视大全 (iysdq1.com) 爬虫 v1.8")
    parser.add_argument("url", nargs="?", default="https://www.iysdq1.com")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--test", choices=["home", "homevideo", "category", "detail", "player", "search", "proxy"])
    parser.add_argument("--category", default="1")
    parser.add_argument("--page", default="1")
    parser.add_argument("--keyword", default="测试")
    parser.add_argument("--vod-id", default="177600")
    parser.add_argument("--area", default="")
    parser.add_argument("--class", dest="cls", default="")
    parser.add_argument("--lang", default="")
    parser.add_argument("--letter", default="")
    parser.add_argument("--year", default="")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    spider = Spider()
    spider.siteUrl = args.url
    spider.config["host"] = args.url

    if args.test == "home":
        print(json.dumps(spider.homeContent(), ensure_ascii=False, indent=2)[:2000])
    elif args.test == "homevideo":
        result = spider.homeVideoContent()
        print(f"首页推荐: {len(result.get('list', []))} 条")
    elif args.test == "category":
        extend = {}
        for k, v in [("area", args.area), ("class", args.cls),
                     ("lang", args.lang), ("letter", args.letter), ("year", args.year)]:
            if v:
                extend[k] = v
        result = spider.categoryContent(args.category, args.page, False, extend)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
    elif args.test == "detail":
        result = spider.detailContent([args.vod_id])
        print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
    elif args.test == "player":
        result = spider.playerContent("2线", f"{args.vod_id}-1-1")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("url", "").startswith("http://127.0.0.1"):
            print("\n  → 已走本地代理（转发 m3u8）")
            import urllib.request
            try:
                r = urllib.request.urlopen(result["url"], timeout=10)
                body = r.read().decode("utf-8", "replace")
                print(f"  代理返回: {len(body)} 字节")
                print(f"  前 200 字符:\n{body[:200]}")
            except Exception as e:
                print(f"  代理访问失败: {e}")
        else:
            print("\n  → 直链（未走代理）")
    elif args.test == "search":
        result = spider.searchContent(args.keyword, "1", args.page)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
    elif args.test == "proxy":
        port = HLSProxyServer.start(spider.config)
        print(f"代理端口: {port}")
    else:
        print("完整流程测试")
        print("\n[1] 分类")
        cat = spider.categoryContent("1", "1", False, {})
        print(f"  {len(cat.get('list', []))} 条")
        print("\n[2] 详情")
        if cat.get("list"):
            vid = cat["list"][0]["vod_id"]
            detail = spider.detailContent([vid])
            if detail.get("list"):
                d = detail["list"][0]
                print(f"  {d['vod_name']}")
                print(f"  源: {d['vod_play_from']}")
        print("\n[3] 缓存测试")
        url = spider.siteUrl
        import time as _t
        a = _t.time(); spider._get_html(url); t1 = _t.time() - a
        a = _t.time(); spider._get_html(url); t2 = _t.time() - a
        print(f"  首次 {t1:.2f}s / 缓存 {t2:.3f}s")


if __name__ == "__main__":
    main()
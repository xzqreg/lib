# coding=utf-8
"""
4kvm：主备站切换 + 直链优先(优先天翼云) + 内容自检 + 嗅探兜底
"""
import re
import sys
import time
import base64
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        self.site_urls =[
    'https://www.4kvm.pro',
    'https://www.4kvm.org',
    'https://www.4kvm.tv',
    'https://www.4kvm.me',
    'https://www.4kvm.net',
    'https://www.4kvms.com'
];

        self.current_site_url = self.site_urls[0]
        self.timeout = (5, 15)
        self._quick_timeout = (4, 8)
        self._sync_timeout = (5, 12)
        self._play_cache = {}
        self._cache_ttl = 600
        self._preheat_workers = 3
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.current_site_url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        self.categories = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "电视剧"},
            {"type_id": "3", "type_name": "动漫"}
        ]
        self._filters_cache = None

    # ================= 网络 =================
    def _safe_fetch(self, url, headers=None, timeout=None):
        if headers is None:
            headers = self.headers.copy()
        try:
            if timeout is not None:
                return self.fetch(url, headers=headers, timeout=timeout)
            return self.fetch(url, headers=headers)
        except TypeError:
            try:
                return self.fetch(url, headers=headers)
            except Exception as e:
                print(f"[fetch异常] {url} - {e}")
                return None
        except Exception as e:
            print(f"[fetch异常] {url} - {e}")
            return None

    def _resp_text(self, resp):
        if not resp:
            return ''
        try:
            if hasattr(resp, 'text') and resp.text:
                return resp.text
        except Exception:
            pass
        try:
            if hasattr(resp, 'content') and resp.content:
                return resp.content.decode('utf-8', 'ignore')
        except Exception:
            pass
        return ''

    def _fetch_from_sites(self, path, params=None, headers=None, timeout=None):
        if params:
            q = urllib.parse.urlencode(params)
            path = f"{path}&{q}" if '?' in path else f"{path}?{q}"
        sites = [self.current_site_url] + [s for s in self.site_urls if s != self.current_site_url]
        for base in sites:
            url = base.rstrip('/') + path
            h = headers.copy() if headers else self.headers.copy()
            h['Referer'] = base + '/'
            resp = self._safe_fetch(url, headers=h, timeout=timeout or self.timeout)
            if resp and getattr(resp, 'status_code', 200) == 200:
                self.current_site_url = base
                return resp, base
            print(f"[站点失败] {base} {path}")
        return None, None

    # ================= 筛选 =================
    def _fetch_filters_for_classify(self, tid):
        resp, _ = self._fetch_from_sites("/filter", params={"classify": tid})
        html = self._resp_text(resp)
        if not html:
            return []
        soup = BeautifulSoup(html, 'html.parser')
        groups = []
        for container in soup.select('main div.flex.flex-wrap.items-center.gap-3'):
            links = container.select('a[href]')
            if len(links) < 2:
                continue
            first_text = links[0].get_text(strip=True)
            if not first_text.startswith('全部'):
                continue
            group_name = first_text.replace('全部', '', 1).strip()
            param_key = None
            for a in links[1:]:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(a.get('href', '')).query)
                for k in qs:
                    if k not in ('classify', 'page'):
                        param_key = k
                        break
                if param_key:
                    break
            if not param_key or param_key in ('sort_by', 'order'):
                continue
            options = []
            for a in links:
                text = a.get_text(strip=True)
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(a.get('href', '')).query)
                val = qs[param_key][0] if param_key in qs and qs[param_key] else ''
                if text.startswith('全部'):
                    val = ''
                options.append({"n": text, "v": val})
            if options:
                groups.append({"key": param_key, "name": group_name, "value": options})
        return groups

    def _get_all_filters(self):
        if self._filters_cache is not None:
            return self._filters_cache
        filters = {}
        for cat in self.categories:
            g = self._fetch_filters_for_classify(cat["type_id"])
            if g:
                filters[cat["type_id"]] = g
        if "1" in filters:
            filters.setdefault("3", filters["1"])
            filters.setdefault("4", filters["1"])
        self._filters_cache = filters
        return filters

    # ================= 列表 =================
    def _parse_cards(self, html, limit=None):
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.select('div[data-vod-id]')
        if limit:
            cards = cards[:limit]
        out = []
        for card in cards:
            a = card.select_one('a.block[href^="/play/"]')
            if not a:
                continue
            vod_id = card.get('data-vod-id', '').strip() or a.get('href', '').replace('/play/', '').strip()
            if not vod_id:
                continue
            title_tag = card.select_one('h3.text-white') or card.select_one('h3')
            vod_name = title_tag.get_text(strip=True) if title_tag else ''
            if not vod_name:
                continue
            img = card.select_one('img[data-src]')
            vod_pic = ''
            if img:
                src = img.get('data-src', '')
                if src and not src.startswith('data:'):
                    vod_pic = src if src.startswith('http') else 'https:' + src
            remark_tag = card.select_one('.text-green-500, .text-yellow-400, span[class*="px-1.5"]')
            vod_remarks = remark_tag.get_text(strip=True) if remark_tag else ''
            out.append({
                "vod_id": vod_id, "vod_name": vod_name,
                "vod_pic": vod_pic, "vod_remarks": vod_remarks
            })
        return out

    def homeContent(self, filter):
        resp, _ = self._fetch_from_sites("/")
        html = self._resp_text(resp)
        video_list = self._parse_cards(html, limit=20) if html else []
        return {"class": self.categories, "list": video_list, "filters": self._get_all_filters()}

    def homeVideoContent(self):
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        params = {"classify": tid}
        if extend:
            for k, v in extend.items():
                if v and k != 'classify':
                    params[k] = v
        if page > 1:
            params['page'] = page
        resp, _ = self._fetch_from_sites("/filter", params=params)
        html = self._resp_text(resp)
        if not html:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}
        video_list = self._parse_cards(html)
        soup = BeautifulSoup(html, 'html.parser')
        pagecount = page
        pt = soup.find(string=re.compile(r'共\s*\d+\s*页'))
        if pt:
            nums = re.findall(r'\d+', pt)
            if nums:
                pagecount = int(nums[-1])
        else:
            pb = soup.select_one('.flex.justify-center')
            if pb:
                for a in pb.select('a[href*="page="]'):
                    t = a.get_text(strip=True)
                    if t.isdigit():
                        pagecount = max(pagecount, int(t))
        return {"list": video_list, "page": page, "pagecount": pagecount,
                "limit": 24, "total": len(video_list) * pagecount}

    # ================= 详情（同步抓第一集 + 后台预热其余） =================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        resp, base_url = self._fetch_from_sites(f"/play/{vod_id}")
        html = self._resp_text(resp)
        if not html:
            return {"list": []}
        soup = BeautifulSoup(html, 'html.parser')

        title_elem = soup.select_one('h1.text-xl') or soup.select_one('h1') or soup.select_one('h2')
        vod_name = title_elem.get_text(strip=True) if title_elem else vod_id

        vod_pic = ''
        img_elem = soup.select_one('img.w-full') or soup.select_one('img[src]')
        if img_elem:
            src = img_elem.get('src', '') or img_elem.get('data-src', '')
            if src and not src.startswith('data:'):
                vod_pic = src if src.startswith('http') else 'https:' + src

        vod_director = vod_actor = vod_content = ''
        info_block = soup.select_one('.rounded-lg div.grid') or soup.select_one('div.grid')
        if info_block:
            text = info_block.get_text(' ', strip=True)
            m = re.search(r'导演\s*([^主\n]+)', text)
            if m: vod_director = m.group(1).strip()
            m = re.search(r'主演\s*([^剧\n]+)', text)
            if m: vod_actor = m.group(1).strip()
            m = re.search(r'剧情简介\s*(.+)', text, re.DOTALL)
            if m:
                vod_content = m.group(1).strip()
            else:
                m = re.search(r'简介\s*(.+)', text, re.DOTALL)
                if m:
                    vod_content = m.group(1).strip()

        play_from_list = []
        play_url_list = []
        ep_manager = soup.select_one('[x-data*="episodeManager"]')
        if ep_manager:
            xdata = ep_manager.get('x-data', '')
            lines_raw = re.findall(r'\{[^}]*lineName\s*:\s*\'([^\']+)\'[^}]*episodeCount\s*:\s*(\d+)[^}]*\}', xdata)
            lines_info = [{'lineName': n, 'episodeCount': int(c)} for n, c in lines_raw]
            lines_eps = {}
            for a in ep_manager.select('a[data-episode]'):
                line = a.get('data-line', '1')
                ep = a.get('data-episode', '')
                href = a.get('href', '')
                if not href or not ep:
                    continue
                full_url = href if href.startswith('http') else base_url.rstrip('/') + href
                lines_eps.setdefault(line, []).append((int(ep), full_url))
            for line_key in sorted(lines_eps.keys()):
                eps = sorted(lines_eps[line_key], key=lambda x: x[0])
                line_name = f'线路{line_key}'
                for info in lines_info:
                    line_name = info['lineName']
                    break
                if not eps:
                    continue
                play_from_list.append(line_name)
                play_url_list.append('#'.join([f"第{e[0]}集${e[1]}" for e in eps]))

        if not play_url_list:
            play_from_list.append('播放')
            play_url_list.append(f"播放${vod_id}")

        result = [{
            "vod_id": vod_id, "vod_name": vod_name, "vod_pic": vod_pic,
            "vod_content": vod_content, "vod_actor": vod_actor,
            "vod_director": vod_director, "vod_area": "", "vod_year": "",
            "vod_play_from": '$$$'.join(play_from_list),
            "vod_play_url": '$$$'.join(play_url_list)
        }]

        # 收集所有分集 URL
        all_ep, seen = [], set()
        for url_str in play_url_list:
            for pair in url_str.split('#'):
                if '$' in pair:
                    u = pair.split('$')[-1].strip()
                    if u.startswith('http') and u not in seen:
                        seen.add(u)
                        all_ep.append(u)

        # 同步抓第一集
        if all_ep:
            first = all_ep[0]
            print(f"[详情] 同步抓第一集: {first}")
            t0 = time.time()
            real = self._extract_play_url(first, quick=False, timeout=self._sync_timeout)
            if real and self._check_direct(real):
                self._play_cache[first] = {
                    'url': real,
                    'header': self._build_header(first),
                    'ts': time.time()
                }
                print(f"[同步OK {time.time()-t0:.1f}s] {real[:120]}")
            else:
                print(f"[同步失败 {time.time()-t0:.1f}s] {first}")

            rest = all_ep[1:]
            if rest:
                t = threading.Thread(target=self._preheat, args=(rest,))
                t.daemon = True
                t.start()
                print(f"[预热] 后台 {len(rest)} 集")

        return {"list": result}

    def _preheat(self, urls):
        def worker(u):
            c = self._play_cache.get(u)
            if c and time.time() - c['ts'] < self._cache_ttl:
                return
            real = self._extract_play_url(u, quick=True)
            if real and self._check_direct(real):
                self._play_cache[u] = {
                    'url': real,
                    'header': self._build_header(u),
                    'ts': time.time()
                }
                print(f"[预热OK] {u} -> {real[:110]}")
            else:
                print(f"[预热失败] {u}")
        try:
            with ThreadPoolExecutor(max_workers=self._preheat_workers) as ex:
                list(ex.map(worker, urls))
        except Exception as e:
            print(f"[预热线程异常] {e}")

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        params = {"q": key}
        if page > 1:
            params['page'] = page
        resp, _ = self._fetch_from_sites("/search", params=params)
        html = self._resp_text(resp)
        if not html:
            return {"list": [], "page": page, "pagecount": 1}
        video_list = self._parse_cards(html, limit=30)
        if not video_list:
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.select('a.block[href^="/play/"]'):
                href = a.get('href', '')
                vod_id = href.replace('/play/', '').strip()
                if not vod_id:
                    continue
                h3 = a.select_one('h3')
                vod_name = h3.get_text(strip=True) if h3 else href
                img = a.select_one('img[data-src]')
                vod_pic = ''
                if img:
                    src = img.get('data-src', '')
                    if src and not src.startswith('data:'):
                        vod_pic = src if src.startswith('http') else 'https:' + src
                video_list.append({"vod_id": vod_id, "vod_name": vod_name,
                                   "vod_pic": vod_pic, "vod_remarks": ''})
        return {"list": video_list, "page": page, "pagecount": 1}

    # ================= 播放 =================
    def playerContent(self, flag, id, vipFlags):
        play_url = id if id.startswith('http') else f"{self.current_site_url.rstrip('/')}/play/{id}"
        now = time.time()

        # 1) 缓存命中
        cached = self._play_cache.get(play_url)
        if cached and now - cached['ts'] < self._cache_ttl:
            print(f"[播放] 缓存命中 -> {play_url}")
            return {"parse": 0, "url": cached['url'], "header": cached['header']}

        # 2) 现场抓 + 自检，重试2次
        for attempt in range(2):
            real = self._extract_play_url(play_url, quick=False)
            if real and self._check_direct(real):
                header = self._build_header(play_url)
                self._play_cache[play_url] = {'url': real, 'header': header, 'ts': now}
                print(f"[播放] 直链有效(第{attempt+1}次) -> {real[:120]}")
                return {"parse": 0, "url": real, "header": header}
            time.sleep(0.3)

        # 3) 兜底嗅探
        print(f"[播放] 直链失败，退回嗅探 -> {play_url}")
        return {"parse": 1, "url": play_url, "header": self._build_header(play_url)}

    def _build_header(self, play_url):
        h = self.headers.copy()
        h['Referer'] = self.current_site_url.rstrip('/') + '/'
        h['Origin'] = self.current_site_url.rstrip('/')
        return h

    def _check_direct(self, url):
        """检查直链是否真的能拿到媒体内容"""
        if not url:
            return False
        try:
            resp = self._safe_fetch(url, headers={'User-Agent': self.headers['User-Agent']},
                                    timeout=(3, 6))
            if not resp:
                return False
            code = getattr(resp, 'status_code', 0)
            if code != 200:
                print(f"[自检] {url[:80]} HTTP {code} -> 无效")
                return False

            # 取前 500 字节判断内容
            body = self._resp_text(resp)[:500]
            body_stripped = body.lstrip()

            # m3u8：必须以 #EXTM3U 开头
            if '.m3u8' in url.lower():
                if body_stripped.startswith('#EXTM3U'):
                    return True
                print(f"[自检] m3u8内容异常(token过期?): {body_stripped[:60]!r}")
                return False

            # mp4/flv/ts：不能是文本错误页
            if any(x in url.lower() for x in ('.mp4', '.flv', '.ts')):
                # 文本错误页特征
                if body_stripped.startswith(('{', '<', 'token', 'error', 'Token', 'Error')):
                    print(f"[自检] mp4内容异常: {body_stripped[:60]!r}")
                    return False
                # 二进制内容一般包含不可打印字符
                printable = sum(1 for c in body[:200] if 32 <= ord(c) < 127)
                if len(body) > 0 and printable / max(len(body[:200]), 1) > 0.95:
                    # 全是可打印字符，很可能是错误文本
                    print(f"[自检] mp4疑似文本页: {body_stripped[:60]!r}")
                    return False
                return True

            return True
        except Exception as e:
            print(f"[自检异常] {e}")
            return False

    # ================= 直链提取（优先天翼云） =================
    def _extract_play_url(self, play_url, depth=0, quick=False, timeout=None):
        if depth > (1 if quick else 3):
            return None
        if timeout is None:
            timeout = self._quick_timeout if quick else self.timeout
        resp = self._safe_fetch(play_url, headers=self.headers, timeout=timeout)
        html = self._resp_text(resp)
        if not html:
            return None
        norm = html.replace('\\/', '/')

        # 层1：优先扫天翼云 + 非过期 OSS
        hit = self._scan(norm)
        if hit:
            print(f"[提取-层1] {hit[:110]}")
            return hit

        soup = BeautifulSoup(html, 'html.parser')

        # 层2：data-*
        for tag in soup.find_all(True):
            for attr, val in tag.attrs.items():
                if not isinstance(val, str):
                    continue
                if attr.startswith('data-') and any(x in val for x in ('.mp4', '.m3u8', '.flv', 'ctyun')):
                    u = self._abs(val)
                    print(f"[提取-层2] {u[:110]}")
                    return u

        # 层3：meta
        for meta in soup.select('meta[content]'):
            c = meta.get('content', '')
            if any(x in c for x in ('.mp4', '.m3u8', '.flv', 'ctyun')):
                m = re.search(r'https?://[^\s"\']+', c)
                if m:
                    print(f"[提取-层3] {m.group(0)[:110]}")
                    return m.group(0)

        # 层4：script + base64
        for s in soup.select('script'):
            txt = s.string or s.get_text() or ''
            if not txt:
                continue
            txt = txt.replace('\\/', '/')
            hit = self._scan(txt)
            if hit:
                print(f"[提取-层4] {hit[:110]}")
                return hit
            for b64 in re.findall(r'["\']([A-Za-z0-9+/=]{40,})["\']', txt):
                try:
                    dec = base64.b64decode(b64).decode('utf-8', 'ignore').replace('\\/', '/')
                    hit = self._scan(dec)
                    if hit:
                        print(f"[提取-层4-b64] {hit[:110]}")
                        return hit
                except Exception:
                    pass

        # 层5：iframe 递归
        for iframe in soup.select('iframe[src]'):
            src = iframe.get('src', '').strip()
            if not src or src.startswith(('javascript:', 'about:', 'data:')):
                continue
            sub = self._extract_play_url(self._abs(src), depth + 1, quick, timeout)
            if sub:
                print(f"[提取-层5-iframe] {sub[:110]}")
                return sub

        # 层6：URL decode 再扫
        try:
            dec = urllib.parse.unquote(norm)
            if dec != norm:
                hit = self._scan(dec)
                if hit:
                    print(f"[提取-层6] {hit[:110]}")
                    return hit
        except Exception:
            pass

        # 层7：相对路径
        m = re.search(r'["\'](/[^"\']+\.(?:m3u8|mp4|flv)(?:\?[^"\']*)?)["\']', norm, re.IGNORECASE)
        if m:
            u = self._abs(m.group(1))
            print(f"[提取-层7] {u[:110]}")
            return u

        return None

    def _scan(self, text):
        """扫描直链，优先天翼云/长效源，其次其他 mp4，最后 m3u8"""

        # 1) 天翼云 OBS mp4（带签名，长效）
        for m in re.finditer(
                r'https?://[^\s"\'<>\\]+?\.ctyun\.cn[^\s"\'<>\\]*?\.mp4(?:\?[^\s"\'<>\\]*)?',
                text, re.IGNORECASE):
            u = m.group(0).strip()
            if u:
                return u

        # 2) 其他非过期域名的 mp4（排除 oss.douyinbit.com，它的 token 常失效）
        for m in re.finditer(
                r'https?://(?!oss\.douyinbit\.com)[^\s"\'<>\\]+?\.mp4(?:\?[^\s"\'<>\\]*)?',
                text, re.IGNORECASE):
            u = m.group(0).strip()
            if u:
                return u

        # 3) m3u8（原有逻辑）
        for pat in [
            r'https?://[^\s"\'<>\\]+?\.m3u8(?:\?[^\s"\'<>\\]*)?',
            r'"(?:url|src|file|playUrl|play_url|videoUrl|video_url|source|m3u8|hls)"\s*:\s*"(https?://[^"]+)"',
        ]:
            for m in re.finditer(pat, text, re.IGNORECASE):
                u = (m.group(1) if m.lastindex else m.group(0)).strip()
                if u and ('.m3u8' in u or '.mp4' in u):
                    return u

        # 4) flv
        for m in re.finditer(r'https?://[^\s"\'<>\\]+?\.flv(?:\?[^\s"\'<>\\]*)?', text, re.IGNORECASE):
            u = m.group(0).strip()
            if u:
                return u

        return None

    def _abs(self, url):
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.current_site_url.rstrip('/') + url
        return url
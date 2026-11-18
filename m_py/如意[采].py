#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '如意',
  lang: 'hipy',
})
"""

import json, re, sys, threading
import requests
from concurrent.futures import ThreadPoolExecutor, wait

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def destroy(self): pass
        def localProxy(self, param): pass


class Spider(BaseSpider):
    def __init__(self):
        self.name = '如意影视'
        self.host = 'https://www.r5y.net'
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Referer': self.host + '/',
            'Accept': 'application/json, text/plain, */*',
            'X-Requested-With': 'XMLHttpRequest',
        }
        self.timeout = 5
        self.verify = False
        requests.packages.urllib3.disable_warnings()
        self._all_srcs = ['ffzy', 'zd', 'xg', 'wu', 'sn']
        self._pool = ThreadPoolExecutor(max_workers=8)
        self.session = requests.Session()
        self.session.headers.update(self.header)
        self._warm = threading.Event()
        threading.Thread(target=self._warmup, daemon=True).start()

    def _warmup(self):
        try:
            r = self.session.get(self.host + '/api_proxy.php',
                                 params={'do': 'home'}, timeout=15, verify=False, stream=True)
            r.close()
            print(f'[{self.name}] 预热完成')
        except Exception as e:
            print(f'[{self.name}] 预热失败: {e}')
        finally:
            self._warm.set()

    def getName(self): return self.name
    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|avi|mkv|flv|ts)(\?|$)', str(url), re.I))
    def manualVideoCheck(self): return False
    def destroy(self):
        try: self._pool.shutdown(wait=False)
        except: pass
    def init(self, extend=""): pass
    def localProxy(self, param): return None

    def _fix_pic(self, u):
        if not u: return ''
        u = str(u).strip()
        if u.startswith('http://') or u.startswith('https://'):
            return u
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return self.host + u
        return u

    def _get(self, params):
        if not self._warm.is_set():
            self._warm.wait(timeout=15)
        try:
            r = self.session.get(self.host + '/api_proxy.php', params=params,
                                 timeout=self.timeout, verify=self.verify)
            r.encoding = 'utf-8'
            return r.json()
        except Exception:
            return None

    def _norm(self, s):
        if not s: return ''
        s = re.sub(r'\s+', '', str(s))
        s = re.sub(r'[（(【\[].*?[）)】\]]', '', s)
        return s.lower()

    def _fmt(self, data, with_source=False):
        out = []
        for it in (data or []):
            try:
                vid = str(it.get('vod_id', '') or '')
                src = (it.get('source') or '').strip()
                if with_source and src and vid:
                    vid = f'{src}_{vid}'
                out.append({
                    'vod_id': vid,
                    'vod_name': it.get('vod_name', '') or '',
                    'vod_pic': self._fix_pic(it.get('vod_pic', '')),
                    'vod_remarks': it.get('vod_remarks', '') or '',
                })
            except Exception:
                continue
        return out

    def homeContent(self, filter):
        try:
            data = self._get({'do': 'home'}) or {}
            classes = [{'type_name': (c.get('type_name') or '').strip(),
                        'type_id': str(c.get('type_id', ''))}
                       for c in data.get('classes', [])]
            print(f'[{self.name}] 分类数量: {len(classes)}')
            return {'class': classes, 'filters': {}}
        except Exception as e:
            print(f'[{self.name}] 获取首页分类失败: {e}')
            return {'class': [], 'filters': {}}

    def homeVideoContent(self):
        try:
            data = self._get({'do': 'home'}) or {}
            lst = []
            for k in ('movies', 'series', 'variety', 'anime'):
                lst.extend(self._fmt(data.get(k)))
            print(f'[{self.name}] 首页视频: {len(lst)} 条')
            return {'list': lst}
        except Exception as e:
            print(f'[{self.name}] 首页视频失败: {e}')
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            data = self._get({'do': 'list', 'tid': tid, 'pg': pg}) or {}
            lst = self._fmt(data.get('list'))
            print(f'[{self.name}] 分类 {tid} 第 {pg} 页: {len(lst)} 条')
            return {
                'list': lst,
                'page': int(pg),
                'pagecount': int(data.get('pagecount', 9999) or 9999),
                'limit': len(lst),
                'total': int(data.get('total', 0) or 0),
            }
        except Exception as e:
            print(f'[{self.name}] 分类爬取失败: {e}')
            return {'list': [], 'page': int(pg), 'pagecount': 1, 'limit': 0, 'total': 0}

    def _find_and_fetch(self, src, name_norm, vod_name):
        try:
            sd = self._get({'do': 'search', 'wd': vod_name, 'src': src}) or {}
            for it in (sd.get('list') or [])[:3]:
                if self._norm(it.get('vod_name', '')) != name_norm:
                    continue
                sid = str(it.get('vod_id') or '')
                if not sid:
                    continue
                dd = self._get({'do': 'sources', 'id': sid, 'src': src}) or {}
                return src, dd.get('lines') or []
        except Exception:
            pass
        return src, []

    def detailContent(self, ids):
        try:
            vid = str(ids[0]) if isinstance(ids, list) else str(ids)
            src_key, real_id = ('', vid)
            if '_' in vid:
                src_key, real_id = vid.split('_', 1)

            params = {'do': 'sources', 'id': real_id}
            if src_key:
                params['src'] = src_key
            data = self._get(params) or {}
            v = data.get('vod') or {}
            vod_name = (v.get('vod_name') or '').strip()
            if not vod_name:
                print(f'[{self.name}] 详情为空: {vid}')
                return {'list': []}

            from_list, url_list, seen = [], [], set()

            def add_lines(lines):
                for ln in (lines or []):
                    try:
                        f = (ln.get('from') or '').strip()
                        label = (ln.get('source') or f).strip()
                        eps = ln.get('episodes') or []
                        if not f or not eps or f in seen:
                            continue
                        chunks = []
                        for e in eps:
                            eu = e.get('url') or ''
                            en = (e.get('name') or '播放').strip()
                            if eu:
                                chunks.append(f'{en}${eu}')
                        if not chunks:
                            continue
                        seen.add(f)
                        from_list.append(label)
                        url_list.append('#'.join(chunks))
                    except Exception:
                        continue

            add_lines(data.get('lines'))
            print(f'[{self.name}] 主源 lines: {len(from_list)} 条')

            target = self._norm(vod_name)
            todo = [s for s in self._all_srcs if s != src_key]
            if todo:
                futs = [self._pool.submit(self._find_and_fetch, s, target, vod_name)
                        for s in todo]
                done, not_done = wait(futs, timeout=3.5)
                for fu in done:
                    try:
                        src, lines = fu.result()
                        before = len(from_list)
                        add_lines(lines)
                        added = len(from_list) - before
                        if added:
                            print(f'[{self.name}]   + {src} 补充 {added} 条')
                    except Exception:
                        continue
                for fu in not_done:
                    fu.cancel()

            content = re.sub(r'<[^>]+>', '', v.get('vod_content', '') or '').strip()
            print(f'[{self.name}] 详情 {vid}: 最终 {len(from_list)} 条线路')

            return {'list': [{
                'vod_id': vid,
                'vod_name': vod_name,
                'vod_pic': self._fix_pic(v.get('vod_pic', '')),
                'vod_year': str(v.get('vod_year', '') or ''),
                'vod_area': v.get('vod_area', '') or '',
                'vod_remarks': v.get('vod_remarks', '') or '',
                'vod_actor': v.get('vod_actor', '') or '',
                'vod_director': v.get('vod_director', '') or '',
                'vod_content': content,
                'vod_play_from': '$$$'.join(from_list),
                'vod_play_url': '$$$'.join(url_list),
            }]}
        except Exception as e:
            print(f'[{self.name}] 详情解析失败: {e}')
            return {'list': []}

    def searchContent(self, key, quick, pg='1'):
        try:
            data = self._get({'do': 'search', 'wd': key, 'pg': pg}) or {}
            lst = self._fmt(data.get('list'), with_source=True)
            print(f'[{self.name}] 搜索 "{key}": {len(lst)} 条')
            return {
                'list': lst,
                'page': int(pg),
                'pagecount': int(data.get('pagecount', 1) or 1),
                'limit': len(lst),
                'total': int(data.get('total', 0) or 0),
            }
        except Exception as e:
            print(f'[{self.name}] 搜索失败: {e}')
            return {'list': [], 'page': int(pg), 'pagecount': 1, 'limit': 0, 'total': 0}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = str(id or '').strip()
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('/'):
                url = self.host + url
            print(f'[{self.name}] 播放: {flag} -> {url[:70]}...')
            return {'parse': 0, 'playUrl': '', 'url': url, 'header': json.dumps(self.header)}
        except Exception as e:
            print(f'[{self.name}] 播放解析失败: {e}')
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': json.dumps(self.header)}

# ========== 万能兼容补丁 ==========
# 目的：兼容 drpy-node 的 Spider(t4_api=...) 初始化 + 关闭 localProxy
_OrigSpider = Spider

class Spider(_OrigSpider):
    def __init__(self, *args, **kwargs):
        kwargs.pop("t4_api", None)          # 丢弃 t4_api，避免 TypeError
        try:
            super().__init__(*args, **kwargs)
        except TypeError:
            try:
                super().__init__()
            except Exception:
                pass
        self.t4_api = None
        self.use_proxy = False              # ★ 不启用 localProxy

    def init(self, extend=""):
        try:
            super().init(extend)
        except Exception:
            pass
        self.extend = extend
        self.use_proxy = False

    def localProxy(self, params):
        return [404, "text/plain", "Not Found"]
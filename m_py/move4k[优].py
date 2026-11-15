# coding=utf-8
# !/usr/bin/python
import sys
import json
import requests
import random
import string
from urllib.parse import quote, unquote

sys.path.append('..')
try:
    from base.spider import Spider
except:
    from base.spider import Spider as BaseSpider
    class Spider(BaseSpider):
        pass

class Spider(Spider):
    def getName(self):
        return "Move影视"

    def init(self, extend=""):
        self.host = 'http://47.94.148.11'
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.session.headers.update(self.headers)
        
        self.filters_map = {}
        self.init_filters()

    def init_filters(self):
        try:
            self.session.get(self.host, timeout=10)
            # 批量获取分类1,2,3,4的筛选数据
            for tid in ['1', '2', '3', '4']:
                try:
                    r = self.session.get(f'{self.host}/type/{tid}', timeout=10)
                    r.encoding = 'utf-8'
                    d = self.parse_type_resp(r.text)
                    if d and 'filters' in d:
                        self.filters_map[tid] = self.build_filters(d['filters'])
                except:
                    pass
        except:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        classes = [
            {'type_id': '1', 'type_name': '电影'},
            {'type_id': '2', 'type_name': '剧集'},
            {'type_id': '3', 'type_name': '动漫'},
            {'type_id': '4', 'type_name': '综艺'},
        ]
        return {'class': classes, 'filters': self.filters_map}

    def homeVideoContent(self):
        try:
            r = self.session.get(self.host, timeout=10)
            r.encoding = 'utf-8'
            data = self.extract_json(r.text, 'KANKAN_HOME')
            if not data:
                return {'list': []}

            seen = set()
            videos = []
            
            def add_video(v):
                if not v or 'vod_id' not in v:
                    return
                vid = str(v['vod_id'])
                if vid in seen:
                    return
                seen.add(vid)
                videos.append({
                    'vod_id': vid,
                    'vod_name': v.get('vod_name', ''),
                    'vod_pic': v.get('vod_pic') or v.get('vod_douban_pic', ''),
                    'vod_remarks': v.get('vod_remarks', '')
                })

            for v in data.get('recommend', []):
                add_video(v)
            
            for cat in data.get('categories', []):
                for v in cat.get('videos', []):
                    add_video(v)

            return {'list': videos}
        except:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg)
        sort_val = extend.get('sort', 'hits')
        
        params = [
            f'type_id={tid}',
            f'page={page}',
            f'sort={sort_val}'
        ]
        
        for k in ['class', 'area', 'year']:
            if extend.get(k):
                params.append(f'{k}={extend[k]}')
                
        url = f"{self.host}/kankan/filter?{'&'.join(params)}"
        
        try:
            r = self.session.get(url, timeout=10)
            r.encoding = 'utf-8'
            data = self.parse_type_resp(r.text)
            if not data:
                return {'page': page, 'pagecount': page, 'limit': 0, 'total': 0, 'list': []}
            
            vlist = []
            for v in data.get('list', []):
                vlist.append({
                    'vod_id': str(v.get('vod_id', '')),
                    'vod_name': v.get('vod_name', ''),
                    'vod_pic': v.get('vod_pic') or v.get('vod_douban_pic', ''),
                    'vod_remarks': v.get('vod_remarks', '')
                })
                
            pagecount = page
            if len(vlist) > 0 and data.get('has_more'):
                pagecount = page + 1
                
            return {
                'page': page,
                'pagecount': pagecount,
                'limit': len(vlist),
                'total': data.get('total', len(vlist)),
                'list': vlist
            }
        except:
            return {'page': page, 'pagecount': page, 'limit': 0, 'total': 0, 'list': []}

    def detailContent(self, ids):
        vod_id = str(ids[0])
        data = None
        
        # 尝试多个详情页路径
        tries = [f'/play/{vod_id}.html', f'/play/{vod_id}', f'/detail/{vod_id}.html', f'/detail/{vod_id}']
        for u in tries:
            try:
                r = self.session.get(f'{self.host}{u}', timeout=10)
                r.encoding = 'utf-8'
                d = self.extract_json(r.text, 'KANKAN_PAGE')
                if d and 'detail' in d:
                    data = d
                    break
            except:
                continue
                
        if not data or 'detail' not in data:
            return {'list': []}
            
        d = data['detail']
        sources = d.get('sources', [])
        froms = []
        urls = []
        
        for s in sources:
            eps = s.get('episodes', [])
            if not eps:
                continue
            from_name = s.get('name') or s.get('from', '默认')
            froms.append(from_name)
            
            ep_urls = []
            for i, e in enumerate(eps):
                title = e.get('title') or f'第{i+1}集'
                # 拼装播放格式：集数名$vod_id|from|index
                ep_urls.append(f"{title}${d.get('vod_id')}|{s.get('from')}|{i}")
                
            urls.append('#'.join(ep_urls))
            
        vod = {
            'vod_id': str(d.get('vod_id', '')),
            'vod_name': d.get('vod_name', ''),
            'vod_pic': d.get('vod_pic') or d.get('vod_douban_pic', ''),
            'vod_year': d.get('vod_year', ''),
            'vod_area': d.get('vod_area', ''),
            'vod_actor': d.get('vod_actor', ''),
            'vod_director': d.get('vod_director', ''),
            'vod_content': d.get('vod_content', ''),
            'vod_remarks': d.get('vod_remarks', ''),
            'vod_play_from': '$$$'.join(froms) if froms else '默认',
            'vod_play_url': '$$$'.join(urls) if urls else f"正片${d.get('vod_id')}|default|0"
        }
        
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        parts = id.split('|')
        if len(parts) < 3:
            return {'parse': 0, 'jx': 0, 'url': id}
            
        vod_id, from_str, index = parts[0], parts[1], parts[2]
        rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))
        
        url = f"{self.host}/kankan/decode?vod_id={quote(vod_id)}&from={quote(from_str)}&index={quote(index)}&session_id={rand_str}"
        
        try:
            headers = {
                'Accept': 'application/json',
                'X-Requested-With': 'mark.via',
                'Referer': f'{self.host}/'
            }
            r = self.session.get(url, headers=headers, timeout=10)
            j = json.loads(r.text)
            
            if j and j.get('code') == 200 and j.get('data') and j.get('data', {}).get('url'):
                return {
                    'parse': 0,
                    'jx': 0,
                    'url': j['data']['url'],
                    'header': {
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36',
                        'Referer': f'{self.host}/'
                    }
                }
        except:
            pass
            
        return {'parse': 1, 'jx': 0, 'url': id}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg)
        url = f"{self.host}/search?wd={quote(key)}"
        if page > 1:
            url += f'&page={page}'
            
        try:
            r = self.session.get(url, timeout=10)
            r.encoding = 'utf-8'
            data = self.extract_json(r.text, 'KANKAN_PAGE')
            result = data.get('result') if data else None
            
            if not result:
                return {'page': page, 'pagecount': page, 'limit': 20, 'total': 0, 'list': []}
                
            vlist = []
            for v in result.get('list', []):
                vlist.append({
                    'vod_id': str(v.get('vod_id', '')),
                    'vod_name': v.get('vod_name', ''),
                    'vod_pic': v.get('vod_pic') or v.get('vod_douban_pic', ''),
                    'vod_remarks': v.get('vod_remarks', '')
                })
                
            pagecount = page
            if isinstance(result.get('page_count'), int) and result.get('page_count') > 0:
                pagecount = result['page_count']
            elif result.get('has_more'):
                pagecount = page + 1
                
            return {
                'page': page,
                'pagecount': pagecount,
                'limit': 20,
                'total': result.get('total', 0),
                'list': vlist
            }
        except:
            return {'page': page, 'pagecount': page, 'limit': 20, 'total': 0, 'list': []}

    # ============ 工具函数 ============

    def extract_json(self, html, name):
        marker = f'window.{name} = '
        idx = html.find(marker)
        if idx < 0:
            return None
        start = idx + len(marker)
        
        # 使用 JSONDecoder 的 raw_decode 方法原生解析，完美替代 JS 的括号匹配逻辑
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(html[start:])
            return obj
        except:
            return None

    def parse_type_resp(self, txt):
        if not txt:
            return None
        d = self.extract_json(txt, 'KANKAN_TYPE')
        if d:
            return d
        try:
            j = json.loads(txt)
            return j.get('data') or j.get('result') or j
        except:
            return None

    def build_filters(self, f):
        out = []
        if f.get('class') and len(f['class']) > 0:
            out.append({'key': 'class', 'name': '类型', 'value': [{'n': x, 'v': x} for x in f['class']]})
        if f.get('area') and len(f['area']) > 0:
            out.append({'key': 'area', 'name': '地区', 'value': [{'n': x, 'v': x} for x in f['area']]})
        if f.get('year') and len(f['year']) > 0:
            out.append({'key': 'year', 'name': '年份', 'value': [{'n': x, 'v': x} for x in f['year']]})
        if f.get('sorts') and len(f['sorts']) > 0:
            out.append({'key': 'sort', 'name': '排序', 'value': [{'n': x.get('label'), 'v': x.get('value')} for x in f['sorts']]})
        return out
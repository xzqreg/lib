# -*- coding: utf-8 -*-
# by @Qist
import re
import sys
import requests
from lxml import etree
from base.spider import Spider


def _doc(text):
    try:
        return etree.HTML(text or "")
    except Exception:
        return None


def _text(el):
    return ''.join(el.itertext()).strip() if el is not None else ''


def _attr(el, name):
    return (el.get(name) or '') if el is not None else ''


def _first(root, xp):
    if root is None:
        return None
    els = root.xpath(xp)
    return els[0] if els else None


class Spider(Spider):
    def getName(self):
        return "闪雷影视"

    def init(self, extend=""):
        pass

    host = 'http://60.6.229.145:88'
    ip = '60.6.229.145'
    header = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Mobile Safari/537.36',
    }
    encoding = 'gb2312'

    class_names = '电视剧&大陆地区&港台地区&日韩地区&欧美地区&其他地区&动作片&喜剧片&恐怖片&科幻片&战争片&动画片&爱情片&综艺片&剧情片&MTV'.split('&')
    class_urls = '10&20&21&22&23&24&1&2&3&4&5&6&7&8&9&12'.split('&')

    def _videos(self, root):
        """从列表页提取影片（原 pyquery 版 dl/dd[classid=h4] 逻辑）"""
        videos = []
        for dl in (root.xpath('//dl') if root is not None else []):
            h4 = dl.xpath('.//dd[@classid="h4"]')
            if not h4:
                continue
            a = _first(h4[0], './/a')
            href = _attr(a, 'href')
            if not href:
                continue
            pic = _attr(_first(dl, './/dt//img'), 'src')
            if pic and pic.startswith('../'):
                pic = self.host + '/' + pic.replace('../', '')
            elif pic and not pic.startswith('http'):
                pic = self.host + '/' + pic.lstrip('/')
            spans = dl.xpath('.//dt//span')
            remarks = _text(spans[1]) if len(spans) > 1 else ''
            vid_match = re.search(r'[Cc]lass[Ii][Dd]=(\d+)', href)
            videos.append({
                'vod_id': vid_match.group(1) if vid_match else href,
                'vod_name': _text(a),
                'vod_pic': pic,
                'vod_remarks': remarks,
            })
        return videos

    def homeContent(self, filter):
        try:
            result = {'class': [], 'list': []}
            for name, cid in zip(self.class_names, self.class_urls):
                result['class'].append({'type_name': name, 'type_id': cid})
            resp = self.fetch(f"{self.host}/jdl/List.asp?ClassId=10", headers=self.header)
            result['list'] = self._videos(_doc(resp.text))[:10]
            return result
        except Exception as e:
            print(f"Error in homeContent: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"class": [], "list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            url = f"{self.host}/jdl/List.asp?ClassId={tid}&searchword=&page={pg}"
            resp = self.fetch(url, headers=self.header)
            videos = self._videos(_doc(resp.text))
            return {
                'list': videos,
                'page': int(pg),
                'pagecount': 999,
                'limit': len(videos),
                'total': 999999,
            }
        except Exception as e:
            print(f"Error in categoryContent: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def detailContent(self, ids):
        try:
            url = f"{self.host}/jdl/movie.asp?ClassId={ids[0]}"
            resp = self.fetch(url, headers=self.header)
            root = _doc(resp.text)

            vod = {
                'vod_id': ids[0],
                'vod_name': _text(_first(root, '//li[@classid="h4"]')),
                'vod_pic': '',
                'vod_remarks': '',
                'vod_year': '',
                'vod_area': '',
                'vod_director': '',
                'vod_actor': '',
                'vod_content': '',
            }

            cover_img = _attr(_first(root, '//*[contains(@class,"intro")]//*[contains(@class,"img")]//img'), 'src')
            if cover_img and cover_img.startswith('../'):
                vod['vod_pic'] = f"{self.host}/{cover_img[3:]}"
            elif cover_img and not cover_img.startswith('http'):
                vod['vod_pic'] = f"{self.host}/{cover_img}"
            else:
                vod['vod_pic'] = cover_img

            actor_info = _text(_first(root, '//li[contains(., "主　　演")]'))
            if actor_info:
                vod['vod_actor'] = actor_info.replace('主　　演：', '').strip()

            content_parts = []
            for kw in ('状　　态', '类　　型', '拍摄地区', '更新时间', '单集时长'):
                part = _text(_first(root, '//li[contains(., "%s")]' % kw))
                if part:
                    content_parts.append(part)
            vod['vod_content'] = '\n'.join(content_parts)

            play_urls = []
            for a in (root.xpath('//div[contains(@class,"listt")]//a') if root is not None else []):
                title = _text(a)
                href = _attr(a, 'href')
                if title and href:
                    play_urls.append(f"{title}${self.host}{href}")

            vod['vod_play_from'] = '闪雷影视'
            vod['vod_play_url'] = '#'.join(play_urls) if play_urls else '无播放源'
            return {"list": [vod]}
        except Exception as e:
            print(f"Error in detailContent: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        try:
            url = f"{self.host}/jdl/List.asp?ClassId=30&type=&searchword={key}&page={pg}"
            resp = self.fetch(url, headers=self.header)
            return {'list': self._videos(_doc(resp.text)), 'page': pg}
        except Exception as e:
            print(f"Error in searchContent: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'list': [], 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        try:
            if ',' in id:
                parts = id.split(',')
                classid = parts[2]
                movno = parts[3]
                play_url = f"{self.host}/PlayMov.asp?ClassId={classid}&video=2&exe=0&down=0&movNo={movno}&vgver=undefined&ClientIP={self.ip}"
            else:
                play_url = id

            resp = self.fetch(play_url, headers=self.header)
            html = resp.text

            video_match = re.search(r"videoarr\.push\(['\"](.*?)['\"]\)", html)
            if video_match:
                video_url = re.sub(r'https?://(?:[\d.]+|[\w\-]+)(?::\d+)?/', f'{self.host}/', video_match.group(1))
                return {"parse": 0, "url": video_url, "header": self.header, "playUrl": ""}

            js_open_matches = re.findall(r'player\.open\s*\(\s*["\']([^"\']+)["\']\s*\)', html)
            if js_open_matches:
                video_url = js_open_matches[0]
                if not video_url.startswith('http'):
                    video_url = self.host + '/' + video_url.lstrip('/')
                return {"parse": 0, "url": video_url, "header": self.header, "playUrl": ""}

            return {"parse": 1, "url": play_url}
        except Exception as e:
            print(f"Error in playerContent: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"parse": 1, "url": id}

    def fetch(self, url, headers=None):
        session = requests.Session()
        if headers:
            session.headers.update(headers)
        else:
            session.headers.update(self.header)
        response = session.get(url, timeout=25)
        response.encoding = self.encoding
        return response

    def post(self, url, headers=None, data=None):
        session = requests.Session()
        if headers:
            session.headers.update(headers)
        else:
            session.headers.update(self.header)
        response = session.post(url, data=data, timeout=25)
        response.encoding = self.encoding
        return response

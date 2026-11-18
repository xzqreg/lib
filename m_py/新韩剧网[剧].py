"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '新韩剧网',
  lang: 'hipy'
})
"""

# -*- coding: utf-8 -*-
# @Author  : Doubebly   (pyquery -> lxml 适配安卓 Pyramid)
# @file    : 新韩剧网

import re
import sys
import requests as B
from urllib import parse
from lxml import etree
from Crypto.Cipher import AES as A
from Crypto.Util.Padding import unpad
import base64 as I
sys.path.append('..')
from base.spider import Spider as E


def _doc(text):
    try:
        return etree.HTML(text or "")
    except Exception:
        return None


def _text(el):
    if el is None:
        return ''
    if isinstance(el, str):
        return el.strip()
    return ''.join(el.itertext()).strip()


def _attr(el, name):
    return (el.get(name) or '') if el is not None else ''


def _first(root, xp):
    if root is None:
        return None
    els = root.xpath(xp)
    return els[0] if els else None


def _item(li):
    """列表页单个 li -> vod（兼容两种模板：带 title/data-original 的海报版 和 紧凑版）"""
    a = _first(li, './/a')
    if a is None:
        return None
    href = _attr(a, 'href')
    if not href:
        return None
    name = _attr(a, 'title') or ''.join(a.xpath('./text()')).strip() or _text(a)
    if not name:
        p = _first(li, './/p//a')
        name = _text(p)
    pic = _attr(a, 'data-original')
    if pic and not pic.startswith(('https', 'http')):
        pic = 'https:' + pic
    if not pic:
        pic = 'https://youke2.picui.cn/s1/2025/12/21/694796745c0c6.png'
    remarks = _text(_first(li, './/span[contains(@class,"tip")]')) or _text(_first(li, './/span'))
    return {'vod_id': href, 'vod_name': name, 'vod_pic': pic, 'vod_remarks': remarks}


class Spider(E):

    def getName(self):
        return self.name

    def init(self, extend='{}'):
        self.debug = False
        self.name = '新韩剧网'
        self.error_play_url = 'https://kjjsaas-sh.oss-cn-shanghai.aliyuncs.com/u/3401405881/20240818-936952-fc31b16575e80a7562cdb1f81a39c6b0.mp4'
        self.home_url = 'https://www.hanju7.com'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36',
            'Referer': 'https://www.hanju7.com/'
        }
        self.extend = extend

    def homeContent(self, filter):
        G = {'class': [
            {'type_id': '1', 'type_name': '韩剧'},
            {'type_id': '3', 'type_name': '韩国电影'},
            {'type_id': '4', 'type_name': '韩国综艺'},
            {'type_id': 'hot', 'type_name': '排行榜'},
            {'type_id': 'new', 'type_name': '最新更新'},
        ], 'filters': {}, 'list': [], 'parse': 0, 'jx': 0}
        try:
            H = B.get(self.home_url, headers=self.headers)
            H.encoding = 'utf-8'
            root = _doc(H.text)
            for li in (root.xpath('//div[contains(@class,"list")]//ul//li') if root is not None else []):
                item = _item(li)
                if item:
                    G['list'].append(item)
        except Exception as e:
            print(e)
        return G

    def categoryContent(self, cid, page, filter, ext):
        H = int(page)
        G = cid
        result = {'list': [], 'parse': 0, 'jx': 0}
        if G in ['hot', 'new']:
            J = self.home_url + "/%s.html" % G
        else:
            J = self.home_url + "/list/%s---%d.html" % (G, H - 1)
        try:
            K = B.get(J, headers=self.headers)
            K.encoding = 'utf-8'
            root = _doc(K.text)
            if G in ['hot', 'new']:
                for li in (root.xpath('//div[contains(@class,"txt")]//ul//li') if root is not None else []):
                    a = _first(li, './/a')
                    if a is None or not _attr(a, 'href'):
                        continue
                    result['list'].append({
                        'vod_id': _attr(a, 'href'),
                        'vod_name': _text(a),
                        'vod_pic': 'https://youke2.picui.cn/s1/2025/12/21/694796745c0c6.png',
                        'vod_remarks': _text(_first(li, './/*[@id="actor"]')),
                        'style': {'type': 'list'},
                    })
                result['pagecount'] = 1
                result['page'] = H
            else:
                for li in (root.xpath('//div[contains(@class,"list")]//ul//li') if root is not None else []):
                    item = _item(li)
                    if item:
                        result['list'].append(item)
        except Exception as e:
            print(e)
        return result

    def detailContent(self, did):
        result = {'list': [], 'parse': 0, 'jx': 0}
        H = did[0]
        try:
            I = B.get(self.home_url + H, headers=self.headers)
            I.encoding = 'utf-8'
            root = _doc(I.text)
            urls = []
            for li in (root.xpath('//div[contains(@class,"play")]//ul//li') if root is not None else []):
                a = _first(li, './/a')
                if a is None:
                    continue
                m = re.search(r"'(.*?)'", _attr(a, 'onclick'))
                if not m:
                    continue
                urls.append("%s$%s" % (_text(a), m.group(1)))

            info = _first(root, '//div[contains(@class,"detail")]//div[contains(@class,"info")]')
            dls = info.xpath('.//dl') if info is not None else []

            def dd(i):
                if i < len(dls):
                    x = dls[i].xpath('.//dd')
                    if x:
                        return _text(x[0])
                return ''

            vod = {
                'type_name': dd(2),
                'vod_id': H,
                'vod_name': dd(0),
                'vod_remarks': dd(4),
                'vod_year': dd(5),
                'vod_area': '',
                'vod_actor': dd(1),
                'vod_director': '',
                'vod_content': _text(_first(root, '//div[contains(@class,"juqing")]')),
                'vod_play_from': _text(_first(root, '//*[@id="playlist"]')),
                'vod_play_url': '#'.join(urls),
            }
            result['list'].append(vod)
        except Exception as e:
            print(e)
        return result

    def searchContent(self, key, quick, page='1'):
        result = {'list': [], 'parse': 0, 'jx': 0}
        try:
            headers = self.headers.copy()
            headers['Content-type'] = 'application/x-www-form-urlencoded'
            rsp = B.post(self.home_url + '/search/', headers=headers,
                         data="show=searchkey&keyboard=%s" % parse.quote(key))
            rsp.encoding = 'utf-8'
            root = _doc(rsp.text)
            for li in (root.xpath('//div[contains(@class,"txt")]//ul//li') if root is not None else []):
                a = _first(li, './/a')
                if a is None or not _attr(a, 'href'):
                    continue
                result['list'].append({
                    'vod_id': _attr(a, 'href'),
                    'vod_name': _text(a),
                    'vod_pic': 'https://youke2.picui.cn/s1/2025/12/21/694796745c0c6.png',
                    'vod_remarks': _text(_first(li, './/*[@id="actor"]')),
                    'style': {'type': 'list'},
                })
            result['pagecount'] = 1
            result['page'] = 1
        except Exception as e:
            print(e)
        return result

    def playerContent(self, flag, pid, vipFlags):
        result = {'url': self.error_play_url, 'parse': 0, 'jx': 0, 'header': {}}
        try:
            rsp = B.get(self.home_url + "/u/u1.php?ud=%s" % pid, headers=self.headers)
            if rsp.ok:
                key = bytes([109, 121, 45, 116, 111, 45, 110, 101, 119, 104, 97, 110, 45, 50, 48, 50, 53, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
                data = I.b64decode(rsp.text)
                iv, body = data[:16], data[16:]
                result['url'] = unpad(A.new(key, A.MODE_CBC, iv).decrypt(body), A.block_size).decode().strip()
        except Exception as e:
            print(e)
        return result

    def homeVideoContent(self):
        return {'list': []}

    def isVideoFormat(self, url):
        return url.endswith(('.mp4', '.m3u8', '.flv', '.avi', '.wmv', '.mkv'))

    def manualVideoCheck(self):
        return False

    def localProxy(self, params):
        return None

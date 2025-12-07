import os
import json
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from requests.exceptions import JSONDecodeError

try:
    from fake_useragent import UserAgent
except ImportError:
    UserAgent = None


class TuoiTreCrawler:
    REACTION_MAP = {
        '1': 'like', '3': 'love', '5': 'haha', 
        '7': 'sad', '9': 'wow', '11': 'angry', '13': 'star'
    }

    def __init__(self):
        self.base_url = "https://tuoitre.vn"
        self.comment_api_url = "https://id.tuoitre.vn/api/getlist-comment.api"
        self.article_reaction_api_url = "https://s5.tuoitre.vn/showvote-reaction.htm"
        self.app_key = "lHLShlUMAshjvNkHmBzNqERFZammKUXB1DjEuXKfWAwkunzW6fFbfrhP/IG0Xwp7aPwhwIuucLW1TVC9lzmUoA=="

        self.stats = {
            "total_posts_saved": 0,
            "max_comments_found": 0,
            "posts_with_audio": 0,
            "errors": 0,
            "high_comment_post_found": False
        }

        self.folders = {
            "data": "data",
            "audio": "audio",
            "images": "images"
        }

        for folder in self.folders.values():
            os.makedirs(folder, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self._get_user_agent(),
            'Referer': self.base_url,
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Origin': self.base_url
        })

    def _get_user_agent(self):
        if UserAgent:
            try:
                return UserAgent().random
            except:
                pass
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def get_post_id(self, url):
        try:
            filename = urlparse(url).path.split('/')[-1].replace('.htm', '')
            candidate_id = filename.split('-')[-1]
            return candidate_id if candidate_id.isdigit() and len(candidate_id) > 7 else None
        except:
            return None

    def download_file(self, url, folder, filename):
        if not url:
            return None
        url = url if url.startswith('http') else f"{self.base_url}/{url.lstrip('/')}"
        os.makedirs(folder, exist_ok=True)
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                path = os.path.join(folder, filename)
                with open(path, 'wb') as f:
                    f.write(resp.content)
                print(f"    [Downloaded] {filename}")
                return path
        except Exception as e:
            print(f"    [Download Error] {filename}: {e}")
        return None

    def get_audio_urls(self, soup, post_id):
        audio_urls = []
        audio_tag = soup.find('audio')
        if audio_tag and audio_tag.get('src'):
            audio_urls.append(audio_tag['src'] if audio_tag['src'].startswith('http') else self.base_url + audio_tag['src'])

        try:
            meta_date = soup.find("meta", property="article:published_time")
            if meta_date:
                yyyy, mm, dd = meta_date['content'].split("T")[0].split("-")
                voices = ['nu', 'nam', 'nam-1', 'nu-1']
                formats = ['m4a', 'mp3']
                base_url = "https://tts.mediacdn.vn"
                for voice in voices:
                    for fmt in formats:
                        url = f"{base_url}/{yyyy}/{mm}/{dd}/tuoitre-{voice}-{post_id}.{fmt}"
                        try:
                            if url not in audio_urls and self.session.head(url, timeout=2).status_code == 200:
                                audio_urls.append(url)
                        except:
                            continue
        except:
            pass

        return list(set(audio_urls))

    def fetch_comments(self, post_id, article_id):
        print(f"    [Fetching Comments] Post ID: {post_id}")
        comments = []
        params = {
            'appKey': self.app_key,
            'pageindex': 1,
            'pagesize': 100,
            'objId': article_id,
            'objType': 1,
            'sort': 2
        }
        headers = self.session.headers.copy()
        headers.update({
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f"{self.base_url}/{article_id}.htm"
        })

        try:
            resp = self.session.get(self.comment_api_url, params=params, headers=headers, timeout=5)
            if resp.status_code != 200:
                return comments

            data = resp.json().get('Data')
            if isinstance(data, str):
                data = json.loads(data)
            if not isinstance(data, list):
                return comments

            for c in data:
                reactions = {self.REACTION_MAP[rid]: count for rid, count in c.get('reactions', {}).items() if rid in self.REACTION_MAP and count > 0}
                comment_obj = {
                    "commentId": c.get('id'),
                    "author": c.get('sender_fullname'),
                    "text": c.get('content'),
                    "date": c.get('created_date'),
                    "vote_react_list": reactions,
                    "replies": []
                }
                for r in c.get('child_comments', []):
                    reply_reactions = {self.REACTION_MAP[rid]: count for rid, count in r.get('reactions', {}).items() if rid in self.REACTION_MAP and count > 0}
                    comment_obj['replies'].append({
                        "commentId": r.get('id'),
                        "author": r.get('sender_fullname'),
                        "text": r.get('content'),
                        "vote_react_list": reply_reactions
                    })
                comments.append(comment_obj)
        except Exception as e:
            print(f"    [Comment Fetch Error] {post_id}: {e}")

        print(f"    [Comments Fetched] Count: {len(comments)}")
        return comments

    def fetch_article_reactions(self, article_id):
        reactions = {'general_votes': 0, 'star_ratings': 0, 'other_type_votes': 0}
        params = {'newsid': article_id, 'm': 'viewreact'}
        try:
            resp = self.session.get(self.article_reaction_api_url, params=params, timeout=5)
            data = resp.json().get('Data', [])
            for item in data or []:
                t = item.get('Type')
                reactions['general_votes' if t == 2 else 'star_ratings' if t == 3 else 'other_type_votes'] += item.get('TotalVotes', 0) + item.get('TotalStar', 0)
        except Exception as e:
            print(f"    [Reaction Fetch Error] {article_id}: {e}")
        return reactions

    def parse_post(self, url, category, check_only=False):
        post_id = self.get_post_id(url)
        if not post_id:
            return False

        print(f"[Parsing Post] {post_id} | Category: {category}")
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"    [Error] Failed to fetch URL: {url}")
                return False

            soup = BeautifulSoup(resp.content, 'html.parser')
            article_id = soup.find('input', {'id': 'hdNewsId'}) or soup.find('input', {'id': 'article_id'})
            article_id = article_id['value'] if article_id else post_id

            comments = self.fetch_comments(post_id, article_id)
            article_reactions = self.fetch_article_reactions(article_id)

            if check_only and len(comments) <= 20:
                return False

            content_div = soup.select_one('#main-detail-body, .detail-content, .fck_detail')
            content = ""
            if content_div:
                for garbage in content_div.select('.relate-container, .knc-content, .read-more, script, style, .type_audio'):
                    garbage.decompose()
                content = content_div.get_text(strip=True)

            audio_urls = self.get_audio_urls(soup, post_id)
            audio_paths = []
            if audio_urls:
                self.stats["posts_with_audio"] += 1
                for i, a_url in enumerate(audio_urls):
                    ext = a_url.split('.')[-1].split('?')[0]
                    filename = f"{post_id}_{i}.{ext}"
                    saved = self.download_file(a_url, self.folders['audio'], filename)
                    if saved:
                        audio_paths.append(f"audio/{filename}")

            if content_div:
                img_folder = os.path.join(self.folders['images'], post_id)
                for i, img in enumerate(content_div.find_all('img')):
                    src = img.get('data-src') or img.get('src')
                    if src and src.startswith('http'):
                        self.download_file(src, img_folder, f"img_{i}.jpg")

            title = soup.select_one('h1.article-title, h1.detail-title')
            author = soup.select_one('.author-info .name, .detail-author .name')
            date = soup.select_one('.detail-time, .date-time')

            if len(comments) > 20:
                self.stats["high_comment_post_found"] = True
                print("    ★ High comment post found! ★")
            self.stats["max_comments_found"] = max(self.stats["max_comments_found"], len(comments))
            self.stats["total_posts_saved"] += 1

            post_data = {
                "postId": post_id,
                "articleId": article_id,
                "title": title.get_text(strip=True) if title else "No Title",
                "content": content,
                "author": author.get_text(strip=True) if author else "Unknown",
                "date": date.get_text(strip=True) if date else "Unknown",
                "category": category,
                "article_reactions": article_reactions,
                "audio_podcast": audio_paths,
                "comments": comments
            }

            with open(os.path.join(self.folders['data'], f"{post_id}.json"), 'w', encoding='utf-8') as f:
                json.dump(post_data, f, ensure_ascii=False, indent=4)
            print(f"    [Post Saved] {post_id}")

            return True
        except Exception as e:
            print(f"    [Error Parsing Post] {post_id}: {e}")
            self.stats["errors"] += 1
            return False

    def crawl_category(self, category_url, limit, start_page=1):
        print(f"\n--- Crawling Category: {category_url} ---")
        count = 0
        page = start_page
        while count < limit and page < start_page + 10:
            url = category_url if page == 1 else f"{category_url.replace('.htm', '')}/trang-{page}.htm"
            print(f"[Category Page] {url}")
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.content, 'html.parser')
                links = {self.base_url + a['href'] if not a['href'].startswith('http') else a['href']
                         for a in soup.select('h3 a, .box-category-link-title, .article-title a')
                         if a.get('href') and a['href'].endswith('.htm') and 'video' not in a['href']}

                for link in list(links):
                    if count >= limit:
                        break
                    cat_name = category_url.split('/')[-1].replace('.htm', '')
                    if self.parse_post(link, cat_name):
                        count += 1
                        time.sleep(random.uniform(0.5, 1.0))
            except Exception as e:
                print(f"    [Category Page Error] {url}: {e}")
            page += 1

    def hunt_for_comments(self):
        print("\n--- Hunting for high-comment posts ---")
        if self.stats["high_comment_post_found"]:
            print("[Already Found] Requirement met previously.")
            return

        target_url = "https://tuoitre.vn/ban-doc.htm"
        page = 1
        while page < 10:
            url = target_url if page == 1 else f"https://tuoitre.vn/ban-doc/trang-{page}.htm"
            print(f"[Hunt Page] {url}")
            try:
                resp = self.session.get(url, timeout=10)
                soup = BeautifulSoup(resp.content, 'html.parser')
                links = {self.base_url + a['href'] if not a['href'].startswith('http') else a['href']
                         for a in soup.select('h3 a, .box-category-link-title, .article-title a')
                         if a.get('href') and a['href'].endswith('.htm')}

                for link in list(links):
                    if self.parse_post(link, "ban-doc-hunt", check_only=True):
                        print("[Success] High-comment requirement satisfied.")
                        return
                    time.sleep(0.5)
            except Exception as e:
                print(f"    [Hunt Page Error] {url}: {e}")
            page += 1

    def run(self, config):
        print("=== TUOI TRE CRAWLER STARTED ===")
        for url, limit in config.items():
            self.crawl_category(url, limit)
        self.hunt_for_comments()
        print("\n=== FINAL REPORT ===")
        print(f"Total Posts Saved: {self.stats['total_posts_saved']}")
        print(f"Max Comments Found: {self.stats['max_comments_found']}")
        print(f"Audio Posts Found: {self.stats['posts_with_audio']}")
        print(f"Errors: {self.stats['errors']}")
        print("Data is saved in: ./data, ./audio, ./images")
        print("=====================")


if __name__ == "__main__":
    config = {
        "https://tuoitre.vn/thoi-su.htm": 35,
        "https://tuoitre.vn/the-gioi.htm": 35,
        "https://tuoitre.vn/phap-luat.htm": 35
    }
    TuoiTreCrawler().run(config)

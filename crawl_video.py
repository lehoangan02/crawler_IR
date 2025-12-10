import time
import os
import requests
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
TARGET_LINKS = 1000  
SAVE_FOLDER = "tuoitre_videos_selenium"
if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)
def get_video_links_selenium():
    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    url = "https://tuoitre.vn/video.htm"
    print(f"Opening {url}...")
    driver.get(url)
    collected_links = set()
    scroll_pause_time = 2.0
    while len(collected_links) < TARGET_LINKS:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause_time)
        try:
            view_more_btn = driver.find_element(By.CLASS_NAME, "view-more-seciton") 
            if view_more_btn.is_displayed():
                print("Clicking 'Xem thêm' button...")
                driver.execute_script("arguments[0].click();", view_more_btn)
                time.sleep(2) 
        except:
            pass 
        video_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/']")
        new_count = 0
        for el in video_elements:
            href = el.get_attribute('href')
            if href and "/video/" in href and not href.endswith("video.htm"):
                if href not in collected_links:
                    collected_links.add(href)
                    new_count += 1
        print(f"Collected {len(collected_links)}/{TARGET_LINKS} links... (Found {new_count} new this scroll)")
        if new_count == 0:
            time.sleep(3)
    driver.quit()
    return list(collected_links)
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'}
def download_video(page_url):
    try:
        r = requests.get(page_url, headers=headers, timeout=10)
        mp4_match = re.search(r'https?://[^\s"\']+\.mp4', r.text)
        if not mp4_match:
            print(f" [x] No MP4 found: {page_url}")
            return
        mp4_url = mp4_match.group(0)
        filename = page_url.split("/")[-1].replace(".htm", ".mp4")
        save_path = os.path.join(SAVE_FOLDER, filename)
        if os.path.exists(save_path):
            print(f" [Skip] Already exists: {filename}")
            return
        print(f" [Down] Downloading: {filename}")
        with requests.get(mp4_url, headers=headers, stream=True, timeout=20) as vid_r:
            vid_r.raise_for_status()
            with open(save_path, 'wb') as f:
                for chunk in vid_r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        print(f" [Error] {e}")
if __name__ == "__main__":
    print("--- STEP 1: CRAWLING LINKS WITH SELENIUM ---")
    all_links = get_video_links_selenium()
    print(f"\n--- STEP 2: DOWNLOADING {len(all_links)} VIDEOS ---")
    for i, link in enumerate(all_links):
        print(f"[{i+1}/{len(all_links)}]", end=" ")
        download_video(link)
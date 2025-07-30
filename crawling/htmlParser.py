from bs4 import BeautifulSoup
import traceback
import re
import requests
import lxml.html
import time
import urllib
from urllib.parse import urljoin, urlparse, urlencode
import numpy as np
import sys, json
import tracker

from utils.timeout import timeout

def is_url_on_same_or_sub_domain(url_to_check):
    with open(tracker.config_file_name, 'r') as f_r:
        website_infos = json.load(f_r)
        starting_url = website_infos['homepage']
    if urlparse(url_to_check).hostname == None:
        return False

    starting_domain_parts = urlparse(starting_url).hostname.split('.')
    starting_domain_parts.reverse()
    if starting_domain_parts[-1] == "www":
        starting_domain_parts = starting_domain_parts[:-1]

    url_to_check_domain_parts = urlparse(url_to_check).hostname.split('.')
    url_to_check_domain_parts.reverse()
    if url_to_check_domain_parts[-1] == "www":
        url_to_check_domain_parts = url_to_check_domain_parts[:-1]

    if len(starting_domain_parts) > len(url_to_check_domain_parts):
        return False

    return starting_domain_parts == url_to_check_domain_parts[:len(starting_domain_parts)]

class HTMLParser:
    # The HTMLParser class
    def __init__(self):
      self.html = ''
      self.session = requests.Session()

    @timeout(10)
    def getHTML(self, url):
        new_url = None
        headers = [ {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36"}, 
                    {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:47.0) Gecko/20100101 Firefox/47.3'}        
        ]  
        h = np.random.randint(0,2)
        try:
            if url.startswith("http"):
                p = {"url":url}
                url = "http://localhost:8025/?" + urlencode(p)
            tracker.nb_visited += 1
            r = self.session.get(url, headers=headers[h], allow_redirects = False)
            if r.status_code >=300 and r.status_code < 400:
                while True:
                    if r.status_code < 300 or r.status_code >= 400:
                        break
                    location = r.headers.get('Location')
                    tracker.nb_visited += 1
                    if location:
                        if location.startswith("/"):
                            original_url = url.split("?url=")[1]
                            merged_original_url = urljoin(original_url, location)
                            new_url = merged_original_url
                            if merged_original_url in tracker.all_seen: break
                            tracker.all_seen.add(merged_original_url)
                            p = {"url":merged_original_url}
                            merged_url = "http://localhost:8025/?" + urlencode(p)
                            r = self.session.get(merged_url, headers=headers[h], allow_redirects = False)
                        elif location.startswith("http"):
                            if is_url_on_same_or_sub_domain(location):
                                new_url = location
                                if location in tracker.all_seen: break
                                tracker.all_seen.add(location)
                                p = {"url":location}
                                r = self.session.get("http://localhost:8025/?" + urlencode(p), headers=headers[h], allow_redirects = False)
                            else:
                                break
                        else:
                            break
                    else:
                        break
            html = r.text
        except:
            html = ""    
        self.html = html
        return html, new_url

    def getLang(self, url):
        request = requests.head(url)
        return request.headers

    def getTitle(self, url):
        html = self.html #self.getHTML(url)
        if html == "":
            return ""
        title_pattern = re.compile("<title>(.*?)</title>", re.IGNORECASE)
        # regex is an order of magnitude faster than beautifulsoup when extracting title
        try:
            res = title_pattern.search(html)
            if res:
                return res.group(1).strip()
            else:
                return ""
        except:
            traceback.print_exc()
            return ""

    def getBody(self, url):
        html = self.html #self.getHTML(url)
        if html == "":
            return ""
        try:
            soup = BeautifulSoup(html, "html.parser")
            for script in soup(["script", "style"]):
                script.extract()
            text = soup.get_text()
            text = " ".join(text.split())
            if text == "" or text == " ":
                return self.getTitle(html)
            return text
        except:
            return self.getTitle(html)

    def getMeta(self, url):
        html = self.html #self.getHTML(url)
        """
            Extract title, description, keywords
            Returns:
            --------
            a lower case string that is the concatination of title, desc and keywords.
        """
        try:
            metadata = []
            soup = BeautifulSoup(html, 'lxml')
            title = soup.find('title')
            title_text = title.text if title else ""
            metadata.append(title_text.strip())
                
            metatags = soup.find_all('meta')
            for tag in metatags:
                if 'name' in tag.attrs.keys() and tag.attrs['name'].strip().lower() in ['description', 'keywords']:
                    try:
                        metadata.append(tag.attrs['content'].strip())
                    except:
                        print(tag.attrs.keys())

            res = ' '.join(metadata) 
            if not res:
                print("Empty Metadata")
            return res
        except:
            print("Metadata extraction fails")
            return ""


if __name__== "__main__":
    ## Just an example

    import time
    t1 = time.time()

    parser = HTMLParser()

    url = "https://computer.howstuffworks.com/virus.htm"

    parser.getHTML(url)

    # print(parser.html)

    title = parser.getTitle(url)
    # meta = parser.getMeta(url)
    body = parser.getBody(url)

    print("Title:")
    print(title)
    # print("meta:")
    # print(meta)
    print("body:")
    print(body)

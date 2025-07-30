from bs4 import BeautifulSoup, SoupStrainer
import requests
import re
from urllib.parse import urlparse, urljoin, urlencode
from time import sleep
import pandas as pd
import time 
from .htmlParser import is_url_on_same_or_sub_domain
from utils.timeout import timeout
from utils.utils import from_list_to_dict
import ast
import tracker
import sqlite3, json

df = pd.read_csv('./files/countries_urls.csv')
l_countries = list(df["Alpha-2 code"])
l_countries = [str(country).lower() for country in l_countries]
l_countries.extend(["de"]) 
d_countries = from_list_to_dict(l_countries)
f = open("./files/more_lang.txt", "r")
for line in f:
    lang = line.split(" ")[0]
    d_countries[lang] = 0

del f 
del df
del l_countries
try: del d_countries["en"]
except: pass 
try: del d_countries["us"]
except: pass
try: del d_countries["gb"]
except: pass

class URLextractor:
    # Class for the URLs extractor 
    def __init__(self, l_countries=[]):
        # Pattern for legal characters of a base URL
        self.l_countries = l_countries
        self.pattern = re.compile("[-\.:;\"\'\(\)\*\+\]\[\^%<=>{}$\{!\}@`~\|#&,\/\\\_-]")

    @timeout(8)
    def extractURLS(self, url, url_redirection, html=None):
        '''
            A function that returns the extracted URLs and anchor texts from a given URL.
        
            Parameters:
                url:    String
                html:   requests.get(); default None
        '''

        if url_redirection is not None:
            url = url_redirection

        with open(tracker.config_file_name, 'r') as f_r:
            website_infos = json.load(f_r)
            db_name = website_infos['db_name']
            db_path = website_infos['db_file']
            con = sqlite3.connect("../"+db_path)
            cur = con.cursor()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:47.0) Gecko/20100101 Firefox/47.3'} 
        if url[0:4] != 'http': 
            url = 'http://' + url
        try:
            if html is None or html == "":
                p = {"url":url}
                html = requests.get("http://localhost:8025/?" + urlencode(p), headers=headers)
                html = html.text
            if html == "Either no HTML resource, or no CT in headers." or html == "URL not found in archive":
                return [], []

            soup = BeautifulSoup(html, features="lxml")
            extracted = {}
            extractedURLs = []
            extractedAnchors = []
            domain_name = urlparse(url).netloc # get doimain name
            link_attrs = [
                         ('a', 'href'),
                         ('area', 'href'),
                         ('frame', 'src'),
                         ('iframe', 'src'),
            ]
            for tag, attr in link_attrs:
                for element in soup.find_all(tag):
                    new_url = element.get(attr)
                    if not new_url: continue
                    href = urljoin(url, new_url)
                    #print(href)
                    #parsed_href = urlparse(href)
                    # Remove URL GET parameters, URL fragments, etc.
                    #href = parsed_href.scheme + "://" + parsed_href.netloc + parsed_href.path
                    new_url = href
                    n_url = new_url.lower()
                    # Check for non-English URL 
                    '''
                    eng = True
                    spl = n_url.split("/")
                    for w in spl:
                        if len(w) < 2: continue
                        #if not eng: break
                        try: 
                            d_countries[w]
                            eng = False
                            break
                        except: 
                            spll = w.split(".")
                            for ww in spll:
                                if len(ww) < 2: continue
                                try: 
                                    d_countries[ww]
                                    eng = False
                                    break
                                except: continue
                            #if not eng: break       
                            spll = w.split("-")
                            for ww in spll:
                                if len(ww) < 2: continue
                                try: 
                                    d_countries[ww]
                                    eng = False
                                    break
                                except: continue
                    '''
                    #if not eng: continue
                    if True:
                    #if n_url != "#" and n_url != "" and isinstance(n_url, str) and n_url[-3:] != "pdf" and n_url[-3:] != "zip" and n_url[-3:] != "eps" and n_url[-3:] != "gps" and n_url[-3:] != "mp4" and n_url[-3:] != "mp3" and n_url[-3:] != "ogv":
                        #if new_url[0:4] != 'http':
                        #    continue
                        if not is_url_on_same_or_sub_domain(new_url): continue
                        r = cur.execute(f"SELECT headers FROM {db_name} WHERE url = ?;", (new_url,)).fetchone()
                        if r is not None:
                            headers = ast.literal_eval(r[0])
                            for k, v in headers.items():
                                key = k.decode() if isinstance(k, bytes) else k
                                if key.lower() == "content-type":
                                    raw_val = v[0] if isinstance(v, list) and v else v
                                    content_type = raw_val.decode() if isinstance(raw_val, bytes) else raw_val
                                    break
                            if "html" not in content_type.lower():
                                continue
                    
                        # Append the corresponding anchor text
                        new_url = new_url.split("#")[0]
                        new_anchor = element.string
                        new_anchor = re.sub("([\n\t]|  )", "", str(new_anchor))
                        if new_anchor != 'None':
                            # domain_name = urlparse(new_url).netloc #get doimain name
                            new_url_words_str = re.sub(self.pattern, " ", new_url)
                            new_anchor = new_anchor + " " + new_url_words_str
                            new_anchor = re.sub("   ", " ", new_anchor)
                            new_anchor = re.sub("  ", " ", new_anchor)
                            new_anchor = re.sub("https", "", new_anchor)
                            new_anchor = re.sub("http", "", new_anchor)
                            # new_anchor = re.sub("    ", "  ", new_anchor)
                        else:
                            new_anchor = ""
                        if new_url not in tracker.all_seen:
                            extracted[new_url] = new_anchor
                            tracker.all_seen.add(new_url)
            extractedURLs = list(extracted.keys())
            extractedAnchors = list(extracted.values())
            return extractedURLs, extractedAnchors
        except:
            return ["https://en.wikipedia.org/wiki/Main_Page"], ["main page"]
            
        return extractedURLs, extractedAnchors

    def getDomain(self, url):
        '''
            url:        String

            Returns     String; the domain of the given url
        '''
        if re.search(".i.sport", url): return "i.sport"
        domain_name = urlparse(url).netloc
        domain_name = re.sub("www.", "", domain_name)
        return domain_name

    def setPattern(self, pattern):
        '''
            Setter method for setting the url pattern attribute
        
            Parameters:
                pattern:    String
        '''
        self.pattern = pattern
        return


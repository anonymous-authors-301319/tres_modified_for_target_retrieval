import sqlite3
import re
from urllib.parse import urljoin, urlparse
from lxml import html
from tqdm import tqdm
import json, sys, ast
import numpy as np

mime_types_data_resources = {'application/octet-stream', 'application/pdf', 'text/csv', 'application/csv', 'text/x-csv', 'application/x-csv', 'text/x-comma-separated-values', 'text/comma-separated-values', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/pdf', 'application/x-pdf', 'application/zip', 'application/x-zip-compressed', 'application/zip-compressed', 'application/x-tar', 'application/x-gtar', 'application/x-gzip', 'application/xml', 'application/json', 'text/json', 'application/yaml', 'text/yaml', 'text/x-yaml', 'application/x-yaml', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/vnd.openxmlformats-officedocument.wordprocessingml.template', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'text/plain', 'application/vnd.oasis.opendocument.text', 'application/vnd.ms-excel.sheet.macroenabled.12', 'application/x-7z-compressed', 'application/vnd.oasis.opendocument.presentation', 'application/rdf+xml', 'application/rss+xml', 'application/vnd.ms-excel', 'application/vnd.rar', 'application/x-rar-compressed', 'application/x-gtar'}

def is_url_on_same_or_sub_domain(starting_url, url_to_check):
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

def parse_db_headers(header_str):
    try:
        raw_headers = ast.literal_eval(header_str)
    except Exception as e:
        print(f"[Error parsing headers] {e}")
        return {}

    headers = {}
    for k, v_list in raw_headers.items():
        if isinstance(k, bytes):
            key = k.decode('utf-8', errors='ignore').lower()
        else:
            key = str(k).lower()

        if isinstance(v_list, list) and v_list:
            val = v_list[0]
            if isinstance(val, bytes):
                headers[key] = val.decode('utf-8', errors='ignore')
            else:
                headers[key] = str(val)
        else:
            headers[key] = ''

    return headers

def extract_links(html_content, base_url):
    try:
        tree = html.fromstring(html_content)
    except Exception as e:
        print(f"[HTML Parse Error] {base_url}: {e}")
        return []

    xpath_exprs = [
        '//a/@href',
        '//area/@href',
        '//frame/@src',
        '//iframe/@src'
    ]

    links = set()
    for expr in xpath_exprs:
        for href in tree.xpath(expr):
            href = href.strip()
            if href:
                full_url = urljoin(base_url, href)
                full_url = full_url.split("#")[0]
                links.add(full_url)
    return links

def get_ct_and_length(headers_str, body, content_length_from_db):
    headers = parse_db_headers(headers_str)
    content_type = headers.get("content-type",None)

    if content_type and 'html' in content_type:
        content_length = len(body.encode('utf-8')) if isinstance(body, str) else len(body or "")
    elif content_length_from_db is not None:
        content_length = content_length_from_db
    else:
        content_length = len(body or "")
    
    return content_type, content_length

def process_log(log_path, db_path, db_name, starting_url):
    conn = sqlite3.connect("../../../"+db_path)
    cursor = conn.cursor()

    nb_targets = [0]
    all_seen = set()
    all_targets = set()
    data_volume = []
    data_volume.append((0,0))

    with open(log_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            if "Serving on port " in raw_line: continue
            parts = raw_line.split("|")
            status = int(parts[-1].split("status:")[1])
            url = '|'.join(parts[:-2]).split("URL:")[1]
            print(url, "and", status) 

            if url in all_seen: continue
 
            all_seen.add(url) 
            nb_targets.append(len(all_targets))

            if status >= 400:
                continue

            cursor.execute(f"SELECT headers, body, content_length FROM {db_name} WHERE url = ?;", (url,))
            row = cursor.fetchone()

            headers, body, content_length = row

            if status >= 300:
                data_volume.append((data_volume[-1][0] + content_length, data_volume[-1][1]))
                continue

            ct, cl = get_ct_and_length(headers, body, content_length)

            if ";" in ct: ct = ct.split(";")[0]

            assert(status == 200)

            if "html" not in ct:
                if ct in mime_types_data_resources:
                    all_targets.add(url)
                    nb_targets[-1] = len(all_targets)
                    data_volume.append((data_volume[-1][0], data_volume[-1][1] + content_length))
                else: data_volume.append((data_volume[-1][0] + content_length, data_volume[-1][1]))
                continue
            else:
                child_links = extract_links(body, url)
                data_volume.append((data_volume[-1][0] + content_length, data_volume[-1][1]))
                for child_url in child_links:
                    if not is_url_on_same_or_sub_domain(starting_url, child_url): continue
                    if child_url in all_seen: continue
                    cursor.execute(f"SELECT headers, content_length FROM {db_name} WHERE url = ?;", (child_url,))
                    child_row = cursor.fetchone()
                    if child_row is None: 
                        all_seen.add(child_url)
                        nb_targets.append(len(all_targets)) # 404 pages
                        continue
                    child_headers, child_length = child_row
                    child_ct, child_cl = get_ct_and_length(child_headers, None, child_length)
                    if child_ct is None:
                        all_seen.add(child_url)
                        nb_targets.append(len(all_targets)) #No CT
                        data_volume.append((data_volume[-1][0] + child_length, data_volume[-1][1]))
                        continue
                    if "html" in child_ct: continue
                    all_seen.add(child_url)

                    if ";" in child_ct: child_ct = child_ct.split(";")[0]
                    if child_ct in mime_types_data_resources:
                        all_targets.add(child_url)
                        data_volume.append((data_volume[-1][0], data_volume[-1][1] + child_length))
                    else: data_volume.append((data_volume[-1][0] + child_length, data_volume[-1][1]))
                    nb_targets.append(len(all_targets))
    
    np.save(f"nb_resources_of_interest_{db_name}_tres.npy", nb_targets)
    np.save(f"data_volume_{db_name}_tres.npy", data_volume)

    conn.close()

if __name__=="__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python3 {sys.argv[0]} <log_file> <json_config_file>")
    else:
        log_file = sys.argv[1]
        json_config_file = sys.argv[2]
        with open(json_config_file, 'r') as f_r
            wi = json.load(f_r)
            db_path = wi['db_file']
            db_name = wi['db_name']
            starting_url = wi['homepage']
        process_log(log_file, db_path, db_name, starting_url)

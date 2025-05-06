import os
import re
import requests

def fetch_links(url):
    try:
        response = requests.get(url)
        response.raise_for_status() # Raise an exception for bad status codes
        soup = BeautifulSoup(response.text, 'html.parser')

        # 抓取链接，假设链接都在 <a> 标签内
        links = []
        for a in soup.find_all('a', href=True):
            link = a['href']
            if not link.startswith('https://t.me'):
                links.append(link)
        return links
    
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return []

def test_link(link):
    try:
        response = requests.head(link, allow_redirects=True)
        return response.status_code < 400
    
    except requests.RequestException:
        return False

def update_subscribes(links, file_path):
    existing_links = set()
    try:
        with open(file_path, 'r') as f:
            existing_links = set(line.strip() for line in f)
    
    except FileNotFoundError:
        pass

   new_links = set(links) - existing_links 
   
   valid_links = [link for link in new_links if test_link(link)]

   with open(file_path,'a') as f:
       for link in valid_links:
           f.write(link + '\n')

def main():
     base_url=os.environ.get('BASE_URL','https://t.me/dingyue_center')
     file_path=os.environ.get('FILE_PATH','data/subscribes.txt')

     links=fetch_links(base_url)
     update_subscribes(links,file_path)

if __name__=='__main__':
     main()

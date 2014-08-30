import os
import sqlite3
import sys
import threading
import time
import urllib
import urllib2

from ConfigParser import ConfigParser
from multiprocessing import Process
from Queue import Queue
from urlparse import urlparse

import mechanize

from vk.core import API


PERMISSIONS = 30
VERSION = 5.24
DISPLAY = 'page'
URI = 'https://oauth.vk.com/blank.html'
FILE_DIR = os.path.dirname(os.path.realpath(__file__)) + '/media/'


class TokenFactory(object):

    def get_token_pair(self):
        conn = sqlite3.connect('vk.db')
        c = conn.cursor()

        c.execute('SELECT * FROM tokens')
        data = c.fetchone()
        conn.close()

        return data

    def store_token_pair(self, url):
        conn = sqlite3.connect('vk.db')
        c = conn.cursor()
        data = self._authorize(url)
        c.execute("INSERT INTO tokens(access_token, user_id) VALUES (?, ?)", data)
        conn.commit()
        conn.close()
        
        return data

    def _authorize(self, url):
        data = {}
        count = 0
        br = mechanize.Browser()
        br.open(url)
        # vk login
        br.select_form(nr=0)
        
        email = raw_input('Enter your VK login(email or phone): ')
        password = raw_input('Enter your VK pass: ')

        br.form['email'] = email
        br.form['pass'] = password
        br.submit()
        
        for form in br.forms():
            count = count + 1

        if count > 0:
            self.br.select_form(nr=0)
            self.br.submit()
        
        url = br.response().geturl()
        url_data = urlparse(url)

        if url_data.fragment and url_data.fragment.split('&'):
            for fragment in url_data.fragment.split('&'):
                row = fragment.split('=')
                data[row[0]] = row[1]

        return data['access_token'], data['user_id']


class DownloadThread(threading.Thread):
    output_lock = threading.Lock()

    def __init__(self, queue, dest_folder):
        super(DownloadThread, self).__init__()
        self.queue = queue
        self.dest_folder = dest_folder

    def run(self):
        while True:
            item = self.queue.get()
            try:
                self.download_item(item)
            except Exception as e:
                print(e.message)
            self.queue.task_done()

    def download_item(self, item):
        name = item['title'] + '.mp3'
        u = urllib2.urlopen(item['url'])
        f = open(self.dest_folder + name, 'wb')
        meta = u.info()
        file_size = int(meta.getheaders("Content-Length")[0])
        file_size_dl = 0
        block_sz = 8192

        while True:
            buffer = u.read(block_sz)
            if not buffer:
                break

            file_size_dl += len(buffer)
            f.write(buffer)
            status = r"[%s] Downloading %s %10d  [%3.2f%%]" % \
                (self.ident, name, file_size_dl, file_size_dl * 100. / file_size)
            status = status + chr(8)*(len(status)+1)
            with self.output_lock:
                sys.stdout.write(status)
                sys.stdout.flush()

        f.close()


def setup_db():
    conn = sqlite3.connect('vk.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE tokens(access_token text, user_id text)''')

    conn.close()


def main(numthreads=10):
    t1 = time.time()
    queue = Queue()
    factory = TokenFactory()
    config = ConfigParser()
    config.read('vk_api.conf')

    url = API.get_url(
        app_id=config.get('api', 'id'), app_key=config.get('api', 'key'), 
        permissions=PERMISSIONS, redirect_uri=URI, display=DISPLAY, api_version=VERSION)

    # TODO: check token expiration
    token_pair = factory.get_token_pair()
    if not token_pair:
        token_pair = factory.store_token_pair(url)
    
    api = API(token=token_pair[0],user_id=token_pair[1])
    audio = api.audio
    data = audio.get

    if data:
        for item in data['response']['items']:
            queue.put(item)

        for i in range(numthreads):
            t = DownloadThread(queue, FILE_DIR)
            t.start()

        queue.join()


    t2 = time.time()
    print('Time: {0}'.format(t2-t1))


if __name__ == '__main__':
    if os.path.isfile('vk.db'):
        print('Fetch audio')
        main()
    else:
        print('setup DB')
        setup_db()
#!/usr/bin/python3

from concurrent.futures import thread
import datetime
import json
import os
import re
import signal
import sys
import traceback
import urllib.request
from io import BytesIO
from dotenv import load_dotenv
import requests
from PIL import Image
from threading import Thread

# ENV VARS
load_dotenv()

# CONSTANTS
THREADS = int(os.getenv('THREADS'))
CLEANER = re.compile('<.*?>')
API_VERSION = os.getenv('API_VERSION')
USER_TO_LOG_IN = os.getenv('USER_TO_LOG_IN')
PASSWORD_TO_LOG_IN = os.getenv('PASSWORD_TO_LOG_IN')
SAVE_FOLDER_NAME = os.getenv('SAVE_FOLDER_NAME')
REAL_SAVE_FOLDER_NAME = os.path.join(
    os.path.dirname(__file__), SAVE_FOLDER_NAME)
NUMBER_OF_MEDIAS_PER_CALL = 50  # 50 is the maximum
MAIN_USER_GRAPH_URL = "https://graph.instagram.com/%s/USER_ID/media" % API_VERSION
USERNAME_TO_ID_API = "https://i.instagram.com/api/v1/users/web_profile_info/?username="
USER_AGENT_ANDROID = "Instagram 219.0.0.12.117 Android"
USER_AGENT_ANDROID_HEADERS = {
    'User-Agent': USER_AGENT_ANDROID
}
GRAPH_BASE_QUERY = "https://www.instagram.com/graphql/query/?query_hash=e769aa130647d2354c40ea6a439bfc08&variables={%22id%22:%22USER_ID%22,%22first%22:" + str(
    NUMBER_OF_MEDIAS_PER_CALL) + "}"
GRAPH_BASE_QUERY_CONTINUE = "https://www.instagram.com/graphql/query/?query_hash=e769aa130647d2354c40ea6a439bfc08&variables={%22id%22:%22USER_ID%22,%22first%22:" + str(
    NUMBER_OF_MEDIAS_PER_CALL) + ",%22after%22:%22LAST_IMAGE%22}"

total_medias = 0
downloaded_medias = 0

# CTRL + c fires this function
def call_close(sig, frame):
    print("\n\n[*] Exiting...\n")
    sys.exit(1)


'''
Retrives the full url of the medias in json and fill the array with the following prototype.

PROTOTYPE
    {
        'timestamp' : None,
        'url' : None,
        'is_video' : None,
        'order' : None
    }

    If the post has more than one media, it adds a counter of medias of the post.
'''
def get_medias_urls(json, medias):

    for node in json["data"]['user']['edge_owner_to_timeline_media']['edges']:

        if 'edge_sidecar_to_children' in node['node'].keys():
            order = 0
            for subnode in node['node']['edge_sidecar_to_children']['edges']:
                medias.append({
                    'timestamp': node['node']['taken_at_timestamp'],
                    'url': (subnode['node']['video_url'] if subnode['node']['is_video'] else subnode['node']['display_url']).replace('\\0026', '&'),
                    'is_video': subnode['node']['is_video'],
                    'order': order
                })
                order += 1
        else:
            medias.append({
                'timestamp': node['node']['taken_at_timestamp'],
                'url': (node['node']['video_url'] if node['node']['is_video'] else node['node']['display_url']).replace('\\0026', '&'),
                'is_video': node['node']['is_video'],
                'order': None
            })


'''
Removes HTML tags and return the cleaned data.
'''
def remove_tags(raw_html):
    cleantext = re.sub(CLEANER, '', raw_html)
    return cleantext


'''
Creates folders with the real save folder name and inside it, creates a folder with
the username and inside other two folder for photos and videos
'''
def create_folders(username):
    if not os.path.isdir(REAL_SAVE_FOLDER_NAME):
        os.mkdir(REAL_SAVE_FOLDER_NAME)
    if not os.path.isdir(os.path.join(REAL_SAVE_FOLDER_NAME, username)):
        os.mkdir(os.path.join(REAL_SAVE_FOLDER_NAME, username))
    if not os.path.isdir(os.path.join(REAL_SAVE_FOLDER_NAME, username, 'images')):
        os.mkdir(os.path.join(REAL_SAVE_FOLDER_NAME, username, 'images'))
    if not os.path.isdir(os.path.join(REAL_SAVE_FOLDER_NAME, username, 'videos')):
        os.mkdir(os.path.join(REAL_SAVE_FOLDER_NAME, username, 'videos'))


'''
Saves the medias calling the urls in the medias prototypes.
'''
def save_medias(username, medias):
    global total_medias
    total_medias = len(medias)

    for batch_media in batch(medias, n=THREADS):
        threads = []
        for media in batch_media:
            t = Thread(target=save_media, args=[media, username])
            threads.append(t)

        for x in threads:
            x.start()

        # Wait for all of them to finish
        for x in threads:
            x.join()


def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx:min(ndx + n, l)]


def thread_finished():
    global total_medias
    global downloaded_medias
    downloaded_medias += 1
    print('%d of %d medias downloaded' % (downloaded_medias, total_medias))


def save_media(media, username):
    if media['is_video']:
        try:
            full_path = os.path.join(REAL_SAVE_FOLDER_NAME, username, 'videos', datetime.datetime.utcfromtimestamp(media['timestamp']).strftime(
                '%Y-%m-%d_%H_%M_%S') + (str(media['order']) + '_' if media['order'] is not None else '') + '.mp4')
            urllib.request.urlretrieve(media['url'], full_path)
        except Exception as err:
            print('Video with url %s couldn\'t be downloaded' %
                  media['url'])
    else:
        try:
            response = requests.get(media['url'])
            img = Image.open(BytesIO(response.content))

            full_path = os.path.join(REAL_SAVE_FOLDER_NAME, username, 'images', datetime.datetime.utcfromtimestamp(media['timestamp']).strftime(
                '%Y-%m-%d_%H_%M_%S') + (('_' + str(media['order'])) if media['order'] is not None else '') + '.jpg')
            img.save(full_path, "JPEG")
        except IOError as err:
            print('Image with url %s couldn\'t be downloaded' %
                  media['url'])

    thread_finished()


def login_instagram():
    link = 'https://www.instagram.com/accounts/login/'
    login_url = 'https://www.instagram.com/accounts/login/ajax/'

    time = int(datetime.datetime.now().timestamp())
    s = requests.session()
    response = s.get(link)
    m = re.findall(r"csrf_token\":\"(.*?)\"", response.text)
    csrf = m[0]
    payload = {
        'username': USER_TO_LOG_IN,
        'enc_password': f'#PWD_INSTAGRAM_BROWSER:0:{time}:{PASSWORD_TO_LOG_IN}',
        'queryParams': {},
        'optIntoOneTap': 'false'
    }

    login_header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.120 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/accounts/login/",
        "x-csrftoken": csrf
    }

    login_response = s.post(login_url, data=payload, headers=login_header)
    json_data = json.loads(login_response.text)

    if json_data["authenticated"]:
        print("login successful")
    else:
        print('Login failed')
        sys.exit(2)
    return s


'''
MAIN FUNCTION
'''
if __name__ == '__main__':

    signal.signal(signal.SIGINT, call_close)  # Initializes CTRL+C handler

    # If no username is passed as argument, it ask for it
    if len(sys.argv) == 2:
        username = sys.argv[1]
    else:
        username = input('No username set. Please enter an username: ')

    # Session init of requests
    session = requests.session()

    # Getting the username ID of instagram
    try:
        profile_info_text = session.get(
            USERNAME_TO_ID_API + username, headers=USER_AGENT_ANDROID_HEADERS).text
        profile_info = json.loads(profile_info_text)
        user_id = profile_info['data']['user']['id']
    except:
        print("Username does not exist")
        sys.exit(1)

    try:
        session_instagram = login_instagram()
        req = session_instagram.get(
            GRAPH_BASE_QUERY.replace('USER_ID', user_id))
        json_data = json.loads(remove_tags(req.text))
        medias = list()
        continue_search = json_data["data"]['user']['edge_owner_to_timeline_media']['page_info']['has_next_page']
        last_image = ''
        # Save the last image identifier given in the request if more pages are available
        if (continue_search):
            last_image = json_data["data"]['user']['edge_owner_to_timeline_media']['page_info']['end_cursor']
        get_medias_urls(json_data, medias)

        # Iteration on folowing pages if necessary
        while continue_search:
            req = session_instagram.get(GRAPH_BASE_QUERY_CONTINUE.replace(
                'USER_ID', user_id).replace('LAST_IMAGE', last_image))
            json_data = json.loads(remove_tags(req.text))
            continue_search = json_data["data"]['user']['edge_owner_to_timeline_media']['page_info']['has_next_page']
            last_image = ''
            if (continue_search):
                last_image = json_data["data"]['user']['edge_owner_to_timeline_media']['page_info']['end_cursor']
            get_medias_urls(json_data, medias)
        print('Number of medias: %d' % len(medias))
    except Exception as e:
        print("An error ocurred while trying to get user posts: %s" % str(e))
        exit(1)

    try:
        create_folders(username)
        save_medias(username, medias)
    except Exception as e:
        print("An error ocurred while saving images and videos: %s" % str(e))
        print(traceback.format_exc())
        exit(1)

    print("Done")

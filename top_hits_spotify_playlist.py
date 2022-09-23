import base64
from crypt import methods
import requests
import os
from datetime import date
from flask import Flask, redirect, request, render_template

client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')
redirect_uri = 'http://127.0.0.1:5000/callback'

default_playlist_name = f'My Artist\'s Top Hits {date.today().year }'

# TODO Replace Global vars with session storage
user_defined_playlist_name = ''
callbackVals = {}

app = Flask(__name__)


@app.route("/")
def home():
    return render_template('index.html',
                           isCallback=False,
                           authUrl=get_auth_url)

@app.route("/generate-playlist", methods=['POST'])
def generate_playlist():
    if request.form['playlistName']:
        global user_defined_playlist_name 
        user_defined_playlist_name = request.form['playlistName']

    return redirect(get_auth_url())


@app.route("/callback")
def callback():
    auth_code = request.args.get('code')

    if auth_code:
        access_token = get_access_token(auth_code)

        if access_token:
            playlist_name = user_defined_playlist_name if user_defined_playlist_name else default_playlist_name

            user_id = get_user_id(access_token)
            user_artists = get_artists(access_token)
            if len(user_artists):
                artists_top_hits = get_top_hits(access_token, user_artists)
                top_hits_playlist_id = create_top_hits_playlist(access_token, user_id, playlist_name)
                if len(artists_top_hits) and top_hits_playlist_id:
                    errors = add_top_hits_to_playlist(access_token, top_hits_playlist_id, artists_top_hits)

            # user_artists = []
            # artists_top_hits = []
            # errors = []

    callbackVals['isCallback'] = True
    callbackVals['userAllowedAuth'] = True if auth_code else False
    callbackVals['validAccessToken'] = True if access_token else False
    callbackVals['playlistName'] = playlist_name
    callbackVals['numOfArtists'] = len(user_artists)
    callbackVals['numOfSongsToAdd'] = len(artists_top_hits)
    callbackVals['errorsEncountered'] = errors

    return redirect('generated-playlist')

@app.route("/generated-playlist")
def generated_playlist():
    return render_template('index.html',
                           isCallback=True if callbackVals['isCallback'] else False,
                           userAllowedAuth=True if callbackVals['userAllowedAuth'] else False,
                           validAccessToken=True if callbackVals['validAccessToken'] else False,
                           playlistName=callbackVals['playlistName'] if callbackVals['playlistName'] else '',
                           numOfArtists=callbackVals['numOfArtists'] if callbackVals['numOfArtists'] else 0,
                           numOfSongsToAdd=callbackVals['numOfSongsToAdd'] if callbackVals['numOfSongsToAdd'] else 0,
                           errorsEncountered=callbackVals['errorsEncountered'] if callbackVals['errorsEncountered'] else [])

def get_auth_url():
    auth_url = 'https://accounts.spotify.com/authorize'
    auth_url += '?response_type=code'
    auth_url += f'&client_id={client_id}'
    auth_url += '&scope=user-read-private user-read-email playlist-read-private playlist-modify-private user-follow-read'
    auth_url += f'&redirect_uri={redirect_uri}'

    return auth_url


def get_access_token(auth_code):
    access_token = None
    access_token_url = 'https://accounts.spotify.com/api/token'
    auth_message = f'{client_id}:{client_secret}'

    headers = {
        'Authorization': f'Basic {encode_string(auth_message)}', 'Content-Type': 'application/x-www-form-urlencoded'}
    data = {'code': auth_code, 'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'}

    response = requests.post(url=access_token_url, headers=headers, data=data)

    if response.status_code == 200:
        access_token = response.json()['access_token']

    return access_token


def encode_string(message):
    message_bytes = message.encode('ascii')
    base64_bytes = base64.b64encode(message_bytes)

    return base64_bytes.decode('ascii')


def get_user_id(access_token):
    user_id = ''
    create_playlist_url = f'https://api.spotify.com/v1/me'

    headers = {'Authorization': f'Bearer {access_token}',
               'Content-Type': 'application/json'}

    response = requests.get(url=create_playlist_url, headers=headers)

    if response.status_code != 200:
        error_message = response.json()['error']['message']
        user_id = f' error message: {error_message}'
    else:
        user_id = response.json()['id']

    return user_id


def create_top_hits_playlist(access_token, user_id, playlist_name):
    top_hits_playlist_id = None
    create_playlist_url = f'https://api.spotify.com/v1/users/{user_id}/playlists'

    headers = {'Authorization': f'Bearer {access_token}',
               'Content-Type': 'application/json'}
    json = {'name': playlist_name, 'public': 'false'}

    response = requests.post(url=create_playlist_url, headers=headers, json=json)

    if response.status_code == 201:
        top_hits_playlist_id = response.json()['id']

    return top_hits_playlist_id


def get_artists(access_token):
    artists = []
    after = ''
    query_limit = 50
    get_artists_url = f'https://api.spotify.com/v1/me/following?type=artist&limit={query_limit}'
    headers = {'Authorization': f'Bearer {access_token}',
               'Content-Type': 'application/json'}

    response = requests.get(url=get_artists_url, headers=headers)

    if response.status_code == 200:
        items = response.json()['artists']['items']

        total = response.json()['artists']['total']
        after = response.json()['artists']['cursors']['after']

        while total > 0:
            next_artists_url = f'https://api.spotify.com/v1/me/following?type=artist&limit={query_limit}&after={after}'

            response = requests.get(url=next_artists_url, headers=headers)

            if response.status_code == 200:
                items += response.json()['artists']['items']

                total = response.json()['artists']['total']
                after = response.json()['artists']['cursors']['after']

        for item in items:
            artists.append(item['id'])

    return artists


def get_top_hits(access_token, artist_ids):
    top_hits = []
    market = 'US'
    headers = {'Authorization': f'Bearer {access_token}',
               'Content-Type': 'application/json'}

    for artist_id in artist_ids:
        get_top_hits_url = f'https://api.spotify.com/v1/artists/{artist_id}/top-tracks?market={market}'

        response = requests.get(url=get_top_hits_url, headers=headers)

        tracks = response.json()['tracks']

        for track in tracks:
            top_hits.append(track['uri'])

    return top_hits


def add_top_hits_to_playlist(access_token, playlist_id, top_hits):
    add_items_to_playlist_url = f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks'
    headers = {'Authorization': f'Bearer {access_token}',
               'Content-Type': 'application/json'}

    uris = []
    errors = []

    for top_hit in top_hits:
        uris.append(top_hit)

        if len(uris) > 99:
            json = {'uris': uris}
            response = requests.post(
                url=add_items_to_playlist_url, headers=headers, json=json)

            if response.status_code != 201:
                errors.append(response.json()['error']['message'])
                # TODO: add some retry mechanism for failures?

            uris = []

    return errors

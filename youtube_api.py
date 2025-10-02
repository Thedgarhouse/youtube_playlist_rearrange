# youtube_api.py

import googleapiclient.discovery
import googleapiclient.errors
from itertools import islice

# Constants for YouTube
BATCH_SIZE = 50
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

def build_youtube_client(credentials):
    """Initializes and returns the authenticated YouTube API client."""
    return googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials
    )

def fetch_all_playlist_track_ids(youtube_client, playlist_ids):
    """
    Fetches all unique video IDs from a list of source playlists.
    
    Returns: set of video IDs.
    """
    all_track_ids = []
    
    for playlist_id in playlist_ids:
        print(f'-> Collecting IDs from playlist: {playlist_id}')
        next_token = None
        while True:
            request = youtube_client.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                pageToken=next_token
            )
            response = request.execute()
            
            for item in response.get('items', []):
                all_track_ids.append(item['contentDetails']['videoId'])
            
            next_token = response.get('nextPageToken')
            if not next_token:
                break
    
    unique_ids = set(all_track_ids)
    print(f'Total unique video IDs collected: {len(unique_ids)}')
    return unique_ids

def fetch_video_details_in_batches(youtube_client, video_ids: list):
    """
    Fetches snippet (title/description) for a list of video IDs in batches.
    
    Returns: list of dicts [{video_id, title, description}, ...]
    """
    id_iterator = iter(video_ids)
    complete_videos_info = []
    
    print(f'Starting to fetch details for {len(video_ids)} tracks in batches of {BATCH_SIZE}...')
    
    while True:
        batch_of_ids = list(islice(id_iterator, BATCH_SIZE))
        
        if not batch_of_ids:
            break
            
        tracks_id_string = ','.join(batch_of_ids)
        request = youtube_client.videos().list(
            part="snippet",
            id=tracks_id_string
        )
        response = request.execute()
        
        videos_info = [
            {
                "video_id": item["id"],
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"]
            }
            for item in response.get('items', [])
        ]
        complete_videos_info.extend(videos_info)
        
    print(f"Finished fetching details. Total video records collected: {len(complete_videos_info)}")
    return complete_videos_info

def create_playlist_on_youtube(youtube_client, title, description=""):
    """Creates a new playlist and returns the playlist ID."""
    request = youtube_client.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "privacyStatus": "private"  # Defaulting to private for new lists
            }
        }
    )
    response = request.execute()
    return response.get('id')

def add_video_to_playlist(youtube_client, playlist_id, video_id):
    """Adds a single video item to a playlist."""
    request = youtube_client.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
    )
    request.execute()
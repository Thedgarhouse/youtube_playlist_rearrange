# app_main.py

import os
import json
import sys
from itertools import islice

# Import functionality from other modules
import google_auth_oauthlib.flow
import googleapiclient.errors
from google import genai
from youtube_api import (
    build_youtube_client, 
    fetch_all_playlist_track_ids, 
    fetch_video_details_in_batches,
    create_playlist_on_youtube,
    add_video_to_playlist
)
from gemini_logic import get_gemini_client, generate_playlists_from_videos

# --- Configuration and Constants ---

# IMPORTANT: You must define these constants at the top of your main file
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
STATE_FILE = 'playlists_to_process.json'
VIDEO_INFO_CACHE_FILE = 'video_info_cache.json'
NUM_PLAYLISTS_TO_GENERATE = 5

def load_config():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            return config
    except FileNotFoundError:
        print("FATAL: config.json file not found. Please create it.")
        sys.exit(1)

# --- State Management Functions ---

def save_state(data, file_path):
    """Saves the current processing state."""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)
        
def load_state(file_path):
    """Loads the processing state."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def save_and_exit(data):
    """Saves the current state and exits the program gracefully."""
    save_state(data, STATE_FILE)
    print("\n" + "="*50)
    print("QUOTA LIMIT REACHED. CURRENT PROGRESS SAVED.")
    print(f"Please resume tomorrow after quota reset. State saved to {STATE_FILE}")
    print("="*50)
    sys.exit(0) # Exit code 0 for success/planned interruption

# --- Main Logic Functions ---

def run_analysis_phase(youtube_client, gemini_client, source_playlist_ids):
    """
    Phase 1: Gathers video data, calls Gemini, enriches data, and saves to state file.
    Runs once when the state file does not exist.
    """
    print("\n--- PHASE 1: STARTING ANALYSIS AND DATA GATHERING ---")
    
    # 1. Gather all unique video IDs (Low Quota Cost)
    unique_video_ids = fetch_all_playlist_track_ids(youtube_client, source_playlist_ids)
    video_ids_list = list(unique_video_ids) # Preserve consistent order for indices
    
    # 2. Fetch details for batch processing (Low Quota Cost)
    complete_videos_info = fetch_video_details_in_batches(youtube_client, video_ids_list)

    # Cache the lookup table needed for Phase 2, as fetching this is low cost but essential.
    save_state(complete_videos_info, VIDEO_INFO_CACHE_FILE)
    
    # 3. Call Gemini for Playlist Generation
    playlist_data = generate_playlists_from_videos(
        gemini_client, complete_videos_info, NUM_PLAYLISTS_TO_GENERATE
    )
    
    if not playlist_data:
        print("FATAL: Gemini analysis failed. Exiting.")
        sys.exit(1)

    # 4. Enrich Data with Status and Save Initial State
    for playlist in playlist_data['playlists']:
        playlist['status'] = 'PENDING'
        playlist['tracks'] = [
            {"index": idx, "status": "PENDING"} for idx in playlist.pop('video_indices')
        ]
        playlist['youtube_playlist_id'] = None # Placeholder for ID after creation
        
    save_state(playlist_data, STATE_FILE)
    print(f"\n--- ANALYSIS COMPLETE. INITIAL STATE SAVED to {STATE_FILE} ---")
    
    return complete_videos_info # Return lookup table to immediately proceed to Phase 2

def run_execution_phase(youtube_client):
    """
    Phase 2: Loads state, iterates through pending tasks, and executes YouTube Write Ops.
    Runs repeatedly until all tasks are complete or quota is hit.
    """
    print("\n--- PHASE 2: RESUMING PLAYLIST CREATION AND TRACK INSERTION ---")
    playlist_data = load_state(STATE_FILE)
    complete_videos_info = load_state(VIDEO_INFO_CACHE_FILE)
    
    if not playlist_data or not complete_videos_info:
        print("FATAL: Cannot resume. State or video info cache file is missing.")
        sys.exit(1)

    # Create mapping for lookup: Index -> Video ID
    index_to_video_id = {i: v.get('video_id') for i, v in enumerate(complete_videos_info)}
    
    for playlist in playlist_data.get('playlists', []):
        if playlist.get('status') == 'COMPLETED':
            continue
            
        # 1. Create Playlist on YouTube if ID is missing (50 units)
        if not playlist.get('youtube_playlist_id'):
            print(f"\n[CREATE] Creating playlist: {playlist['playlist_title']}")
            try:
                playlist_id = create_playlist_on_youtube(youtube_client, playlist['playlist_title'], playlist.get('playlist_description', ''))
                playlist['youtube_playlist_id'] = playlist_id
            except googleapiclient.errors.HttpError as e:
                if e.resp.status == 403 and 'quota' in str(e).lower():
                    print(f"\n[QUOTA EXCEEDED] while creating playlist.")
                    save_and_exit(playlist_data) 
                # Handle other creation errors
                print(f"Error creating playlist {playlist['playlist_title']}: {e}")
                continue
                
        # 2. Add Tracks to Playlist
        youtube_playlist_id = playlist['youtube_playlist_id']
        pending_tracks = [t for t in playlist['tracks'] if t['status'] == 'PENDING']
        
        print(f"Processing {len(pending_tracks)} tracks for: {playlist['playlist_title']}")

        for track in pending_tracks:
            track_id = index_to_video_id.get(track['index'])
            
            if not track_id:
                track['status'] = 'SKIPPED'; continue # Skip bad index
            
            try:
                # Attempt insert (50 units cost)
                add_video_to_playlist(youtube_client, youtube_playlist_id, track_id)
                track['status'] = 'COMPLETED'
                print(f"  -> Added track {track_id} | Tracks remaining today: ~{10000 / 50 - len([t for p in playlist_data.get('playlists', []) for t in p.get('tracks', []) if t['status'] == 'COMPLETED'])}")
                
            except googleapiclient.errors.HttpError as e:
                if e.resp.status == 403 and 'quota' in str(e).lower():
                    print(f"\n[QUOTA EXCEEDED] while adding item.")
                    save_and_exit(playlist_data)
                else:
                    print(f"  -> Error adding track {track_id}: {e}")
                    track['status'] = 'FAILED'
        
        # Check if playlist is fully completed (no more PENDING or FAILED)
        if all(t['status'] != 'PENDING' for t in playlist['tracks']):
            playlist['status'] = 'COMPLETED'
            print(f"\nPlaylist '{playlist['playlist_title']}' is fully complete.")

    print("\n--- EXECUTION COMPLETE: All tasks processed for the day. ---")
    save_state(playlist_data, STATE_FILE) # Save final state if no quota hit

def main():
    config = load_config()

    # 1. Authorization and Client Setup
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    client_secrets_file = config["YOUTUBE_SECRETS_FILE"] 

    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, SCOPES)
    credentials = flow.run_local_server()
    youtube_client = build_youtube_client(credentials)
    gemini_client = get_gemini_client()

    source_playlist_ids = config["SOURCE_PLAYLIST_IDS"]

    # 2. Determine Execution Path
    if not os.path.exists(STATE_FILE):
        # Run Phase 1: Analysis, Generation, and Initial Save
        run_analysis_phase(youtube_client, gemini_client, source_playlist_ids)
    
    # Run Phase 2: Execution (either immediately after Phase 1, or on resume)
    run_execution_phase(youtube_client)


if __name__ == "__main__":
    main()
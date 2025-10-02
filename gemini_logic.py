# gemini_logic.py

from google import genai
from google.genai import types
from google.genai.errors import APIError
import json

def get_gemini_client():
    """Initializes and returns the Gemini API client."""
    try:
        # Client automatically looks for GEMINI_API_KEY environment variable
        client = genai.Client()
        return client
    except Exception as e:
        print(f"Error initializing Gemini client: {e}")
        print("FATAL: Ensure GEMINI_API_KEY environment variable is set.")
        exit()

def get_api_schemas():
    """Defines and returns the structured output schemas."""
    
    playlist_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "playlist_title": types.Schema(
                type=types.Type.STRING,
                description="A compelling title for the suggested playlist."
            ),
            "playlist_description": types.Schema(
                type=types.Type.STRING,
                description="A catchy description for what to expect from the contents of this playlist."
            ),
            "video_indices": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.INTEGER),
                description="A list of 0-based integer indices corresponding to the positions of the videos in the original input list that belong to this playlist."
            ),
        },
        required=["playlist_title", "playlist_description", "video_indices"]
    )

    root_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "playlists": types.Schema(
                type=types.Type.ARRAY,
                items=playlist_schema,
                description="A list of suggested playlists based on the provided video data, strictly limited to the number requested in the prompt."
            )
        },
        required=["playlists"]
    )
    
    return root_schema

def generate_playlists_from_videos(client, video_data_list: list, num_playlists: int):
    """
    Sends all video data to Gemini and requests a structured list of playlists.
    
    Returns: Parsed JSON data (dict) or None on failure.
    """
    root_schema = get_api_schemas()
    video_data_json = json.dumps(video_data_list)
    
    system_instruction = (
        "You are an expert in creating diverse and accurate music playlists. Your task is to process the provided JSON data about YouTube videos and suggest diverse playlists. You can repeat indices in playlists if they fit several themes, but ensure that every index is present in at least one playlist. The videos are music tracks. Your response MUST be a single JSON object that strictly adheres to the provided schema."
    )
    
    user_prompt = f"""
        Analyze the following list of video data and **generate exactly {num_playlists} highly relevant playlists**.

        The input list is a zero-based array. The output must reference videos by their 0-based index.

        For each playlist:
        1.  Create a descriptive title.
        2.  Provide a description for the contents of the suggested playlist.
        3.  Populate the 'video_indices' list with the 0-based integer index of every video from the input that fits the playlist theme. You MUST use indices, not video IDs.

        Here is the video data in JSON format:

        ```json
        {video_data_json}
        ```
    """
    
    content = [user_prompt]
    print(f"--- Sending {len(video_data_list)} video records to Gemini for analysis (Requesting {num_playlists} playlists) ---")

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=root_schema,
                # Setting max output tokens to the safe limit
                max_output_tokens=65000 
            )
        )
        if response.text:
            return json.loads(response.text)
        else:
            print(f"[Gemini Error]: Empty response received. Check response metadata for Finish Reason.")
            return None
            
    except APIError as e:
        print(f"\n[Gemini API Error]: {e}")
        return None
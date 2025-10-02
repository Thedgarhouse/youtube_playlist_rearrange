# YouTube Playlist Creator (Gemini & YouTube Data API)

This Python application uses the **YouTube Data API** to analyze songs from existing playlists and the **Gemini API** to generate new, categorized playlists from the entire collection. It is designed for multi-day use to respect the strict YouTube Quota limits on playlist insertion.

---

## ⚙️ Setup and Installation

### 1. Prerequisites

You must have Python 3.8+ installed.

1.  **Clone the repository:**
    ```bash
    git clone [YOUR_REPO_URL]
    cd [YOUR_REPO_NAME]
    ```

2.  **Create and activate a virtual environment (`venv` is in .gitignore):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On macOS/Linux
    venv\Scripts\activate     # On Windows
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### 2. API Key and Credentials

1.  **Gemini API Key:**
    * Get a key from Google AI Studio.
    * Set it as an environment variable (the Python client reads this automatically):
        ```bash
        export GEMINI_API_KEY="YOUR_GEMINI_KEY"
        ```

2.  **YouTube OAuth 2.0 Credentials:**
    * Create an OAuth 2.0 Client ID in your Google Cloud Console.
    * Download the JSON file and save it locally.

### 3. Configuration

Create a file named **`config.json`** in the project root to hold your sensitive local paths and data IDs (this file is excluded by `.gitignore`).

```json
// config.json
{
  "YOUTUBE_SECRETS_FILE": "/path/to/your/secrets/client_secret_xyz.json",
  "SOURCE_PLAYLIST_IDS": [
    "PLrplYS-YkuOC1Lna08Zfzb-GylUQxWWdO",
    "PLrplYS-YkuOD2akeI5JMZBtEQ6Jta3Rus"
    // ... all other source playlist IDs
  ]
}
```

---

## ▶️ How to Run the Application

The app manages its process across multiple days using a persistent state file (`playlists_to_process.json`).

### First Run (Analysis & Generation - Phase 1)

The script detects the absence of the state file, runs the low-cost data collection and Gemini analysis, and saves the generated playlist structure.

1.  **Execution:**
    ```bash
    python app_main.py
    ```
2.  **Output:** The script will save the generated playlists structure to `playlists_to_process.json` and immediately proceed to Phase 2.

### Subsequent Runs (Creation & Resumption - Phase 2)

The script loads the saved state and resumes the expensive YouTube playlist item insertions where it last stopped.

1.  **Execution:**
    ```bash
    python app_main.py
    ```
2.  **Quota Limit:** The script will continue adding videos until the daily YouTube quota is exhausted. Upon hitting the quota error, it **saves the current progress** and exits gracefully.
3.  **Resume:** Run `python app_main.py` again the following day after the quota resets.
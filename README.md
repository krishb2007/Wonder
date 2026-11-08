# Hackathon

## Run Wonder

Wonder's reliable summary narration uses the voices installed on macOS. Start its local server from the project root:

```sh
python3 serve.py
```

Then open http://127.0.0.1:8765/copy-paste/curio.html. Keep the server running while using the app. Press Ctrl+C in the terminal to stop it.

The Listen control generates and plays a WAV narration of the article summary using the selected Mac voice. The Auto option uses the default available voice. On unsupported systems or if the local service is unavailable, the app can fall back to browser speech synthesis.

Ten openly licensed recordings are available as voice-sample previews from a story's Read view. They are static sample clips, not voices that can narrate article text. Credits, source links, and licenses are listed in `copy-paste/voice-previews/CREDITS.md`.

The Discover feed uses scroll snapping and viewport-aware article sizing so each full preview moves into focus as you scroll.

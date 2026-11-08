#!/usr/bin/env python3
"""Serve Wonder locally with macOS-generated narration audio."""

import json
import logging
import pathlib
import re
import subprocess
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


ROOT = pathlib.Path(__file__).resolve().parent
VOICE_LINE = re.compile(r"^\s*(.*?)\s+([a-z]{2}_[A-Z]{2})\s+#")
VOICE_PRIORITY = ("Samantha", "Daniel", "Karen", "Moira", "Tessa", "Alex", "Rishi")
NON_SPEECH_VOICE = re.compile(
    r"bad news|bahh|bells|boing|bubbles|cellos|good news|grandma|grandpa|"
    r"jester|junior|organ|ralph|superstar|trinoids|whisper|wobble|zarvox",
    re.IGNORECASE,
)
MAX_TEXT_LENGTH = 6000


def available_voices():
    if sys.platform != "darwin":
        raise RuntimeError("The local narration server currently requires macOS.")
    result = subprocess.run(
        ["/usr/bin/say", "-v", "?"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    voices = {}
    for line in result.stdout.splitlines():
        match = VOICE_LINE.match(line)
        if not match:
            continue
        display_name, locale = match.groups()
        if not locale.startswith("en_") or NON_SPEECH_VOICE.search(display_name):
            continue
        voice_name = display_name.split(" (", 1)[0]
        voices.setdefault(
            voice_name,
            {"id": voice_name, "name": display_name, "lang": locale.replace("_", "-")},
        )
    priority = {name: index for index, name in enumerate(VOICE_PRIORITY)}
    return sorted(
        voices.values(),
        key=lambda voice: (
            priority.get(voice["id"], len(priority)),
            voice["name"].casefold(),
        ),
    )[:10]


def send_json(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class WonderHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if urlsplit(self.path).path == "/api/voices":
            try:
                voices = available_voices()
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                logging.exception("Could not load local narration voices")
                send_json(self, 503, {"error": str(error)})
                return
            send_json(self, 200, {"voices": voices})
            return
        super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/narration":
            send_json(self, 404, {"error": "Not found."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            send_json(self, 400, {"error": "Invalid content length."})
            return
        if content_length <= 0 or content_length > 16_384:
            send_json(self, 413, {"error": "Narration request is empty or too large."})
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            send_json(self, 400, {"error": "Invalid JSON request."})
            return
        if not isinstance(payload, dict):
            send_json(self, 400, {"error": "Narration request must be an object."})
            return
        text = payload.get("text")
        voice_id = payload.get("voice")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            send_json(self, 400, {"error": "Narration text must contain 1–6000 characters."})
            return
        if not isinstance(voice_id, str):
            send_json(self, 400, {"error": "Choose an available narration voice."})
            return

        try:
            voices = {voice["id"]: voice for voice in available_voices()}
            voice = voices.get(voice_id)
            if voice is None:
                send_json(self, 400, {"error": "That narration voice is not available on this Mac."})
                return
            with tempfile.TemporaryDirectory(prefix="wonder-narration-") as directory:
                source = pathlib.Path(directory) / "narration.aiff"
                output = pathlib.Path(directory) / "narration.wav"
                subprocess.run(
                    ["/usr/bin/say", "-v", voice_id, "-o", str(source), text],
                    check=True,
                    capture_output=True,
                    timeout=45,
                )
                subprocess.run(
                    ["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16", str(source), str(output)],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                audio = output.read_bytes()
        except subprocess.TimeoutExpired:
            send_json(self, 504, {"error": "Local narration took too long. Try a shorter summary."})
            return
        except subprocess.CalledProcessError as error:
            logging.error("Local narration command failed: %s", error.stderr.decode("utf-8", "replace"))
            send_json(self, 502, {"error": "macOS could not generate the narration audio."})
            return
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            logging.exception("Could not generate local narration")
            send_json(self, 503, {"error": str(error)})
            return

        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(audio)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    address = ("127.0.0.1", 8765)
    server = ThreadingHTTPServer(address, WonderHandler)
    print(f"Wonder is running at http://{address[0]}:{address[1]}/copy-paste/curio.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Wonder.")
    finally:
        server.server_close()

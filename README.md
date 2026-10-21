# Harness settings

A local web page for saving your API keys. Keys are stored in your computer's
keychain (macOS Keychain, Windows Credential Manager, or Linux Secret Service).

## Run it

1. Install Python 3.10 or newer from python.org.
2. Open a terminal in this folder and run:

   ```
   pip install -r requirements.txt
   python server.py
   ```

3. Your browser opens to http://127.0.0.1:8765. Paste a key, click Save key.

Keys are never shown again after saving. To change one, paste a new key.
The page only listens on your own computer, not your network.

import asyncio
import re
import os
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession # Für GitHub Actions, um die Session als String zu laden
import aiohttp

# Konfiguration
API_ID = os.environ.get('TELEGRAM_API_ID')
API_HASH = os.environ.get('TELEGRAM_API_HASH')
# Session-String: Erzeugen Sie diesen lokal und speichern Sie ihn als GitHub Secret (z.B. TELEGRAM_SESSION_STRING)
# Führen Sie dazu lokal ein Skript aus, das `client.session.save()` aufruft, nachdem Sie sich angemeldet haben,
# oder drucken Sie `client.session.save()` (was den String zurückgibt) und kopieren Sie ihn.
# Beispiel für lokale Generierung des Session Strings:
# async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
#     print("Bitte geben Sie Ihre Telefonnummer ein oder bestätigen Sie mit dem QR-Code...")
#     await client.start()
#     print("Erfolgreich angemeldet.")
#     print("Ihr Session-String ist:", client.session.save())
#     await client.disconnect()
# WICHTIG: Wenn Sie den Session-String nicht verwenden, verwendet Telethon eine lokale Datei session_name.session
# Dies funktioniert in GitHub Actions nur, wenn Sie die Session-Datei zwischen Läufen cachen.
# Der Session-String ist oft die bessere Methode für kurzlebige Umgebungen wie Actions.
SESSION_STRING = os.environ.get('TELEGRAM_SESSION_STRING')
SESSION_NAME = "default_session" # Wird verwendet, wenn kein SESSION_STRING vorhanden ist

CHANNEL_USERNAME = 'dingyue_center'
OUTPUT_FILE = 'data/t.txt'
URL_REGEX = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+'

# Logging-Konfiguration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def fetch_all_urls(client):
    """Holt alle Nachrichten aus dem Kanal und extrahiert URLs."""
    urls = set()
    try:
        entity = await client.get_entity(CHANNEL_USERNAME)
        logger.info(f"Beginne mit dem Abrufen von Nachrichten aus {CHANNEL_USERNAME}...")
        # Das Abrufen aller Nachrichten (limit=None) kann bei großen Kanälen sehr lange dauern.
        # Für Tests oder regelmäßige Läufe sollten Sie dies ggf. begrenzen (z.B. die letzten X Nachrichten).
        # z.B. messages = await client.get_messages(entity, limit=1000)
        async for message in client.iter_messages(entity, limit=None): # limit=None für alle Nachrichten
            if message.text:
                found_urls = re.findall(URL_REGEX, message.text)
                for url in found_urls:
                    # Einfache Normalisierung: füge http hinzu, wenn es fehlt und mit www. beginnt
                    if url.startswith("www."):
                        url = "http://" + url
                    urls.add(url.strip('.').strip(',')) # Entferne übliche Satzzeichen am Ende
        logger.info(f"{len(urls)} einzigartige URLs aus Nachrichten extrahiert.")
    except Exception as e:
        logger.error(f"Fehler beim Abrufen von Nachrichten oder Extrahieren von URLs: {e}")
    return list(urls)

async def check_url_validity(session, url):
    """Prüft, ob eine URL erreichbar ist (Status < 400)."""
    try:
        # Ein Timeout ist wichtig, um nicht ewig zu warten
        async with session.head(url, timeout=10, allow_redirects=True) as response:
            is_valid = response.status < 400
            if is_valid:
                logger.debug(f"URL {url} ist gültig (Status: {response.status}).")
            else:
                logger.debug(f"URL {url} ist ungültig (Status: {response.status}).")
            return url, is_valid
    except aiohttp.ClientError as e: # Behandelt Verbindungsfehler, SSL-Fehler etc.
        logger.debug(f"Client-Fehler beim Überprüfen der URL {url}: {type(e).__name__}")
        return url, False
    except asyncio.TimeoutError:
        logger.debug(f"Timeout beim Überprüfen der URL {url}.")
        return url, False
    except Exception as e:
        logger.warning(f"Unerwarteter Fehler beim Überprüfen der URL {url}: {e}")
        return url, False

async def main():
    """Hauptfunktion zum Ausführen des Skripts."""
    if not API_ID or not API_HASH:
        logger.error("TELEGRAM_API_ID und TELEGRAM_API_HASH müssen als Umgebungsvariablen gesetzt sein.")
        return

    if SESSION_STRING:
        client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
    else:
        # Verwendet eine lokale Session-Datei. In GitHub Actions muss diese gecacht werden
        # oder der SESSION_STRING-Ansatz wird empfohlen.
        logger.info(f"Verwende lokale Session-Datei: {SESSION_NAME}.session")
        client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

    try:
        logger.info("Verbinde mit Telegram...")
        await client.connect()
        if not await client.is_user_authorized() and not SESSION_STRING: # Bei SESSION_STRING wird keine erneute Auth benötigt
            logger.warning("Nicht autorisiert. Lokale Ausführung? Bitte authentifizieren.")
            # In einer GitHub Action würde dies fehlschlagen, wenn keine gültige Session vorhanden ist.
            # Hier könnte man versuchen, sich anzumelden, aber das ist für Actions nicht ideal.
            # await client.start() # Dies würde eine interaktive Anmeldung erfordern
            logger.error("Autorisierung fehlgeschlagen. Stellen Sie eine gültige Session-Datei oder einen Session-String bereit.")
            return

        logger.info("Erfolgreich mit Telegram verbunden.")

        all_urls = await fetch_all_urls(client)
        if not all_urls:
            logger.info("Keine URLs gefunden.")
            return

        logger.info(f"Beginne mit der Validierung von {len(all_urls)} URLs...")
        valid_urls = []
        # Connector mit Limit, um nicht zu viele gleichzeitige Verbindungen zu öffnen
        conn = aiohttp.TCPConnector(limit=20) # Limit für gleichzeitige Anfragen
        async with aiohttp.ClientSession(connector=conn) as http_session:
            tasks = [check_url_validity(http_session, url) for url in all_urls]
            results = await asyncio.gather(*tasks) # Führt alle Checks parallel aus

            for url, is_valid in results:
                if is_valid:
                    valid_urls.append(url)
        
        logger.info(f"{len(valid_urls)} gültige URLs gefunden.")

        # Erstelle das data-Verzeichnis, falls es nicht existiert
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            for url in sorted(valid_urls): # Sortiert für konsistente Ausgabe
                f.write(url + '\n')
        logger.info(f"Gültige URLs wurden in {OUTPUT_FILE} gespeichert.")

    except Exception as e:
        logger.error(f"Ein Fehler ist im Hauptprozess aufgetreten: {e}", exc_info=True)
    finally:
        if client.is_connected():
            logger.info("Schließe die Telegram-Verbindung.")
            await client.disconnect()
        logger.info("Skript beendet.")

if __name__ == '__main__':
    # In Python 3.7+ kann asyncio.run() verwendet werden
    # Für ältere Versionen: loop = asyncio.get_event_loop(); loop.run_until_complete(main())
    asyncio.run(main())

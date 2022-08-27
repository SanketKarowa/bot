from os import getenv

TG_TOKEN = getenv("TG-KEY")
API_ID = getenv("API-ID")
API_HASH = getenv("API-HASH")
AUTHORIZED_IDS = [-1001722038446, 1072139158, 227723943]
NGROK_URL = ["http://127.0.0.1:4040/api/tunnels"]
MQTT_HOST = getenv("MQTT_HOST")
MQTT_PORT = int(getenv("MQTT_PORT"))

import subprocess
import time
from math import ceil, floor, log
import pyrogram.errors
import requests
from pyrogram import Client, filters, enums
from pyrogram.errors import PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from pyrogram.errors.exceptions import MessageIdInvalid
from config import API_ID, API_HASH, TG_TOKEN, AUTHORIZED_IDS, NGROK_URL, MQTT_HOST, MQTT_PORT
from logging2 import Logger
import psutil
import paho.mqtt.client as mqtt

app = Client("home_ant_bot", api_id=API_ID, api_hash=API_HASH, bot_token=TG_TOKEN)
mqttc = mqtt.Client()
logger = Logger(__name__)
system_info_filter = filters.create(lambda _, __, query: query.data.startswith("sys_info"))
ngrok_info_filter = filters.create(lambda _, __, query: query.data.startswith("ng_info"))
sol_info_filter = filters.create(lambda _, __, query: query.data.startswith("sol_info"))
menu_filter = filters.create(lambda _, __, query: query.data.startswith("menu"))
MENU_BTN = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", "menu")]])
BATT_TOPIC = "/esp8266/batt"
BATT2_TOPIC = "/esp8266/batt2"
BATT3_TOPIC = "/esp8266/batt3"
RELAY1_TOPIC = "/status/r1"
RELAY2_TOPIC = "/status/r2"
RELAY3_TOPIC = "/status/r3"
MAINS_TOPIC = "/esp8266/main"
MAINS_ON_RESP = "MAINS ON"
MAINS_OFF_RESP = "MAINS OFF"
RELAY1_ON_RESP = "11"
RELAY1_OFF_RESP = "10"
RELAY2_ON_RESP = "21"
RELAY2_OFF_RESP = "20"
RELAY3_ON_RESP = "31"
RELAY3_OFF_RESP = "30"
MSG_ID = None
CHAT_ID = None
CALLBACK_QUERY_ID = None
MQTT_DATA = {}
MQTT_ON_MSG_DELAY = 2
STARTUP_MSG_DELAY = 10

def convert_size(size_bytes) -> str:
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(floor(log(size_bytes, 1024)))
    p = pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


def send_startup_msg() -> None:
    time.sleep(STARTUP_MSG_DELAY)
    logger.info("sending startup msg")
    try:
        app.send_message(AUTHORIZED_IDS[0], "🤖 <b>Bot Started</b>", parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.error(f"Failed to send startup msg: {str(e)}")


def send_menu(message, chat) -> None:
    buttons = [[InlineKeyboardButton("⛰️ Ngrok", "ng_info")], [InlineKeyboardButton("🖥️ System Info", "sys_info")],
               [InlineKeyboardButton("☀️ Solar Status", "sol_info")]]
    try:
        app.edit_message_text(chat, message, text="Home-Ant", reply_markup=InlineKeyboardMarkup(buttons))
    except (MessageIdInvalid, pyrogram.errors.MessageAuthorRequired):
        app.send_message(chat, text="Home-Ant", reply_markup=InlineKeyboardMarkup(buttons))
    except PeerIdInvalid:
        logger.error(f"error sending menu PeerIdInvalid: {chat}")


@app.on_callback_query(filters=menu_filter)
def menu(client: Client, callback_query: CallbackQuery) -> None:
    if mqttc.is_connected():
        logger.info(f"disconnecting MQTT server: {MQTT_HOST}:{MQTT_PORT}")
        mqttc.disconnect()
        mqttc.loop_stop()
    send_menu(callback_query.message.id, callback_query.from_user.id)


@app.on_message(filters=filters.command("start"))
def start_command(client: Client, message: Message) -> None:
    """Start the bot."""
    try:
        uid = message.from_user.id
        logger.info(f"start command sent by: {message.from_user.first_name}")
    except AttributeError:
        uid = message.chat.id
        logger.info(f"start command sent by: {uid}")
    if uid in AUTHORIZED_IDS:
        send_menu(message.id, uid)
    else:
        app.send_message(uid, "You are not authorized to use this bot")


@app.on_callback_query(filters=system_info_filter)
def sys_info(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"sys info command sent by: {callback_query.from_user.first_name}")
    try:
        temp = psutil.sensors_temperatures()
        cpu_temp = ""
        if len(temp) != 0:
            if "coretemp" in temp:
                key = "coretemp"
            elif "cpu_thermal" in temp:
                key = "cpu_thermal"
            else:
                key = None
            if key:
                for t in temp[key]:
                    cpu_temp += f"{t.current}°C  "
        else:
            cpu_temp += "NA"

        txt = f"**============SYSTEM============**\n" \
              f"**CPU Usage:** {psutil.cpu_percent(interval=None)}%\n" \
              f"**CPU Freq:** {ceil(psutil.cpu_freq(percpu=False).current)} MHz\n" \
              f"**CPU Cores:** {psutil.cpu_count(logical=True)}\n" \
              f"**CPU Temp:** {cpu_temp}\n" \
              f"**Free Memory:** {convert_size(psutil.virtual_memory().available)} of " \
              f"{convert_size(psutil.virtual_memory().total)}\n" \
              f"**Used Memory:** {convert_size(psutil.virtual_memory().used)} ({psutil.virtual_memory().percent}%)\n" \
              f"**Disks usage:** {convert_size(psutil.disk_usage('/').used)} of " \
              f"{convert_size(psutil.disk_usage('/').total)} ({psutil.disk_usage('/').percent}%)\n" \
              f"**Uptime:** {subprocess.check_output('uptime --pretty', shell=True).decode()}"
    except (AttributeError, KeyError, subprocess.SubprocessError, subprocess.CalledProcessError) as e:
        txt = f"‼️ Failed to get system info: {str(e)}"
    app.edit_message_text(callback_query.from_user.id,
                          callback_query.message.id,
                          txt,
                          parse_mode=enums.ParseMode.MARKDOWN,
                          reply_markup=MENU_BTN)


@app.on_callback_query(filters=ngrok_info_filter)
def ngrok_info_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"ng_info cmd sent by: {callback_query.from_user.first_name}")
    msg = ""
    status_count = 0
    logger.info("fetching ngrok info")
    for url in NGROK_URL:
        try:
            response = requests.get(url, headers={'Content-Type': 'application/json'})
        except (requests.ConnectionError, requests.HTTPError):
            logger.error(f'failed to connect: {url}')
        else:
            if response.ok:
                status_count += 1
                tunnels = response.json()["tunnels"]
                for tunnel in tunnels:
                    msg += f'🚀 <b>Name:</b> <code>{tunnel["name"]}</code>\n'
                    msg += f'⚡ <b>URL:</b> {tunnel["public_url"]}\n\n'
            response.close()
    if status_count == 0:
        app.answer_callback_query(callback_query.id, '‼️ Failed to get api response', True)
    else:
        app.edit_message_text(callback_query.from_user.id, callback_query.message.id, msg, parse_mode=enums.ParseMode.HTML, reply_markup=MENU_BTN)


def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected with result code: {str(rc)}")
    try:
        app.answer_callback_query(CALLBACK_QUERY_ID, f"Connected to {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe([(BATT_TOPIC, 0), (BATT2_TOPIC, 0), (BATT3_TOPIC, 0), (MAINS_TOPIC, 0),
                          (RELAY1_TOPIC, 0), (RELAY2_TOPIC, 0), (RELAY3_TOPIC, 0)])
    except Exception as err:
        msg = f"Error in on_connect: {str(err)}"
        logger.error(msg)


def on_message(client, userdata, msg):
    time.sleep(MQTT_ON_MSG_DELAY)
    global MQTT_DATA
    global MSG_ID
    MQTT_DATA[msg.topic] = msg.payload.decode()
    text = ""
    try:
        for topic in MQTT_DATA:
            resp = MQTT_DATA.get(topic)
            if topic == MAINS_TOPIC:
                text += f"⚡ <b>{topic}</b>: "
                if resp == MAINS_ON_RESP:
                    text += "🟢\n\n"
                if resp == MAINS_OFF_RESP:
                    text += "🔴\n\n"
            elif topic == RELAY1_TOPIC:
                text += f"⚙ <b>{topic}</b>: "
                if resp == RELAY1_ON_RESP:
                    text += "🟢\n\n"
                if resp == RELAY1_OFF_RESP:
                    text += "🔴\n\n"
            elif topic == RELAY2_TOPIC:
                text += f"⚙ <b>{topic}</b>: "
                if resp == RELAY2_ON_RESP:
                    text += "🟢\n\n"
                if resp == RELAY2_OFF_RESP:
                    text += "🔴\n\n"
            elif topic == RELAY3_TOPIC:
                text += f"⚙ <b>{topic}</b>: "
                if resp == RELAY3_ON_RESP:
                    text += "🟢\n\n"
                if resp == RELAY3_OFF_RESP:
                    text += "🔴\n\n"
            elif topic == BATT_TOPIC:
                text += f"🔋 <b>{topic}</b>: <code>{resp}</code>\n\n"
            elif topic == BATT2_TOPIC:
                text += f"🔋 <b>{topic}</b>: <code>{resp}</code>\n\n"
            elif topic == BATT3_TOPIC:
                text += f"🔋 <b>{topic}</b>: <code>{resp}</code>\n\n"
            else:
                text += f"<code>{resp}</code>\n\n"
            logger.info(f"{topic}: {resp}")
        app.edit_message_text(CHAT_ID, MSG_ID, text, parse_mode=enums.ParseMode.HTML, reply_markup=MENU_BTN)
    except pyrogram.errors.BadRequest:
        pass
    except Exception as e:
        logger.error(f"error sending topic payload info: {str(e)}")


mqttc.on_connect = on_connect
mqttc.on_message = on_message


@app.on_callback_query(filters=sol_info_filter)
def sol_info_callback(client: Client, callback_query: CallbackQuery) -> None:
    global MSG_ID
    global CHAT_ID
    global CALLBACK_QUERY_ID
    MSG_ID = callback_query.message.id
    CHAT_ID = callback_query.from_user.id
    CALLBACK_QUERY_ID = callback_query.id
    try:
        if not mqttc.is_connected():
            logger.info(f"connecting to MQTT server: {MQTT_HOST}:{MQTT_PORT}")
            mqttc.connect(host=MQTT_HOST, port=MQTT_PORT)
            mqttc.loop_start()
    except Exception as err:
        msg = f"error while connecting to MQTT server: {str(err)}"
        app.answer_callback_query(CALLBACK_QUERY_ID, msg, True)
        logger.error(msg)

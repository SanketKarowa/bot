import subprocess
import time
from math import ceil, floor, log
import requests
from pyrogram import Client, filters, enums
from pyrogram.errors import PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from pyrogram.errors.exceptions import MessageIdInvalid
from requests import HTTPError
from config import API_ID, API_HASH, TG_TOKEN, AUTHORIZED_IDS, NGROK_URL
from logging2 import Logger
import psutil

app = Client("home_ant_bot", api_id=API_ID, api_hash=API_HASH, bot_token=TG_TOKEN)
logger = Logger(__name__)
system_info_filter = filters.create(lambda _, __, query: query.data.startswith("sys_info"))
ngrok_info_filter = filters.create(lambda _, __, query: query.data.startswith("ng_info"))


def convert_size(size_bytes) -> str:
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(floor(log(size_bytes, 1024)))
    p = pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


def send_startup_msg() -> None:
    time.sleep(5)
    logger.info("sending startup msg")
    for user_id in AUTHORIZED_IDS:
        try:
            app.send_message(user_id, "🤖 <b>Bot Started</b>", parse_mode=enums.ParseMode.HTML)
        except PeerIdInvalid:
            logger.error(f"Failed to send msg to {user_id}")


def send_menu(message, chat) -> None:
    buttons = [[InlineKeyboardButton("⛰️ Ngrok", "ng_info")], [InlineKeyboardButton("🖥️ System Info", "sys_info")],
               [InlineKeyboardButton("☀️ Solar Status", "sol_info")]]
    try:
        app.edit_message_text(chat, message, text="Home-Ant", reply_markup=InlineKeyboardMarkup(buttons))
    except MessageIdInvalid:
        app.send_message(chat, text="Home-Ant", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_message(filters=filters.command("start"))
def start_command(client: Client, message: Message) -> None:
    """Start the bot."""
    logger.info(f"start command sent by: {message.from_user.first_name}")
    if message.from_user.id in AUTHORIZED_IDS:
        send_menu(message.id, message.chat.id)
    else:
        app.send_message(message.chat.id, "You are not authorized to use this bot")


@app.on_callback_query(filters=system_info_filter)
def sys_info(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"sys info command sent by: {callback_query.from_user.first_name}")
    button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", "menu")]])
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
                          reply_markup=button)


@app.on_callback_query(filters=ngrok_info_filter)
def ngrok_info_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"ng_info cmd sent by: {callback_query.from_user.first_name}")
    button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", "menu")]])
    msg = ""
    status_count = 0
    logger.info("fetching ngrok info")
    for url in NGROK_URL:
        try:
            response = requests.get(url, headers={'Content-Type': 'application/json'})
        except (ConnectionError, HTTPError):
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
        msg = '‼️ <b>Failed to get api response</b>'
    app.edit_message_text(callback_query.from_user.id,
                          callback_query.message.id,
                          msg,
                          parse_mode=enums.ParseMode.HTML,
                          reply_markup=button)



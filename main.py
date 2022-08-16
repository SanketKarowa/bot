from bot import app, send_startup_msg
import threading

if __name__ == '__main__':
    threading.Thread(target=send_startup_msg).start()
    app.run()

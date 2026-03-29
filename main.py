# main.py (Enhanced Version - Anti Gangguan Koneksi)

import telebot
import time
import requests
import sys
import logging
import random
from datetime import datetime
from typing import Optional

# Import spesifik untuk menangani error API Telegram
from telebot.apihelper import ApiTelegramException, ApiException

from config import API_TOKEN
from core.database import create_tables, populate_default_config, init_default_admin
from core.scheduler import init_scheduler

# Import semua fungsi pendaftaran handler
from handlers.admin_handlers import register_admin_handlers
from handlers.user_handlers import register_user_handlers, register_help_handler
from handlers.swap_handler import register_swap_handlers


class BotManager:
    """Class untuk mengelola lifecycle bot dengan lebih baik"""
    
    def __init__(self):
        self.bot: Optional[telebot.TeleBot] = None
        self.scheduler = None
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_successful_poll = None
        
    def setup_logging(self):
        """Konfigurasi logging ke file + console dengan rotasi"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
            handlers=[
                logging.FileHandler("log_bot.txt", encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
    def check_api_connection(self) -> bool:
        """Cek koneksi awal ke Telegram API"""
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                r = requests.get(
                    f"https://api.telegram.org/bot{API_TOKEN}/getMe",
                    timeout=10
                )
                r.raise_for_status()
                data = r.json()
                
                if data.get("ok"):
                    bot_info = data['result']
                    logging.info(f"✓ Koneksi API Telegram OK - Bot: @{bot_info.get('username')}")
                    return True
                else:
                    logging.error(f"✗ Respon API tidak OK: {data}")
                    
            except requests.exceptions.Timeout:
                logging.warning(f"Timeout saat cek koneksi (attempt {attempt}/{max_retries})")
            except Exception as e:
                logging.error(f"Error cek koneksi (attempt {attempt}/{max_retries}): {e}")
            
            if attempt < max_retries:
                time.sleep(5 * attempt)
        
        logging.error("Gagal terhubung ke Telegram API setelah beberapa percobaan")
        return False
    
    def initialize_bot(self):
        """Inisialisasi bot dan semua komponennya"""
        try:
            logging.info("Menginisialisasi Bot Jadwal Pro...")
            
            # Setup database
            logging.info("Mengecek struktur database...")
            create_tables()
            populate_default_config()
            init_default_admin()
            logging.info("✓ Database siap")
            
            # Cek koneksi API
            if not self.check_api_connection():
                return False
            
            # Inisialisasi Bot dengan konfigurasi optimal
            self.bot = telebot.TeleBot(
                API_TOKEN,
                threaded=True,
                num_threads=2
            )
            
            # Daftarkan semua handler
            register_admin_handlers(self.bot)
            register_user_handlers(self.bot)
            register_swap_handlers(self.bot)
            register_help_handler(self.bot)
            logging.info("✓ Handlers terdaftar")
            
            # Inisialisasi scheduler
            self.scheduler = init_scheduler(self.bot)
            logging.info("✓ Scheduler aktif")
            
            self.last_successful_poll = datetime.now()
            logging.info("=" * 50)
            logging.info("🤖 Bot siap menerima perintah!")
            logging.info("=" * 50)
            
            return True
            
        except Exception as e:
            logging.error(f"Error saat inisialisasi bot: {e}", exc_info=True)
            return False
    
    def cleanup(self):
        """Cleanup resources sebelum restart/shutdown"""
        try:
            if self.scheduler:
                logging.info("Menghentikan scheduler...")
                self.scheduler.shutdown(wait=False)
            if self.bot:
                logging.info("Menutup koneksi bot...")
                self.bot.stop_polling()
        except Exception as e:
            logging.error(f"Error saat cleanup: {e}")
    
    def calculate_backoff_delay(self, base_delay: int = 10) -> int:
        """Hitung delay dengan exponential backoff + jitter"""
        exp_backoff = min(base_delay * (2 ** self.consecutive_errors), 300)
        jitter = random.uniform(0, 0.3 * exp_backoff)
        return int(exp_backoff + jitter)
    
    def reset_error_counter(self):
        """Reset counter error setelah polling sukses"""
        if self.consecutive_errors > 0:
            logging.info(f"✓ Koneksi pulih setelah {self.consecutive_errors} error berturut-turut")
            self.consecutive_errors = 0
        self.last_successful_poll = datetime.now()
    
    def handle_polling_error(self, error: Exception) -> int:
        """Handle berbagai jenis error dan return delay untuk retry"""
        self.consecutive_errors += 1
        
        # Cek apakah sudah terlalu banyak error berturut-turut
        if self.consecutive_errors >= self.max_consecutive_errors:
            logging.critical(
                f"⚠️  Terlalu banyak error berturut-turut ({self.consecutive_errors}). "
                "Reinisialisasi bot..."
            )
            self.cleanup()
            time.sleep(30)
            
            if self.initialize_bot():
                self.consecutive_errors = 0
                return 5
            else:
                logging.critical("Gagal reinisialisasi bot. Bot akan berhenti.")
                sys.exit(1)
        
        # Handle specific errors
        if isinstance(error, ApiTelegramException):
            if hasattr(error, "error_code"):
                code = error.error_code
                
                if code == 502:
                    logging.error("502 Bad Gateway - Server Telegram bermasalah sementara")
                    return self.calculate_backoff_delay(15)
                
                elif code == 503:
                    logging.error("503 Service Unavailable - Layanan Telegram sedang down")
                    return self.calculate_backoff_delay(20)
                
                elif code == 429:
                    retry_after = getattr(error, "retry_after", 60)
                    logging.warning(f"429 Rate Limited - Retry setelah {retry_after} detik")
                    return retry_after + random.randint(5, 10)
                
                elif code == 409:
                    logging.error("409 Conflict - Bot mungkin berjalan di tempat lain!")
                    return 60
                
                else:
                    logging.error(f"Telegram API Error (kode {code}): {error}")
                    return self.calculate_backoff_delay(10)
            else:
                logging.error(f"Telegram API Error tanpa kode: {error}")
                return self.calculate_backoff_delay(10)
        
        elif isinstance(error, requests.exceptions.ConnectionError):
            logging.error("Connection Error - Tidak bisa terhubung ke server")
            return self.calculate_backoff_delay(15)
        
        elif isinstance(error, requests.exceptions.Timeout):
            logging.error("Timeout Error - Request terlalu lama")
            return self.calculate_backoff_delay(10)
        
        elif isinstance(error, requests.exceptions.ReadTimeout):
            logging.error("Read Timeout - Koneksi terputus saat membaca data")
            return self.calculate_backoff_delay(10)
        
        else:
            logging.error(f"Unexpected Error: {type(error).__name__}", exc_info=True)
            return self.calculate_backoff_delay(15)
    
    def run(self):
        """Main loop dengan error handling yang robust"""
        if not self.initialize_bot():
            logging.critical("Gagal menginisialisasi bot. Program berhenti.")
            sys.exit(1)
        
        polling_timeout = 30  # Timeout lebih pendek untuk responsif
        
        while True:
            try:
                # Polling dengan timeout yang wajar
                self.bot.polling(
                    non_stop=True,
                    timeout=polling_timeout,
                    long_polling_timeout=polling_timeout
                )
                
            except KeyboardInterrupt:
                logging.info("\n" + "=" * 50)
                logging.info("🛑 Bot dihentikan oleh user (Ctrl+C)")
                logging.info("=" * 50)
                self.cleanup()
                break
            
            except Exception as e:
                delay = self.handle_polling_error(e)
                
                logging.info(f"⏳ Mencoba ulang dalam {delay} detik... ({self.consecutive_errors}/{self.max_consecutive_errors} error)")
                time.sleep(delay)
                
                # Setelah error, coba polling lagi
                continue
            
            else:
                # Polling berhenti tanpa error (normal termination)
                self.reset_error_counter()
        
        logging.info("✓ Bot telah berhenti dengan baik")
        sys.exit(0)


def run_web_server():
    """Run Flask web server in background thread"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    from web.app import create_app
    app = create_app()
    
    # Disable Flask's default logging to avoid duplicate logs
    import logging as flask_logging
    flask_log = flask_logging.getLogger('werkzeug')
    flask_log.setLevel(flask_logging.WARNING)
    
    logging.info("🌐 Web Dashboard running at http://localhost:5050")
    
    # Use threaded=False to avoid signal handling issues
    from werkzeug.serving import make_server
    server = make_server('0.0.0.0', 5050, app, threaded=True)
    server.serve_forever()


def main():
    """Entry point aplikasi"""
    import signal
    from threading import Thread
    
    bot_manager = BotManager()
    bot_manager.setup_logging()
    
    # Signal handler for graceful shutdown
    def signal_handler(signum, frame):
        logging.info("\n" + "=" * 50)
        logging.info("🛑 Menerima signal interrupt (Ctrl+C)")
        logging.info("=" * 50)
        bot_manager.cleanup()
        logging.info("✓ Bot telah berhenti dengan baik")
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start web server in background thread
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logging.info("🚀 Web Dashboard thread started")
    
    # Tangkap semua uncaught exceptions
    try:
        bot_manager.run()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logging.critical(f"FATAL ERROR: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
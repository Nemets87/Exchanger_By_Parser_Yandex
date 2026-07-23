r"""
Универсальный обменник валют с живыми курсами (парсинг Яндекс.Конвертера).
Поддерживает Firefox (локально) и Chrome/Firefox (CI).
Логирование, анти-оверлей, адаптивные локаторы, обработка капчи.
Запуск:
  python exchanger.py                        # интерактивный обменник (Firefox)
  python exchanger.py --fetch-rates          # получить курсы, сохранить в rates.json
  python exchanger.py --fetch-rates --headless --browser chrome   # для CI (если Chrome)
"""

import os
import sqlite3
import time
import random
import sys
import json
import logging
from datetime import date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException, TimeoutException

# -----------------------------------------------------------------------------
# ЛОГГЕР
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# КОНФИГУРАЦИЯ
# -----------------------------------------------------------------------------
DB_NAME = 'exchanger.db'
GECKODRIVER_PATH = r"C:\WebDriver\geckodriver.exe"

# =============================================================================
# 1. БАЗА ДАННЫХ
# =============================================================================
class Database:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        with sqlite3.connect(self.db_name) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users_balance (
                    UserID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Balance_RUB REAL NOT NULL,
                    Balance_USD REAL NOT NULL,
                    Balance_EUR REAL NOT NULL
                );
            """)
            cur.execute("SELECT COUNT(*) FROM users_balance")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "INSERT INTO users_balance (Balance_RUB, Balance_USD, Balance_EUR) VALUES (?, ?, ?)",
                    (100000.0, 1000.0, 1000.0)
                )
        logger.info("База данных готова.")

    def get_balances(self, user_id=1):
        with sqlite3.connect(self.db_name) as conn:
            cur = conn.cursor()
            cur.execute("SELECT Balance_RUB, Balance_USD, Balance_EUR FROM users_balance WHERE UserID = ?", (user_id,))
            row = cur.fetchone()
            if row:
                return {'RUB': row[0], 'USD': row[1], 'EUR': row[2]}
            return None

    def update_balance(self, user_id, currency, amount):
        with sqlite3.connect(self.db_name) as conn:
            cur = conn.cursor()
            cur.execute(f"UPDATE users_balance SET Balance_{currency} = Balance_{currency} + ? WHERE UserID = ?", (amount, user_id))

# =============================================================================
# 2. ПАРСЕР КУРСОВ (Firefox + Chrome, универсальные локаторы)
# =============================================================================
class ExchangeRateFetcher:
    URL = "https://yandex.ru/search/?text=%D0%BA%D1%83%D1%80%D1%81+usd+%D0%BA+%D1%80%D1%83%D0%B1%D0%BB%D1%8E&lr=39&clid=2261451&win=620"
    GECKODRIVER_PATH = r"C:\WebDriver\geckodriver.exe"

    SWITCHER_LOCATORS = [
        "//button[starts-with(@aria-label, 'Валюта:')]",
        "//button[contains(@class,'Select2-Button')]",
        "//button[.//span[contains(text(),'USD') or contains(text(),'EUR')]]",
        "//article//button[contains(.,'USD') or contains(.,'EUR')]",
        "//button[contains(@aria-label,'Валюта')]",
        "//article//button[.//img[contains(@alt,'USD') or contains(@alt,'EUR')]]",
    ]
    OPTION_LOCATORS = {
        'USD': [
            "//*[contains(@class,'Select2-Option') and contains(.,'USD')]",
            "//*[@role='option' and contains(.,'USD')]",
            "//div[contains(@class,'ConverterSelect')]//*[contains(text(),'USD')]",
            "//li[contains(.,'USD')]",
            "//*[contains(text(),'Доллар')]",
        ],
        'EUR': [
            "//*[contains(@class,'Select2-Option') and contains(.,'EUR')]",
            "//*[@role='option' and contains(.,'EUR')]",
            "//div[contains(@class,'ConverterSelect')]//*[contains(text(),'EUR')]",
            "//li[contains(.,'EUR')]",
            "//*[contains(text(),'Евро')]",
        ]
    }
    INPUT_LOCATORS = [
        "//article[.//button[starts-with(@aria-label, 'Валюта:')]]//input[@type='text']",
        "//article//input[@type='text' and contains(@value, ',')]",
        "//input[@type='text' and contains(@value, ',')]",
        "//button[starts-with(@aria-label, 'Валюта:')]/following::input[@type='text'][1]",
        "//button[starts-with(@aria-label, 'Валюта:')]/ancestor::div[1]//input[@type='text']",
        "//input[contains(@value, ',')]",
        "//span[contains(text(),'RUB')]/following::input[@type='text']",
        "//input[@type='text' and string-length(@value) > 0]",
    ]
    CANCEL_BTN_ABSOLUTE = "/html/body/main/div[2]/div/div/div[2]/div/div/div/div[3]/button"
    ROBOT_CANCEL_ABSOLUTE = "/html/body/div[1]/div/main/div/form/div[3]/div/div[1]/div[1]"

    def __init__(self, headless=False, use_local_driver=True, browser='firefox', firefox_binary=None):
        self.headless = headless
        self.use_local_driver = use_local_driver
        self.browser = browser
        self.firefox_binary = firefox_binary
        self.driver = None

    def _start_browser(self):
        if self.browser == 'chrome':
            options = webdriver.ChromeOptions()
            if self.headless:
                options.add_argument('--headless')
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
            self.driver = webdriver.Chrome(options=options)
        else:
            options = FirefoxOptions()
            if self.headless:
                options.add_argument('--headless')
            options.add_argument('--private')
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.set_preference("dom.webdriver.enabled", False)
            options.set_preference("useAutomationExtension", False)
            options.set_preference("dom.webnotifications.enabled", False)
            options.set_preference("dom.push.enabled", False)
            options.set_preference("general.useragent.override",
                                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0")
            if self.firefox_binary:
                options.binary_location = self.firefox_binary
            if self.use_local_driver:
                service = FirefoxService(executable_path=self.GECKODRIVER_PATH)
                self.driver = webdriver.Firefox(options=options, service=service)
            else:
                self.driver = webdriver.Firefox(options=options)
            try:
                self.driver.delete_all_cookies()
                self.driver.execute_script("window.localStorage.clear();")
                self.driver.execute_script("window.sessionStorage.clear();")
            except:
                pass
        logger.info("Браузер %s успешно запущен.", self.browser)

    # ... (все остальные методы без изменений: _remove_overlays, _detect_captcha, _safe_click, _find_with_fallbacks, _fetch_single_rate, get_rates)
    # Я не копирую их ради краткости, они уже рабочие.

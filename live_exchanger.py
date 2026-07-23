import sqlite3
import time
import random
from datetime import date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.common.exceptions import ElementClickInterceptedException

DB_NAME = 'exchanger.db'

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
        print("✅ База данных готова.")

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

class ExchangeRateFetcher:
    URL = "https://yandex.ru/search/?text=%D0%BA%D1%83%D1%80%D1%81+usd+%D0%BA+%D1%80%D1%83%D0%B1%D0%BB%D1%8E&lr=39&clid=2261451&win=620"
    GECKODRIVER_PATH = r"C:\WebDriver\geckodriver.exe"

    # Локаторы для разных браузеров (Firefox / Chrome)
    # Кнопка переключения валют
    SWITCHER_LOCATORS = [
        "//button[starts-with(@aria-label, 'Валюта:')]",                     # Firefox
        "//button[contains(@class,'Select2-Button')]",                       # Chrome
        "//article//button[.//span[contains(text(),'USD') or contains(text(),'EUR')]]",  # Универсальный
        "//article//button"                                                  # Совсем общий (запасной)
    ]
    # Опция USD
    OPTION_USD_LOCATORS = [
        "//*[contains(@class,'Select2-Option') and contains(.,'USD')]",
        "//*[@role='option' and contains(.,'USD')]",
        "//div[contains(@class,'ConverterSelect')]//*[contains(text(),'USD')]"
    ]
    # Опция EUR
    OPTION_EUR_LOCATORS = [
        "//*[contains(@class,'Select2-Option') and contains(.,'EUR')]",
        "//*[@role='option' and contains(.,'EUR')]",
        "//div[contains(@class,'ConverterSelect')]//*[contains(text(),'EUR')]"
    ]
    # Поле ввода курса
    INPUT_LOCATORS = [
        "//article[.//button[starts-with(@aria-label, 'Валюта:')]]//input[@type='text']",
        "//article//input[@type='text' and contains(@value, ',')]",
        "//input[@type='text' and contains(@value, ',')]"
    ]
    # Кнопки закрытия рекламных окон (оставим старые абсолютные, они редко меняются)
    CANCEL_BTN_ABSOLUTE = "/html/body/main/div[2]/div/div/div[2]/div/div/div/div[3]/button"
    ROBOT_CANCEL_ABSOLUTE = "/html/body/div[1]/div/main/div/form/div[3]/div/div[1]/div[1]"

    def __init__(self, headless=False, use_local_driver=True, browser='firefox'):
        self.headless = headless
        self.use_local_driver = use_local_driver
        self.browser = browser
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
            options.set_preference("dom.webnotifications.enabled", False)
            options.set_preference("dom.push.enabled", False)
            options.set_preference("dom.webdriver.enabled", False)
            options.set_preference("useAutomationExtension", False)
            options.set_preference("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0")
            if self.use_local_driver:
                service = FirefoxService(executable_path=self.GECKODRIVER_PATH)
                self.driver = webdriver.Firefox(options=options, service=service)
            else:
                self.driver = webdriver.Firefox(options=options)
            self._clear_session()
        print(f"🟢 Браузер {self.browser} успешно запущен.")

    def _clear_session(self):
        if self.driver:
            try:
                self.driver.delete_all_cookies()
                self.driver.execute_script("window.localStorage.clear();")
                self.driver.execute_script("window.sessionStorage.clear();")
            except:
                pass

    def _remove_overlays(self):
        evil_classes = [
            'DistributionSplashScreenModalAddonBefore',
            'DistributionSplashScreenModalScene',
            'modal', 'popup', 'overlay', 'dialog'
        ]
        for cls in evil_classes:
            try:
                elements = self.driver.find_elements(By.XPATH, f"//*[contains(@class,'{cls}')]")
                for el in elements:
                    if el.is_displayed():
                        self.driver.execute_script("arguments[0].style.display = 'none';", el)
            except:
                pass
        try:
            dialogs = self.driver.find_elements(By.XPATH, "//*[@role='dialog']")
            for d in dialogs:
                if d.is_displayed():
                    self.driver.execute_script("arguments[0].style.display = 'none';", d)
        except:
            pass

    def _detect_captcha(self):
        captcha_locators = [
            "//iframe[contains(@src,'captcha')]",
            "//div[contains(@class,'smart-captcha')]",
            "//div[@id='captcha']",
            "//input[@type='checkbox' and contains(@class,'CheckboxCaptcha')]"
        ]
        for locator in captcha_locators:
            try:
                self.driver.find_element(By.XPATH, locator)
                return True
            except:
                pass
        return False

    def _safe_click(self, element):
        try:
            element.click()
        except ElementClickInterceptedException:
            print("   ⚠️ Клик перехвачен! Срочно чищу все окна...")
            self._remove_overlays()
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", element)

    def _find_with_fallbacks(self, locators, description):
        """Перебирает список локаторов, пока не найдёт кликабельный элемент."""
        wait = WebDriverWait(self.driver, 10)
        for i, locator in enumerate(locators):
            try:
                element = wait.until(EC.element_to_be_clickable((By.XPATH, locator)))
                if i > 0:
                    print(f"   ⚠️ {description}: использован резервный локатор #{i+1}")
                return element
            except:
                continue
        raise Exception(f"Не удалось найти {description} ни по одному локатору")

    def _fetch_single_rate(self, currency):
        wait = WebDriverWait(self.driver, 20)
        self._remove_overlays()
        time.sleep(0.3)

        # Ищем кнопку переключения валют с помощью нескольких локаторов
        switcher = self._find_with_fallbacks(self.SWITCHER_LOCATORS, "кнопка валюты")
        current_text = switcher.text.strip()
        print(f"  🔄 Текущая кнопка: {current_text}")

        if currency not in current_text.upper():
            print(f"  🔄 Переключаю на {currency}...")
            self._safe_click(switcher)
            time.sleep(random.uniform(0.5, 0.8))
            self._remove_overlays()
            time.sleep(0.3)

            opt_locators = self.OPTION_USD_LOCATORS if currency == 'USD' else self.OPTION_EUR_LOCATORS
            option = self._find_with_fallbacks(opt_locators, f"опция {currency}")
            self._safe_click(option)

            # Ждём, пока на кнопке появится нужная валюта
            wait.until(lambda d: currency in d.find_element(By.XPATH, self.SWITCHER_LOCATORS[0]).text.upper()
                       if d.find_elements(By.XPATH, self.SWITCHER_LOCATORS[0])
                       else currency in d.find_element(By.XPATH, self.SWITCHER_LOCATORS[1]).text.upper())
            # Выводим, что получилось
            new_text = ""
            for loc in self.SWITCHER_LOCATORS:
                try:
                    new_text = self.driver.find_element(By.XPATH, loc).text
                    break
                except:
                    pass
            print(f"  ✅ Кнопка теперь: {new_text}")
        else:
            print(f"  ✅ Валюта {currency} уже выбрана.")

        # Поле ввода курса
        input_elem = self._find_with_fallbacks(self.INPUT_LOCATORS, "поле ввода курса")
        print("  🔄 Ожидаю значение курса...")
        wait.until(lambda d: input_elem.get_attribute('value') != '')
        rate_str = input_elem.get_attribute('value')
        print(f"  🎯 Сырое значение: '{rate_str}'")
        rate_str = rate_str.replace(',', '.').replace(' ', '')
        return float(rate_str)

    def get_rates(self):
        try:
            self._start_browser()
            self.driver.get(self.URL)
            wait = WebDriverWait(self.driver, 20)

            time.sleep(random.uniform(3, 5))
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(random.uniform(1, 2))

            print("🧹 Проверяю, не появилась ли капча...")
            if self._detect_captcha():
                print("❌ Обнаружена капча! Скриншот сохранён.")
                self.driver.save_screenshot("captcha_detected.png")
                return None

            print("🧹 Закрываю все всплывающие окна...")
            self._remove_overlays()
            time.sleep(0.5)
            try:
                cancel_btn = wait.until(EC.element_to_be_clickable((By.XPATH, self.CANCEL_BTN_ABSOLUTE)))
                self._safe_click(cancel_btn)
                time.sleep(0.3)
            except:
                pass
            try:
                robot_cancel = wait.until(EC.element_to_be_clickable((By.XPATH, self.ROBOT_CANCEL_ABSOLUTE)))
                self._safe_click(robot_cancel)
                time.sleep(0.3)
            except:
                pass
            self._remove_overlays()
            time.sleep(0.5)

            print("🟢 Приступаю к получению курсов...") 
            usd_rub = self._fetch_single_rate('USD')
            eur_rub = self._fetch_single_rate('EUR')
            print(f"🟢 Итог: USD/RUB={usd_rub}, EUR/RUB={eur_rub}")
            return {'USD_RUB': usd_rub, 'EUR_RUB': eur_rub}

        except Exception as e:
            print(f"❌ Ошибка в процессе: {e}")
            if self.driver:
                self.driver.save_screenshot("error_final.png")
            return None
        finally:
            if self.driver:
                self.driver.quit()
                print("🟢 Закрываю браузер.")

class CurrencyExchanger:
    CURRENCY_MAP = {'1': 'RUB', '2': 'USD', '3': 'EUR'}

    def __init__(self, database, fetcher=None):
        self.db = database
        self.fetcher = fetcher or ExchangeRateFetcher()

    def _load_rates_from_db(self):
        today = date.today().isoformat()
        with sqlite3.connect(self.db.db_name) as conn:
            cur = conn.cursor()
            cur.execute("SELECT CurrencyFrom, CurrencyTo, Rate FROM rates WHERE UpdatedAt = ?", (today,))
            rows = cur.fetchall()
            if len(rows) >= 2:
                rates = {}
                for cur_from, cur_to, rate in rows:
                    if cur_from == 'USD' and cur_to == 'RUB':
                        rates['USD_RUB'] = rate
                    elif cur_from == 'EUR' and cur_to == 'RUB':
                        rates['EUR_RUB'] = rate
                if 'USD_RUB' in rates and 'EUR_RUB' in rates:
                    print("📦 Использую курсы из локальной базы данных.")
                    return rates['USD_RUB'], rates['EUR_RUB']
        return None

    def _load_rates(self):
        db_rates = self._load_rates_from_db()
        if db_rates:
            return db_rates
        print("⏳ Загружаем курсы с биржи...")
        live = self.fetcher.get_rates()
        if live is None:
            print("⚠️ Не удалось загрузить курсы. Используем резервные.")
            return 70.0, 80.0
        print("✅ Актуальные курсы загружены.")
        return live['USD_RUB'], live['EUR_RUB']

    def _show_rates(self, usd, eur):
        usd_to_eur = usd / eur
        eur_to_usd = eur / usd
        print(f"  1 USD = {usd:.2f} RUB")
        print(f"  1 EUR = {eur:.2f} RUB")
        print(f"  1 USD = {usd_to_eur:.4f} EUR")
        print(f"  1 EUR = {eur_to_usd:.4f} USD")

    def _input_currency(self, prompt):
        print(prompt)
        for k, v in self.CURRENCY_MAP.items():
            print(f"{k}. {v}")
        choice = input("Ваш выбор: ").strip()
        if choice not in self.CURRENCY_MAP:
            print("❌ Неверный выбор!")
            return None
        return self.CURRENCY_MAP[choice]

    def run(self):
        print("\n" + "=" * 50)
        print("  ДОБРО ПОЖАЛОВАТЬ В ОБМЕННЫЙ ПУНКТ (ЖИВЫЕ КУРСЫ)")
        print("=" * 50)

        usd, eur = self._load_rates()
        self._show_rates(usd, eur)

        rates = {
            ('RUB', 'USD'): usd,
            ('RUB', 'EUR'): eur,
            ('USD', 'RUB'): 1 / usd,
            ('EUR', 'RUB'): 1 / eur,
            ('USD', 'EUR'): eur / usd,
            ('EUR', 'USD'): usd / eur
        }

        target = self._input_currency("Введите какую валюту желаете получить:")
        if not target:
            return
        try:
            amount = float(input(f"Какая сумма Вас интересует ({target})? "))
            if amount <= 0:
                print("❌ Сумма должна быть больше нуля!")
                return
        except ValueError:
            print("❌ Некорректное число!")
            return

        source = self._input_currency("Какую валюту готовы предложить взамен?")
        if not source or source == target:
            print("❌ Нельзя обменять одинаковые валюты!")
            return

        required = amount * rates[(source, target)]
        balances = self.db.get_balances()
        if not balances:
            print("❌ Не удалось получить баланс!")
            return

        current = balances[source]
        print(f"\nДля получения {amount:.2f} {target} необходимо {required:.2f} {source}.")
        print(f"Ваш текущий баланс {source}: {current:.2f}")

        if current < required:
            print(f"❌ Недостаточно средств! Не хватает {required - current:.2f} {source}.")
            return

        self.db.update_balance(1, source, -required)
        self.db.update_balance(1, target, amount)
        print("✅ Обмен успешно выполнен!")

        new_balances = self.db.get_balances()
        print("Обновлённый баланс:")
        for cur, bal in new_balances.items():
            print(f"  {cur}: {bal:.2f}")

def main():
    db = Database()
    exchanger = CurrencyExchanger(db, fetcher=ExchangeRateFetcher())
    print("🏦 Обменный пункт с живыми курсами готов к работе.")
    while True:
        exchanger.run()
        if input("\nХотите совершить ещё один обмен? (y/n): ").strip().lower() != 'y':
            print("👋 До свидания!")
            break

if __name__ == "__main__":
    main()

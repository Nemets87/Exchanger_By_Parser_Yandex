import sqlite3
import time
import random
import sys
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import ElementClickInterceptedException

# --------------------------------------------------------------
# КОНФИГУРАЦИЯ
# --------------------------------------------------------------
DB_NAME = 'exchanger.db'
# Локальный путь к geckodriver (если он есть). Если None – Selenium Manager.
LOCAL_GECKODRIVER_PATH = r"C:\WebDriver\geckodriver.exe"

# --------------------------------------------------------------
# 1. ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# --------------------------------------------------------------
def init_db():
    """Создаёт таблицу и начальный баланс, если их нет."""
    with sqlite3.connect(DB_NAME) as db:
        cur = db.cursor()
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
            print("✅ База данных создана, начальный баланс зачислен.")
        else:
            print("✅ База данных уже существует.")

# --------------------------------------------------------------
# 2. ПОЛУЧЕНИЕ БАЛАНСА
# --------------------------------------------------------------
def get_balances(user_id=1):
    """Возвращает словарь с балансами пользователя."""
    with sqlite3.connect(DB_NAME) as db:
        cur = db.cursor()
        cur.execute("SELECT Balance_RUB, Balance_USD, Balance_EUR FROM users_balance WHERE UserID = ?", (user_id,))
        row = cur.fetchone()
        if row:
            return {'RUB': row[0], 'USD': row[1], 'EUR': row[2]}
        else:
            return None

# --------------------------------------------------------------
# 3. ПАРСИНГ ЖИВЫХ КУРСОВ (АНТИ-КАПЧА + УДАЛЕНИЕ ПОМЕХ)
# --------------------------------------------------------------
def get_live_rates(headless=False, use_local_driver=True):
    """
    Получает курсы USD/RUB и EUR/RUB с Яндекс.Конвертера.
    headless: запускать ли браузер без окна (для CI нужно True)
    use_local_driver: если True – использовать LOCAL_GECKODRIVER_PATH
    """
    print("🟢 Шаг 0: Запуск Firefox...")
    firefox_options = Options()
    if headless:
        firefox_options.add_argument('--headless')
    # Если передан путь к бинарнику – используем его
    if firefox_binary:
        firefox_options.binary_location = firefox_binary
    firefox_options.add_argument("--disable-blink-features=AutomationControlled")
    firefox_options.set_preference("dom.webnotifications.enabled", False)
    firefox_options.set_preference("dom.push.enabled", False)
    firefox_options.set_preference(
        "general.useragent.override",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
    )

    try:
        if use_local_driver and LOCAL_GECKODRIVER_PATH:
            service = Service(executable_path=LOCAL_GECKODRIVER_PATH)
            driver = webdriver.Firefox(options=firefox_options, service=service)
        else:
            driver = webdriver.Firefox(options=firefox_options)
        print("🟢 Браузер успешно запущен.")
    except Exception as e:
        print(f"❌ Не удалось запустить Firefox: {e}")
        return None

    try:
        url = "https://yandex.ru/search/?text=%D0%BA%D1%83%D1%80%D1%81+usd+%D0%BA+%D1%80%D1%83%D0%B1%D0%BB%D1%8E&lr=39&clid=2261451&win=620"
        print(f"🟢 Шаг 1: Открываю страницу: {url}")
        driver.get(url)
        wait = WebDriverWait(driver, 20)

        time.sleep(random.uniform(2, 4))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(random.uniform(0.5, 1.5))

        # Проверка на капчу
        print("🧹 Проверяю, не появилась ли капча...")
        captcha_detected = False
        try:
            driver.find_element(By.XPATH, "//iframe[contains(@src,'captcha')] | //div[contains(@class,'smart-captcha')] | //div[@id='captcha']")
            captcha_detected = True
        except:
            pass
        if not captcha_detected:
            try:
                driver.find_element(By.XPATH, "//input[@type='checkbox' and contains(@class,'CheckboxCaptcha')]")
                captcha_detected = True
            except:
                pass

        if captcha_detected:
            print("❌ Обнаружена капча! Скриншот сохранён. Переключаюсь на резервные курсы.")
            driver.save_screenshot("captcha_detected.png")
            return None

        # Функция для скрытия перекрывающих окон (не трогаем HeaderForm)
        def remove_overlays():
            overlays = driver.find_elements(By.XPATH,
                "//*[contains(@class,'DistributionSplashScreenModalAddonBefore') or "
                "contains(@class,'modal') or contains(@class,'popup') or "
                "@role='dialog']"
            )
            for overlay in overlays:
                if overlay.is_displayed() and 'HeaderForm' not in overlay.get_attribute('class'):
                    driver.execute_script("arguments[0].style.display = 'none';", overlay)
                    print(f"   🧹 Скрыт: {overlay.tag_name} class={overlay.get_attribute('class')}")

        # Этап очистки
        print("🧹 Закрываю рекламные окна...")
        try:
            cancel_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "/html/body/main/div[2]/div/div/div[2]/div/div/div/div[3]/button")))
            cancel_btn.click()
            time.sleep(0.5)
        except:
            pass
        try:
            robot_cancel = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "/html/body/div[1]/div/main/div/form/div[3]/div/div[1]/div[1]")))
            robot_cancel.click()
            time.sleep(0.5)
        except:
            pass
        remove_overlays()
        time.sleep(0.5)

        print("🟢 Приступаю к получению курсов...")

        def fetch_rate(currency_code):
            print(f"  🔄 Запрашиваю курс для {currency_code}...")
            switcher_xpath = "/html/body/main/div[1]/div[3]/div/div/div[1]/ul/li[2]/div/article/div[1]/div[1]/span/button"
            switcher = wait.until(EC.element_to_be_clickable((By.XPATH, switcher_xpath)))
            current_text = switcher.text.strip()
            print(f"  🔄 Текущая кнопка: {current_text}")

            if currency_code not in current_text.upper():
                print(f"  🔄 Переключаю на {currency_code}...")
                switcher.click()
                time.sleep(random.uniform(0.5, 0.8))
                remove_overlays()
                time.sleep(0.3)

                if currency_code == 'USD':
                    option_xpath = "/html/body/main/div[1]/div[3]/div/div/div[1]/ul/li[2]/div/article/div[1]/div[1]/span/div/div/div[2]/div/div[1]"
                else:  # EUR
                    option_xpath = "/html/body/main/div[1]/div[3]/div/div/div[1]/ul/li[2]/div/article/div[1]/div[1]/span/div/div/div[3]/div/div[1]"

                try:
                    option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
                    option.click()
                except ElementClickInterceptedException:
                    print("  ⚠️ Клик перехвачен! Скрываю окна...")
                    remove_overlays()
                    time.sleep(0.5)
                    option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
                    driver.execute_script("arguments[0].click();", option)

                wait.until(lambda d: currency_code in d.find_element(By.XPATH, switcher_xpath).text.upper())
                print(f"  ✅ Кнопка теперь: {driver.find_element(By.XPATH, switcher_xpath).text}")
            else:
                print(f"  ✅ Валюта {currency_code} уже выбрана.")

            input_xpath = "/html/body/main/div[1]/div[3]/div/div/div[1]/ul/li[2]/div/article/div[1]/div[2]/div/span/input"
            print("  🔄 Ожидаю значение курса...")
            wait.until(lambda d: d.find_element(By.XPATH, input_xpath).get_attribute('value') != '')
            rate_str = driver.find_element(By.XPATH, input_xpath).get_attribute('value')
            print(f"  🎯 Сырое значение: '{rate_str}'")
            rate_str = rate_str.replace(',', '.').replace(' ', '')
            return float(rate_str)

        usd_rub = fetch_rate('USD')
        eur_rub = fetch_rate('EUR')
        print(f"🟢 Итог: USD/RUB={usd_rub}, EUR/RUB={eur_rub}")
        return {'USD_RUB': usd_rub, 'EUR_RUB': eur_rub}

    except Exception as e:
        print(f"❌ Ошибка в процессе: {e}")
        driver.save_screenshot("error_final.png")
        return None
    finally:
        print("🟢 Закрываю браузер.")
        driver.quit()

# --------------------------------------------------------------
# 4. ОПЕРАЦИЯ ОБМЕНА
# --------------------------------------------------------------
def exchange_operation():
    """Одна операция обмена валюты с живыми или резервными курсами."""
    print("\n" + "=" * 50)
    print("  ДОБРО ПОЖАЛОВАТЬ В ОБМЕННЫЙ ПУНКТ (ЖИВЫЕ КУРСЫ)")
    print("=" * 50)

    print("⏳ Загружаем курсы с биржи...")
    # Для локального обмена используем видимый браузер и локальный драйвер
    live = get_live_rates(headless=False, use_local_driver=True)
    if live is None:
        print("⚠️ Не удалось загрузить курсы. Используем резервные.")
        usd_rub = 70.0
        eur_rub = 80.0
    else:
        usd_rub = live['USD_RUB']
        eur_rub = live['EUR_RUB']
        print("✅ Актуальные курсы загружены.")

    usd_to_eur = usd_rub / eur_rub
    eur_to_usd = eur_rub / usd_rub

    print(f"  1 USD = {usd_rub:.2f} RUB")
    print(f"  1 EUR = {eur_rub:.2f} RUB")
    print(f"  1 USD = {usd_to_eur:.4f} EUR")
    print(f"  1 EUR = {eur_to_usd:.4f} USD")
    print("=" * 50)

    rates = {
        ('RUB', 'USD'): usd_rub,
        ('RUB', 'EUR'): eur_rub,
        ('USD', 'RUB'): 1 / usd_rub,
        ('EUR', 'RUB'): 1 / eur_rub,
        ('USD', 'EUR'): eur_to_usd,
        ('EUR', 'USD'): usd_to_eur
    }

    # --- Шаг 1: Выбор целевой валюты ---
    print("\nВведите какую валюту желаете получить:")
    print("1. RUB")
    print("2. USD")
    print("3. EUR")
    target_choice = input("Ваш выбор (1/2/3): ").strip()
    currency_map = {'1': 'RUB', '2': 'USD', '3': 'EUR'}
    if target_choice not in currency_map:
        print("❌ Неверный номер валюты!")
        return
    target = currency_map[target_choice]

    # --- Шаг 2: Сумма ---
    try:
        amount = float(input(f"Какая сумма Вас интересует ({target})? "))
        if amount <= 0:
            print("❌ Сумма должна быть больше нуля!")
            return
    except ValueError:
        print("❌ Некорректное число!")
        return

    # --- Шаг 3: Исходная валюта ---
    print("\nКакую валюту готовы предложить взамен?")
    print("1. RUB")
    print("2. USD")
    print("3. EUR")
    source_choice = input("Ваш выбор (1/2/3): ").strip()
    if source_choice not in currency_map:
        print("❌ Неверный номер валюты!")
        return
    source = currency_map[source_choice]

    if source == target:
        print("❌ Нельзя обменять одинаковые валюты!")
        return

    pair = (source, target)
    if pair not in rates:
        print(f"❌ Обмен {source} на {target} не поддерживается!")
        return
    rate = rates[pair]
    required = amount * rate

    balances = get_balances()
    if not balances:
        print("❌ Не удалось получить баланс!")
        return

    current_balance = balances[source]
    print(f"\nДля получения {amount:.2f} {target} необходимо {required:.2f} {source}.")
    print(f"Ваш текущий баланс {source}: {current_balance:.2f}")

    if current_balance < required:
        print(f"❌ Недостаточно средств! Не хватает {required - current_balance:.2f} {source}.")
        return

    with sqlite3.connect(DB_NAME) as db:
        cur = db.cursor()
        cur.execute(f"UPDATE users_balance SET Balance_{source} = Balance_{source} - ? WHERE UserID = 1", (required,))
        cur.execute(f"UPDATE users_balance SET Balance_{target} = Balance_{target} + ? WHERE UserID = 1", (amount,))
    print("✅ Обмен успешно выполнен!")

    new_balances = get_balances()
    print("Обновлённый баланс:")
    for cur_name, bal in new_balances.items():
        print(f"  {cur_name}: {bal:.2f}")

# --------------------------------------------------------------
# 5. ГЛАВНЫЙ ЦИКЛ ПРОГРАММЫ
# --------------------------------------------------------------
def main():
    args = sys.argv[1:]
    fetch_only = '--fetch-rates' in args
    headless = '--headless' in args

    # Определяем, какой драйвер использовать
    use_local = not headless  # в CI (headless) не используем локальный драйвер

    # Для CI можно передать путь к Firefox через аргумент или переменную окружения
    firefox_binary = os.environ.get('FIREFOX_BINARY')  # переменная окружения
    # Если передан аргумент --firefox-bin, берём его
    for arg in args:
        if arg.startswith('--firefox-bin='):
            firefox_binary = arg.split('=', 1)[1]
            break

    if fetch_only:
        print("📡 Режим получения курсов...")
        rates = get_live_rates(headless=headless, use_local_driver=use_local, firefox_binary=firefox_binary)
        # ... остальное без изменений
        if rates:
            print(f"USD/RUB = {rates['USD_RUB']}")
            print(f"EUR/RUB = {rates['EUR_RUB']}")
            with open('rates.json', 'w', encoding='utf-8') as f:
                json.dump(rates, f, indent=2)
            print("✅ Курсы сохранены в rates.json")
        else:
            print("❌ Не удалось получить курсы.")
    else:
        print("🏦 Обменный пункт с живыми курсами готов к работе.")
        while True:
            exchange_operation()
            again = input("\nХотите совершить ещё один обмен? (y/n): ").strip().lower()
            if again != 'y':
                print("👋 До свидания!")
                break

if __name__ == "__main__":
    init_db()
    main()

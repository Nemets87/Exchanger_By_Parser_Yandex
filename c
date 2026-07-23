import sqlite3
from datetime import date
from live_exchanger import ExchangeRateFetcher, DB_NAME

def update_rates_in_db():
    print("Запуск обновления курсов в CI (браузер Chrome)...")
    # ВАЖНО: явно указываем браузер Chrome
    fetcher = ExchangeRateFetcher(
        headless=True,
        use_local_driver=False,
        browser='chrome'
    )
    rates = fetcher.get_rates()
    if rates is None:
        print("Не удалось получить живые курсы. Обновление прервано.")
        return False

    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rates (
                CurrencyFrom TEXT NOT NULL,
                CurrencyTo   TEXT NOT NULL,
                Rate         REAL NOT NULL,
                UpdatedAt    TEXT NOT NULL,
                PRIMARY KEY (CurrencyFrom, CurrencyTo, UpdatedAt)
            );
        """)
        today = date.today().isoformat()
        pairs = [('USD', 'RUB', rates['USD_RUB']), ('EUR', 'RUB', rates['EUR_RUB'])]
        for cur_from, cur_to, rate in pairs:
            cur.execute(
                "INSERT OR REPLACE INTO rates (CurrencyFrom, CurrencyTo, Rate, UpdatedAt) VALUES (?, ?, ?, ?)",
                (cur_from, cur_to, rate, today)
            )
        conn.commit()
    print(f"Курсы на {today} сохранены в базу данных.")
    return True

if __name__ == "__main__":
    success = update_rates_in_db()
    if not success:
        exit(1)

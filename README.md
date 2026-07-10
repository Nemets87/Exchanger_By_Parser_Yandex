# Live Exchange Rates & Converter

Интерактивный обменник валют с живыми курсами (USD/RUB, EUR/RUB) с парсингом через Selenium. Работает локально и в GitHub Actions.

## Возможности
- 💱 Конвертация RUB, USD, EUR с проверкой баланса (база SQLite)
- 🌐 Живые курсы с Яндекс.Конвертера
- 🤖 Автоматический обход всплывающих окон и капчи
- 🚀 CI/CD: ежедневное обновление курсов в артефактах GitHub

## Установка и запуск локально
1. Клонируйте репозиторий
2. Установите зависимости: `pip install -r requirements.txt`
3. Для интерактивного обменника: `python live_exchanger.py`
4. Для получения курсов в файл: `python live_exchanger.py --fetch-rates`
5. (Опционально) Укажите путь к geckodriver в переменной LOCAL_GECKODRIVER_PATH

## CI курсы
Курсы обновляются ежедневно, результат можно скачать в разделе Actions → последний запуск → Artifacts.

# Exchanger By Parser Yandex

Обменник валют (RUB, USD, EUR) с живыми курсами, полученными через парсинг Яндекс.Конвертера.

- Локально: `python live_exchanger.py`
- CI/CD: курсы обновляются ежедневно и сохраняются в `exchanger.db`

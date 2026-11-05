# Credit Risk Desk

[![Tests](https://github.com/shumakovaes/credit-risk-desk/actions/workflows/tests.yml/badge.svg)](https://github.com/shumakovaes/credit-risk-desk/actions/workflows/tests.yml)

Самостоятельное рабочее место кредитного аналитика: портфель, карточки клиентов, проверка заявки, модель риска и отчёт с объяснениями. Учебный проект на исторических **розничных** данных Berka, подготовленный для портфолио на стыке финансов и разработки.

**Python · PostgreSQL · SQLAlchemy · Alembic · scikit-learn · FastAPI · Streamlit · Docker Compose**

![Портфель](reports/portfolio.png)

## Что работает

- Импорт восьми исходных таблиц Berka, проверка связей и дат, транзакционная загрузка в PostgreSQL.
- Портфель с фильтрами по региону и статусу, экспорт выбранного среза в CSV.
- Поиск клиента, счета, кредиты и последние операции.
- Калькулятор аннуитетного платежа, включая нулевую ставку.
- Проверка суммы, срока, заявленного лимита, нагрузки и доступности истории.
- Logistic Regression и Dummy baseline; отдельные train/validation/test, порог по стоимости ошибок.
- Заявка через API или интерфейс: исторические признаки берутся из БД автоматически.
- Объяснение вкладов признаков, сохранение заявки с версиями модели и правил, журнал и JSON-отчёт.
- Детерминированная синтетическая демонстрация без интернета и без ложных ML-метрик.

Здесь нет банковской интеграции, актуальных кредитных решений и корпоративной PD. Доход, действующие платежи и доступный лимит в заявке вводит пользователь. Приложение показывает, какие проверки прошли и что требует внимания.

## Быстрый запуск

Требуется работающий Docker Engine / Docker Desktop. Из корня репозитория:

```sh
docker compose up --build -d
```

- Интерфейс: http://localhost:8501
- Документация API: http://localhost:8000/docs
- PostgreSQL: localhost:5433

При первом запуске миграции и демоданные загружаются автоматически. Повторный запуск сохраняет заявки. Все порты опубликованы только на localhost. Пароль в Compose предназначен для локальной демонстрации.

Проверить состояние: `docker compose ps -a`. У `db`, `api` и `ui` должен быть статус `healthy`; `init` выполняется один раз и нормально завершается с кодом 0. Остановить сервисы с сохранением данных: `docker compose stop`; запустить снова: `docker compose up -d`. Постоянные сервисы настроены на автоматический перезапуск, пока они не остановлены вручную.

Сборка, импорт Berka, обучение и запуск в Docker проверены. После дополнительной проверки исправлены ошибки граничных входных данных; полный набор содержит **39 тестов**. [Первый протокол](docs/validation.md) · [повторная проверка и исправления](docs/review.md).

По умолчанию включён **demo**: 60 синтетических клиентов, 48 кредитов, 2 880 транзакций. ML в этом режиме отключён; даже при пройденных правилах заявка направляется на ручную проверку.

Для полного режима с Berka и обучением, в PowerShell:

```powershell
# Если демоверсия уже запущена: остановить её контейнеры, данные сохранятся.
docker compose stop
$env:DATA_MODE = 'berka'
docker compose -p creditdesk-berka up --build -d
docker compose -p creditdesk-berka logs -f init
```

В bash: `DATA_MODE=berka docker compose -p creditdesk-berka up --build -d`.
Отдельное имя Compose-проекта создаёт отдельный том PostgreSQL. Первый запуск скачивает открытые данные из зеркала, импортирует их и обучает модель. Исходные данные и артефакты сохраняются в `data/raw/` и `artifacts/`. Для переключения обратно остановите проект Berka и задайте `DATA_MODE=demo`.

## Локальный запуск без Docker

Нужны Python 3.12 и PostgreSQL 17. Создайте отдельную пустую базу и пользователя. Не используйте рабочую банковскую БД.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
Copy-Item .env.example .env
# Укажите в .env адрес своей базы в DATABASE_URL.
python -m alembic upgrade head
credit-desk seed-demo
python -m uvicorn credit_risk_desk.api:app --host 127.0.0.1 --port 8000
```

Во втором терминале из корня репозитория, с активным окружением:

```powershell
python -m streamlit run streamlit_app.py --server.address 127.0.0.1
```

Для реальных данных используйте другую пустую БД в `DATABASE_URL` и вместо `seed-demo`:

```powershell
python -m alembic upgrade head
credit-desk download-berka
credit-desk import-berka
credit-desk train
```

Если зеркало недоступно, положите восемь оригинальных файлов `*.asc` в `data/raw/berka` и выполните последние две команды. Поддерживается также `--directory /path/to/asc`. Импорт проверяет все данные до записи и не перезаписывает существующий набор. Для смены набора используйте отдельную базу.

## Проверенный результат обучения

234 завершённых кредита: 203 статуса A и 31 статуса B. Train: 140, validation: 47, test: 47. В test всего **6** неблагоприятных исходов.

| Метрика test | Logistic Regression | Постоянная вероятность из train |
|---|---:|---:|
| ROC-AUC | 0,687 | 0,500 |
| Average Precision, сводная метрика PR | 0,449 | 0,128 |
| Brier score, меньше — лучше | 0,1098 | 0,1114 |

Порог 0,10076 выбран **на validation** при условной стоимости пропуска проблемного кредита 5 и ложного сигнала 1. Test: TP=4, FP=8, FN=2, TN=33; precision=0,333, recall=0,667. Это ретроспективная проверка на маленькой исторической выборке. Преимущество по Brier небольшое; устойчивость и перенос на новые выдачи не доказаны.

Точная конфигурация, ID разбиения, метрики и калибровочные точки: [training-report.json](reports/training-report.json). Подробности: [карточка модели](docs/model-card.md).

## Проверки

```powershell
# Отдельная PostgreSQL-база с именем, заканчивающимся на _test.
$env:TEST_DATABASE_URL = 'postgresql+psycopg://creditdesk:creditdesk@localhost:5433/creditdesk_test'
python -m pytest -q
```

Без `TEST_DATABASE_URL` выполняются unit-тесты, интеграционные пропускаются. Полный прогон проверяет PostgreSQL, API, отсутствие операций будущего в признаках, одинаковый расчёт признаков для обучения и заявок, правила, сохранение отчётов и все экраны через Streamlit AppTest. В `.github/workflows/tests.yml` подготовлен CI с PostgreSQL.

[Протокол фактически выполненных проверок](docs/validation.md) · [демонстрация за 5 минут](docs/demo.md) · [структура данных](docs/data-and-architecture.md) · [правила](docs/business-rules.md) · [разбор для собеседования](docs/interview.md).

## Структура

```text
src/credit_risk_desk/   импорт, финансы, правила, ML, сервис, API, CLI
migrations/            Alembic и PostgreSQL SQL-функция признаков
config/                изменяемая политика бизнес-правил
streamlit_app.py        интерфейс, обращающийся к API
tests/                 unit, PostgreSQL, API и UI
reports/               результаты выполненного прогона и скриншоты
docs/                  архитектура, модель, демонстрация, источники
```

Независимый репозиторий: ему не нужен второй проект [Credit Analyst Copilot](https://github.com/shumakovaes/credit-analyst-copilot). LLM-компонентов здесь нет.

Идея предметной области: [Czech-Bank-Scoring](https://github.com/andrewpetrovich6/Czech-Bank-Scoring). Реализация, SQL-витрина, API, правила, интерфейс и тесты написаны самостоятельно; код исходного проекта не переносился. Данные подготовлены Petr Berka и Marta Sochorova для PKDD’99. [Источники и условия использования](docs/sources.md).

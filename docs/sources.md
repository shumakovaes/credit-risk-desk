# Источники и атрибуция

- Источник идеи: [andrewpetrovich6/Czech-Bank-Scoring](https://github.com/andrewpetrovich6/Czech-Bank-Scoring). Предметная область — кредитные данные Berka и признаки из операций. Его исходный код, ноутбуки и результаты в этот репозиторий не переносились.
- Первоначальный набор: Petr Berka, Marta Sochorova, Financial Data / PKDD’99 Discovery Challenge. [Исходная страница](http://sorry.vse.cz/~berka/challenge/pkdd1999/berka.htm); при реализации она была недоступна.
- [Доступное зеркало восьми оригинальных ASC-файлов](https://github.com/jlacko/berka-dataset). [Копия оригинального описания](https://github.com/jlacko/berka-dataset/blob/master/Financial%20Data%20description.pdf) использована для проверки статусов A/B/C/D, отношений таблиц, дат и семантики операций.
- [Парсер/исследование Andrew Ganse](https://github.com/aganse/datasci_ipynbs/blob/master/pkdd99_bank_data.py) дополнительно указывает валюту CZK; в исходном табличном описании единица валюты отдельным полем не указана.
- [scikit-learn: метрики](https://scikit-learn.org/stable/modules/model_evaluation.html), [Pipeline](https://scikit-learn.org/stable/modules/generated/sklearn.pipeline.Pipeline.html).
- [SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html), [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing).

В оригинальном PDF для `type` перечислены PRIJEM/VYDAJ. В файле встречается также VYBER; импорт интерпретирует его как списание и сохраняет исходный файл для проверки. Поле `operation` в исходном описании также использует VYBER для снятия наличных. Нельзя выдавать это расширение словаря за точную копию документации.

Снимок фактически использованных файлов зафиксирован в `reports/data-manifest.json` с SHA-256. Зеркало не содержит отдельного LICENSE для данных; не предполагается, что они лицензированы под MIT или пригодны для любого коммерческого использования. Исходные файлы исключены из Git и архива исходного кода. Пользователь загружает их отдельно для воспроизводимого учебного исследования. Лицензия MIT этого репозитория распространяется на его собственный код, а не на чужой набор данных или зависимости.

Самостоятельная часть проекта: слои данных и проверки, миграции, SQL-функция признаков без операций будущего, постановка на A/B, baseline и протокол оценки, отдельный движок правил, API, интерфейс, журнал, тесты и документация. Упоминание вуза авторов исходных идей не является заявлением об авторстве или принадлежности этого репозитория вузу.

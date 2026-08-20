# API и безопасность

## Wordstat v2

Официальный endpoint топа:

```text
POST https://searchapi.api.cloud.yandex.net/v2/wordstat/topRequests
Authorization: Api-Key <key>
```

Нужны `YANDEX_SEARCH_API_KEY`, `YANDEX_FOLDER_ID`, роль сервисного аккаунта
`search-api.webSearch.user` и scope ключа `yc.search-api.execute`.

Скрипт по умолчанию выводит план. Для реального платного вызова:

```bash
python scripts/yandex_direct_toolkit.py wordstat-top \
  --phrase "купить теплицу" --regions 213 --num-phrases 200 \
  --execute --confirm WORDSTAT:1 --output outputs/wordstat.json
```

Не повторяй запрос после неясного ответа вслепую: сначала проверь выходной файл и
статус. На 429 учитывай `Retry-After`; не запускай плотный параллелизм.

## Direct API

Direct OAuth-токен отличается от API-ключа Search API. Нужны приложение с scope
`direct:api`, одобренный доступ API Директа и принятые условия.

Endpoint ЕПК и комбинаторных объектов:

```text
https://api.direct.yandex.com/json/v501/<service>
https://api-sandbox.direct.yandex.com/json/v501/<service>
```

Дополнительные заголовки:

```text
Authorization: Bearer <token>
Client-Login: <managed client, if needed>
Accept-Language: ru
Content-Type: application/json; charset=utf-8
```

## Dry-run и подтверждение

`direct-request` не выполняет HTTP без `--execute`. Для read-метода достаточно
`--execute`. Для мутации скрипт печатает точный token:

```text
SANDBOX:<service>:<method>
LIVE:<service>:<method>
```

Повтори команду с `--execute --confirm <token>`. Это технический предохранитель,
но агент все равно обязан показать пользователю payload и получить разрешение.

## Безопасный порядок публикации

1. `validate-package`.
2. `build-responsive-payload`.
3. Dry-run каждого Direct payload.
4. Человек подтверждает окружение и точный набор объектов.
5. Публикация остановленных кампаний/неактивных объектов небольшой партией.
6. Read-back через `get`, сохранение ID и ошибок.
7. Отдельное подтверждение модерации/активации и бюджета.

Удаление, архив, запуск, изменение стратегии/бюджета и массовая минусация — разные
изменения и не объединяются одним общим подтверждением.

## Секреты

- Только переменные окружения или secret manager.
- Не показывай token/API-key в логах, URL, Markdown или payload-файле.
- Не читай и не коммить `.env.local`.
- Перед коммитом ищи `AQAAAA`, `Api-Key`, `Authorization: Bearer` и известные имена
  секретов; совпадение в документации допустимо только как placeholder без значения.

## Ошибки и частичный успех

Direct может вернуть результат поэлементно. Не считай весь вызов успешным по HTTP
200: проверь `Errors` и `Warnings` каждого `AddResults`/`UpdateResults`. При неясном
успехе сначала прочитай созданные объекты; не повторяй mutation вслепую.

Отчетный endpoint может возвращать 201/202 до готовности. Учитывай заголовок
`retryIn`; не создавай новый отчет, пока не проверен предыдущий.

# yandex.direct

Production-навык для полного цикла работы с Яндекс Директом: от исследования
спроса и проектирования ЕПК до комбинаторных объявлений, Метрики, A/B-тестов и
безопасной работы с API.

> В репозитории находится один главный агентный навык `$yandex-direct`. Внутри
> него собраны специализированные режимы, которые подключаются по задаче.

## Возможности на русском

| Навык | Что делает | Основной результат |
|---|---|---|
| Сбор семантики | Wordstat v2, ассоциации, частотность, регионы, устройства и сезонность | Очищенное семантическое ядро с источниками данных |
| Проверка интента | Проверяет выдачу и определяет, что человек действительно хочет купить | Целевые, условные, информационные и минусуемые запросы |
| Анализ конкурентов | Изучает офферы и пробелы конкурентов без копирования их текстов | Матрица конкурентных отличий и рекламных углов |
| Архитектура ЕПК | Разделяет Поиск, РСЯ, бренд, конкурентов, ретаргетинг и товарные сценарии | Карта кампаний, групп, ключей и автотаргетинга |
| Комбинаторные объявления | Генерирует до 7 заголовков и 3 взаимозаменяемых текстов `ResponsiveAd` | Проверенный пакет продающих объявлений |
| Посадочные страницы | Проверяет message match, H1, оффер, доказательства и CTA | Согласованная цепочка «запрос → объявление → страница» |
| Модерация | Проверяет формулировки, обещания, страницу, контакты и регулируемые тематики | Compliance-отчет с блокерами и доказательствами |
| Метрика и оптимизация | Проверяет цели, доход, CRM, звонки, CPA, ДРР, ROAS и поисковые запросы | План измерения и список обоснованных улучшений |
| A/B-тестирование | Проектирует чистые эксперименты и считает эффект/неопределенность | Readout без преждевременного объявления победителя |
| Безопасный API | Создает `v501` payload, работает через dry-run и требует подтверждение live-записи | Контролируемая публикация с проверяемыми ID и ответами API |

Подробное описание каждого режима, его входов, выходов и команд находится в
**[документе «Навыки и возможности»](docs/skills-ru.md)**.

## Быстрая установка

```bash
npx skills add shelpakovzhenya-art/yandex.direct
```

Пример запуска агента:

```text
Используй $yandex-direct. Собери семантику для установки теплиц в Московской
области, спроектируй ЕПК и подготовь комбинаторные объявления без публикации.
```

## Важное ограничение

Инструмент не гарантирует продажи или победу над любым конкурентом. Он усиливает
то, чем можно управлять: качество спроса, релевантность, доказуемость оффера,
структуру аккаунта, измерения и скорость итераций. Live-изменения и расход бюджета
всегда требуют отдельного явного подтверждения.

---

## English overview

Production-oriented agent skill for researching demand, designing, validating,
launching, and improving Yandex Direct campaigns.

The project is deliberately built for the current Yandex stack rather than for
Google Ads terminology copied into Russian:

- Yandex Search API Wordstat v2 for demand, associations, dynamics, regions, and devices;
- Unified Performance Campaigns (ЕПК) and combinatorial `ResponsiveAd` creatives;
- up to 7 independent headlines and 3 interchangeable texts per combinatorial ad;
- Yandex Direct API `v501` payloads;
- Yandex Metrica goals, ecommerce, offline conversions, CPA/DRR/profit feedback;
- mandatory moderation, landing-page, and claim checks;
- dry-run by default and an explicit confirmation phrase for every API mutation.

## What it does

1. Turns a product brief into seed themes and commercial intent hypotheses.
2. Collects up to 2,000 Wordstat phrases per seed and keeps measured data separate from inference.
3. Clusters phrases by buying job, separates Search, YAN, brand, competitor, and remarketing intent.
4. Produces campaign/group structure, cross-negatives, and an autotargeting test plan.
5. Generates grounded combinatorial ads from verified facts, reviews, objections, and landing-page claims.
6. Checks Yandex character limits, grammar/style risks, unsupported claims, URL rules, and message match.
7. Builds ready-to-review `ads.add` payloads for `ResponsiveAd`.
8. Audits search terms, designs clean A/B tests, and optimizes toward conversions and profit.
9. Can call Wordstat v2 and the generic Direct API without third-party Python packages.

It cannot guarantee sales or beat every competitor. It is designed to improve
the controllable parts: demand coverage, relevance, truthful differentiation,
measurement quality, testing discipline, and speed of iteration.

## Install the skill

```bash
npx skills add shelpakovzhenya-art/yandex.direct
```

Or copy `skills/yandex-direct` into your Codex/agent skills directory.

## Quick start

Invoke `$yandex-direct` with the product, region, landing URL, economics, and
verified offer facts. The skill will ask only for missing decisions that can
materially change the campaign.

Run the deterministic helper:

```bash
python skills/yandex-direct/scripts/yandex_direct_toolkit.py --help
python skills/yandex-direct/scripts/yandex_direct_toolkit.py validate-package examples/campaign-package.example.json
python skills/yandex-direct/scripts/yandex_direct_toolkit.py build-responsive-payload examples/campaign-package.example.json --output outputs/ads.add.json
```

Wordstat and Direct calls are previews unless `--execute` is supplied. Paid
Wordstat calls also require a confirmation token; live Direct mutations require
a more specific confirmation token printed by the preview.

## Credentials

Copy `.env.example` values into your local secret manager or `.env.local`.
The toolkit reads environment variables but never loads or commits an env file.

- Wordstat v2: `YANDEX_SEARCH_API_KEY`, `YANDEX_FOLDER_ID`.
- Direct: `YANDEX_DIRECT_TOKEN`; optionally `YANDEX_DIRECT_CLIENT_LOGIN`.

Never commit OAuth tokens, API keys, or service-account JSON.

## Verification

```bash
python -m unittest discover -s tests -v
python C:/Users/della/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/yandex-direct
```

Official rules change. The skill requires a fresh check of the linked official
Yandex pages before a live launch or a compliance-sensitive campaign.

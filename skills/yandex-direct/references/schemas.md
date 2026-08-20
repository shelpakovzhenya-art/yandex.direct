# Схемы артефактов

## Brief

```json
{
  "product": "",
  "business_model": "b2c|b2b|marketplace|local",
  "geo": {"names": [], "region_ids": []},
  "audiences": [],
  "primary_goal": "",
  "goal_value": null,
  "gross_margin": null,
  "target_cpa": null,
  "target_drr": null,
  "budget": {"amount": null, "period": "week|month", "currency": "RUB"},
  "landing_urls": [],
  "verified_claims": [],
  "constraints": [],
  "api_mode": "research|draft|sandbox|production"
}
```

## Campaign package

`validate-package` and `build-responsive-payload` accept:

```json
{
  "meta": {"account": "", "mode": "draft", "checked_at": "YYYY-MM-DD"},
  "segments": [
    {
      "segment_id": "seg-01",
      "intent": "",
      "ad_group_id": 123,
      "keywords": [],
      "negative_keywords": [],
      "responsive_ad": {
        "titles": [""],
        "texts": [""],
        "href": "https://example.ru/page",
        "display_url_path": "usluga",
        "ad_image_hashes": [],
        "sitelink_set_id": null,
        "ad_extension_ids": [],
        "video_extension_ids": [],
        "business_id": null,
        "erir_ad_description": null
      },
      "landing": {"h1": "", "claims_visible": []},
      "claim_refs": []
    }
  ]
}
```

`ad_group_id` нужен только для Direct payload. Удали null/пустые необязательные
поля перед API — builder делает это автоматически.

## Семантика CSV

Вход минимум с колонкой `phrase`. Допустимы `count|volume|impressions`, `source`,
`seed`, `region`, `device`. Выход нормализатора:

```text
phrase,normalized_phrase,volume,source,seed,region,device,intent_hint,
confidence,offer_match,review_required,duplicate_count
```

`intent_hint` — эвристика, не финальный вердикт. Решение после проверки выдачи.

## Search terms CSV

Рекомендуемые поля:

```text
query,impressions,clicks,cost,conversions,revenue
```

Поддерживаются распространенные русские заголовки. Аудитор рассчитывает CTR, CR,
CPA, ROAS и только предлагает `negative_review`, не изменяет кампанию.

## UTM

```text
base_url + utm_source + utm_medium + utm_campaign + utm_content + utm_term
```

Параметры добавляются с сохранением существующего query string и fragment.

## Журнал изменения

```json
{
  "timestamp": "ISO-8601",
  "actor": "",
  "environment": "sandbox|production",
  "object_ids": [],
  "hypothesis": "",
  "payload_sha256": "",
  "confirmation": "",
  "response_summary": "",
  "read_back": "",
  "next_read_date": "",
  "rollback": ""
}
```

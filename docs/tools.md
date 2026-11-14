# Tool reference

All tools return **JSON strings** (pretty-printed). Errors look like `{"error": "..."}`.

Public GraphQL needs **no token**. Set `BIRDWEATHER_STATION_TOKEN` only when you want station REST for richer detection fields / all-time stats.

**Period rules**

- Dates are `YYYY-MM-DD` in the station timezone (or an explicit IANA `timezone`).
- `days=N` = last N calendar days **including today** in that timezone.
- Prefer either `days` **or** `from_date`/`to_date`, not both.

Samples below use a generic placeholder station (`12345` / “Example Station”) and keep the live response shape. Counts and detections change over time — treat them as shape references. Find your real id at `https://app.birdweather.com/stations/<id>`.

---

## `get_station`

Station metadata: name, coords, timezone, detection range / thresholds. With a token, also returns all-time REST stats.

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `station_id` | string | yes | Numeric BirdWeather station id |

```json
{
  "station": {
    "id": "12345",
    "name": "Example Station",
    "type": "puc",
    "timezone": "America/Los_Angeles",
    "location": null,
    "continent": "North America",
    "country": "United States",
    "state": "California",
    "coords": {
      "lat": 37.77,
      "lon": -122.42
    },
    "earliestDetectionAt": "2026-03-26T14:51:16-07:00",
    "latestDetectionAt": "2026-11-14T09:00:05-08:00",
    "minConfidence": 0.5,
    "minProbability": 0.05,
    "edition": "standard",
    "hasProbabilities": true
  },
  "source": "graphql"
}
```

With token, expect `"source": "graphql+rest"` and a `rest_stats` object (`detections`, `species`, `period: "all"`).

---

## `station_counts`

Detection + unique-species counts for a period.

| Param | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `station_id` | string | yes | | |
| `days` | int | no | `7` | Ignored if dates set |
| `from_date` / `to_date` | string | no | | `YYYY-MM-DD` |
| `timezone` | string | no | station TZ | IANA name |

```json
{
  "station": {
    "id": "12345",
    "name": "Example Station",
    "timezone": "America/Los_Angeles",
    "counts": {
      "detections": 497,
      "species": 31
    }
  },
  "period": {
    "from": "2026-11-08",
    "to": "2026-11-14",
    "timezone": "America/Los_Angeles"
  },
  "source": "graphql"
}
```

---

## `get_weather`

Latest weather reading when BirdWeather has one for the station. Many stations return `"weather": null`.

| Param | Type | Required |
|-------|------|----------|
| `station_id` | string | yes |

```json
{
  "station": {
    "id": "12345",
    "name": "Example Station",
    "timezone": "America/Los_Angeles",
    "weather": null
  },
  "source": "graphql"
}
```

---

## `recent_detections`

Detections with time window, optional species filter, min confidence, limit, and cursor pagination.

| Param | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `station_id` | string | yes | | |
| `days` | int | no | `1` | |
| `from_date` / `to_date` | string | no | | |
| `timezone` | string | no | station TZ | |
| `species` | string | no | | id, common, or scientific name |
| `min_confidence` | float | no | | `0`–`1` |
| `limit` | int | no | `25` | max 100 |
| `after` | string | no | | previous `page_info.endCursor` |

With a station token, REST is preferred (`"source": "rest"`) and payloads may include extra fields (e.g. image URLs).

```json
{
  "station": {
    "id": "12345",
    "name": "Example Station",
    "timezone": "America/Los_Angeles"
  },
  "period": {
    "from": "2026-11-14",
    "to": "2026-11-14",
    "timezone": "America/Los_Angeles"
  },
  "detections": [
    {
      "id": "12298322874",
      "timestamp": "2026-11-14T07:18:29-08:00",
      "confidence": 0.7451745867729187,
      "probability": 0.712704598903656,
      "score": 8.85959682780985,
      "certainty": "almost_certain",
      "mode": "live",
      "speciesId": "134",
      "species": {
        "id": "134",
        "commonName": "House Finch",
        "scientificName": "Haemorhous mexicanus"
      },
      "soundscape": {
        "id": "19523572653",
        "url": "https://media.birdweather.com/soundscapes/12345/12345-20261114-151829.flac",
        "startTime": 0.0,
        "endTime": 3.0,
        "duration": 9,
        "mode": "live"
      }
    }
  ],
  "total_count": 3171087,
  "species_count": 1658,
  "page_info": {
    "hasNextPage": false,
    "endCursor": "MjAyNi0xMS0xNFQwNzoxODoyOS4wMDAwMDAtMDg6MDB8MTIyOTgzMjI4NzQ"
  },
  "source": "graphql"
}
```

---

## `top_species` / `species_list`

Ranked species by detection count. `species_list` is an alias of `top_species` (default `limit` 50 vs 25).

| Param | Type | Required | Default |
|-------|------|----------|---------|
| `station_id` | string | yes | |
| `days` | int | no | `7` |
| `from_date` / `to_date` | string | no | |
| `timezone` | string | no | station TZ |
| `limit` | int | no | `25` / `50` |
| `offset` | int | no | `0` |

```json
{
  "station": {
    "id": "12345",
    "name": "Example Station",
    "timezone": "America/Los_Angeles"
  },
  "period": {
    "from": "2026-11-08",
    "to": "2026-11-14",
    "timezone": "America/Los_Angeles"
  },
  "species": [
    {
      "speciesId": "134",
      "count": 273,
      "averageProbability": null,
      "species": {
        "id": "134",
        "commonName": "House Finch",
        "scientificName": "Haemorhous mexicanus",
        "thumbnailUrl": "https://media.birdweather.com/species/134/HouseFinch-thumbnail-ea7d4c693d0ac395d440407b51951f22.jpg"
      }
    },
    {
      "speciesId": "414",
      "count": 51,
      "averageProbability": null,
      "species": {
        "id": "414",
        "commonName": "Anna's Hummingbird",
        "scientificName": "Calypte anna",
        "thumbnailUrl": "https://media.birdweather.com/species/414/AnnasHummingbird-thumbnail-5aab746f35880840785b5648823d5b9a.jpg"
      }
    }
  ],
  "source": "graphql"
}
```

---

## `daily_counts`

Per-day totals, optionally with per-species breakdown.

| Param | Type | Required | Default |
|-------|------|----------|---------|
| `station_id` | string | yes | |
| `days` | int | no | `7` |
| `from_date` / `to_date` | string | no | |
| `timezone` | string | no | station TZ |
| `species` | string | no | filter to one species |
| `include_species_breakdown` | bool | no | `true` |

**Timezone / range behavior:** BirdWeather’s public `dailyDetectionCounts` GraphQL field buckets by **UTC calendar day** even when a timezone is passed, and can return an extra following-day row when `from_date == to_date`. This tool instead loads detections for the requested period and **re-aggregates them into local calendar days** in the station timezone (or the explicit `timezone` you pass). The result always includes one row per inclusive local date in `[from, to]` (quiet days have `total: 0`) and never includes days outside that range. Newer dates are listed first. Large windows on busy stations may take longer because detections are paginated.

```json
{
  "station_id": "12345",
  "period": {
    "from": "2026-11-12",
    "to": "2026-11-14",
    "timezone": "America/Los_Angeles"
  },
  "days": [
    { "date": "2026-11-14", "dayOfYear": 318, "total": 10 },
    { "date": "2026-11-13", "dayOfYear": 317, "total": 54 },
    { "date": "2026-11-12", "dayOfYear": 316, "total": 96 }
  ],
  "source": "graphql"
}
```

---

## `species_info`

Species profile: names, eBird / Wikipedia / BirdWeather links, images, summary.

Provide **one of** `species_id`, `scientific_name`, or `query` (common or scientific name).

| Param | Type | Required |
|-------|------|----------|
| `species_id` | string | one of |
| `scientific_name` | string | one of |
| `query` | string | one of |

```json
{
  "species": {
    "id": "134",
    "commonName": "House Finch",
    "scientificName": "Haemorhous mexicanus",
    "classification": "avian",
    "alpha": "HOFI",
    "alpha6": "HAEMEX",
    "ebirdCode": "houfin",
    "ebirdUrl": "https://ebird.org/species/houfin",
    "birdweatherUrl": "https://app.birdweather.com/species/house-finch",
    "wikipediaUrl": "https://en.wikipedia.org/wiki/House_finch",
    "wikipediaSummary": "The house finch (Haemorhous mexicanus) is a bird in the finch family Fringillidae. It is native to western North America and has been introduced to the eastern half of the continent and Hawaii. This species and the other \"American rosefinches\" are placed in the genus Haemorhous.",
    "imageUrl": "https://media.birdweather.com/species/134/HouseFinch-standard-3329463dada4a864431241d37400ba54.jpg",
    "thumbnailUrl": "https://media.birdweather.com/species/134/HouseFinch-thumbnail-ea7d4c693d0ac395d440407b51951f22.jpg",
    "imageLicense": "CC BY 2.0",
    "stationCount": 13472,
    "mlUrl": "https://search.macaulaylibrary.org/catalog?taxonCode=houfin"
  },
  "source": "graphql"
}
```

---

## `search_species`

Search the catalog by common or scientific name fragment.

| Param | Type | Required | Default |
|-------|------|----------|---------|
| `query` | string | yes | |
| `limit` | int | no | `20` |
| `after` | string | no | pagination cursor |

```json
{
  "species": [
    {
      "id": "75",
      "commonName": "Common Raven",
      "scientificName": "Corvus corax",
      "classification": "avian",
      "thumbnailUrl": "https://media.birdweather.com/species/75/CommonRaven-thumbnail-9a460bb77e431d214ef6c2f97d3ddd0d.jpg",
      "ebirdCode": "comrav"
    },
    {
      "id": "705",
      "commonName": "Australian Raven",
      "scientificName": "Corvus coronoides",
      "classification": "avian",
      "thumbnailUrl": "https://media.birdweather.com/species/705/AustralianRaven-thumbnail-6f68a64991cd9a4b48cf745bcd7ee56f.jpg",
      "ebirdCode": "ausrav1"
    }
  ],
  "total_count": 8,
  "page_info": {
    "hasNextPage": true,
    "endCursor": "Mg"
  },
  "source": "graphql"
}
```

---

## `search_stations`

Stations near a lat/lon (default 25 km) and/or by name. Geographic hits include `distance_km`, nearest first.

| Param | Type | Required | Default |
|-------|------|----------|---------|
| `lat` / `lon` | float | for geo | both required together |
| `radius_km` | float | no | `25` |
| `query` | string | no | name search |
| `limit` | int | no | `20` |
| `after` | string | no | cursor |

```json
{
  "stations": [
    {
      "id": "12345",
      "name": "Example Station",
      "type": "puc",
      "timezone": "America/Los_Angeles",
      "continent": "North America",
      "country": "United States",
      "state": "California",
      "coords": { "lat": 37.77, "lon": -122.42 },
      "distance_km": 1.2
    },
    {
      "id": "67890",
      "name": "Nearby Example Pi",
      "type": "birdnetpi",
      "timezone": "America/Los_Angeles",
      "coords": { "lat": 37.78, "lon": -122.41 },
      "distance_km": 2.4
    }
  ],
  "total_count": 8,
  "page_info": {
    "hasNextPage": true,
    "endCursor": "Mw"
  },
  "source": "graphql"
}
```

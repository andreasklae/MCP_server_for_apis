# Wikipedia API (MediaWiki)

## Overview
The MediaWiki API provides programmatic access to Wikipedia content, including articles, search, and geolocation features.

## Base URLs
- English: `https://en.wikipedia.org/w/api.php`
- Norwegian Bokmål: `https://no.wikipedia.org/w/api.php`
- Norwegian Nynorsk: `https://nn.wikipedia.org/w/api.php`

## Authentication
None required — public API.

## Rate Limits
- Be polite: max 200 requests/second for bots
- Use `User-Agent` header identifying your application

## Key Endpoints

### Search Articles
```
GET /w/api.php?action=query&list=search&srsearch=<query>&format=json
```

Parameters:
- `srsearch` — search query (required)
- `srlimit` — max results (default 10, max 500)
- `sroffset` — pagination offset

### Get Article Summary
```
GET /w/api.php?action=query&prop=extracts&exintro=true&explaintext=true&titles=<title>&format=json
```

Parameters:
- `titles` — article title(s), pipe-separated
- `exintro` — only get intro section
- `explaintext` — return plain text (not HTML)
- `exsentences` — limit to N sentences

### Geosearch (Articles Near Location)
```
GET /w/api.php?action=query&list=geosearch&gscoord=<lat>|<lon>&gsradius=<meters>&format=json
```

Parameters:
- `gscoord` — coordinates as `lat|lon`
- `gsradius` — search radius in meters (max 10000)
- `gslimit` — max results (default 10, max 500)

### Get Full Page Content
```
GET /w/api.php?action=parse&page=<title>&format=json
```

Returns parsed HTML content of the article.

## Response Format
All responses are JSON with structure:
```json
{
  "batchcomplete": "",
  "query": {
    // results here
  }
}
```

## Error Handling
Errors include `error` object with `code` and `info` fields.

## Official Documentation
- https://www.mediawiki.org/wiki/API:Main_page
- https://www.mediawiki.org/wiki/API:Query
- https://www.mediawiki.org/wiki/API:Geosearch


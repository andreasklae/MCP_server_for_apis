# Store Norske Leksikon (SNL) API

## Overview
Store norske leksikon is the Norwegian national encyclopedia, providing authoritative Norwegian-language articles on a wide range of topics.

## Base URL
```
https://snl.no/api/v1/
```

## Authentication
None required — public API.

## Key Endpoints

### Search Articles
```
GET https://snl.no/api/v1/search?query=<term>
```

Parameters:
- `query` — search term (required)
- `limit` — max results (default 10)
- `offset` — pagination offset

Response:
```json
[
  {
    "title": "Article Title",
    "article_id": 12345,
    "permalink": "https://snl.no/artikkel",
    "snippet": "Preview text...",
    "article_type": "article"
  }
]
```

### Get Article by ID
```
GET https://snl.no/api/v1/article/<id>
```

Response includes full article content, metadata, authors, etc.

### Get Article by URL/Slug
Articles can also be fetched via their URL slug:
```
GET https://snl.no/<slug>.json
```

For example: `https://snl.no/Oslo.json`

## Response Format
- Search returns an array of article previews
- Article endpoints return full article objects

## Article Object Structure
```json
{
  "article_id": 12345,
  "headword": "Article Title",
  "permalink": "https://snl.no/path",
  "article_url": "https://snl.no/path",
  "subject_url": "https://snl.no/subject",
  "subject_title": "Subject Area",
  "xhtml_body": "<p>Article content in HTML...</p>",
  "plain_text_body": "Plain text version...",
  "created_at": "2020-01-01T00:00:00Z",
  "changed_at": "2024-01-01T00:00:00Z",
  "license_name": "CC BY-SA 3.0",
  "authors": [
    {
      "full_name": "Author Name"
    }
  ],
  "images": []
}
```

## Rate Limits
No explicit rate limits documented, but be respectful.

## License
Content is licensed under CC BY-SA 3.0.

## Official Documentation
- https://snl.no/api/dokumentasjon
- https://snl.no/Store_norske_leksikon


# Riksantikvaren OGC API

## Overview
The OGC API Features service from Riksantikvaren provides access to Norwegian cultural heritage data, including the official Askeladden register and user-contributed "Brukeminner" (cultural memories).

## Base URL
```
https://api.ra.no/
```

## Authentication
None required — public API.

## License
- **Askeladden data**: NLOD (Norwegian License for Open Government Data)
- **Brukeminner data**: Creative Commons licenses

## Key Endpoints

### Landing Page
```
GET https://api.ra.no/
```
Returns API overview and links to collections.

### List Collections
```
GET https://api.ra.no/collections
```

Returns available data collections. Key collections include:
- `kulturminner` — Cultural heritage sites from Askeladden
- `brukeminner` — User-contributed cultural memories
- Various thematic collections

### Get Collection Info
```
GET https://api.ra.no/collections/{collectionId}
```

### Query Features
```
GET https://api.ra.no/collections/{collectionId}/items
```

Parameters:
- `limit` — max features to return (default varies, max 1000)
- `offset` — pagination offset
- `bbox` — bounding box filter: `minLon,minLat,maxLon,maxLat`
- `datetime` — temporal filter
- `filter` — CQL2 filter expression for advanced queries (see Text Search below)
- `filter-lang` — Filter language: `cql2-text` (default) or `cql2-json`

Response (GeoJSON FeatureCollection):
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "12345",
      "geometry": {
        "type": "Point",
        "coordinates": [10.75, 59.91]
      },
      "properties": {
        "navn": "Feature Name",
        "beskrivelse": "Description",
        // ... other properties
      }
    }
  ],
  "numberMatched": 1000,
  "numberReturned": 10,
  "links": [
    {
      "rel": "next",
      "href": "..."
    }
  ]
}
```

### Get Single Feature
```
GET https://api.ra.no/collections/{collectionId}/items/{featureId}
```

Returns a single GeoJSON Feature.

## Coordinate System
- Default: WGS84 (EPSG:4326)
- Coordinates are in `[longitude, latitude]` order (GeoJSON standard)

## Common Properties (Askeladden)
- `lokalitetsId` — Unique identifier
- `navn` — Name
- `kommune` — Municipality
- `fylke` — County
- `kategori` — Category
- `vernestatus` — Protection status
- `datering` — Dating/period

## Common Properties (Brukeminner)
- `tittel` — Title
- `beskrivelse` — Description
- `kategori` — Category
- `opprettet` — Created date
- `forfatter` — Contributor

## Pagination
Use `limit` and `offset` parameters. Check `links` array for `next` relation.

## Text Search with CQL2

The API supports powerful text search using CQL2 (Common Query Language 2) filter expressions.

### Basic Text Search (Case-Insensitive)
Use the `CASEI()` function with `LIKE` operator for case-insensitive partial matching:

```
GET https://api.ra.no/kulturminner/collections/kulturminner/items?
  filter=CASEI(navn) LIKE CASEI('%slott%')&
  filter-lang=cql2-text&
  f=json
```

This finds all sites with "slott" in the name (case-insensitive).

### Search Multiple Fields
Combine filters with `OR` to search across multiple fields:

```
GET https://api.ra.no/kulturminner/collections/kulturminner/items?
  filter=CASEI(navn) LIKE CASEI('%festning%') OR CASEI(informasjon) LIKE CASEI('%festning%')&
  filter-lang=cql2-text&
  f=json
```

### Examples

**Find "Akershus festning":**
```
filter=CASEI(navn) LIKE CASEI('%akershus%') AND CASEI(navn) LIKE CASEI('%festning%')&filter-lang=cql2-text
```

**Find any "slott" (castle):**
```
filter=CASEI(navn) LIKE CASEI('%slott%')&filter-lang=cql2-text
```

**Find sites in Oslo:**
```
filter=kommune='Oslo'&filter-lang=cql2-text
```

### CQL2 Operators
- `LIKE` — Pattern matching (use `%` as wildcard)
- `=`, `<>`, `<`, `>`, `<=`, `>=` — Comparison operators
- `AND`, `OR`, `NOT` — Logical operators
- `CASEI()` — Case-insensitive function
- `BETWEEN`, `IN` — Advanced operators
- `S_INTERSECTS()`, `S_WITHIN()` — Spatial operators
- `T_AFTER()`, `T_BEFORE()` — Temporal operators

For full CQL2 specification, see: [OGC CQL2 Standard](https://docs.ogc.org/is/21-065r2/21-065r2.html)

## Error Handling
Standard HTTP error codes. Errors return JSON with message.

## Tips for AI Guide App
- Use CQL2 `filter` parameter with `CASEI()` for text search
- Use `bbox` to find features near a user's location (works best for brukerminner)
- Combine kulturminner search with ArcGIS API for better spatial queries
- Combine with Wikipedia/SNL for additional context
- Consider caching frequently accessed features

## Official Information
- https://api.ra.no/ (API documentation)
- https://kulturminnesok.no/ (Web interface)
- https://www.riksantikvaren.no/ (Organization website)


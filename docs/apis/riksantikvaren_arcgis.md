# Riksantikvaren ArcGIS REST API

## Overview
The ArcGIS REST API from Riksantikvaren provides map services and spatial query capabilities for Norwegian cultural heritage data. This offers more flexible querying than the OGC API, especially for complex spatial operations.

## Base URL
```
https://kart.ra.no/arcgis/rest/services/Distribusjon
```

## Authentication
None required — public API.

## License
Data is licensed under NLOD (Norwegian License for Open Government Data).

## Service Structure
The API exposes multiple map and feature services:

```
/Distribusjon/
├── Kulturminner/MapServer       # Cultural heritage sites
├── Fredete/MapServer            # Protected sites
├── Skipsfunn/MapServer          # Ship finds
├── Brukeminner/MapServer        # User-contributed memories
└── ... other services
```

## Key Endpoints

### List Services
```
GET https://kart.ra.no/arcgis/rest/services/Distribusjon?f=json
```

Returns available services and their types.

### Get Service Info
```
GET https://kart.ra.no/arcgis/rest/services/Distribusjon/{ServiceName}/MapServer?f=json
```

Returns layers, spatial reference, extent, etc.

### Get Layer Info
```
GET https://kart.ra.no/arcgis/rest/services/Distribusjon/{ServiceName}/MapServer/{layerId}?f=json
```

Returns fields, geometry type, and other metadata.

### Query Features
```
GET https://kart.ra.no/arcgis/rest/services/Distribusjon/{ServiceName}/MapServer/{layerId}/query
```

Parameters:
- `where` — SQL-like attribute filter (e.g., `kategori='Kirke'`)
- `geometry` — spatial filter geometry (JSON)
- `geometryType` — type of geometry (`esriGeometryPoint`, `esriGeometryEnvelope`, etc.)
- `spatialRel` — spatial relationship (`esriSpatialRelIntersects`, `esriSpatialRelWithin`, etc.)
- `outFields` — fields to return (`*` for all)
- `returnGeometry` — whether to return geometry (`true`/`false`)
- `outSR` — output spatial reference (e.g., `4326` for WGS84)
- `f` — format (`json`, `geojson`)
- `resultOffset` — pagination offset
- `resultRecordCount` — max records per request

### Query Example: Features in Bounding Box
```
GET /query?
  where=1=1&
  geometry={"xmin":10.5,"ymin":59.8,"xmax":10.9,"ymax":60.0}&
  geometryType=esriGeometryEnvelope&
  spatialRel=esriSpatialRelIntersects&
  outFields=*&
  returnGeometry=true&
  outSR=4326&
  f=geojson
```

### Query Example: Features Near Point
```
GET /query?
  where=1=1&
  geometry={"x":10.75,"y":59.91}&
  geometryType=esriGeometryPoint&
  distance=1000&
  units=esriSRUnit_Meter&
  spatialRel=esriSpatialRelIntersects&
  outFields=*&
  returnGeometry=true&
  f=geojson
```

### Identify (Multi-layer Query)
```
GET https://kart.ra.no/arcgis/rest/services/Distribusjon/{ServiceName}/MapServer/identify
```

Parameters:
- `geometry` — point or envelope
- `geometryType` — geometry type
- `layers` — which layers to query (`all`, `visible`, or specific IDs)
- `tolerance` — pixel tolerance for point queries
- `mapExtent` — current map extent
- `imageDisplay` — image dimensions

## Response Formats

### Standard JSON
```json
{
  "objectIdFieldName": "OBJECTID",
  "features": [
    {
      "attributes": {
        "OBJECTID": 12345,
        "navn": "Feature Name",
        "kategori": "Category"
      },
      "geometry": {
        "x": 10.75,
        "y": 59.91
      }
    }
  ]
}
```

### GeoJSON (with `f=geojson`)
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "OBJECTID": 12345,
        "navn": "Feature Name"
      },
      "geometry": {
        "type": "Point",
        "coordinates": [10.75, 59.91]
      }
    }
  ]
}
```

## Spatial References
- Default output is often in UTM Zone 33N (EPSG:25833)
- Use `outSR=4326` to get WGS84 coordinates
- Input geometry should match the service's spatial reference or specify `inSR`

## Pagination
- Use `resultOffset` and `resultRecordCount`
- Check `exceededTransferLimit` in response to know if more results exist

## Common Services and Layers

### Kulturminner (Cultural Heritage)
Layers include:
- Points, lines, polygons for various heritage types
- Categories: churches, farms, industrial sites, etc.

### Fredete (Protected Sites)
- Legally protected cultural heritage sites
- Includes protection zones

### Brukeminner (User-contributed)
- Public contributions to cultural memory
- Less formally verified than Askeladden data

## Tips for AI Guide App
- Use point queries with distance buffer for "nearby" searches
- Request only needed fields to reduce response size
- Use `f=geojson` for easier parsing
- Cache layer metadata to avoid repeated requests

## Official Documentation
- ArcGIS REST API: https://developers.arcgis.com/rest/services-reference/
- Riksantikvaren services: https://kart.ra.no/arcgis/rest/services/Distribusjon


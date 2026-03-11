# GeoJSON Export Example

This document demonstrates how to use the GeoJSON export feature to export COP updates for mapping platforms.

## Overview

The GeoJSON export feature converts COP updates into RFC 7946 compliant GeoJSON format for integration with:

- **Web mapping libraries**: Leaflet, Mapbox GL JS, Google Maps
- **GIS platforms**: ArcGIS, QGIS
- **Spatial databases**: PostGIS, MongoDB geospatial queries
- **Geospatial analysis tools**: Turf.js, GeoPandas

## API Endpoints

### Export GeoJSON

```http
GET /api/v1/exports/geojson/{update_id}
```

**Query Parameters:**
- `include_non_spatial` (boolean, default: `false`): Include items without location as features with null geometry
- `pretty` (boolean, default: `false`): Pretty-print JSON with indentation

**Response:**
- Content-Type: `application/geo+json`
- Returns RFC 7946 compliant GeoJSON FeatureCollection

**Example Request:**

```bash
curl -X GET "https://api.integritykit.aidarena.org/api/v1/exports/geojson/67890?pretty=true" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o cop-update-67890.geojson
```

### Preview GeoJSON Export

```http
GET /api/v1/exports/geojson/{update_id}/preview
```

**Query Parameters:**
- `include_non_spatial` (boolean, default: `false`): Include items without location

**Response:**
- Content-Type: `application/json`
- Returns GeoJSON FeatureCollection with export statistics

**Example Request:**

```bash
curl -X GET "https://api.integritykit.aidarena.org/api/v1/exports/geojson/67890/preview" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## GeoJSON Structure

### FeatureCollection

```json
{
  "type": "FeatureCollection",
  "features": [...],
  "metadata": {
    "cop_update_id": "67890",
    "cop_update_title": "Shelter Status Update",
    "update_number": 1,
    "published_at": "2026-03-10T14:30:00+00:00",
    "workspace_id": "W12345",
    "feature_count": 2,
    "export_timestamp": "2026-03-10T14:35:00+00:00",
    "export_format": "GeoJSON RFC 7946",
    "coordinate_system": "WGS84 (EPSG:4326)"
  }
}
```

### Feature Structure

Each COP line item with location becomes a GeoJSON Feature:

```json
{
  "type": "Feature",
  "id": "candidate-12345",
  "geometry": {
    "type": "Point",
    "coordinates": [-89.6501, 39.7817]  // [longitude, latitude]
  },
  "properties": {
    // Identification
    "line_item_id": "candidate-12345",
    "cop_update_id": "cop-update-67890",
    "cop_update_title": "Shelter Status Update",

    // Content
    "text": "Shelter Alpha at 123 Main St has reached capacity.",

    // 5W Framework Fields
    "what": "Shelter capacity reached",
    "where": "123 Main St, Springfield",
    "when_timestamp": "2026-03-10T12:30:00+00:00",
    "when_description": "2 hours ago",
    "who": "Emergency Management Agency",
    "so_what": "Redirecting evacuees to Shelter Bravo",

    // Status and Classification
    "status": "verified",
    "status_label": "VERIFIED",
    "risk_tier": "elevated",
    "category": null,

    // Publishing Metadata
    "published_at": "2026-03-10T14:30:00+00:00",
    "slack_permalink": "https://slack.com/archives/C123456/p1234567892",

    // Evidence
    "citations": [
      "https://slack.com/archives/C123/p1234567890"
    ],
    "citation_count": 1,

    // Editing
    "was_edited": false
  }
}
```

## Location Data Extraction

The GeoJSON export service extracts location coordinates from COP candidate evidence snapshots in multiple formats:

### Supported Location Formats

#### 1. Explicit Location Object (Recommended)

```json
{
  "fields_snapshot": {
    "location": {
      "lat": 39.7817,
      "lon": -89.6501
    }
  }
}
```

#### 2. GeoJSON-Style Coordinates

```json
{
  "fields_snapshot": {
    "location": {
      "coordinates": [-89.6501, 39.7817]  // [lon, lat] GeoJSON order
    }
  }
}
```

#### 3. Coordinates Array

```json
{
  "fields_snapshot": {
    "coordinates": [39.7817, -89.6501]  // [lat, lon]
  }
}
```

#### 4. Text Parsing from "where" Field

The service can parse coordinates from text:

```json
{
  "fields_snapshot": {
    "where": "Location at 39.7817, -89.6501"
  }
}
```

Supported text formats:
- `"40.7128, -74.0060"`
- `"lat: 40.7128, lon: -74.0060"`
- `"latitude: 40.7128, longitude: -74.0060"`

## Integration Examples

### Leaflet.js

```javascript
// Fetch GeoJSON
fetch('/api/v1/exports/geojson/67890?pretty=true', {
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN'
  }
})
  .then(response => response.json())
  .then(geojson => {
    // Add to Leaflet map
    L.geoJSON(geojson, {
      pointToLayer: function(feature, latlng) {
        // Customize marker based on status
        const color = feature.properties.status === 'verified' ? 'green' : 'orange';
        return L.circleMarker(latlng, {
          radius: 8,
          fillColor: color,
          color: '#fff',
          weight: 1,
          opacity: 1,
          fillOpacity: 0.8
        });
      },
      onEachFeature: function(feature, layer) {
        // Add popup with details
        const props = feature.properties;
        layer.bindPopup(`
          <h3>${props.status_label}</h3>
          <p><strong>What:</strong> ${props.what}</p>
          <p><strong>Where:</strong> ${props.where}</p>
          <p><strong>When:</strong> ${props.when_description}</p>
          <p><strong>Risk Tier:</strong> ${props.risk_tier}</p>
          <a href="${props.slack_permalink}" target="_blank">View in Slack</a>
        `);
      }
    }).addTo(map);
  });
```

### Mapbox GL JS

```javascript
// Fetch GeoJSON
fetch('/api/v1/exports/geojson/67890', {
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN'
  }
})
  .then(response => response.json())
  .then(geojson => {
    // Add source
    map.addSource('cop-updates', {
      type: 'geojson',
      data: geojson
    });

    // Add layer
    map.addLayer({
      id: 'cop-updates-layer',
      type: 'circle',
      source: 'cop-updates',
      paint: {
        'circle-radius': 8,
        'circle-color': [
          'match',
          ['get', 'status'],
          'verified', '#22c55e',
          'in_review', '#f59e0b',
          '#6b7280'
        ],
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff'
      }
    });

    // Add click handler
    map.on('click', 'cop-updates-layer', (e) => {
      const props = e.features[0].properties;
      new mapboxgl.Popup()
        .setLngLat(e.lngLat)
        .setHTML(`
          <h3>${props.status_label}</h3>
          <p>${props.text}</p>
        `)
        .addTo(map);
    });
  });
```

### QGIS Import

1. **Open QGIS**
2. **Layer → Add Layer → Add Vector Layer**
3. **Protocol: HTTP(S)**
4. **URI:** `https://api.integritykit.aidarena.org/api/v1/exports/geojson/67890`
5. **Add authentication headers** (Settings → Authentication)
6. **Style the layer** based on `status`, `risk_tier`, or other properties

### ArcGIS Online

1. **Export GeoJSON** to file:
   ```bash
   curl -X GET "https://api.integritykit.aidarena.org/api/v1/exports/geojson/67890" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -o cop-update.geojson
   ```

2. **Upload to ArcGIS Online:**
   - Content → Add Item → From your computer
   - Upload `cop-update.geojson`
   - Add to map and style

### Python GeoPandas

```python
import geopandas as gpd
import requests

# Fetch GeoJSON
response = requests.get(
    'https://api.integritykit.aidarena.org/api/v1/exports/geojson/67890',
    headers={'Authorization': 'Bearer YOUR_TOKEN'}
)
geojson = response.json()

# Create GeoDataFrame
gdf = gpd.GeoDataFrame.from_features(geojson['features'])

# Analysis
print(f"Total features: {len(gdf)}")
print(f"Verified items: {(gdf['status'] == 'verified').sum()}")
print(f"In review items: {(gdf['status'] == 'in_review').sum()}")

# Spatial operations
buffer_500m = gdf.to_crs(epsg=3857).buffer(500).to_crs(epsg=4326)

# Export to shapefile
gdf.to_file('cop_update.shp')
```

## Export Statistics

The preview endpoint provides useful statistics:

```json
{
  "data": {
    "update_id": "67890",
    "geojson": {...},
    "stats": {
      "total_features": 2,
      "spatial_features": 2,
      "non_spatial_features": 0,
      "verified_features": 1,
      "in_review_features": 1,
      "has_metadata": true
    }
  }
}
```

## Non-Spatial Features

By default, line items without location coordinates are excluded. To include them with `null` geometry:

```bash
curl -X GET "https://api.integritykit.aidarena.org/api/v1/exports/geojson/67890?include_non_spatial=true"
```

Non-spatial features have all properties but no geometry:

```json
{
  "type": "Feature",
  "id": "candidate-99999",
  "geometry": null,
  "properties": {
    "text": "General update without location",
    "status": "verified",
    ...
  }
}
```

## Best Practices

### 1. Coordinate System

GeoJSON uses **WGS84 (EPSG:4326)** with coordinates in **[longitude, latitude]** order:

```json
"coordinates": [-89.6501, 39.7817]  // [lon, lat]
```

### 2. Location Data Quality

For best results, store location data in evidence snapshots as:

```json
"fields_snapshot": {
  "location": {
    "lat": 39.7817,
    "lon": -89.6501,
    "accuracy": 100  // meters (optional)
  }
}
```

### 3. Caching

GeoJSON exports are cached for 5 minutes. The `Cache-Control` header indicates:

```
Cache-Control: public, max-age=300
```

### 4. Large Exports

For COP updates with many line items:
- Use the standard endpoint (not preview) for production use
- Enable caching in your HTTP client
- Consider spatial filtering in your mapping application

### 5. Filtering by Status

Filter features in your application by the `status` property:

```javascript
// Only show verified items
const verifiedFeatures = geojson.features.filter(
  f => f.properties.status === 'verified'
);
```

## Error Handling

### 404 Not Found

```json
{
  "detail": "COP update 67890 not found"
}
```

### 422 Unprocessable Entity

```json
{
  "error": {
    "code": "GEOJSON_EXPORT_ERROR",
    "message": "COP update cannot be exported to GeoJSON format",
    "details": [
      {"reason": "Cannot export unpublished COP update"}
    ]
  }
}
```

Common reasons:
- COP update not published
- No verified or in-review items
- No items with location data (when `include_non_spatial=false`)

## References

- **RFC 7946 GeoJSON Specification**: https://tools.ietf.org/html/rfc7946
- **GeoJSON.org**: https://geojson.org/
- **Leaflet GeoJSON Tutorial**: https://leafletjs.com/examples/geojson/
- **Mapbox GL JS GeoJSON Source**: https://docs.mapbox.com/mapbox-gl-js/example/geojson-layer/

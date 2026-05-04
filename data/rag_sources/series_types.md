# ECharts Series Types

Each series in the `series` array must have a `type` field.
Below are the most commonly used types with their key options.

---

## bar — Bar Chart

Best for: comparing discrete categories side-by-side.

```json
{
  "type": "bar",
  "name": "Sales Q1",
  "data": [120, 200, 150, 80, 70, 110],
  "barWidth": "40%",
  "stack": "total",
  "label": { "show": true, "position": "top" },
  "itemStyle": { "borderRadius": [4, 4, 0, 0] }
}
```

Key options:
- `barWidth` — pixel or percentage width of each bar
- `barGap` — gap between bars of different series (`"30%"` default)
- `stack` — group name; bars with the same stack value are stacked
- `label.position` — `"top"`, `"inside"`, `"insideTop"`, `"bottom"`
- `itemStyle.borderRadius` — rounds bar corners `[topLeft, topRight, bottomRight, bottomLeft]`
- `emphasis.focus` — `"series"` fades other series on hover

Horizontal bar chart: swap `xAxis.type` to `"value"` and `yAxis.type` to `"category"`.

---

## line — Line Chart

Best for: showing trends over time or continuous data.

```json
{
  "type": "line",
  "name": "Revenue",
  "data": [95, 160, 130, 90],
  "smooth": true,
  "areaStyle": {},
  "symbol": "circle",
  "symbolSize": 8,
  "lineStyle": { "width": 2 }
}
```

Key options:
- `smooth` — `true` for smooth curves, `false` (default) for straight segments
- `areaStyle` — add a filled area below the line (pass `{}` to enable)
- `areaStyle.opacity` — fill transparency (0–1)
- `symbol` — data point marker shape: `"circle"`, `"rect"`, `"triangle"`, `"diamond"`, `"none"`
- `symbolSize` — size of the marker in pixels
- `lineStyle.type` — `"solid"`, `"dashed"`, `"dotted"`
- `connectNulls` — `true` to draw through `null` data gaps

Multiple line series on the same Cartesian axes is the standard pattern for comparison.

### Object data points + tooltip fields (important)

For `xAxis.type: "category"` with `xAxis.data: ["2026-01", ...]`, each line point must supply the **Y value in the `value` property**. Arbitrary keys like `revenue` alone are **ignored** for plotting — the chart will look empty.

Correct pattern (one line = revenue on Y, extra fields for tooltip):

```json
"series": [{
  "type": "line",
  "name": "Revenue",
  "data": [
    { "value": 12450, "orders": 166, "avg_order_value": 75.0 },
    { "value": 13820, "orders": 172, "avg_order_value": 80.3 }
  ]
}]
```

Use `tooltip.formatter` with `_echarts_fn` to show `d.value` (revenue) plus `d.orders`, `d.avg_order_value`, etc.

Wrong (no line drawn):

```json
"data": [{ "revenue": 12450, "orders": 166 }]
```

---

## pie — Pie / Donut Chart

Best for: showing part-to-whole relationships.

```json
{
  "type": "pie",
  "name": "Market Share",
  "radius": ["40%", "70%"],
  "center": ["50%", "50%"],
  "data": [
    { "name": "Chrome",  "value": 65 },
    { "name": "Firefox", "value": 15 },
    { "name": "Safari",  "value": 12 },
    { "name": "Other",   "value": 8  }
  ],
  "label": { "show": true, "formatter": "{b}: {d}%" },
  "roseType": false
}
```

Key options:
- `radius` — single value (pie) or `[inner, outer]` array (donut / ring)
- `center` — `[x, y]` position as pixels or percentages
- `data` — array of `{ name, value }` objects (not a flat array)
- `label.formatter` — template: `{a}` series name, `{b}` item name, `{c}` value, `{d}` percentage
- `roseType` — `"area"` or `"radius"` for a Nightingale (rose) chart
- `emphasis.scaleSize` — how much a slice expands on hover

Pie does **not** use `xAxis` / `yAxis`.

---

## scatter — Scatter Plot

Best for: showing correlation between two numeric variables.

```json
{
  "type": "scatter",
  "name": "Users",
  "data": [[10.0, 8.04], [8.0, 6.95], [13.0, 7.58]],
  "symbolSize": 12,
  "itemStyle": { "opacity": 0.8 }
}
```

Key options:
- `data` — array of `[x, y]` pairs (or `[x, y, value]` for bubble charts)
- `symbolSize` — fixed number or a function `(dataItem) => size`
- Use a third value in each data point and map it to `symbolSize` for bubble charts

---

## heatmap — Heatmap

Best for: two-dimensional data density or matrix comparisons.
Requires `visualMap` to map values to colours.

```json
{
  "type": "heatmap",
  "name": "Activity",
  "data": [
    [0, 0, 5], [0, 1, 1], [1, 0, 3], [1, 1, 8]
  ],
  "label": { "show": true }
}
```

Always pair with:
```json
"visualMap": {
  "min": 0,
  "max": 10,
  "calculable": true,
  "orient": "horizontal",
  "left": "center",
  "bottom": "5%"
}
```

`xAxis` and `yAxis` must both be `type: "category"` with the category labels supplied.
Data items are `[xIndex, yIndex, value]`.

---

## radar — Radar / Spider Chart

Best for: comparing multiple attributes of one or more entities.

```json
{
  "type": "radar",
  "data": [
    {
      "name": "Product A",
      "value": [80, 70, 60, 90, 85]
    }
  ]
}
```

Requires a top-level `radar` key defining the axes:
```json
"radar": {
  "indicator": [
    { "name": "Speed",    "max": 100 },
    { "name": "Accuracy", "max": 100 },
    { "name": "Range",    "max": 100 },
    { "name": "Power",    "max": 100 },
    { "name": "Agility",  "max": 100 }
  ]
}
```

Does **not** use `xAxis` / `yAxis`.

---

## funnel — Funnel Chart

Best for: conversion pipelines (e.g. marketing or sales funnels).

```json
{
  "type": "funnel",
  "name": "Conversion",
  "data": [
    { "name": "Impressions", "value": 100 },
    { "name": "Clicks",      "value": 60  },
    { "name": "Sign-ups",    "value": 30  },
    { "name": "Purchases",   "value": 10  }
  ],
  "sort": "descending",
  "label": { "show": true, "position": "inside" }
}
```

- `sort` — `"ascending"`, `"descending"`, or `"none"`
- Data values control the relative width of each funnel stage.

---

## gauge — Gauge / Speedometer

Best for: single KPI with a target range.

```json
{
  "type": "gauge",
  "name": "Score",
  "detail": { "formatter": "{value}%" },
  "data": [{ "value": 72, "name": "Completion" }]
}
```

Key options:
- `min` / `max` — gauge range
- `startAngle` / `endAngle` — arc angles (default 225 / -45)
- `axisLine.lineStyle.color` — array of `[[threshold, color], ...]` for colour bands

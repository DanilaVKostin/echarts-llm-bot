# ECharts Option Object — Overview

An ECharts chart is configured entirely through a single plain JavaScript/JSON object called
`option`. You pass it to a chart instance via `chart.setOption(option)`.

The top-level keys of `option` each control a distinct aspect of the chart.
All keys are optional; ECharts provides sensible defaults.

---

## title

Defines the chart title (and optional subtitle).

```json
"title": {
  "text": "Monthly Sales",
  "subtext": "2024",
  "left": "center"
}
```

Key properties:
- `text` — main title string
- `subtext` — secondary line below the title
- `left` / `top` / `right` / `bottom` — position (pixel, percent, or `"left"/"center"/"right"`)
- `textStyle.fontSize`, `textStyle.fontWeight`, `textStyle.color`

---

## legend

Controls the legend that identifies each data series.

```json
"legend": {
  "data": ["Sales", "Revenue"],
  "orient": "horizontal",
  "bottom": 0
}
```

Key properties:
- `data` — array of series names (must match `series[].name`)
- `orient` — `"horizontal"` (default) or `"vertical"`
- `left` / `right` / `top` / `bottom` — position
- `type` — `"plain"` (default) or `"scroll"` for many series
- `show` — `true` / `false`

---

## tooltip

Configures the floating tooltip shown when hovering over chart elements.

```json
"tooltip": {
  "trigger": "axis",
  "axisPointer": { "type": "shadow" }
}
```

Key properties:
- `trigger` — `"item"` (per data point) or `"axis"` (all series on the same axis value)
- `axisPointer.type` — `"line"`, `"shadow"`, or `"cross"`
- `formatter` — custom string template or function
- `show` — `true` / `false`

---

## xAxis

Defines the horizontal axis (Cartesian charts).

```json
"xAxis": {
  "type": "category",
  "data": ["Jan", "Feb", "Mar", "Apr"]
}
```

Key properties:
- `type` — `"category"` (discrete labels), `"value"` (continuous numeric), `"time"`, `"log"`
- `data` — array of category labels (only for `type: "category"`)
- `name` — axis label
- `axisLabel.rotate` — rotate labels (e.g. `45` degrees) to prevent overlap
- `boundaryGap` — `true` (bars centred on labels) / `false` (line starts at axis edge)

---

## yAxis

Defines the vertical axis (Cartesian charts). Same properties as `xAxis`.

```json
"yAxis": {
  "type": "value",
  "name": "Units Sold"
}
```

For dual-axis charts use an array: `"yAxis": [{...}, {...}]`.
Reference a specific y-axis in a series with `"yAxisIndex": 1`.

---

## series

An array of one or more data series. Each series object must have a `type`.

```json
"series": [
  {
    "name": "Sales",
    "type": "bar",
    "data": [120, 200, 150, 80]
  }
]
```

Common properties shared by all series types:
- `type` — chart type (see Series Types document)
- `name` — shown in legend and tooltip
- `data` — array of values (format depends on type)
- `color` — override the global palette colour
- `label.show` — show data labels on the chart
- `emphasis` — style when the element is highlighted (hover)

---

## color

Global palette array. Applied to series in order.

```json
"color": ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de"]
```

---

## grid

Controls the drawing area for Cartesian charts (margin from the chart edges).

```json
"grid": {
  "left": "10%",
  "right": "5%",
  "bottom": "15%",
  "containLabel": true
}
```

`containLabel: true` ensures axis labels are included within the grid boundary, preventing clipping.

---

## dataZoom

Adds interactive zoom/pan controls.

```json
"dataZoom": [
  { "type": "slider", "xAxisIndex": 0 },
  { "type": "inside", "xAxisIndex": 0 }
]
```

- `type: "slider"` — visible draggable bar
- `type: "inside"` — mouse-wheel / touch zoom with no visible UI element

---

## toolbox

Adds a built-in toolbar with icons for saving, zooming, data view, etc.

```json
"toolbox": {
  "feature": {
    "saveAsImage": {},
    "dataView": { "readOnly": false },
    "restore": {},
    "dataZoom": {}
  }
}
```

---

## dataset

Alternative to embedding data in each series — centralises data in one place.

```json
"dataset": {
  "dimensions": ["month", "sales", "revenue"],
  "source": [
    ["Jan", 120, 95],
    ["Feb", 200, 160],
    ["Mar", 150, 130]
  ]
}
```

Series then reference the dataset by index via `datasetIndex` and declare
`encode: { x: "month", y: "sales" }`.

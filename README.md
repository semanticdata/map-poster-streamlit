# Map Poster Streamlit

This is a Streamlit port of [MapToPoster](https://github.com/originalankur/maptoposter). All credit for the idea and original implementation goes to that project. I just wanted to run it with , a tool I'm more familiar with.

<img alt="Example Poster of Crystal, Minnesota" src="./assets/examples/poster-1.png" width="400" />
<img alt="Example Poster of Minneapolis, Minnesota" src="./assets/examples/poster-2.png" width="400" />

## Development

```bash
uv run streamlit run app.py
```

```bash
uv run ruff format
uv run ruff check
```

## Stack

- **Streamlit** — UI
- **OSMnx** — OpenStreetMap data fetching
- **Matplotlib** — map rendering

## Attributions

Map data © [OpenStreetMap](https://www.openstreetmap.org/).

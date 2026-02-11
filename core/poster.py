"""Poster Generation Module

Core functionality for generating map posters from OSM data.
"""

import io
import logging
import time
from threading import RLock
from typing import Any

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
from geopandas import GeoDataFrame
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim
from matplotlib.font_manager import FontProperties
from networkx import MultiDiGraph
from shapely.geometry import Point

from .cache import CacheError, cache_get, cache_set
from .font_management import load_fonts

logger = logging.getLogger(__name__)

_plot_lock = RLock()

ox.settings.use_cache = True
ox.settings.log_console = False

FONTS = load_fonts()

NOMINATIM_USER_AGENT = "streamlit_map_poster"
NOMINATIM_TIMEOUT = 10
RATE_LIMIT_DELAY = 1.0

ROAD_HIERARCHY = {
    "motorway": ["motorway", "motorway_link"],
    "primary": ["trunk", "trunk_link", "primary", "primary_link"],
    "secondary": ["secondary", "secondary_link"],
    "tertiary": ["tertiary", "tertiary_link"],
    "residential": ["residential", "living_street", "unclassified"],
}

TYPOGRAPHY_SCALE = {
    "main": 60,
    "sub": 22,
    "coords": 14,
    "attr": 8,
}

TEXT_POSITIONS = {
    "city_y": 0.14,
    "country_y": 0.10,
    "coords_y": 0.07,
    "divider_y": 0.125,
    "divider_x_start": 0.4,
    "divider_x_end": 0.6,
    "attr_x": 0.98,
    "attr_y": 0.02,
}

GRADIENT_EXTENT = {
    "bottom": (0.0, 0.25),
    "top": (0.75, 1.0),
}


def is_latin_script(text: str) -> bool:
    """
    Check if text is primarily Latin script.

    Args:
        text: Text to analyze

    Returns:
        True if text is primarily Latin script, False otherwise
    """
    if not text:
        return True

    latin_count = 0
    total_alpha = 0

    for char in text:
        if char.isalpha():
            total_alpha += 1
            if ord(char) < 0x250:
                latin_count += 1

    if total_alpha == 0:
        return True

    return (latin_count / total_alpha) > 0.8


def create_gradient_fade(ax, color: str, location: str = "bottom", zorder: int = 10):
    """
    Creates a fade effect at the top or bottom of the map.

    Args:
        ax: Matplotlib axis
        color: Color for the gradient
        location: 'bottom' or 'top'
        zorder: Z-order for layering
    """
    vals = np.linspace(0, 1, 256).reshape(-1, 1)
    gradient = np.hstack((vals, vals))

    rgb = mcolors.to_rgb(color)
    my_colors = np.zeros((256, 4))
    my_colors[:, 0] = rgb[0]
    my_colors[:, 1] = rgb[1]
    my_colors[:, 2] = rgb[2]

    extent_range = GRADIENT_EXTENT.get(location, GRADIENT_EXTENT["bottom"])
    extent_y_start, extent_y_end = extent_range

    if location == "bottom":
        my_colors[:, 3] = np.linspace(1, 0, 256)
    else:
        my_colors[:, 3] = np.linspace(0, 1, 256)

    custom_cmap = mcolors.ListedColormap(my_colors)

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    y_range = ylim[1] - ylim[0]

    y_bottom = ylim[0] + y_range * extent_y_start
    y_top = ylim[0] + y_range * extent_y_end

    ax.imshow(
        gradient,
        extent=[xlim[0], xlim[1], y_bottom, y_top],
        aspect="auto",
        cmap=custom_cmap,
        zorder=zorder,
        origin="lower",
    )


def get_edge_colors_by_type(
    g: MultiDiGraph,
    theme: dict[str, str],
    road_colors: dict[str, bool] | None = None,
    normalize_all: bool = False,
) -> list[str]:
    """
    Assigns colors to edges based on road type hierarchy.

    Args:
        g: NetworkX graph
        theme: Theme dictionary with color values
        road_colors: Dictionary mapping road types to bool (whether to use special colors).
                     If None, all roads use special colors.
        normalize_all: If True, all roads use the default color regardless of road_colors.

    Returns:
        List of colors corresponding to each edge
    """
    if road_colors is None:
        road_colors = {
            "motorway": True,
            "primary": True,
            "secondary": True,
            "tertiary": True,
            "residential": True,
        }

    edge_colors = []

    for _u, _v, data in g.edges(data=True):
        highway = data.get("highway", "unclassified")

        if isinstance(highway, list):
            highway = highway[0] if highway else "unclassified"

        # Default color for all roads
        color = theme["road_default"]

        # Only apply special colors if not normalizing all
        if not normalize_all:
            for road_type, road_keys in ROAD_HIERARCHY.items():
                if highway in road_keys:
                    if road_colors.get(road_type, True):
                        theme_key = f"road_{road_type}"
                        color = theme.get(theme_key, theme["road_default"])
                    break

        edge_colors.append(color)

    return edge_colors


ROAD_WIDTHS = {
    "motorway": 1.2,
    "primary": 1.0,
    "secondary": 0.8,
    "tertiary": 0.6,
    "residential": 0.4,
}


def get_edge_widths_by_type(
    g: MultiDiGraph,
    road_thickness: dict[str, bool] | None = None,
    normalize_all: bool = False,
) -> list[float]:
    """
    Assigns line widths to edges based on road type.

    Args:
        g: NetworkX graph
        road_thickness: Dictionary mapping road types to bool (whether to use special thickness).
                       If None, all roads use special thickness.
        normalize_all: If True, all roads use the same width regardless of road_thickness.

    Returns:
        List of widths corresponding to each edge
    """
    if road_thickness is None:
        road_thickness = {
            "motorway": True,
            "primary": True,
            "secondary": True,
            "tertiary": True,
            "residential": True,
        }

    edge_widths = []

    for _u, _v, data in g.edges(data=True):
        highway = data.get("highway", "unclassified")

        if isinstance(highway, list):
            highway = highway[0] if highway else "unclassified"

        # Default width for all roads
        width = ROAD_WIDTHS.get("residential", 0.4)

        # Only apply special thickness if not normalizing all
        if not normalize_all:
            for road_type, road_keys in ROAD_HIERARCHY.items():
                if highway in road_keys:
                    if road_thickness.get(road_type, True):
                        width = ROAD_WIDTHS.get(road_type, width)
                    break

        edge_widths.append(width)

    return edge_widths


def get_coordinates(city: str, country: str) -> tuple[float, float] | None:
    """
    Fetches coordinates for a given city and country using geopy.

    Args:
        city: City name
        country: Country name

    Returns:
        (latitude, longitude) tuple or None if lookup fails
    """
    if not city or not country:
        logger.warning("Empty city or country provided to get_coordinates")
        return None

    coords_key = f"coords_{city.lower()}_{country.lower()}"
    cached = cache_get(coords_key)
    if cached:
        logger.debug(f"Using cached coordinates for {city}, {country}")
        return cached

    geolocator = Nominatim(user_agent=NOMINATIM_USER_AGENT, timeout=NOMINATIM_TIMEOUT)

    try:
        time.sleep(RATE_LIMIT_DELAY)
        location = geolocator.geocode(f"{city}, {country}")

        if location:
            coords = (location.latitude, location.longitude)
            try:
                cache_set(coords_key, coords)
                logger.debug(f"Cached coordinates for {city}, {country}")
            except CacheError as e:
                logger.warning(f"Failed to cache coordinates: {e}")
            return coords

        logger.warning(f"Geocoding found no results for '{city}, {country}'")
        return None

    except GeocoderTimedOut:
        logger.error(f"Geocoding timeout for '{city}, {country}'")
        return None
    except GeocoderUnavailable as e:
        logger.error(f"Geocoding service unavailable: {e}")
        return None
    except (ValueError, AttributeError) as e:
        logger.error(f"Invalid geocoding response for '{city}, {country}': {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error geocoding '{city}, {country}': {e}")
        return None


def fetch_graph(point: tuple[float, float], dist: int) -> MultiDiGraph | None:
    """
    Fetch street network graph from OpenStreetMap.

    Args:
        point: (latitude, longitude) tuple for center point
        dist: Distance in meters from center point

    Returns:
        MultiDiGraph of street network, or None if fetch fails
    """
    lat, lon = point
    graph_key = f"graph_{lat:.4f}_{lon:.4f}_{dist}"
    cached = cache_get(graph_key)
    if cached is not None:
        logger.debug(f"Using cached graph for {lat:.4f}, {lon:.4f}")
        return cached

    try:
        g = ox.graph_from_point(
            point, dist=dist, dist_type="bbox", network_type="all", truncate_by_edge=True
        )
        time.sleep(RATE_LIMIT_DELAY / 2)
        try:
            cache_set(graph_key, g)
            logger.debug(f"Cached graph for {lat:.4f}, {lon:.4f}")
        except CacheError as e:
            logger.warning(f"Failed to cache graph: {e}")
        return g

    except ox._errors.InsufficientResponseError:
        logger.warning(f"Insufficient OSM data for location {lat:.4f}, {lon:.4f}")
        return None
    except Exception as e:
        logger.exception(f"Failed to fetch graph for {lat:.4f}, {lon:.4f}: {e}")
        return None


def fetch_features(
    point: tuple[float, float], dist: int, tags: dict[str, Any], name: str
) -> GeoDataFrame | None:
    """
    Fetch geographic features (water, parks, etc.) from OpenStreetMap.

    Args:
        point: (latitude, longitude) tuple for center point
        dist: Distance in meters from center point
        tags: Dictionary of OSM tags to filter features
        name: Name for this feature type (for caching)

    Returns:
        GeoDataFrame of features, or None if fetch fails
    """
    lat, lon = point
    tag_str = "_".join(tags.keys())
    features_key = f"{name}_{lat:.4f}_{lon:.4f}_{dist}_{tag_str}"
    cached = cache_get(features_key)
    if cached is not None:
        logger.debug(f"Using cached {name} features")
        return cached

    try:
        data = ox.features_from_point(point, tags=tags, dist=dist)
        time.sleep(RATE_LIMIT_DELAY / 3)
        try:
            cache_set(features_key, data)
            logger.debug(f"Cached {name} features")
        except CacheError as e:
            logger.warning(f"Failed to cache {name} features: {e}")
        return data

    except ox._errors.InsufficientResponseError:
        logger.debug(f"No {name} features found for location")
        return None
    except Exception as e:
        logger.debug(f"Failed to fetch {name} features: {e}")
        return None


def get_crop_limits(g_proj, center_lat_lon: tuple[float, float], fig, dist: int):
    """
    Calculate crop limits to preserve aspect ratio.

    Args:
        g_proj: Projected graph
        center_lat_lon: (latitude, longitude) of center
        fig: Matplotlib figure
        dist: Distance in meters

    Returns:
        Tuple of (xlim, ylim) tuples
    """
    lat, lon = center_lat_lon

    center = ox.projection.project_geometry(
        Point(lon, lat), crs="EPSG:4326", to_crs=g_proj.graph["crs"]
    )[0]
    center_x, center_y = center.x, center.y

    fig_width, fig_height = fig.get_size_inches()
    aspect = fig_width / fig_height

    half_x = dist
    half_y = dist

    if aspect > 1:
        half_y = half_x / aspect
    else:
        half_x = half_y * aspect

    return (
        (center_x - half_x, center_x + half_x),
        (center_y - half_y, center_y + half_y),
    )


def create_poster(
    city: str,
    country: str,
    point: tuple[float, float],
    dist: int,
    width: float = 12,
    height: float = 16,
    theme: dict[str, str] | None = None,
    fonts: dict[str, str] | None = None,
    display_city: str | None = None,
    display_country: str | None = None,
    road_colors: dict[str, bool] | None = None,
    road_thickness: dict[str, bool] | None = None,
    normalize_all: bool = False,
) -> plt.Figure | None:
    """
    Generate a complete map poster with roads, water, parks, and typography.

    Args:
        city: City name
        country: Country name
        point: (latitude, longitude) tuple for map center
        dist: Map radius in meters
        width: Poster width in inches
        height: Poster height in inches
        theme: Theme dictionary (uses default if None)
        fonts: Font dictionary with paths
        display_city: Override city name on poster
        display_country: Override country name on poster
        road_colors: Dictionary mapping road types to bool for special colors
        road_thickness: Dictionary mapping road types to bool for special thickness
        normalize_all: If True, all roads use default color and thickness

    Returns:
        Matplotlib figure or None if generation fails
    """
    if theme is None:
        theme = {
            "bg": "#F5EDE4",
            "text": "#8B4513",
            "gradient_color": "#F5EDE4",
            "water": "#A8C4C4",
            "parks": "#E8E0D0",
            "road_motorway": "#A0522D",
            "road_primary": "#B8653A",
            "road_secondary": "#C9846A",
            "road_tertiary": "#D9A08A",
            "road_residential": "#E5C4B0",
            "road_default": "#D9A08A",
        }

    display_city = display_city or city
    display_country = display_country or country
    active_fonts = fonts or FONTS

    with _plot_lock:
        try:
            compensated_dist = dist * (max(height, width) / min(height, width)) / 4

            g = fetch_graph(point, compensated_dist)
            if g is None:
                return None

            water = fetch_features(
                point,
                compensated_dist,
                tags={"natural": ["water", "bay", "strait"], "waterway": "riverbank"},
                name="water",
            )

            parks = fetch_features(
                point,
                compensated_dist,
                tags={"leisure": "park", "landuse": "grass"},
                name="parks",
            )

            fig, ax = plt.subplots(figsize=(width, height), facecolor=theme["bg"])
            ax.set_facecolor(theme["bg"])
            ax.set_position((0.0, 0.0, 1.0, 1.0))

            g_proj = ox.project_graph(g)

            if water is not None and not water.empty:
                water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
                if not water_polys.empty:
                    try:
                        water_polys = ox.projection.project_gdf(water_polys)
                    except Exception:
                        water_polys = water_polys.to_crs(g_proj.graph["crs"])
                    water_polys.plot(ax=ax, facecolor=theme["water"], edgecolor="none", zorder=0.5)

            if parks is not None and not parks.empty:
                parks_polys = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])]
                if not parks_polys.empty:
                    try:
                        parks_polys = ox.projection.project_gdf(parks_polys)
                    except Exception:
                        parks_polys = parks_polys.to_crs(g_proj.graph["crs"])
                    parks_polys.plot(ax=ax, facecolor=theme["parks"], edgecolor="none", zorder=0.8)

            edge_colors = get_edge_colors_by_type(g_proj, theme, road_colors, normalize_all)
            edge_widths = get_edge_widths_by_type(g_proj, road_thickness, normalize_all)

            crop_xlim, crop_ylim = get_crop_limits(g_proj, point, fig, compensated_dist)

            ox.plot_graph(
                g_proj,
                ax=ax,
                bgcolor=theme["bg"],
                node_size=0,
                edge_color=edge_colors,
                edge_linewidth=edge_widths,
                show=False,
                close=False,
            )
            ax.set_aspect("equal", adjustable="box")
            ax.set_xlim(crop_xlim)
            ax.set_ylim(crop_ylim)

            create_gradient_fade(ax, theme["gradient_color"], location="bottom", zorder=10)
            create_gradient_fade(ax, theme["gradient_color"], location="top", zorder=10)

            scale_factor = min(height, width) / 12.0

            if active_fonts:
                font_sub = FontProperties(
                    fname=active_fonts["light"], size=TYPOGRAPHY_SCALE["sub"] * scale_factor
                )
                font_coords = FontProperties(
                    fname=active_fonts["regular"], size=TYPOGRAPHY_SCALE["coords"] * scale_factor
                )
                font_attr = FontProperties(
                    fname=active_fonts["light"], size=TYPOGRAPHY_SCALE["attr"] * scale_factor
                )
            else:
                font_sub = FontProperties(
                    family="monospace", weight="normal", size=TYPOGRAPHY_SCALE["sub"] * scale_factor
                )
                font_coords = FontProperties(
                    family="monospace", size=TYPOGRAPHY_SCALE["coords"] * scale_factor
                )
                font_attr = FontProperties(
                    family="monospace", size=TYPOGRAPHY_SCALE["attr"] * scale_factor
                )

            if is_latin_script(display_city):
                spaced_city = "  ".join(list(display_city.upper()))
            else:
                spaced_city = display_city

            base_adjusted_main = TYPOGRAPHY_SCALE["main"] * scale_factor
            city_char_count = len(display_city)

            if city_char_count > 10:
                length_factor = 10 / city_char_count
                adjusted_font_size = max(base_adjusted_main * length_factor, 10 * scale_factor)
            else:
                adjusted_font_size = base_adjusted_main

            if active_fonts:
                font_main_adjusted = FontProperties(
                    fname=active_fonts["bold"], size=adjusted_font_size
                )
            else:
                font_main_adjusted = FontProperties(
                    family="monospace", weight="bold", size=adjusted_font_size
                )

            ax.text(
                0.5,
                TEXT_POSITIONS["city_y"],
                spaced_city,
                transform=ax.transAxes,
                color=theme["text"],
                ha="center",
                fontproperties=font_main_adjusted,
                zorder=11,
            )

            ax.text(
                0.5,
                TEXT_POSITIONS["country_y"],
                display_country.upper(),
                transform=ax.transAxes,
                color=theme["text"],
                ha="center",
                fontproperties=font_sub,
                zorder=11,
            )

            lat, lon = point
            coords = (
                f"{lat:.4f}° N / {lon:.4f}° E" if lat >= 0 else f"{abs(lat):.4f}° S / {lon:.4f}° E"
            )
            if lon < 0:
                coords = coords.replace("E", "W")

            ax.text(
                0.5,
                TEXT_POSITIONS["coords_y"],
                coords,
                transform=ax.transAxes,
                color=theme["text"],
                alpha=0.7,
                ha="center",
                fontproperties=font_coords,
                zorder=11,
            )

            ax.plot(
                [TEXT_POSITIONS["divider_x_start"], TEXT_POSITIONS["divider_x_end"]],
                [TEXT_POSITIONS["divider_y"], TEXT_POSITIONS["divider_y"]],
                transform=ax.transAxes,
                color=theme["text"],
                linewidth=1 * scale_factor,
                zorder=11,
            )

            if FONTS:
                font_attr = FontProperties(fname=FONTS["light"], size=TYPOGRAPHY_SCALE["attr"])
            else:
                font_attr = FontProperties(family="monospace", size=TYPOGRAPHY_SCALE["attr"])

            ax.text(
                TEXT_POSITIONS["attr_x"],
                TEXT_POSITIONS["attr_y"],
                "© OpenStreetMap contributors",
                transform=ax.transAxes,
                color=theme["text"],
                alpha=0.5,
                ha="right",
                va="bottom",
                fontproperties=font_attr,
                zorder=11,
            )

            return fig

        except Exception as e:
            logger.exception(f"Error creating poster for {city}, {country}: {e}")
            return None


def fig_to_bytes(fig: plt.Figure, format: str = "png", dpi: int = 300) -> bytes:
    """
    Convert matplotlib figure to bytes for download.

    Args:
        fig: Matplotlib figure
        format: Output format (png, svg, pdf)
        dpi: Resolution for PNG

    Returns:
        Image bytes
    """
    buf = io.BytesIO()
    save_kwargs = {
        "format": format,
        "facecolor": fig.get_facecolor(),
        "bbox_inches": "tight",
        "pad_inches": 0.05,
    }

    if format.lower() == "png":
        save_kwargs["dpi"] = dpi

    fig.savefig(buf, **save_kwargs)
    buf.seek(0)
    return buf.read()


def close_fig(fig: plt.Figure) -> None:
    """
    Close figure and cleanup.

    Args:
        fig: Matplotlib figure to close
    """
    plt.close(fig)

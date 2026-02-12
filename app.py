"""Streamlit Map Poster Generator

An interactive web application for generating beautiful city map posters.
"""

import random
from datetime import datetime

import matplotlib
import streamlit as st

from core import (
    clear_geocoding_debug_info,
    close_fig,
    create_poster,
    fig_to_bytes,
    get_all_themes_info,
    get_coordinates,
    get_geocoding_debug_info,
    load_theme,
)
from core.cache import cache_clear, cache_count, cache_size
from core.logging_config import get_logger, setup_logging

matplotlib.use("Agg")
setup_logging()
logger = get_logger(__name__)

st.set_page_config(
    page_title="Map Poster Generator",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

EXAMPLE_CITIES = [
    ("Paris", "France"),
    ("Tokyo", "Japan"),
    ("New York", "USA"),
    ("London", "UK"),
    ("Barcelona", "Spain"),
    ("Venice", "Italy"),
    ("Dubai", "UAE"),
    ("Singapore", "Singapore"),
]


def init_session_state():
    """Initialize session state variables."""
    if "location" not in st.session_state:
        st.session_state.location = {
            "city": "",
            "country": "",
            "coords": None,
            "mode": "coordinates",  # "city_country" or "coordinates"
            "lat": "",
            "lon": "",
        }
    if "settings" not in st.session_state:
        st.session_state.settings = {
            "theme": "terracotta",
            "distance": 18000,
            "width": 12.0,
            "height": 16.0,
            "format": "png",
            "dpi": 300.0,
        }
    if "preset_just_applied" not in st.session_state:
        st.session_state.preset_just_applied = False
    if "preset_counter" not in st.session_state:
        st.session_state.preset_counter = 0
    if "road_colors" not in st.session_state:
        st.session_state.road_colors = {
            "motorway": True,
            "primary": True,
            "secondary": True,
            "tertiary": True,
            "residential": True,
        }
    if "road_thickness" not in st.session_state:
        st.session_state.road_thickness = {
            "motorway": True,
            "primary": True,
            "secondary": True,
            "tertiary": True,
            "residential": True,
        }
    if "normalize_all" not in st.session_state:
        st.session_state.normalize_all = False
    if "generated_poster" not in st.session_state:
        st.session_state.generated_poster = None
    if "last_generation_time" not in st.session_state:
        st.session_state.last_generation_time = None


def calculate_aspect_ratio_display(width, height):
    """
    Calculate human-readable aspect ratio from dimensions.

    Args:
        width: Width in inches
        height: Height in inches

    Returns:
        Human-readable aspect ratio string
    """
    if height == 0:
        return "Custom"

    ratio = width / height
    ratio_map = {
        (16 / 9): "16:9",
        (16 / 10): "16:10",
        (9 / 16): "9:16",
        (9 / 19): "9:19",
        (9 / 20): "9:20",
        (3 / 4): "3:4",
        (2 / 3): "2:3",
        (1 / 1): "1:1",
        (11.7 / 8.3): "A4",
    }

    for exact_ratio, name in ratio_map.items():
        if abs(ratio - exact_ratio) < 0.01:
            return name

    return f"{ratio:.2f}:1"


def apply_aspect_ratio(width_ratio, height_ratio, base_width):
    """
    Apply aspect ratio while maintaining reasonable dimensions.

    Args:
        width_ratio: Width part of aspect ratio (e.g., 16 for 16:9)
        height_ratio: Height part of aspect ratio (e.g., 9 for 16:9)
        base_width: Desired width in inches
    """
    base_width = float(base_width)
    base_height = base_width * (float(height_ratio) / float(width_ratio))

    if base_height < 4:
        scale_factor = 4.0 / base_height
        base_width *= scale_factor
        base_height = 4.0
    elif base_height > 20:
        scale_factor = 20.0 / base_height
        base_width *= scale_factor
        base_height = 20.0

    new_width = round(base_width, 1)
    new_height = round(base_height, 1)

    st.session_state.settings["width"] = new_width
    st.session_state.settings["height"] = new_height
    st.session_state.preset_just_applied = True

    logger.info(f"Aspect ratio applied: {width_ratio}:{height_ratio} -> {new_width}x{new_height}")

    # Force widget keys to reset by incrementing a counter
    if "preset_counter" not in st.session_state:
        st.session_state.preset_counter = 0
    st.session_state.preset_counter += 1

    st.rerun()


def render_sidebar():
    """Render sidebar configuration panel."""
    st.sidebar.title("⚙️ Configuration")

    with st.sidebar.expander("📍 Location", expanded=True):
        location_mode = st.radio(
            "Input Mode",
            options=["City/Country", "Coordinates"],
            index=0 if st.session_state.location["mode"] == "city_country" else 1,
            key="sidebar_location_mode",
        )
        st.session_state.location["mode"] = (
            "city_country" if location_mode == "City/Country" else "coordinates"
        )

        if st.session_state.location["mode"] == "city_country":
            city = st.text_input(
                "City",
                value=st.session_state.location["city"],
                placeholder="e.g. Paris",
                key="sidebar_city",
            )
            st.session_state.location["city"] = city
            country = st.text_input(
                "Country",
                value=st.session_state.location["country"],
                placeholder="e.g. France",
                key="sidebar_country",
            )
            st.session_state.location["country"] = country
        else:
            lat = st.text_input(
                "Latitude",
                value=st.session_state.location["lat"],
                placeholder="e.g. 48.8566",
                key="sidebar_lat",
            )
            st.session_state.location["lat"] = lat
            lon = st.text_input(
                "Longitude",
                value=st.session_state.location["lon"],
                placeholder="e.g. 2.3522",
                key="sidebar_lon",
            )
            st.session_state.location["lon"] = lon

    with st.sidebar.expander("🎨 Visual Settings", expanded=True):
        themes_info = get_all_themes_info()
        theme_options = {f"{t['name']} ({t['id']})": t["id"] for t in themes_info}
        theme_options_display = list(theme_options.keys())

        current_theme_display = next(
            (k for k, v in theme_options.items() if v == st.session_state.settings["theme"]),
            theme_options_display[0] if theme_options_display else "terracotta",
        )

        selected_theme_display = st.selectbox(
            "Theme",
            options=theme_options_display,
            index=theme_options_display.index(current_theme_display)
            if current_theme_display in theme_options_display
            else 0,
            key="sidebar_theme",
        )
        st.session_state.settings["theme"] = theme_options.get(selected_theme_display, "terracotta")

        col1, col2 = st.columns(2)
        with col1:
            width = st.number_input(
                "Width (in)",
                min_value=4.0,
                max_value=20.0,
                value=st.session_state.settings["width"],
                step=0.1,
                key=f"sidebar_width_{st.session_state.get('preset_counter', 0)}",
            )
        with col2:
            height = st.number_input(
                "Height (in)",
                min_value=4.0,
                max_value=20.0,
                value=st.session_state.settings["height"],
                step=0.1,
                key=f"sidebar_height_{st.session_state.get('preset_counter', 0)}",
            )

        # Always save from number inputs (preset flag only controls whether to skip on THIS rerun)
        st.session_state.settings["width"] = float(width)
        st.session_state.settings["height"] = float(height)

        # Reset preset flag after we've processed the number inputs
        if st.session_state.preset_just_applied:
            logger.info("Preset was applied, skipping number input values")
            st.session_state.preset_just_applied = False
            # Restore session state values that were set by preset
            st.session_state.settings["width"] = float(st.session_state.settings["width"])
            st.session_state.settings["height"] = float(st.session_state.settings["height"])

        width_px = int(width * st.session_state.settings["dpi"])
        height_px = int(height * st.session_state.settings["dpi"])
        st.caption(f"📐 Output: {width:.1f} in × {height:.1f} in ({width_px} × {height_px} px)")

        distance = st.slider(
            "Map Radius (m)",
            min_value=1000,
            max_value=30000,
            value=st.session_state.settings["distance"],
            step=1000,
            key="sidebar_distance",
        )
        st.session_state.settings["distance"] = int(distance)

        output_format = st.selectbox(
            "Output Format",
            options=["png", "svg", "pdf"],
            index=["png", "svg", "pdf"].index(st.session_state.settings["format"]),
            key="sidebar_format",
        )
        st.session_state.settings["format"] = output_format

        dpi = st.slider(
            "DPI (dots per inch)",
            min_value=72.0,
            max_value=600.0,
            value=st.session_state.settings["dpi"],
            step=72.0,
            help="72-96 DPI for web/screens, 150-200 DPI for standard print, 300 DPI for high-quality print",
            key="sidebar_dpi",
        )
        st.session_state.settings["dpi"] = float(dpi)

    with st.sidebar.expander("📝 Display Names"):
        display_city = st.text_input(
            "City Name (override)",
            placeholder="Leave blank to use default",
            key="sidebar_display_city",
        )
        display_country = st.text_input(
            "Country Name (override)",
            placeholder="Leave blank to use default",
            key="sidebar_display_country",
        )
        st.session_state.location["display_city"] = display_city if display_city else None
        st.session_state.location["display_country"] = display_country if display_country else None

    with st.sidebar.expander("📐 Aspect Ratio Presets"):
        st.caption("Quick-select common aspect ratios:")

        # Show current aspect ratio prominently
        width = st.session_state.settings.get("width", 12.0)
        height = st.session_state.settings.get("height", 16.0)

        current_ratio = calculate_aspect_ratio_display(width, height)
        st.info(f"📐 Current: {current_ratio}")

        st.markdown("**Desktop / Laptop (Landscape)**")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("16:9", key="preset_16_9", use_container_width=True):
                apply_aspect_ratio(16, 9, 12)
        with col2:
            if st.button("16:10", key="preset_16_10", use_container_width=True):
                apply_aspect_ratio(16, 10, 12)

        st.markdown("**Phone (Portrait)**")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("9:16", key="preset_9_16", use_container_width=True):
                apply_aspect_ratio(9, 16, 9)
        with col2:
            if st.button("9:19", key="preset_9_19", use_container_width=True):
                apply_aspect_ratio(9, 19, 9)
        with col3:
            if st.button("9:20", key="preset_9_20", use_container_width=True):
                apply_aspect_ratio(9, 20, 9)

        st.markdown("**Print / Poster**")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("3:4 ⭐", key="preset_3_4", use_container_width=True):
                apply_aspect_ratio(3, 4, 12)
        with col2:
            if st.button("2:3", key="preset_2_3", use_container_width=True):
                apply_aspect_ratio(2, 3, 12)
        with col3:
            if st.button("A4", key="preset_a4", use_container_width=True):
                st.session_state.settings["width"] = 11.7
                st.session_state.settings["height"] = 8.3
                st.rerun()

        st.markdown("**Social Media**")
        if st.button("1:1 (Instagram)", key="preset_1_1", use_container_width=True):
            apply_aspect_ratio(1, 1, 12)

        st.divider()
        st.caption("💡 Tips:")
        st.caption("- Use presets for quick aspect ratios")
        st.caption("- Manually adjust width/height for exact dimensions")
        st.caption("- Pixel dimensions update with DPI setting")

    with st.sidebar.expander("🛣️ Road Styles"):
        # Global normalize option
        st.session_state.normalize_all = st.checkbox(
            "🔄 Normalize All",
            value=st.session_state.normalize_all,
            help="All roads use the same color and thickness",
            key="sidebar_normalize_all",
        )

        if st.session_state.normalize_all:
            st.caption("All options below are disabled when Normalize All is on")
        else:
            st.caption("Enable special colors and thicknesses per road type:")

        st.divider()

        disabled = st.session_state.normalize_all

        # Motorways
        st.markdown("**Motorways**")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.road_colors["motorway"] = st.checkbox(
                "Color",
                value=st.session_state.road_colors["motorway"],
                key="color_motorway",
                disabled=disabled,
            )
        with col2:
            st.session_state.road_thickness["motorway"] = st.checkbox(
                "Thickness",
                value=st.session_state.road_thickness["motorway"],
                key="thickness_motorway",
                disabled=disabled,
            )

        # Primary Roads
        st.markdown("**Primary Roads**")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.road_colors["primary"] = st.checkbox(
                "Color",
                value=st.session_state.road_colors["primary"],
                key="color_primary",
                disabled=disabled,
            )
        with col2:
            st.session_state.road_thickness["primary"] = st.checkbox(
                "Thickness",
                value=st.session_state.road_thickness["primary"],
                key="thickness_primary",
                disabled=disabled,
            )

        # Secondary Roads
        st.markdown("**Secondary Roads**")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.road_colors["secondary"] = st.checkbox(
                "Color",
                value=st.session_state.road_colors["secondary"],
                key="color_secondary",
                disabled=disabled,
            )
        with col2:
            st.session_state.road_thickness["secondary"] = st.checkbox(
                "Thickness",
                value=st.session_state.road_thickness["secondary"],
                key="thickness_secondary",
                disabled=disabled,
            )

        # Tertiary Roads
        st.markdown("**Tertiary Roads**")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.road_colors["tertiary"] = st.checkbox(
                "Color",
                value=st.session_state.road_colors["tertiary"],
                key="color_tertiary",
                disabled=disabled,
            )
        with col2:
            st.session_state.road_thickness["tertiary"] = st.checkbox(
                "Thickness",
                value=st.session_state.road_thickness["tertiary"],
                key="thickness_tertiary",
                disabled=disabled,
            )

        # Residential Roads
        st.markdown("**Residential Roads**")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.road_colors["residential"] = st.checkbox(
                "Color",
                value=st.session_state.road_colors["residential"],
                key="color_residential",
                disabled=disabled,
            )
        with col2:
            st.session_state.road_thickness["residential"] = st.checkbox(
                "Thickness",
                value=st.session_state.road_thickness["residential"],
                key="thickness_residential",
                disabled=disabled,
            )


def is_rate_limit_error():
    """Check if last geocoding error was due to rate limiting."""
    geo_debug = get_geocoding_debug_info()
    last_error = geo_debug.get("last_error", "")
    if not last_error:
        return False
    return (
        "509" in last_error or "Bandwidth Limit" in last_error or "rate limit" in last_error.lower()
    )


def render_debug_panel():
    """Render debug panel (hidden behind checkbox)."""
    show_debug = st.sidebar.toggle("🐛 Debug Mode", value=False)

    if show_debug:
        with st.sidebar.expander("💾 Cache"):
            count = cache_count()
            size = cache_size()

            col1, col2 = st.columns(2)
            col1.metric("Items", count)
            col2.write(f"{size / 1024:.1f} KB")

            if st.button("Clear Cache", key="clear_cache_button", use_container_width=True):
                cache_clear()
                st.success("Cache cleared!")
                st.rerun()

        with st.sidebar.expander("🌍 Geocoding Debug"):
            geo_debug = get_geocoding_debug_info()

            col1, col2, col3 = st.columns(3)
            col1.metric("Requests", geo_debug["request_count"])
            col2.metric("Success", geo_debug["success_count"], delta_color="normal")
            col3.metric("Failed", geo_debug["failure_count"], delta_color="inverse")

            if geo_debug["last_query"]:
                st.text_input("Last Query", value=geo_debug["last_query"], disabled=True)

            if geo_debug["last_result"]:
                st.text_area(
                    "Last Result",
                    value=f"Coordinates: {geo_debug['last_result'].get('coordinates', 'N/A')}\n"
                    f"Address: {geo_debug['last_result'].get('address', 'N/A')}\n"
                    f"Time: {geo_debug['last_result'].get('elapsed_seconds', 'N/A')}s",
                    disabled=True,
                    height=100,
                )

            if geo_debug["last_error"]:
                st.text_area("Last Error", value=geo_debug["last_error"], disabled=True, height=80)

            if geo_debug["last_time"]:
                st.caption(f"Last request: {geo_debug['last_time']}")

            col1, col2 = st.columns(2)
            if col1.button("Clear Geocoding Debug", use_container_width=True):
                clear_geocoding_debug_info()
                st.success("Geocoding debug cleared!")
                st.rerun()

            if col2.button("Test Paris", use_container_width=True):
                with st.spinner("Testing geocoding for Paris, France..."):
                    result = get_coordinates("Paris", "France")
                    if result:
                        st.success(
                            f"Test successful! Coordinates: {result[0]:.4f}, {result[1]:.4f}"
                        )
                    else:
                        st.error("Test failed!")
                    st.rerun()

        with st.sidebar.expander("🔍 Session State Debug"):
            st.write("**Settings:**")
            st.write(f"- width: {st.session_state.settings.get('width', 'NOT SET')}")
            st.write(f"- height: {st.session_state.settings.get('height', 'NOT SET')}")
            st.write(f"- dpi: {st.session_state.settings.get('dpi', 'NOT SET')}")
            st.write(f"- distance: {st.session_state.settings.get('distance', 'NOT SET')}")

            st.write("**Flags:**")
            st.write(f"- preset_just_applied: {st.session_state.preset_just_applied}")

            st.write("**Aspect Ratio:**")
            width = st.session_state.settings.get("width", 0)
            height = st.session_state.settings.get("height", 0)
            ratio = width / height if height > 0 else 0
            st.write(f"- Current ratio: {ratio:.2f}")
            st.write(f"- Display: {calculate_aspect_ratio_display(width, height)}")


def render_main_area():
    """Render main content area."""
    st.title("🗺️ Map Poster Generator")

    st.caption(
        "⏱️ Note: Poster generation takes 1-3 minutes. This app runs on free tier hardware, please be patient!"
    )

    city = st.session_state.location["city"]
    country = st.session_state.location["country"]
    lat = st.session_state.location["lat"]
    lon = st.session_state.location["lon"]
    mode = st.session_state.location["mode"]

    # Validate input based on mode
    if mode == "city_country":
        if not city or not country:
            st.info("👈 Enter a city and country in the sidebar to get started.")
            return
    else:  # coordinates mode
        if not lat or not lon:
            st.info("👈 Enter latitude and longitude in the sidebar to get started.")
            return
        try:
            lat_float = float(lat)
            lon_float = float(lon)
            if not (-90 <= lat_float <= 90) or not (-180 <= lon_float <= 180):
                st.error(
                    "❌ Invalid coordinates. Latitude must be -90 to 90, Longitude must be -180 to 180."
                )
                return
        except ValueError:
            st.error("❌ Invalid coordinates. Please enter numeric values.")
            return

    col1, col2 = st.columns([2, 1])

    with col1:
        generate_btn = st.button("🎨 Generate Poster", type="primary", use_container_width=True)

    with col2:
        example_btn = st.button("🎲 Random Example", use_container_width=True)

    if generate_btn or example_btn:
        if example_btn:
            city, country = random.choice(EXAMPLE_CITIES)
            st.session_state.location["city"] = city
            st.session_state.location["country"] = country
            st.session_state.location["mode"] = "city_country"
            st.rerun()
            return

        coords = None
        display_city_name = None
        display_country_name = None

        if mode == "city_country":
            with st.spinner(f"🗺️ Fetching map data for {city}, {country}..."):
                coords = get_coordinates(city, country)

                if not coords:
                    if is_rate_limit_error():
                        st.error(
                            f"❌ Geocoding service is currently rate-limited. "
                            f"Unable to find coordinates for '{city}, {country}'."
                        )
                        st.warning(
                            """
                            **Alternative Solution:** Use the **Coordinates** input mode instead.

                            To find coordinates for your location:
                            1. Visit [OpenStreetMap.org](https://www.openstreetmap.org/)
                            2. Navigate to your desired location
                            3. Right-click on the map
                            4. Select "Show address" to see the latitude/longitude
                            5. Copy the coordinates and paste them in the sidebar
                            """
                        )
                        if st.button(
                            "🔄 Switch to Coordinates Mode",
                            key="switch_to_coords",
                            use_container_width=True,
                        ):
                            st.session_state.location["mode"] = "coordinates"
                            st.rerun()
                    else:
                        st.error(
                            f"❌ Could not find coordinates for '{city}, {country}'. Check the spelling and try again."
                        )
                    return

                st.session_state.location["coords"] = coords
                lat_float, lon_float = coords
                display_city_name = city
                display_country_name = country
                st.success(f"✅ Found coordinates: {lat_float:.4f}, {lon_float:.4f}")
        else:
            lat_float = float(lat)
            lon_float = float(lon)
            coords = (lat_float, lon_float)
            display_city_name = st.session_state.location.get("display_city") or "Custom"
            display_country_name = st.session_state.location.get("display_country") or "Location"
            st.success(f"✅ Using coordinates: {lat_float:.4f}, {lon_float:.4f}")

        with st.spinner("🎨 Generating poster..."):
            theme_name = st.session_state.settings["theme"]
            theme = load_theme(theme_name)

            fig = create_poster(
                city=display_city_name,
                country=display_country_name,
                point=coords,
                dist=st.session_state.settings["distance"],
                width=st.session_state.settings["width"],
                height=st.session_state.settings["height"],
                theme=theme,
                display_city=st.session_state.location.get("display_city"),
                display_country=st.session_state.location.get("display_country"),
                road_colors=st.session_state.road_colors,
                road_thickness=st.session_state.road_thickness,
                normalize_all=st.session_state.normalize_all,
            )

            if fig is None:
                st.error("❌ Failed to generate poster. Try a different location or settings.")
                return

            st.session_state.generated_poster = fig
            st.session_state.last_generation_time = datetime.now()

    if st.session_state.generated_poster is not None:
        render_results()


def render_results():
    """Render generated poster and download options."""
    tab1, tab2 = st.tabs(["🖼️ Poster", "⬇️ Download"])

    with tab1:
        st.pyplot(st.session_state.generated_poster)

    with tab2:
        fig = st.session_state.generated_poster
        output_format = st.session_state.settings["format"]
        city = st.session_state.location["city"]
        theme_name = st.session_state.settings["theme"]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        city_slug = city.lower().replace(" ", "_")
        filename = f"{city_slug}_{theme_name}_{timestamp}.{output_format}"

        image_bytes = fig_to_bytes(fig, format=output_format, dpi=st.session_state.settings["dpi"])

        mime_types = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"}
        mime_type = mime_types.get(output_format, "image/png")

        st.download_button(
            label=f"Download {output_format.upper()}",
            data=image_bytes,
            file_name=filename,
            mime=mime_type,
            use_container_width=True,
        )

        col1, col2 = st.columns(2)
        col1.metric("Size", f"{len(image_bytes):,} bytes")
        if st.session_state.last_generation_time:
            col2.metric(
                "Generated",
                st.session_state.last_generation_time.strftime("%H:%M:%S"),
            )

        if st.button("🗑️ Clear Poster", key="clear_poster_button"):
            close_fig(st.session_state.generated_poster)
            st.session_state.generated_poster = None
            st.session_state.last_generation_time = None
            st.rerun()


def render_footer():
    """Render footer information."""
    st.divider()
    st.caption(
        "🗺️ Map Poster Generator is a port of [MapToPoster](https://github.com/originalankur/maptoposter) | Data © [OpenStreetMap](https://www.openstreetmap.org/)"
    )


def main():
    """Main application entry point."""
    init_session_state()
    render_sidebar()
    render_debug_panel()
    render_main_area()
    render_footer()


if __name__ == "__main__":
    main()

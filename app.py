"""Streamlit Map Poster Generator

An interactive web application for generating beautiful city map posters.
"""

import random
from datetime import datetime

import matplotlib
import streamlit as st

from core import (
    close_fig,
    create_poster,
    fig_to_bytes,
    get_all_themes_info,
    get_coordinates,
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
        }
    if "settings" not in st.session_state:
        st.session_state.settings = {
            "theme": "terracotta",
            "distance": 18000,
            "width": 12,
            "height": 16,
            "format": "png",
        }
    if "generated_poster" not in st.session_state:
        st.session_state.generated_poster = None
    if "last_generation_time" not in st.session_state:
        st.session_state.last_generation_time = None


def render_sidebar():
    """Render sidebar configuration panel."""
    st.sidebar.title("⚙️ Configuration")

    with st.sidebar.expander("📍 Location", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            city = st.text_input(
                "City",
                value=st.session_state.location["city"],
                placeholder="e.g. Paris",
                key="sidebar_city",
            )
        with col2:
            country = st.text_input(
                "Country",
                value=st.session_state.location["country"],
                placeholder="e.g. France",
                key="sidebar_country",
            )
        st.session_state.location["city"] = city
        st.session_state.location["country"] = country

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
                min_value=4,
                max_value=20,
                value=st.session_state.settings["width"],
                step=1,
                key="sidebar_width",
            )
        with col2:
            height = st.number_input(
                "Height (in)",
                min_value=4,
                max_value=20,
                value=st.session_state.settings["height"],
                step=1,
                key="sidebar_height",
            )
        st.session_state.settings["width"] = width
        st.session_state.settings["height"] = height

        distance = st.slider(
            "Map Radius (m)",
            min_value=1000,
            max_value=30000,
            value=st.session_state.settings["distance"],
            step=1000,
            key="sidebar_distance",
        )
        st.session_state.settings["distance"] = distance

        output_format = st.selectbox(
            "Output Format",
            options=["png", "svg", "pdf"],
            index=["png", "svg", "pdf"].index(st.session_state.settings["format"]),
            key="sidebar_format",
        )
        st.session_state.settings["format"] = output_format

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


def render_main_area():
    """Render main content area."""
    st.title("🗺️ Map Poster Generator")

    city = st.session_state.location["city"]
    country = st.session_state.location["country"]

    if not city or not country:
        st.info("👈 Enter a city and country in the sidebar to get started.")
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
            st.rerun()
            return

        with st.spinner(f"🗺️ Fetching map data for {city}, {country}..."):
            coords = get_coordinates(city, country)

            if not coords:
                st.error(f"❌ Could not find coordinates for '{city}, {country}'. Check the spelling and try again.")
                return

            st.session_state.location["coords"] = coords
            lat, lon = coords
            st.success(f"✅ Found coordinates: {lat:.4f}, {lon:.4f}")

        with st.spinner("🎨 Generating poster..."):
            theme_name = st.session_state.settings["theme"]
            theme = load_theme(theme_name)

            fig = create_poster(
                city=city,
                country=country,
                point=coords,
                dist=st.session_state.settings["distance"],
                width=st.session_state.settings["width"],
                height=st.session_state.settings["height"],
                theme=theme,
                display_city=st.session_state.location.get("display_city"),
                display_country=st.session_state.location.get("display_country"),
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

        image_bytes = fig_to_bytes(fig, format=output_format)

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

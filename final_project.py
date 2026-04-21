"""
Name: Anar Badruun
CS230-2
Final Project: Global Airports Explorer
Data: Airports Around the World + ISO Country Codes    
URL: http://localhost:8501   http://10.100.228.205:8501

Description:
This program is an interactive Streamlit data explorer for global airports.
Users can filter airports by country, continent, airport type, elevation, and
scheduled service. The app answers questions such as:
1) What airports exist in a selected country or region?
2) Which countries have the most airports?
3) How do airport types compare across countries and continents?
It includes multiple charts, an interactive map, summary metrics, and query tables.

References:
- Course project brief and uploaded datasets
- Streamlit documentation: https://docs.streamlit.io/
- PyDeck documentation: https://deckgl.readthedocs.io/
- Plotly documentation: https://plotly.com/python/
"""

import pandas as pd
import streamlit as st
import plotly.express as px
import pydeck as pdk


# Page setup
st.set_page_config(
    page_title="Global Airports Explorer",
    page_icon="✈️",
    layout="wide"
)


# Data loading
@st.cache_data
def load_data():
    """Load airport and ISO country data from Excel files."""
    airports = pd.read_excel("airport-codes.xlsx")
    countries = pd.read_excel("wikipedia-iso-country-codes.xlsx")
    return airports, countries


# #[LAMBDA]
split_coord = lambda x, idx: float(str(x).split(",")[idx].strip()) if pd.notna(x) and "," in str(x) else None


# #[FUNC2P]
def prepare_data(airports_df, countries_df, include_unknown=False):
    """
    Clean and merge airport and country data.
    include_unknown has a default value to satisfy the requirement.
    """
    df = airports_df.copy()
    iso = countries_df.copy()

    # #[COLUMNS]
    # Add latitude and longitude from coordinates
    df["longitude"] = df["coordinates"].apply(lambda x: split_coord(x, 0))
    df["latitude"] = df["coordinates"].apply(lambda x: split_coord(x, 1))

    # Add a simple scheduled_service flag if not present
    df["scheduled_service"] = df["iata_code"].notna().map({True: "yes", False: "no"})

    # Merge with country names
    df = df.merge(
        iso[["English short name lower case", "Alpha-2 code", "Alpha-3 code"]],
        left_on="iso_country",
        right_on="Alpha-2 code",
        how="left"
    )

    df.rename(
        columns={
            "English short name lower case": "country_name",
            "Alpha-3 code": "country_code_3"
        },
        inplace=True
    )

    # Continent labels
    continent_map = {
        "AF": "Africa",
        "AN": "Antarctica",
        "AS": "Asia",
        "EU": "Europe",
        "NA": "North America",
        "OC": "Oceania",
        "SA": "South America"
    }
    df["continent_name"] = df["continent"].map(continent_map)

    if not include_unknown:
        df = df[df["country_name"].notna()].copy()

    # Fill missing text fields for easier display
    text_cols = ["municipality", "gps_code", "iata_code", "local_code", "country_name", "continent_name"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")

    # Fix missing elevations
    df["elevation_ft"] = pd.to_numeric(df["elevation_ft"], errors="coerce")

    return df


# #[FUNCRETURN2]
def get_summary_info(df):
    """Return multiple summary values."""
    total_airports = len(df)
    total_countries = df["country_name"].nunique()
    highest_elev = df["elevation_ft"].max() if not df["elevation_ft"].dropna().empty else 0
    lowest_elev = df["elevation_ft"].min() if not df["elevation_ft"].dropna().empty else 0
    return total_airports, total_countries, highest_elev, lowest_elev


# #[FUNC2P]
def filter_airports(
    df,
    country="All",
    continents=None,
    airport_types=None,
    elevation_range=(0, 20000),
    scheduled_choice="All",
    keyword=""
):
    """
    Filter the airport data based on multiple user selections.
    """
    filtered = df.copy()

    # #[FILTER1]
    if country != "All":
        filtered = filtered[filtered["country_name"] == country]

    # #[FILTER2]
    if continents:
        filtered = filtered[filtered["continent_name"].isin(continents)]

    if airport_types:
        filtered = filtered[filtered["type"].isin(airport_types)]

    filtered = filtered[
        filtered["elevation_ft"].fillna(-9999).between(elevation_range[0], elevation_range[1])
        | filtered["elevation_ft"].isna()
    ]

    if scheduled_choice == "Scheduled only":
        filtered = filtered[filtered["scheduled_service"] == "yes"]
    elif scheduled_choice == "Non-scheduled only":
        filtered = filtered[filtered["scheduled_service"] == "no"]

    if keyword.strip():
        keyword_lower = keyword.strip().lower()
        filtered = filtered[
            filtered["name"].str.lower().str.contains(keyword_lower, na=False)
            | filtered["municipality"].str.lower().str.contains(keyword_lower, na=False)
            | filtered["iso_region"].str.lower().str.contains(keyword_lower, na=False)
        ]

    return filtered


# #[FUNCCALL2]
def country_count_table(df, top_n=10):
    """Build a sorted country count table."""
    # #[PIVOTTABLE]
    counts = pd.pivot_table(
        df,
        index="country_name",
        values="ident",
        aggfunc="count"
    ).reset_index()

    counts.rename(columns={"ident": "airport_count"}, inplace=True)

    # #[SORT]
    counts = counts.sort_values(by="airport_count", ascending=False).head(top_n)
    return counts


# #[FUNCCALL2]
def type_count_table(df):
    """Build a sorted airport type count table."""
    type_counts = df["type"].value_counts().reset_index()
    type_counts.columns = ["type", "count"]

    # #[SORT]
    type_counts = type_counts.sort_values(by="count", ascending=False)
    return type_counts


def region_country_comparison(df, selected_continents):
    """Compare airport counts across continents."""
    if not selected_continents:
        compare_df = df.copy()
    else:
        compare_df = df[df["continent_name"].isin(selected_continents)].copy()

    grouped = compare_df.groupby(["continent_name", "type"]).size().reset_index(name="count")
    return grouped


def build_map(df):
    """Create an interactive PyDeck map."""
    map_df = df.dropna(subset=["latitude", "longitude"]).copy()

    if map_df.empty:
        return None

    # Marker size based on airport type
    radius_lookup = {
        "large_airport": 40000,
        "medium_airport": 25000,
        "small_airport": 12000,
        "heliport": 8000,
        "seaplane_base": 10000,
        "closed": 7000,
        "balloonport": 7000
    }

    # #[DICTMETHOD]
    # Use dictionary methods explicitly
    radius_keys = list(radius_lookup.keys())
    default_radius = radius_lookup.get("small_airport", 12000)

    # #[ITERLOOP]
    radii = []
    for airport_type in map_df["type"]:
        if airport_type in radius_keys:
            radii.append(radius_lookup.get(airport_type, default_radius))
        else:
            radii.append(default_radius)

    # #[COLUMNS]
    map_df["radius"] = radii

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[longitude, latitude]",
        get_radius="radius",
        get_fill_color="[30, 144, 255, 160]",
        pickable=True,
        stroked=True,
        filled=True,
        radius_min_pixels=2,
        radius_max_pixels=30,
        line_width_min_pixels=1
    )

    view_state = pdk.ViewState(
        latitude=float(map_df["latitude"].mean()),
        longitude=float(map_df["longitude"].mean()),
        zoom=1,
        pitch=0
    )

    tooltip = {
        "html": """
            <b>{name}</b><br/>
            Country: {country_name}<br/>
            City: {municipality}<br/>
            Type: {type}<br/>
            Elevation: {elevation_ft} ft<br/>
            IATA: {iata_code}<br/>
            Region: {iso_region}
        """,
        "style": {"backgroundColor": "navy", "color": "white"}
    }

    return pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="mapbox://styles/mapbox/light-v9"
    )


def main():
    # Title and intro
    st.title("✈️ Global Airports Explorer")
    st.markdown(
        """
        Explore airport distribution around the world by country, continent, 
        airport type, elevation, and service level.  
        This app helps answer questions like:
        - Which airports are in a selected country or region?
        - Which countries have the most airports?
        - How do airport types compare across continents?
        """
    )

    # Load and prepare data
    airports_raw, countries_raw = load_data()
    df = prepare_data(airports_raw, countries_raw)

    # Sidebar controls
    st.sidebar.header("Filters and Controls")  # #[ST3]

    # #[ST1]
    country_options = ["All"] + sorted(df["country_name"].dropna().unique().tolist())
    selected_country = st.sidebar.selectbox("Choose a country", country_options)

    continent_options = sorted([c for c in df["continent_name"].dropna().unique().tolist() if c != "Unknown"])
    selected_continents = st.sidebar.multiselect(
        "Choose one or more continents",
        continent_options,
        default=continent_options
    )

    airport_type_options = sorted(df["type"].dropna().unique().tolist())

    # #[LISTCOMP]
    default_types = [airport_type for airport_type in airport_type_options if airport_type != "closed"]

    selected_types = st.sidebar.multiselect(
        "Choose airport types",
        airport_type_options,
        default=default_types
    )

    max_elev = int(df["elevation_ft"].dropna().max()) if not df["elevation_ft"].dropna().empty else 10000

    # #[ST2]
    selected_elevation = st.sidebar.slider(
        "Select elevation range (feet)",
        min_value=-200,
        max_value=max_elev,
        value=(-200, min(max_elev, 10000))
    )

    scheduled_option = st.sidebar.radio(
        "Scheduled service filter",
        ["All", "Scheduled only", "Non-scheduled only"]
    )

    keyword = st.sidebar.text_input("Search airport name, city, or region")

    top_n = st.sidebar.slider("Top number of countries to display", 5, 25, 10)

    # Apply filters
    filtered_df = filter_airports(
        df,
        country=selected_country,
        continents=selected_continents,
        airport_types=selected_types,
        elevation_range=selected_elevation,
        scheduled_choice=scheduled_option,
        keyword=keyword
    )

    
    # Summary metrics
    total_airports, total_countries, highest_elev, lowest_elev = get_summary_info(filtered_df)

    # #[MAXMIN]
    highest_airport_name = "N/A"
    lowest_airport_name = "N/A"
    if not filtered_df["elevation_ft"].dropna().empty:
        highest_row = filtered_df.loc[filtered_df["elevation_ft"].idxmax()]
        lowest_row = filtered_df.loc[filtered_df["elevation_ft"].idxmin()]
        highest_airport_name = highest_row["name"]
        lowest_airport_name = lowest_row["name"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Filtered Airports", f"{total_airports:,}")
    c2.metric("Countries in Results", f"{total_countries:,}")
    c3.metric("Highest Elevation", f"{highest_elev:,.0f} ft")
    c4.metric("Lowest Elevation", f"{lowest_elev:,.0f} ft")

    st.caption(
        f"Highest elevation airport in current results: **{highest_airport_name}** | "
        f"Lowest elevation airport in current results: **{lowest_airport_name}**"
    )

    # Tabs for navigation
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Airport Query Results", "Country Rankings", "Airport Type Analysis", "Interactive Map"]
    )

    # Tab 1: Query results
    with tab1:
        st.subheader("Airport Query Results")
        st.write(
            "This table answers the question: **Which airports are in the selected country or region, "
            "and which ones match the chosen type and elevation filters?**"
        )

        display_cols = [
            "ident", "name", "type", "country_name", "continent_name", "municipality",
            "iso_region", "iata_code", "elevation_ft", "scheduled_service"
        ]
        st.dataframe(filtered_df[display_cols], use_container_width=True, height=450)

        csv_data = filtered_df[display_cols].to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download filtered results as CSV",
            data=csv_data,
            file_name="filtered_airports.csv",
            mime="text/csv"
        )

    # Tab 2: Country rankings
    with tab2:
        st.subheader("Countries with the Highest Number of Airports")
        st.write(
            "This chart highlights countries with the largest airport counts after applying your filters."
        )

        country_counts = country_count_table(filtered_df, top_n=top_n)

        # #[CHART1]
        fig_country = px.bar(
            country_counts,
            x="country_name",
            y="airport_count",
            color="airport_count",
            title=f"Top {top_n} Countries by Number of Airports",
            labels={"country_name": "Country", "airport_count": "Airport Count"},
            text="airport_count"
        )
        fig_country.update_layout(
            xaxis_tickangle=-45,
            showlegend=False,
            title_x=0.1
        )
        st.plotly_chart(fig_country, use_container_width=True)

        st.dataframe(country_counts, use_container_width=True)

    # Tab 3: Type analysis
    with tab3:
        st.subheader("Airport Type Analysis")
        st.write(
            "These visuals compare airport type distributions and show how airport structures vary "
            "across the filtered data."
        )

        type_counts = type_count_table(filtered_df)

        col_left, col_right = st.columns(2)

        with col_left:
            # #[CHART2]
            fig_types = px.pie(
                type_counts,
                names="type",
                values="count",
                title="Distribution of Airport Types",
                hole=0.35
            )
            fig_types.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_types, use_container_width=True)

        with col_right:
            comparison_df = region_country_comparison(filtered_df, selected_continents)
            if not comparison_df.empty:
                fig_compare = px.bar(
                    comparison_df,
                    x="continent_name",
                    y="count",
                    color="type",
                    barmode="group",
                    title="Airport Types by Continent",
                    labels={"continent_name": "Continent", "count": "Count", "type": "Airport Type"}
                )
                st.plotly_chart(fig_compare, use_container_width=True)
            else:
                st.info("No continent comparison available for the current filters.")

        st.dataframe(type_counts, use_container_width=True)

    # Tab 4: Map
    with tab4:
        st.subheader("Interactive Airport Map")
        st.write(
            "This map displays airport locations using latitude and longitude. "
            "Hover over a marker to see airport details."
        )

        airport_map = build_map(filtered_df)

        if airport_map is not None:
            # #[MAP]
            st.pydeck_chart(airport_map, use_container_width=True)
        else:
            st.warning("No airports with valid latitude/longitude are available for the current filters.")

    
    # Extra insights section
    st.markdown("---")
    st.subheader("Quick Insights")

    if not filtered_df.empty:
        most_common_type = filtered_df["type"].mode().iloc[0]
        most_common_country = (
            filtered_df["country_name"].value_counts().idxmax()
            if not filtered_df["country_name"].value_counts().empty
            else "N/A"
        )

        st.write(
            f"- The most common airport type in the current results is **{most_common_type}**."
        )
        st.write(
            f"- The country with the most airports in the current filtered view is **{most_common_country}**."
        )
        st.write(
            "- Use the sidebar to compare airport distributions across countries, continents, and elevation ranges."
        )
    else:
        st.info("No data matched the current filters. Try widening the elevation range or selecting more airport types.")


if __name__ == "__main__":
    main()
    
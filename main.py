# -------------------------------------------------------------------------------
# Name          Simplified Historic Heat Flux App Frontend
# Description:  Streamlit app to download met data from ASOS stations
#               for the past 10 days and display results of heat flux calculations
# Author:       Chandler Engel
# -------------------------------------------------------------------------------

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils import (
    get_metar,
    make_metar_dataframe_local,
    calc_fluxes,
    build_energy_df,
    return_lat_lon,
    plot_met,
    plot_historic_heat_fluxes,
)
import pandas as pd
import datetime
import io

# Function to calculate start and end dates for the 10-day lookback
def get_lookback_dates(days=10):
    end_date = datetime.datetime.utcnow()
    start_date = end_date - datetime.timedelta(days=days)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")

# Cache the data processing to improve performance
@st.cache_data
def st_make_metar_dataframe(df):
    return make_metar_dataframe_local(df)

@st.cache_data
def convert_df(df):
    return df.to_csv(index=True).encode('utf-8')

st.set_page_config(page_title="Historic Modeled Heat Flux", layout="wide")

st.title("Historic Modeled Heat Flux Calculation Tool - Variable Lookback")

st.markdown("""
Enter the **airport code** below and press **Go** to retrieve, process, and visualize the heat flux data for the past 10 days.
""")

# Input Section
airport_code = st.text_input(
    'Enter Airport Code (e.g., Ogallala Airport: "OGA")', 'OGA'
)

T_water_C = st.number_input('water temperature (C)', value=2)

lookback_days = st.number_input('Time Period to Look Back (days)', value=10)

if st.button("Go"):
    with st.spinner("Processing..."):
        try:
            # Step 1: Calculate Date Range
            startts, endts = get_lookback_dates(days=lookback_days)
            st.write(f"**Date Range:** {startts} to {endts}")

            # Step 2: Download METAR Data
            data = get_metar(airport_code, startts, endts)

            # Convert raw data to DataFrame
            raw_df = pd.read_csv(io.StringIO(data), skiprows=5, na_values=["M"])

            # Step 3: Process METAR Data
            processed_df = st_make_metar_dataframe(raw_df)

            # # Display Processed Data
            # st.subheader("Processed Meteorological Data")
            # st.write(processed_df)

            # Step 5: Calculate Heat Fluxes
            #T_water_C = 3.0  
            airport_lat, airport_lon = return_lat_lon(processed_df)
            q_sw, q_atm, q_b, q_l, q_h, q_net = calc_fluxes(
                processed_df, T_water_C, airport_lat, airport_lon
            )
            energy_df = build_energy_df(q_sw, q_atm, q_b, q_l, q_h)

            # # Display Heat Flux Data
            # st.subheader("Calculated Heat Fluxes")
            # st.write(energy_df)

            # Step 6: Plot Heat Flux Results
            st.subheader("Modeled Heat Flux Results Plots")
            fig_flux = plot_historic_heat_fluxes(energy_df)
            st.plotly_chart(fig_flux, use_container_width=True)
            #st.pyplot(fig_flux)

            # Download button for energy flux CSV
            tz_label = str(energy_df.index.tz) if energy_df.index.tz else 'UTC'
            flux_export = energy_df.rename(columns={
                'downwelling SW': 'Downwelling Shortwave Radiation (W/m^2)',
                'downwelling LW': 'Downwelling Longwave Radiation (W/m^2)',
                'upwelling LW': 'Upwelling Longwave Radiation (W/m^2)',
                'sensible heat': 'Sensible Heat Flux (W/m^2)',
                'latent heat': 'Latent Heat Flux (W/m^2)',
                'net flux': 'Net Heat Flux (W/m^2)',
            }).rename_axis(f'datetime ({tz_label})')
            flux_export.index = flux_export.index.tz_localize(None)
            flux_export = flux_export.round(4)
            date_start = flux_export.index.min().strftime("%Y%m%d")
            date_end = flux_export.index.max().strftime("%Y%m%d")
            flux_csv = flux_export.to_csv().encode('utf-8-sig')
            st.download_button(
                label="Download Energy Flux Data as CSV",
                data=flux_csv,
                file_name=f"{airport_code}_energy_flux_{date_start}_{date_end}.csv",
                mime="text/csv",
            )

            # Step 4: Plot Meteorological Data
            st.subheader("Meteorological Data Plots - Decoded from")
            fig_met = plot_met(processed_df)
            st.plotly_chart(fig_met, use_container_width=True)

            st.success("Heat flux calculations and plots generated successfully.")

        except Exception as e:
            st.error(f"An error occurred: {e}")

# -------------------------------------------------------------------------------
# Name          Historic Heat Flux App Frontend
# Description:  Streamlit app to download met data from ASOS stations
#               and display results of heat flux calculations
# Author:       Chandler Engel
#               US Army Corps of Engineers
#               Cold Regions Research and Engineering Laboratory (CRREL)
#               Chandler.S.Engel@usace.army.mil
# Created:      31 March 2023
# Updated:      -
#
# --

import streamlit as st
from utils import get_metar, make_metar_dataframe, calc_fluxes, build_energy_df, plot_forecast_heat_fluxes
import pandas as pd


@st.cache_data
def st_make_metar_dataframe(df):
    return make_metar_dataframe(df)


@st.cache_data
def convert_df(df):
    return df.to_csv(index=True).encode('utf-8')


st.set_page_config(layout="wide")

st.title('Historic Heat Flux Calculation Tool')

with st.expander("1 Download Met Data From Iowa State Mesonet", expanded=True):
    station = st.text_input(r'Enter Airport Code, e.g. Ogallala Airport would be "OGA"', 'OGA')
    startts = st.text_input(r'Enter start date in the format YYYYMMDD:', '20230101')
    endts = st.text_input(r'Enter end date in the format YYYYMMDD:', '20230201')
    if st.button('Find data!'):
        data = get_metar(station, startts, endts)
        st.write('Data found for the station and period defined. Click Download button to save locally to CSV.')

        st.download_button(
            "Press to Download",
            data,
            f'{station}_{startts}0000_{endts}0000.csv',
            "text/csv",
            key='download-csv'
        )

with st.expander("2 Upload Met Data to process", expanded=True):
    uploaded_file = st.file_uploader("Choose a file")
    if uploaded_file is not None:
        st.session_state['raw_df'] = pd.read_csv(uploaded_file, skiprows=5, na_values=['M'])
        # st.write(dataframe)

with st.expander("3 Process Met Data into Heat Flux Model inputs", expanded=True):
    if st.button('Process!'):
        st.session_state['df'] = st_make_metar_dataframe(st.session_state.raw_df)
        st.write(st.session_state['df'])

with st.expander("4 Calculate Heat Fluxes", expanded=False):
    T_water_C = st.number_input('Average Water Temperature (C)', value=3)
    st.write('Enter lat/lon location to calculate elevation and solar input')
    lat = st.number_input('Latitude', value=41.1242)
    lon = st.number_input('Longitude', value=-101.3644337)
    st.write('Wind Function Variables:')
    a = st.number_input('a', value=10 ** -6, format='%e')
    b = st.number_input('b', value=10 ** -6, format='%e')
    c = st.number_input('c', value=1.0, format='%f')
    R = st.number_input('R', value=1.0, format='%f')

    if st.button('Calculate Heat Fluxes'):
        q_sw, q_atm, q_b, q_l, q_h, q_net = calc_fluxes(st.session_state['df'], T_water_C, lat, lon, a, b, c, R)
        st.session_state['energy_df'] = build_energy_df(q_sw, q_atm, q_b, q_l, q_h)
        st.write(st.session_state['energy_df'])

        csv = convert_df(st.session_state['energy_df'])

        st.download_button(
            "Press to Download",
            csv,
            "file.csv",
            "text/csv",
            key='download-csv'
        )

with st.expander("5 Plot Results", expanded=True):
    st.write('This may take a very long time if the data is more than a 60 days long. We recommend downloading the '
             'output file and plotting externally for longer datasets.')
    if st.button('Plot Results'):
        fig = plot_forecast_heat_fluxes(st.session_state.energy_df)
        st.write(fig)

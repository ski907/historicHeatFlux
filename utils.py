import iowa_metar_scrape as ia
import datetime
import pandas as pd
import requests
from pvlib.location import Location
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def get_metar(station, startts, endts):
    ###This is a slightly modified version of an example from the Iowa State Mesonet page
    # https://mesonet.agron.iastate.edu/request/download.phtml?network=NE_ASOS
    # https://github.com/akrherz/iem/blob/main/scripts/asos/iem_scraper_example.py

    # expects dates like 19990201 for 2 Feb 1999
    startts = datetime.datetime.strptime(startts, '%Y%m%d')
    endts = datetime.datetime.strptime(endts, '%Y%m%d')

    service = ia.SERVICE + "data=all&tz=Etc/UTC&format=comma&latlon=yes&"

    service += startts.strftime("year1=%Y&month1=%m&day1=%d&")
    service += endts.strftime("year2=%Y&month2=%m&day2=%d&")

    uri = "%s&station=%s" % (service, station)
    print("Downloading: %s" % (station,))
    data = ia.download_data(uri)

    return data


def make_metar_dataframe(df):
    df2 = pd.DataFrame()
    df2['date'] = df.valid
    df2['date'] = pd.to_datetime(df2.date)
    df2['lat'] = df.lat
    df2['lon'] = df.lon
    df2['atmospheric_pressure_inHg'] = df.alti
    df2['atmospheric_pressure_mb'] = df.alti * 33.8639
    df2['air_temperature_F'] = df.tmpf
    df2['air_temperature_C'] = (df.tmpf - 32) * 5 / 9
    df2['dewpoint_F'] = df.dwpf
    df2['dewpoint_C'] = (df.dwpf - 32) * 5 / 9
    df2['humidity_%RH'] = df.relh
    df2['wind_speed_ms'] = df.sknt * 0.51  # 0.51 m/s per knot
    df2['wind_direction_deg_from_N'] = df.drct
    df2 = df2.set_index(df2.date)
    df2 = df2.drop(['date'], axis=1)

    # get cloudiness
    cloud_dict = {'CLR': 0, 'SKC': 0, 'FEW': 1.5 / 8, 'SCT': 3.5 / 8, 'BKN': 6 / 8, 'OVC': 8 / 8}
    df = df.set_index(pd.to_datetime(df.valid))
    df2['cloudiness'] = pd.concat(
        [df.skyc1.map(cloud_dict),
         df.skyc2.map(cloud_dict),
         df.skyc3.map(cloud_dict),
         df.skyc4.map(cloud_dict)], axis=1).max(axis=1)

    tz = 'Etc/UTC'
    df2 = df2.tz_localize(tz=tz)
    return df2


def get_elevation(lat, lon):
    url = f'https://api.opentopodata.org/v1/ned10m?locations={lat},{lon}'
    result = requests.get(url)
    return result.json()['results'][0]['elevation']


def get_solar(lat, lon, elevation, site_name, times, tz):
    site = Location(lat, lon, tz, elevation, site_name)
    cs = site.get_clearsky(times)
    return cs


def calc_solar(q0_a_t, R, Cl):
    # function to calculate solar net solar radition into water using attenuated solar if available
    # R is water reflectivity
    # Cl is cloudiness %
    q_sw = q0_a_t * (1 - R) * (1 - 0.65 * Cl ** 2)
    return q_sw


def calc_downwelling_LW(T_air, Cl):
    Tak = T_air + 273.15
    sbc = 5.670374419 * 10 ** -8  # W m-2 K-4
    # emissivity from Zhang and Johnson 2016
    # Zhang, Z. and Johnson, B.E., 2016. Aquatic nutrient simulation modules (NSMs) developed for hydrologic and hydraulic models.
    emissivity = 0.937 * 10 ** -5 * (1 + 0.17 * Cl ** 2) * Tak ** 2
    q_atm = emissivity * sbc * Tak ** 4
    return q_atm


def calc_upwelling_LW(T_water):
    Twk = T_water + 273.15
    sbc = 5.670374419 * 10 ** -8  # W m-2 K-4
    emissivity = 0.97
    q_b = emissivity * sbc * Twk ** 4
    return q_b


def calc_wind_function(a, b, c, R, U):
    return R * (a + b * U ** c)


def calc_latent_heat(P, T_water, ea, f_U):
    Twk = T_water + 273.15
    Lv = 2.500 * 10 ** 6 - 2.386 * 10 ** 3 * (T_water)
    rho_w = 1000  # kg/m3
    # saturated vapor pressure at water temperature (mb), which is a function of water temperature from Zhang and Johnson 2016
    # Zhang, Z. and Johnson, B.E., 2016. Aquatic nutrient simulation modules (NSMs) developed for hydrologic and hydraulic models.
    es = 6984.505294 + Twk * (-188.903931 + Twk * (2.133357675 + Twk * (-1.28858097 * 10 ** -2 + Twk * (
            4.393587233 * 10 ** -5 + Twk * (-8.023923082 * 10 ** -8 + Twk * 6.136820929 * 10 ** -11)))))
    ql = 0.622 / P * Lv * rho_w * (es - ea) * f_U
    return ql


def calc_sensible_heat(T_air, f_U, T_water):
    Cp = 1.006 * 10 ** 3  # J/kg-K
    rho_w = 1000
    qh = Cp * rho_w * (T_air - T_water) * f_U
    return qh

def calc_vapor_pressure(T_dewpoint):
    return 6.11 * 10 ** (7.5 * T_dewpoint / (237.3 + T_dewpoint))

def plot_met(df):
    # Prepare the data for plotting
    df = df[~df.index.duplicated(keep='first')]
    df_met = df[['air_temperature_C', 'humidity_%RH', 'dewpoint_C', 
                'atmospheric_pressure_mb', 'cloudiness', 'wind_speed_ms']]
    
    df_met = pd.melt(df_met.reset_index(), id_vars=df_met.index.name or 'date', 
                     var_name='variable', value_name='value')
    df_met = df_met.rename(columns={'index': 'date'})
    
    # Create a Plotly figure
    variables = df_met['variable'].unique()
    colors = {
        'air_temperature_C': 'red',
        'humidity_%RH': 'blue',
        'dewpoint_C': 'green',
        'atmospheric_pressure_mb': 'orange',
        'cloudiness': 'purple',
        'wind_speed_ms': 'brown'
    }
    
    fig = make_subplots(
        rows=len(variables),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=variables
    )
    
    for i, var in enumerate(variables, start=1):
        subset = df_met[df_met['variable'] == var]
        fig.add_trace(
            go.Scatter(
                x=subset['date'], 
                y=subset['value'], 
                mode='lines', 
                name=var, 
                line=dict(color=colors.get(var, 'black')),
                connectgaps=True
            ),
            row=i,
            col=1
        )
        
        fig.add_shape(
            type='rect',
            xref='x domain', x0=0, x1=1,
            yref='y domain', y0=0, y1=1,
            line=dict(color='black', width=2),
            row=i, col=1
        )
        
        if var == "air_temperature_C":
            fig.add_hline(
                y=0,
                line_color="black",
                row=i,
                col=1
            )
    
    # Update layout
    fig.update_layout(
        height=300 * len(variables),
        title="Meteorological Data",
        showlegend=False,
        template="plotly_white",
        font=dict(color='black'),
        title_font=dict(color='black', size=16)
    )
    
    fig.update_xaxes(title_text="Date", row=len(variables), col=1)
    
    for i in range(1, len(variables) + 1):
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray', row=i, col=1)
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray', row=i, col=1)
        fig.update_xaxes(tickfont=dict(color='black'), title_font=dict(color='black'), row=i, col=1)
        fig.update_yaxes(tickfont=dict(color='black'), title_font=dict(color='black'), row=i, col=1)
    
    return fig
# def plot_met(df):
#     """
#     Creates a series of subplots, each showing one of the meteorological variables
#     over the same x-axis (date).
#     """
#     df = df[~df.index.duplicated(keep='first')]
#     # Extract each series
#     T_air_C = df['air_temperature_C']
#     relative_humidity = df['humidity_%RH']
#     T_dewpoint_C = df['dewpoint_C']
#     P = df['atmospheric_pressure_mb']
#     Cl = df['cloudiness']
#     U = df['wind_speed_ms']

#     # Create a figure with 5 rows of subplots
#     fig, axes = plt.subplots(nrows=6, ncols=1, figsize=(12, 8), sharex=True)

#     # 1) Air Temperature
#     sns.lineplot(x=df.index, y=T_air_C, ax=axes[0], color='red')
#     axes[0].set_title('Air Temperature (°C)')

#     # 2) Relative Humidity
#     sns.lineplot(x=df.index, y=relative_humidity, ax=axes[1], color='blue')
#     axes[1].set_title('Relative Humidity (%)')

#     # 3) Dewpoint
#     sns.lineplot(x=df.index, y=T_dewpoint_C, ax=axes[2], color='green')
#     axes[2].set_title('Dewpoint (°C)')

#     # 4) Atmospheric Pressure
#     sns.lineplot(x=df.index, y=P, ax=axes[3], color='orange')
#     axes[3].set_title('Atmospheric Pressure (mb)')

#     # 5) Cloudiness
#     sns.lineplot(x=df.index, y=Cl, ax=axes[4], color='purple')
#     axes[4].set_title('Cloudiness')

#     # 6) Wind Speed
#     sns.lineplot(x=df.index, y=U, ax=axes[5], color='brown')
#     axes[5].set_title('Windspeed (m/s)')   

#     # Improve spacing
#     plt.tight_layout()
#     return fig

def calc_fluxes(df, T_water_C, lat, lon, a=10 ** -6, b=10 ** -6, c=1, R=1):
    # calc solar input
    # times = pd.date_range(start=df.index.min(), end=df.index.max(), freq='1H')
    times = df.index
    elevation = get_elevation(lat, lon)

    site_name = 'general location'
    tz = df.index.tz
    ghi = get_solar(lat, lon, elevation, site_name, times, tz).ghi

    # calculate effects of clouds on shortwave
    solar_R = 0.15  # Maidment et al. (1996) Handbook of Hydrology
    Cl = df['cloudiness']
    q_sw = calc_solar(ghi, solar_R, Cl)

    # calc longwave down
    T_air_C = df['air_temperature_C']
    q_atm = calc_downwelling_LW(T_air_C, Cl)

    # calc longwave up
    q_b = calc_upwelling_LW(T_water_C)

    # calc wind function
    # a = 10 ** -6
    # b = 10 ** -6
    # c = 1
    # R = 1

    U = df['wind_speed_ms']
    f_U = calc_wind_function(a, b, c, R, U)

    # calc latent heat
    relative_humidity = df['humidity_%RH']
    T_dewpoint_C = df['dewpoint_C']
    ea = calc_vapor_pressure(T_dewpoint_C)
    P = df['atmospheric_pressure_mb']

    q_l = calc_latent_heat(P, T_water_C, ea, f_U)

    # calc sensible heat
    q_h = calc_sensible_heat(T_air_C, f_U, T_water_C)

    # calculate net heat flux
    q_net = q_sw + q_atm - q_b + q_h - q_l

    return q_sw, q_atm, q_b, q_l, q_h, q_net

def return_lat_lon(df):
    lat = df.lat[0]
    lon = df.lon[0]
    return lat, lon

def build_energy_df(q_sw, q_atm, q_b, q_l, q_h):
    energy_df = pd.DataFrame(
        {'downwelling SW': q_sw, 'downwelling LW': q_atm, 'upwelling LW': -q_b, 'sensible heat': q_h,
         'latent heat': -q_l})
    energy_df['net flux'] = energy_df.sum(axis=1)
    #remove rows with missing data
    energy_df = energy_df.dropna()
    return energy_df


# def plot_forecast_heat_fluxes(energy_df):
#     energy_df = pd.melt(energy_df.reset_index(), id_vars='date')
#     fig, ax = plt.subplots(figsize=(15, 5))
#     ax = sns.lineplot(data=energy_df, x="date", y="value", hue='variable')
#     plt.ylabel('Heat Flux (W/m2)', fontsize=12)
#     plt.xlabel('')
#     return fig


def plot_historic_heat_fluxes(energy_df):
    """
    Create an interactive Plotly line plot of heat fluxes, highlighting 'net flux'
    in bold black.
    """
    # Convert wide DataFrame to long-form
    energy_long = pd.melt(energy_df.reset_index(), id_vars='date')

    # Create the Plotly Express line chart
    fig = px.line(
        energy_long,
        x='date',
        y='value',
        color='variable',
        # color_discrete_sequence=px.colors.qualitative.Bold,
        # If you want consistent coloring per variable, you could specify a dict:
        color_discrete_map={
            'downwelling SW': 'blue',
            'downwelling LW': 'orange',
            'upwelling LW': 'green',
            'sensible heat': 'red',
            'latent heat': 'purple',
            'net flux': 'black'
        },
    )

    # Make the 'net flux' line thicker and black
    for trace in fig.data:
        if trace.name == 'net flux':
            trace.line.width = 3
            trace.line.color = 'black'
        else:
            # Optionally make other lines thinner or semi-transparent
            trace.line.width = 2
            trace.opacity = 0.8

    # Customize layout
    fig.update_layout(
        title='Energy Fluxes',
        xaxis_title='',
        yaxis_title='Energy Flux (W/m²)',
        legend_title_text='Flux Type',
        template='plotly_white'
    )

    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    
    return fig

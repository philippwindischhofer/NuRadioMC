from __future__ import absolute_import, division, print_function  # , unicode_literals
from dash.dependencies import Input, Output, State
import dash
import dash_html_components as html
import dash_core_components as dcc
import plotly.graph_objs as go
import plotly
from plotly import tools
import json
from app import app
import dataprovider
from NuRadioReco.utilities import units
from NuRadioReco.utilities import templates
from NuRadioReco.utilities import trace_utilities
from NuRadioReco.utilities import fft
from NuRadioReco.utilities import geometryUtilities
from NuRadioReco.detector import detector
from NuRadioReco.framework.parameters import stationParameters as stnp
from NuRadioReco.framework.parameters import channelParameters as chp
from NuRadioReco.framework.parameters import electricFieldParameters as efp
from NuRadioReco.eventbrowser.default_layout import default_layout
import NuRadioReco.detector.antennapattern
import numpy as np
import logging
import os

logger = logging.getLogger('traces')

provider = dataprovider.DataProvider()
# if environment variable for templates is set, we use it, otherwise we later
# get the template directory from user input
if 'NURADIORECOTEMPLATES' in os.environ:
    template_provider = templates.Templates(os.environ.get('NURADIORECOTEMPLATES'))
else:
    template_provider = templates.Templates('')
det = detector.Detector()
antenna_pattern_provider = NuRadioReco.detector.antennapattern.AntennaPatternProvider()

layout = html.Div([
    html.Div(id='trigger-trace', style={'display': 'none'}),
    html.Div([
        html.Div([
            html.Div('Electric Field Traces', className='panel-heading'),
            html.Div([
            dcc.Graph(id='efield-trace')
            ], className='panel-body')
        ], className='panel panel-default', style={'flex': '1'}),
        html.Div([
            html.Div('Electric Field Spectrum', className='panel-heading'),
            html.Div([
            dcc.Graph(id='efield-spectrum')
            ], className='panel-body')
        ], className='panel panel-default', style={'flex': '1'})
    ], style={'display': 'flex'}),
    html.Div([
        html.Div([
            html.Div('Channel Traces', className='panel-heading'),
            html.Div([
                dcc.Graph(id='time-trace')
            ], className='panel-body')
        ], className='panel panel-default', style={'flex': '1'}),
        html.Div([
            html.Div('Channel Spectrum', className='panel-heading'),
            html.Div([
                dcc.Graph(id='channel-spectrum')
            ], className='panel-body')
        ], className='panel panel-default', style={'flex': '1'})
    ], style={'display': 'flex'}),
    html.Div([
        html.Div([
            html.Div('Individual Channels', className='panel-heading'),
            html.Div([
                html.Div([
                    html.Div([
                        dcc.Dropdown(id='dropdown-traces',
                            options=[
                                {'label': 'calibrated trace', 'value': 'trace'},
                                {'label': 'cosmic-ray template', 'value': 'crtemplate'},
                                {'label': 'neutrino template', 'value': 'nutemplate'},
                                {'label': 'envelope', 'value': 'envelope'},
                                {'label': 'from rec. E-field', 'value': 'efield'}
                            ],
                            multi=True,
                            value=["trace"]
                        )
                    ], style={'flex': '1'}),
                    html.Div([
                        dcc.Dropdown(id='dropdown-trace-info',
                            options=[
                                {'label': 'RMS', 'value': 'RMS'},
                                {'label': 'L1', 'value': 'L1'}
                            ],
                            multi=True,
                            value=["RMS", "L1"]
                        )
                    ], style={'flex': '1'}),
                ], style={'display': 'flex'}),
                html.Div([
                    html.Div([
                        html.Div([
                            html.Div('Template directory', className='input-group-addon'),
                            dcc.Input(id='template-directory-input', placeholder='template directory', className='form-control'),
                            html.Div([
                                html.Button('load', id='open-template-button', className='btn btn-default')
                            ], className='input-group-btn')
                        ], className='input-group', id='template-input-group')
                    ], style={'flex': '1'}),
                    html.Div('', style={'flex': '1'})
                ], style={'display': 'flex'}),
                dcc.Graph(id='time-traces')
            ], className='panel-body')
        ], className='panel panel-default', style={'flex': '1'})
    ], style={'display': 'flex'}),
    dcc.Graph(id='time-traces2')
])


def get_L1(a):
    ct = np.array(a[1:]) ** 2
    l1 = np.max(ct) / (np.sum(ct) - np.max(ct))
    return l1

@app.callback(
    dash.dependencies.Output('efield-trace', 'figure'),
    [dash.dependencies.Input('trigger-trace', 'children'),
     dash.dependencies.Input('event-counter-slider', 'value'),
     dash.dependencies.Input('filename', 'value'),
     dash.dependencies.Input('station-id-dropdown', 'value')],
     [State('user_id', 'children')])
def update_time_efieldtrace(trigger, evt_counter, filename, station_id, juser_id):
    if filename is None or station_id is None:
        return {}
    user_id = json.loads(juser_id)
    colors = plotly.colors.DEFAULT_PLOTLY_COLORS
    ariio = provider.get_arianna_io(user_id, filename)
    evt = ariio.get_event_i(evt_counter)
    station = evt.get_station(station_id)
    fig = tools.make_subplots(rows=1, cols=1)
    for electric_field in station.get_electric_fields():
        if electric_field.get_trace() is None:
            trace = np.array([[],[],[]])
        else:
            trace = electric_field.get_trace()
        fig.append_trace(go.Scatter(
                x=electric_field.get_times() / units.ns,
                y=trace[0] / units.mV * units.m,
                # text=df_by_continent['country'],
                # mode='markers',
                opacity=0.7,
                marker={
                    'color': colors[0],
                    'line': {'color': colors[0]}
                },
                name='eR'
            ), 1, 1)
        fig.append_trace(go.Scatter(
                x=electric_field.get_times() / units.ns,
                y=trace[1] / units.mV * units.m,
                # text=df_by_continent['country'],
                # mode='markers',
                opacity=0.7,
                marker={
                    'color': colors[1],
                    'line': {'color': colors[1]}
                },
                name='eTheta'
            ), 1, 1)
        fig.append_trace(go.Scatter(
                x=electric_field.get_times() / units.ns,
                y=trace[2] / units.mV * units.m,
                # text=df_by_continent['country'],
                # mode='markers',
                opacity=0.7,
                marker={
                    'color': colors[2],
                    'line': {'color': colors[2]}
                },
                name='ePhi'
            ), 1, 1)
    fig['layout']['xaxis1'].update(title='time [ns]')
    fig['layout']['yaxis1'].update(title='efield [mV/m]')
    fig['layout'].update(default_layout)
    return fig
@app.callback(
    dash.dependencies.Output('efield-spectrum', 'figure'),
    [dash.dependencies.Input('trigger-trace', 'children'),
     dash.dependencies.Input('event-counter-slider', 'value'),
     dash.dependencies.Input('filename', 'value'),
     dash.dependencies.Input('station-id-dropdown', 'value')],
     [State('user_id', 'children')])
def update_efield_spectrum(trigger, evt_counter, filename, station_id, juser_id):
    if filename is None or station_id is None:
        return {}
    user_id = json.loads(juser_id)
    colors = plotly.colors.DEFAULT_PLOTLY_COLORS
    ariio = provider.get_arianna_io(user_id, filename)
    evt = ariio.get_event_i(evt_counter)
    station = evt.get_station(station_id)
    fig = tools.make_subplots(rows=1, cols=1)
    for electric_field in station.get_electric_fields():
        if electric_field.get_frequencies() is None:
            spectrum = np.array([[],[],[]])
            frequencies = np.array([[],[],[]])
        else:
            spectrum = electric_field.get_frequency_spectrum()
            frequencies = electric_field.get_frequencies()
        fig.append_trace(go.Scatter(
                x=frequencies / units.MHz,
                y=np.abs(spectrum[1]) / units.mV,
                opacity=0.7,
                marker={
                    'color': colors[1],
                    'line': {'color': colors[1]}
                },
                name='eTheta'
            ), 1, 1)
        fig.append_trace(go.Scatter(
                x=frequencies / units.MHz,
                y=np.abs(spectrum[2]) / units.mV,
                opacity=0.7,
                marker={
                    'color': colors[2],
                    'line': {'color': colors[2]}
                },
                name='ePhi'
            ), 1, 1)
    fig['layout'].update(default_layout)
    fig['layout']['xaxis1'].update(title='frequency [MHz]')
    fig['layout']['yaxis1'].update(title='amplitude [mV/m]')
    return fig
        
@app.callback(
    dash.dependencies.Output('time-trace', 'figure'),
    [dash.dependencies.Input('trigger-trace', 'children'),
     dash.dependencies.Input('event-counter-slider', 'value'),
     dash.dependencies.Input('filename', 'value'),
     dash.dependencies.Input('station-id-dropdown', 'value')],
     [State('user_id', 'children')])
def update_time_trace(trigger, evt_counter, filename, station_id, juser_id):
    if filename is None or station_id is None:
        return {}
    user_id = json.loads(juser_id)
    colors = plotly.colors.DEFAULT_PLOTLY_COLORS
    ariio = provider.get_arianna_io(user_id, filename)
    evt = ariio.get_event_i(evt_counter)
    station = evt.get_station(station_id)
    traces = []
    fig = tools.make_subplots(rows=1, cols=1)
    for i, channel in enumerate(station.iter_channels()):
        fig.append_trace(go.Scatter(
                x=channel.get_times() / units.ns,
                y=channel.get_trace() / units.mV,
                # text=df_by_continent['country'],
                # mode='markers',
                opacity=0.7,
                marker={
                    'color': colors[i % len(colors)],
                    'line': {'color': colors[i % len(colors)]}
                },
                name='Channel {}'.format(i)
            ), 1, 1)
    fig['layout'].update(default_layout)
    fig['layout']['xaxis1'].update(title='time [ns]')
    fig['layout']['yaxis1'].update(title='voltage [mV]')
    return fig
    
@app.callback(
    dash.dependencies.Output('channel-spectrum', 'figure'),
    [dash.dependencies.Input('trigger-trace', 'children'),
     dash.dependencies.Input('event-counter-slider', 'value'),
     dash.dependencies.Input('filename', 'value'),
     dash.dependencies.Input('station-id-dropdown', 'value')],
     [State('user_id', 'children')])
def update_channel_spectrum(trigger, evt_counter, filename, station_id, juser_id):
    if filename is None or station_id is None:
        return {}
    user_id = json.loads(juser_id)
    colors = plotly.colors.DEFAULT_PLOTLY_COLORS
    ariio = provider.get_arianna_io(user_id, filename)
    evt = ariio.get_event_i(evt_counter)
    station = evt.get_station(station_id)
    traces = []
    fig = tools.make_subplots(rows=1, cols=1)
    maxL1 = 0
    maxY = 0
    for i, channel in enumerate(station.iter_channels()):
        tt = channel.get_times()
        dt = tt[1] - tt[0]
        trace = channel.get_trace()
        ff = np.fft.rfftfreq(len(tt), dt)
        spec = np.abs(np.fft.rfft(trace, norm='ortho'))
        maxL1 = max(maxL1, get_L1(spec))
        maxY = max(maxY, spec.max())
        fig.append_trace(go.Scatter(
                x=ff / units.MHz,
                y=spec / units.mV,
                opacity=0.7,
                marker={
                    'color': colors[i % len(colors)],
                    'line': {'color': colors[i % len(colors)]}
                },
                name='Channel {}'.format(i)
            ), 1, 1)
    fig.append_trace(
           go.Scatter(
                x=[0.9 * ff.max() / units.MHz],
                y=[0.8 * maxY / units.mV],
                mode='text',
                text=['max L1 = {:.2f}'.format(maxL1)],
                textposition='top center'
            ),
        1, 1)
    fig['layout'].update(default_layout)
    fig['layout']['xaxis1'].update(title='frequency [MHz]')
    fig['layout']['yaxis1'].update(title='amplitude [mV]')
    return fig

@app.callback(
    dash.dependencies.Output('dropdown-traces', 'options'),
    [dash.dependencies.Input('event-counter-slider', 'value'),
     dash.dependencies.Input('filename', 'value'),
     dash.dependencies.Input('station-id-dropdown', 'value')],
     [State('user_id', 'children')]
)
def get_dropdown_traces_options(evt_counter, filename, station_id, juser_id):
    if filename is None or station_id is None:
        return []
    user_id = json.loads(juser_id)
    ariio = provider.get_arianna_io(user_id, filename)
    evt = ariio.get_event_i(evt_counter)
    station = evt.get_station(station_id)
    options=[
        {'label': 'calibrated trace', 'value': 'trace'},
        {'label': 'cosmic-ray template', 'value': 'crtemplate'},
        {'label': 'neutrino template', 'value': 'nutemplate'},
        {'label': 'envelope', 'value': 'envelope'},
        {'label': 'from rec. E-field', 'value': 'recefield'}
    ]
    if station.get_sim_station() is not None:
        if len(station.get_sim_station().get_electric_fields()) > 0:
            options.append({'label': 'from sim. E-field', 'value': 'simefield'})
    return options

@app.callback(
    dash.dependencies.Output('time-traces', 'figure'),
    [dash.dependencies.Input('event-counter-slider', 'value'),
     dash.dependencies.Input('filename', 'value'),
     dash.dependencies.Input('dropdown-traces', 'value'),
     dash.dependencies.Input('dropdown-trace-info', 'value'),
     dash.dependencies.Input('station-id-dropdown', 'value'),
     dash.dependencies.Input('open-template-button', 'n_clicks_timestamp')],
     [State('user_id', 'children'),
     State('template-directory-input', 'value')])
def update_time_traces(evt_counter, filename, dropdown_traces, dropdown_info, station_id, open_template_timestamp, juser_id, template_directory):
    if filename is None or station_id is None:
        return {}
    user_id = json.loads(juser_id)
    colors = plotly.colors.DEFAULT_PLOTLY_COLORS
    ariio = provider.get_arianna_io(user_id, filename)
    evt = ariio.get_event_i(evt_counter)
    station = evt.get_station(station_id)
    traces = []
    fig = tools.make_subplots(rows=station.get_number_of_channels(), cols=2,
                              shared_xaxes=True, shared_yaxes=False,
                              vertical_spacing=0.01)
    ymax = 0
    for i, channel in enumerate(station.iter_channels()):
        trace = channel.get_trace() / units.mV
        ymax = max(ymax, np.max(np.abs(trace)))
    if 'trace' in dropdown_traces:
        for i, channel in enumerate(station.iter_channels()):
            tt = channel.get_times() / units.ns
            trace = channel.get_trace() / units.mV
            fig.append_trace(go.Scatter(
                    x=tt,
                    y=trace,
                    # text=df_by_continent['country'],
                    # mode='markers',
                    opacity=0.7,
                    marker={
                        'color': colors[i % len(colors)],
                        'line': {'color': colors[i % len(colors)]}
                    },
                    name=i
                ), i + 1, 1)
            if 'RMS' in dropdown_info:
                fig.append_trace(
                       go.Scatter(
                            x=[0.99 * tt.max()],
                            y=[0.98 * trace.max()],
                            mode='text',
                            text=[r'mu = {:.2f}, STD={:.2f}'.format(np.mean(trace), np.std(trace))],
                            textposition='bottom left'
                        ),
                    i + 1, 1)
    if 'envelope' in dropdown_traces:
        for i, channel in enumerate(station.iter_channels()):
            trace = channel.get_trace() / units.mV
            from scipy import signal
            yy = np.abs(signal.hilbert(trace))
            fig.append_trace(go.Scatter(
                    x=channel.get_times() / units.ns,
                    y=yy,
                    # text=df_by_continent['country'],
                    # mode='markers',
                    opacity=0.7,
                    line=dict(
                        width=4,
                        dash='dot'),  # dash options include 'dash', 'dot', and 'dashdot'
                    marker={
                        'color': colors[i % len(colors)],
                        'line': {'color': colors[i % len(colors)]}
                    },
                    name=i
                ), i + 1, 1)
    if 'crtemplate' in dropdown_traces:
        if not 'NURADIORECOTEMPLATES' in os.environ: # if the environment variable is not set, we have to ask the user to specify the template location
            template_provider.set_template_directory(template_directory)
        ref_template = template_provider.get_cr_ref_template(station_id)
        if(station.has_parameter(stnp.cr_xcorrelations)):
            ref_templates = template_provider.get_set_of_cr_templates(station_id, n=station.get_parameter(stnp.cr_xcorrelations)['number_of_templates'])
        for i, channel in enumerate(station.iter_channels()):
            if(channel.has_parameter(chp.cr_xcorrelations)):
                key = channel.get_parameter(chp.cr_xcorrelations)['cr_ref_xcorr_template']
                logger.info("using template {}".format(key))
                print(ref_templates.keys())
                ref_template = ref_templates[key][channel.get_id()]
            times = channel.get_times()
            trace = channel.get_trace()
            xcorr = channel.get_parameter(chp.cr_xcorrelations)['cr_ref_xcorr']
            xcorrpos = channel.get_parameter(chp.cr_xcorrelations)['cr_ref_xcorr_time']
            dt = times[1] - times[0]
            xcorr_max = xcorr
            if(channel.has_parameter(chp.cr_xcorrelations)):
                xcorr_max = channel.get_parameter(chp.cr_xcorrelations)['cr_ref_xcorr_max']
            flip = np.sign(xcorr_max)
#             flip = 1
            tttemp = np.arange(0, len(ref_template) * dt, dt)
            yy = flip * ref_template * np.abs(trace).max()
            fig.append_trace(go.Scatter(
                    x=tttemp[:len(trace)] / units.ns,
                    y=yy[:len(trace)] / units.mV,
                    # text=df_by_continent['country'],
                    # mode='markers',
                    opacity=0.7,
                    line=dict(
                        width=2,
                        dash='dot'),  # dash options include 'dash', 'dot', and 'dashdot'
                    marker={
                        'color': colors[i % len(colors)],
                        'line': {'color': colors[i % len(colors)]}
                    },
                    name=i
                ), i + 1, 1)
            template_spectrum = fft.time2freq(yy)
            template_freqs = np.fft.rfftfreq(len(yy), dt)
            template_freq_mask = (template_freqs > channel.get_frequencies()[0])&(template_freqs<(channel.get_frequencies()[-1]))
            fig.append_trace(go.Scatter(
                x = template_freqs[template_freq_mask] / units.MHz,
                y = np.abs(template_spectrum)[template_freq_mask] / units.mV,
                line=dict(
                    width=2,
                    dash='dot'
                ),
                name=i
            ), i+1, 2)
            fig.append_trace(
               go.Scatter(
                    x=[0.9 * times.max() / units.ns],
                    y=[0.8 * trace.max() / units.mV],
                    mode='text',
                    text=['cr xcorr= {:.2f}, {:.02f}'.format(xcorr, xcorr_max)],
                    textposition='top center'
                ),
            i + 1, 1)
            fig.append_trace(
               go.Scatter(
                    x=[0.9 * times.max() / units.ns],
                    y=[0.5 * trace.max() / units.mV],
                    mode='text',
                    text=['t = {:.0f}ns'.format(xcorrpos)],
                    textposition='top center'
                ),
            i + 1, 1)
    if 'nutemplate' in dropdown_traces:
        if not 'NURADIORECOTEMPLATES' in os.environ: # if the environment variable is not set, we have to ask the user to specify the template location
            template_provider.set_template_directory(template_directory)
        ref_template = template_provider.get_nu_ref_template(station_id)
        for i, channel in enumerate(station.iter_channels()):
            times = channel.get_times()
            trace = channel.get_trace()
            xcorr = channel.get_parameter(chp.nu_xcorrelations)['nu_ref_xcorr']
            xcorrpos = channel.get_parameter(chp.nu_xcorrelations)['nu_ref_xcorr_time']
            dt = times[1] - times[0]
            flip = np.sign(xcorr)
            tttemp = np.arange(0, len(ref_template) * dt, dt)
            yy = flip * ref_template * np.abs(trace).max()
            fig.append_trace(go.Scatter(
                    x=tttemp[:len(trace)] / units.ns,
                    y=yy[:len(trace)] / units.mV,
                    # text=df_by_continent['country'],
                    # mode='markers',
                    opacity=0.7,
                    line=dict(
                        width=4,
                        dash='dot'),  # dash options include 'dash', 'dot', and 'dashdot'
                    marker={
                        'color': colors[i % len(colors)],
                        'line': {'color': colors[i % len(colors)]}
                    },
                    name=i
                ), i + 1, 1)
            template_spectrum = fft.time2freq(yy)
            template_freqs = np.fft.rfftfreq(len(yy), dt)
            template_freq_mask = (template_freqs > channel.get_frequencies()[0])&(template_freqs<(channel.get_frequencies()[-1]))
            fig.append_trace(go.Scatter(
                x = template_freqs[template_freq_mask] / units.MHz,
                y = np.abs(template_spectrum)[template_freq_mask] / units.mV,
                line=dict(
                    width=2,
                    dash='dot'
                ),
                name=i
            ), i+1, 2)
            
            fig.append_trace(
               go.Scatter(
                    x=[0.9 * times.max() / units.ns],
                    y=[0.8 * trace.max() / units.mV],
                    mode='text',
                    text=['nu xcorr= {:.2f}'.format(xcorr)],
                    textposition='top center'
                ),
            i + 1, 1)
            fig.append_trace(
               go.Scatter(
                    x=[0.9 * times.max() / units.ns],
                    y=[0.5 * trace.max() / units.mV],
                    mode='text',
                    text=['t = {:.0f}ns'.format(xcorrpos)],
                    textposition='top center'
                ),
            i + 1, 1)
    if 'recefield' in dropdown_traces or 'simefield' in dropdown_traces:
        det.update(station.get_station_time_stamp())
    if 'recefield' in dropdown_traces:
        channel_ids = []
        for channel in station.iter_channels():
            channel_ids.append(channel.get_id())
        for electric_field in station.get_electric_fields():
            for i_trace, trace in enumerate(trace_utilities.get_channel_voltage_from_efield(station, electric_field, channel_ids, det, station.get_parameter(stnp.zenith), station.get_parameter(stnp.azimuth), antenna_pattern_provider)):
                    channel = station.get_channel(channel_ids[i_trace])
                    direction_time_delay = geometryUtilities.get_time_delay_from_direction(station.get_parameter(stnp.zenith), station.get_parameter(stnp.azimuth), det.get_relative_position(station.get_id(),channel_ids[i_trace]) - electric_field.get_position())
                    time_shift = direction_time_delay
                    fig.append_trace(go.Scatter(
                        x=(electric_field.get_times() + time_shift)/units.ns,
                        y=fft.freq2time(trace)/units.mV,
                        line=dict(
                            dash='solid',
                            color=colors[i_trace%len(colors)]
                        ),
                        opacity=.5
                    ), i_trace+1, 1)
                    fig.append_trace(go.Scatter(
                        x=electric_field.get_frequencies()/units.MHz,
                        y=np.abs(trace)/units.mV,
                        line=dict(
                            dash='solid',
                            color=colors[i_trace%len(colors)]
                        ),
                        opacity=.5
                    ), i_trace + 1, 2)
    if 'simefield' in dropdown_traces:
        channel_ids = []
        sim_station = station.get_sim_station()
        for channel in station.iter_channels():
            channel_ids.append(channel.get_id())
        for electric_field in sim_station.get_electric_fields():
            for i_trace, trace in enumerate(trace_utilities.get_channel_voltage_from_efield(sim_station, electric_field, channel_ids, det, sim_station.get_parameter(stnp.zenith), sim_station.get_parameter(stnp.azimuth), antenna_pattern_provider)):
                    channel = station.get_channel(channel_ids[i_trace])
                    direction_time_delay = geometryUtilities.get_time_delay_from_direction(sim_station.get_parameter(stnp.zenith), sim_station.get_parameter(stnp.azimuth), det.get_relative_position(sim_station.get_id(),channel_ids[i_trace]) - electric_field.get_position())
                    time_shift = direction_time_delay
                    fig.append_trace(go.Scatter(
                        x=(electric_field.get_times() + time_shift)/units.ns,
                        y=fft.freq2time(trace)/units.mV,
                        line=dict(
                            dash='solid',
                            color=colors[i_trace%len(colors)]
                        ),
                        opacity=.5
                    ), i_trace+1, 1)
                    fig.append_trace(go.Scatter(
                        x=electric_field.get_frequencies()/units.MHz,
                        y=np.abs(trace)/units.mV,
                        line=dict(
                            dash='solid',
                            color=colors[i_trace%len(colors)]
                        ),
                        opacity=.5
                    ), i_trace + 1, 2)
    for i, channel in enumerate(station.iter_channels()):
        fig['layout']['yaxis{:d}'.format(i * 2 + 1)].update(range=[-ymax, ymax])

        tt = channel.get_times()
        dt = tt[1] - tt[0]
        spec = channel.get_frequency_spectrum()
        ff = channel.get_frequencies()
        fig.append_trace(go.Scatter(
                x=ff / units.MHz,
                y=np.abs(spec) / units.mV,
                opacity=0.7,
                marker={
                    'color': colors[i % len(colors)],
                    'line': {'color': colors[i % len(colors)]}
                },
                name=i
            ), i + 1, 2)
        if 'L1' in dropdown_info:
            fig.append_trace(
                   go.Scatter(
                        x=[0.9 * ff.max() / units.MHz],
                        y=[0.8 * np.abs(spec).max() / units.mV],
                        mode='text',
                        text=['max L1 = {:.2f}'.format(get_L1(spec))],
                        textposition='top center'
                    ),
                i + 1, 2)
    fig['layout'].update(default_layout)
    fig['layout']['xaxis1'].update(title='time [ns]')
    fig['layout']['yaxis1'].update(title='voltage [mV]')
    fig['layout'].update(height=1000)
    return fig


@app.callback(
    dash.dependencies.Output('time-traces2', 'figure'),
    [dash.dependencies.Input('event-counter-slider', 'value'),
     dash.dependencies.Input('filename', 'value'),
     dash.dependencies.Input('dropdown-traces', 'value'),
     dash.dependencies.Input('station-id-dropdown', 'value')],
     [State('user_id', 'children')])
def update_time_traces2(evt_counter, filename, dropdown_traces, station_id, juser_id):
    if filename is None or station_id is None:
        return {}
    user_id = json.loads(juser_id)
    colors = plotly.colors.DEFAULT_PLOTLY_COLORS
    ariio = provider.get_arianna_io(user_id, filename)
    evt = ariio.get_event_i(evt_counter)
    station = evt.get_station(station_id)
    traces = []
    fig = tools.make_subplots(rows=4, cols=1,
                              shared_xaxes=True, shared_yaxes=True,
                              vertical_spacing=0.05)
    if 'trace' in dropdown_traces:
        for i, iCh in enumerate(range(4, min([8, station.get_number_of_channels()]))):
            channel = station.get_channel(iCh)
            fig.append_trace(go.Scatter(
                    x=channel.get_times() / units.ns,
                    y=channel.get_trace() / units.mV,
                    # text=df_by_continent['country'],
                    # mode='markers',
                    opacity=0.7,
                    marker={
                        'color': colors[i % len(colors)],
                        'line': {'color': colors[i % len(colors)]}
                    },
                    name=i
                ), i + 1, 1)
    if 'crtemplate' in dropdown_traces:
        ref_templates = template_provider.get_cr_ref_template(station_id)
        for i, iCh in enumerate(range(4, 8)):
            channel = station.get_channel(iCh)
            times = channel.get_times()
            trace = channel.get_trace()
            xcorr = channel['cr_ref_xcorr']
            xcorrpos = channel['cr_ref_xcorr_time']
            dt = times[1] - times[0]
            flip = np.sign(xcorr)
            tttemp = np.arange(0, len(ref_templates[channel.get_id()]) * dt, dt)
            yy = flip * np.roll(ref_templates[channel.get_id()] * np.abs(trace).max(), int(np.round(xcorrpos / dt)))
            fig.append_trace(go.Scatter(
                    x=tttemp[:len(trace)] / units.ns,
                    y=yy[:len(trace)] / units.mV,
                    # text=df_by_continent['country'],
                    # mode='markers',
                    opacity=0.7,
                    line=dict(
                        width=4,
                        dash='dot'),  # dash options include 'dash', 'dot', and 'dashdot'
                    marker={
                        'color': colors[i % len(colors)],
                        'line': {'color': colors[i % len(colors)]}
                    },
                    name=i
                ), i + 1, 1)
    yrange = [-100, 100]
    fig['layout']['xaxis1'].update(title='time [ns]')
    fig['layout']['yaxis1'].update(title='voltage [mV]', range=yrange)
    fig['layout']['yaxis2'].update(title='voltage [mV]', range=yrange)
    fig['layout']['yaxis3'].update(title='voltage [mV]', range=yrange)
    fig['layout']['yaxis4'].update(title='voltage [mV]', range=yrange)
    fig['layout'].update(height=700, width=700)
    fig['layout'].showlegend = False
    return fig

@app.callback(
    Output('template-input-group', 'style'),
    [Input('dropdown-traces', 'value')]
)
def show_template_input(trace_dropdown_options):
    if 'NURADIORECOTEMPLATES' in os.environ:
        return {'display': 'none'}
    if 'crtemplate' in trace_dropdown_options or 'nutemplate' in trace_dropdown_options:
        return {}
    return {'display': 'none'}

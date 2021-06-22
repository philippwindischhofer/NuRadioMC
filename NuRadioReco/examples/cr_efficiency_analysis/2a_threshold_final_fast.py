import numpy as np
from NuRadioReco.utilities import units
import scipy.signal
import helper_cr_eff as hcr
import os
import time
import json
import NuRadioReco.modules.channelGenericNoiseAdder
import NuRadioReco.modules.channelGalacticNoiseAdder
import NuRadioReco.modules.trigger.envelopeTrigger
import NuRadioReco.modules.RNO_G.hardwareResponseIncorporator
import NuRadioReco.modules.eventTypeIdentifier
import NuRadioReco.utilities.fft
from NuRadioReco.detector.generic_detector import GenericDetector
from NuRadioReco.modules.trigger.highLowThreshold import get_majority_logic
import argparse
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('Threshold final')


'''
This script relies on the output of 1a_threshold_estimate_fast.py. It calculates the noise trigger rate of each threshold 
starting from the one given in the dictionary. To obtain a resolution of 0.5 Hz almost 2e6 iterations are necessary.
Therefor I commit this job 100 times to the cluster with an iteration of 20000. 

the sampling rate has a huge influence on the threshold, because the trace has more time to exceed the threshold
for a sampling rate of 1GHz, 1955034 iterations yields a resolution of 0.5 Hz
if galactic noise is used it adds a factor of 10 (n_random_phase) to the number of iterations because it dices the phase 10 times. 
This is done due to computation efficiency

For on passband I used something on the cluster like:
for number in $(seq 0 1 110); do echo $number; qsub Cluster_ntr_2.sh $number; sleep 0.2; done;

for several passbands I used:
FILES=output_threshold_estimate/*

for file in $FILES
do
echo "Processing $file"
  for number in $(seq 0 1 110)
  do echo $number
  qsub /afs/ifh.de/group/radio/scratch/lpyras/Cluster_jobs/Cluster_ntr_threshold_second.sh $file 20000 $number
  sleep 0.2
  done
done
'''

parser = argparse.ArgumentParser(description='Noise Trigger Rate')
parser.add_argument('input_filename', type=str, nargs='?',
                    default='output_threshold_estimate/estimate_threshold_envelope_fast_pb_80_180_i20.json',
                    help='input filename from which the calculation starts.')
parser.add_argument('iterations', type=int, nargs='?', default=20,
                    help='number of iterations within the script. Has to be a multiple of 10 (n_random_phase)')
parser.add_argument('number', type=int, nargs='?', default=1,
                    help='specify how often you would like to run the hole script. Important for cluster use')
parser.add_argument('output_path', type=os.path.abspath, nargs='?', default='',
                    help='Path to save output, most likely the path to the cr_efficiency_analysis directory')
parser.add_argument('threshold_steps', type=int, nargs='?', default=0.000001,
                    help='steps in which threshold increases [V], use 1e-3 with amp, 1e-6 without amp')

args = parser.parse_args()
output_path = args.output_path
abs_output_path = os.path.abspath(args.output_path)
input_filename = args.input_filename
number = args.number
threshold_steps = args.threshold_steps

with open(input_filename, 'r') as fp:
    data = json.load(fp)

detector_file = data['detector_file']
triggered_channels = data['triggered_channels']
default_station = data['default_station']
sampling_rate = data['sampling_rate']
station_time = data['station_time']
station_time_random = data['station_time_random']

Vrms_thermal_noise = data['Vrms_thermal_noise']
T_noise = data['T_noise']
T_noise_min_freq = data['T_noise_min_freq']
T_noise_max_freq = data['T_noise_max_freq ']

galactic_noise_n_side = data['galactic_noise_n_side']
galactic_noise_interpolation_frequencies_start = data['galactic_noise_interpolation_frequencies_start']
galactic_noise_interpolation_frequencies_stop = data['galactic_noise_interpolation_frequencies_stop']
galactic_noise_interpolation_frequencies_step = data['galactic_noise_interpolation_frequencies_step']

passband_trigger = data['passband_trigger']
number_coincidences = data['number_coincidences']
coinc_window = data['coinc_window']
order_trigger = data['order_trigger']
check_trigger_thresholds = data['thresholds']
check_iterations = data['n_iterations']
trigger_efficiency = data['efficiency']
trigger_rate = data['trigger_rate']

hardware_response = data['hardware_response']
n_random_phase = data['n_random_phase']
iterations = args.iterations / n_random_phase  # the factor of 10 is added with the phase of the galactic noise
iterations = int(iterations)

trigger_thresholds = (np.arange(check_trigger_thresholds[-1] + (threshold_steps),
                                check_trigger_thresholds[-1] + (20*threshold_steps),
                                threshold_steps))

logger.info("Processing trigger thresholds {}".format(trigger_thresholds))

det = GenericDetector(json_filename=detector_file, default_station=default_station)
station_ids = det.get_station_ids()
channel_ids = det.get_channel_ids(station_ids[0])

event, station, channel = hcr.create_empty_event(det, station_time, station_time_random, sampling_rate)

eventTypeIdentifier = NuRadioReco.modules.eventTypeIdentifier.eventTypeIdentifier()

channelGenericNoiseAdder = NuRadioReco.modules.channelGenericNoiseAdder.channelGenericNoiseAdder()
channelGenericNoiseAdder.begin()

channelGalacticNoiseAdder = NuRadioReco.modules.channelGalacticNoiseAdder.channelGalacticNoiseAdder()
channelGalacticNoiseAdder.begin(n_side=galactic_noise_n_side,
            interpolation_frequencies=np.arange(galactic_noise_interpolation_frequencies_start,
                                                galactic_noise_interpolation_frequencies_stop,
                                                galactic_noise_interpolation_frequencies_step))
hardwareResponseIncorporator = NuRadioReco.modules.RNO_G.hardwareResponseIncorporator.hardwareResponseIncorporator()

triggerSimulator = NuRadioReco.modules.trigger.envelopeTrigger.triggerSimulator()
triggerSimulator.begin()

t = time.time()  # absolute time of system
sampling_rate = station.get_channel(channel_ids[0]).get_sampling_rate()
dt = 1. / sampling_rate

time = channel.get_times()
channel_trace_start_time = time[0]
channel_trace_final_time = time[len(time)-1]
channel_trace_time_interval = channel_trace_final_time - channel_trace_start_time

trigger_status = []
trigger_rate = []
trigger_efficiency = []
for n_it in range(iterations):
    station = event.get_station(default_station)
    if station_time_random == True:
        station = hcr.set_random_station_time(station)

    eventTypeIdentifier.run(event, station, "forced", 'cosmic_ray')

    channel = hcr.create_empty_channel_trace(station, sampling_rate)

    channelGenericNoiseAdder.run(event, station, det, amplitude=Vrms_thermal_noise, min_freq=T_noise_min_freq,
                                 max_freq=T_noise_max_freq, type='rayleigh', bandwidth=None)

    channelGalacticNoiseAdder.run(event, station, det)

    if hardware_response == True:
        hardwareResponseIncorporator.run(event, station, det, sim_to_data=True)

    for i_phase in range(n_random_phase):
        channel = hcr.add_random_phase(station, sampling_rate)

        trigger_status_all_thresholds = []
        for threshold in trigger_thresholds:
            triggered_bins_channels = []
            channels_that_passed_trigger = []
            for channel in station.iter_channels():
                trace = channel.get_trace()
                frequencies = channel.get_frequencies()
                f = np.zeros_like(frequencies, dtype=complex)
                mask = frequencies > 0
                b, a = scipy.signal.butter(order_trigger, passband_trigger, 'bandpass', analog=True,
                                           output='ba')
                w, h = scipy.signal.freqs(b, a, frequencies[mask])
                f[mask] = h

                sampling_rate = channel.get_sampling_rate()
                freq_spectrum_fft_copy = np.array(channel.get_frequency_spectrum())
                freq_spectrum_fft_copy *= f
                trace_filtered = NuRadioReco.utilities.fft.freq2time(freq_spectrum_fft_copy, sampling_rate)

                # apply envelope trigger to each channel
                triggered_bins = np.abs(scipy.signal.hilbert(trace_filtered)) > threshold

                triggered_bins_channels.append(triggered_bins)

                if True in triggered_bins:
                    channels_that_passed_trigger.append(channel.get_id())

            # check for coincidences with get_majority_logic()
            has_triggered, triggered_bins, triggered_times = get_majority_logic(triggered_bins_channels,
                                                                                 number_coincidences, coinc_window, dt)

            trigger_status_all_thresholds.append(has_triggered)
        trigger_status.append(trigger_status_all_thresholds)

trigger_status = np.array(trigger_status)
triggered_trigger = np.sum(trigger_status, axis=0)
trigger_efficiency = triggered_trigger / len(trigger_status)
trigger_rate = (1 / channel_trace_time_interval) * trigger_efficiency

logger.info("Triggered true per trigger thresholds {}".format(triggered_trigger))

dic = {}
dic['detector_file'] = detector_file
dic['triggered_channels'] = triggered_channels
dic['default_station'] = default_station
dic['sampling_rate'] = sampling_rate
dic['T_noise'] = T_noise
dic['T_noise_min_freq'] = T_noise_min_freq
dic['T_noise_max_freq '] = T_noise_max_freq
dic['Vrms_thermal_noise'] = Vrms_thermal_noise
dic['galactic_noise_n_side'] = galactic_noise_n_side
dic['galactic_noise_interpolation_frequencies_start'] = galactic_noise_interpolation_frequencies_start
dic['galactic_noise_interpolation_frequencies_stop'] = galactic_noise_interpolation_frequencies_stop
dic['galactic_noise_interpolation_frequencies_step'] = galactic_noise_interpolation_frequencies_step
dic['station_time'] = station_time
dic['station_time_random'] = station_time_random
dic['passband_trigger'] = passband_trigger
dic['coinc_window'] = coinc_window
dic['order_trigger'] = order_trigger
dic['number_coincidences'] = number_coincidences
dic['iteration'] = iterations * n_random_phase
dic['threshold'] = trigger_thresholds
#dic['trigger_status'] = trigger_status # booleans of each trigger, needs a lot of storage
dic['triggered_true'] = triggered_trigger
dic['triggered_all'] = len(trigger_status)
dic['efficiency'] = trigger_efficiency
dic['trigger_rate'] = trigger_rate
dic['hardware_response'] = hardware_response
dic['n_random_phase'] = n_random_phase

if os.path.isdir(os.path.join(abs_output_path, 'output_threshold_final')) == False:
    os.mkdir(os.path.join(abs_output_path, 'output_threshold_final'))

output_file = 'output_threshold_final/final_threshold_envelope_fast_pb_{:.0f}_{:.0f}_i{}_{}.json'.format(
        passband_trigger[0] / units.MHz, passband_trigger[1] / units.MHz, len(trigger_status), number)

abs_path_output_file = os.path.normpath(os.path.join(abs_output_path, output_file))
with open(abs_path_output_file, 'w') as outfile:
    json.dump(dic, outfile, cls=hcr.NumpyEncoder, indent=4)
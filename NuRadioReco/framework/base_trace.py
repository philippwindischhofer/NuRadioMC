from __future__ import absolute_import, division, print_function
import numpy as np
import logging
import fractions
from NuRadioReco.utilities import fft, trace_utilities
import scipy.signal
import copy
try:
    import cPickle as pickle
except ImportError:
    import pickle
logger = logging.getLogger("BaseTrace")


class BaseTrace:

    def __init__(self):
        self._sampling_rate = None
        self._time_trace = None
        self._frequency_spectrum = None
        self.__time_domain_up_to_date = True
        self._trace_start_time = 0

    def get_trace(self):
        """
        returns the time trace. If the frequency spectrum was modified before,
        an ifft is performed automatically to have the time domain representation
        up to date.

        Returns: 1 or N dimensional np.array of floats
            the time trace
        """
        if(not self.__time_domain_up_to_date):
            self._time_trace = fft.freq2time(self._frequency_spectrum, self._sampling_rate)
            self.__time_domain_up_to_date = True
            self._frequency_spectrum = None
        return self._time_trace

    def get_frequency_spectrum(self):
        if(self.__time_domain_up_to_date):
            self._frequency_spectrum = fft.time2freq(self._time_trace, self._sampling_rate)
            self._time_trace = None
#             logger.debug("frequency spectrum has shape {}".format(self._frequency_spectrum.shape))
            self.__time_domain_up_to_date = False
        return self._frequency_spectrum

    def set_trace(self, trace, sampling_rate):
        """
        sets the time trace

        Parameters
        -----------
        trace: np.array of floats
            the time series
        sampling_rate: float
            the sampling rage of the trace, i.e., the inverse of the bin width
        """
        if trace is not None:
            if trace.shape[trace.ndim - 1] % 2 != 0:
                raise ValueError('Attempted to set trace with an uneven number ({}) of samples. Only traces with an even number of samples are allowed.'.format(trace.shape[trace.ndim - 1]))
        self.__time_domain_up_to_date = True
        self._time_trace = trace
        self._sampling_rate = sampling_rate
        self._frequency_spectrum = None

    def set_frequency_spectrum(self, frequency_spectrum, sampling_rate):
        self.__time_domain_up_to_date = False
        self._frequency_spectrum = frequency_spectrum
        self._sampling_rate = sampling_rate
        self._time_trace = None

    def get_sampling_rate(self):
        """
        returns the sampling rate of the trace

        Return: float
            sampling rate, i.e., the inverse of the bin width
        """
        return self._sampling_rate

    def get_times(self):
        try:
            length = self.get_number_of_samples()
            times = np.arange(0, length / self._sampling_rate - 0.1 / self._sampling_rate, 1. / self._sampling_rate) + self._trace_start_time
            if(len(times) != length):
                logger.error("time array does not have the same length as the trace. n_samples = {:d}, sampling rate = {:.5g}".format(length, self._sampling_rate))
                raise ValueError("time array does not have the same length as the trace")
        except:
            times = np.array([])
        return times

    def set_trace_start_time(self, start_time):
        self._trace_start_time = start_time

    def add_trace_start_time(self, start_time):
        self._trace_start_time += start_time

    def get_trace_start_time(self):
        return self._trace_start_time

    def get_frequencies(self):
        length = self.get_number_of_samples()
        return np.fft.rfftfreq(length, d=(1. / self._sampling_rate))

    def get_hilbert_envelope(self):
        from scipy import signal
        h = signal.hilbert(self.get_trace())
        return np.array([np.abs(h[0]), np.abs(h[1]), np.abs(h[2])])

    def get_hilbert_envelope_mag(self):
        return np.linalg.norm(self.get_hilbert_envelope(), axis=0)

    def get_number_of_samples(self):
        """
        returns the number of samples in the time domain

        Return: int
            number of samples in time domain
        """
        if(self.__time_domain_up_to_date):
            length = self._time_trace.shape[-1]  # returns the correct length independent of the dimension of the array (channels are 1dim, efields are 3dim)
        else:
            length = (self._frequency_spectrum.shape[-1] - 1) * 2
        return length

    def apply_time_shift(self, delta_t, silent=False):
        """
        Uses the fourier shift theorem to apply a time shift to the trace
        Note that this is a cyclic shift, which means the trace will wrap
        around, which might lead to problems, especially for large time shifts.

        Parameters:
        --------------------
        delta_t: float
            Time by which the trace should be shifted
        silent: boolean (default:False)
            Turn off warnings if time shift is larger than 10% of trace length
            Only use this option if you are sure that your trace is long enough
            to acommodate the time shift
        """
        if delta_t > .1 * self.get_number_of_samples() / self.get_sampling_rate() and not silent:
            logger.warning('Trace is shifted by more than 10% of its length')
        spec = self.get_frequency_spectrum()
        spec *= np.exp(-2.j * np.pi * delta_t * self.get_frequencies())
        self.set_frequency_spectrum(spec, self._sampling_rate)

    def serialize(self):
        data = {'sampling_rate': self.get_sampling_rate(),
                'time_trace': self.get_trace(),
                'trace_start_time': self.get_trace_start_time()}
        return pickle.dumps(data, protocol=4)

    def deserialize(self, data_pkl):
        data = pickle.loads(data_pkl)
        self.set_trace(data['time_trace'], data['sampling_rate'])
        if('trace_start_time' in data.keys()):
            self.set_trace_start_time(data['trace_start_time'])

    def __add__(self, x):
        if not isinstance(x, BaseTrace):
            raise TypeError('+ operator is only defined for 2 BaseTrace objects')
        if self.get_trace() is None or x.get_trace() is None:
            raise ValueError('One of the trace objects has no trace set')
        if self.get_trace().ndim != x.get_trace().ndim:
            raise ValueError('Traces have different dimensions')
        trace_1 = copy.copy(self.get_trace())
        trace_2 = copy.copy(x.get_trace())
        if self.get_sampling_rate() != x.get_sampling_rate():
            if self.get_sampling_rate() > x.get_sampling_rate():
                sampling_rate = self.get_sampling_rate()
                resampling_factor = fractions.Fraction(self.get_sampling_rate() / x.get_sampling_rate())
                if (resampling_factor.numerator != 1):
                    trace_2 = scipy.signal.resample(trace_2, resampling_factor.numerator * len(trace_2))
                if(resampling_factor.denominator != 1):
                    trace_2 = scipy.signal.resample(trace_2, len(trace_2) // resampling_factor.denominator)
            else:
                sampling_rate = x.get_sampling_rate()
                resampling_factor = fractions.Fraction(x.get_sampling_rate() / self.get_sampling_rate())
                if (resampling_factor.numerator != 1):
                    trace_1 = scipy.signal.resample(trace_1, resampling_factor.numerator * len(trace_1))
                if(resampling_factor.denominator != 1):
                    trace_1 = scipy.signal.resample(trace_1, len(trace_1) // resampling_factor.denominator)
        else:
            sampling_rate = self.get_sampling_rate()
        if self.get_trace_start_time() <= x.get_trace_start_time():
            trace_start = self.get_trace_start_time()
            time_offset = x.get_trace_start_time() - self.get_trace_start_time()
            i_start = int(round(time_offset * sampling_rate))
            if trace_1.ndim == 1:
                trace_length = max(trace_1.shape[0], i_start + trace_2.shape[0])
                trace_length += trace_length % 2
                early_trace = np.zeros(trace_length)
                early_trace[:trace_1.shape[0]] = trace_1
                late_trace = np.zeros(trace_length)
                late_trace[:trace_2.shape[0]] = trace_2
            else:
                trace_length = max(trace_1.shape[1], i_start + trace_2.shape[1])
                trace_length += trace_length % 2
                early_trace = np.zeros((trace_1.shape[0], trace_length))
                early_trace[:, :trace_1.shape[1]] = trace_1
                late_trace = np.zeros((trace_2.shape[0], trace_length))
                late_trace[:, :trace_2.shape[1]] = trace_2
        else:
            trace_start = x.get_trace_start_time()
            time_offset = self.get_trace_start_time() - x.get_trace_start_time()
            i_start = int(round(time_offset * sampling_rate))
            if trace_1.ndim == 1:
                trace_length = max(trace_2.shape[0], i_start + trace_1.shape[0])
                trace_length += trace_length % 2
                early_trace = np.zeros(trace_length)
                early_trace[:trace_2.shape[0]] = trace_2
                late_trace = np.zeros(trace_length)
                late_trace[:trace_1.shape[0]] = trace_1
            else:
                trace_length = max(trace_2.shape[1], i_start + trace_1.shape[1])
                trace_length += trace_length % 2
                early_trace = np.zeros((trace_2.shape[0], trace_length))
                early_trace[:, :trace_2.shape[1]] = trace_2
                late_trace = np.zeros((trace_1.shape[0], trace_length))
                late_trace[:, :trace_1.shape[1]] = trace_1
        late_trace_object = BaseTrace()
        late_trace_object.set_trace(late_trace, sampling_rate)
        late_trace_object.apply_time_shift(time_offset, True)
        new_trace = BaseTrace()
        new_trace.set_trace(early_trace + late_trace_object.get_trace(), sampling_rate)
        new_trace.set_trace_start_time(trace_start)
        return new_trace

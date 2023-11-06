import logging

import numpy as np

from NuRadioReco.modules.base import module
from NuRadioReco.modules.base.module import register_run
from NuRadioReco.utilities.signal_processing import half_hann_window, num_double_zeros

from kratos.data_io import lofar_io

logger = module.setup_logger(level=logging.WARNING)


def median_sorted_by_power(psort):
    """
    This function takes a list `psort`, which is assumed to be a sorted list (of indices). This function returns a list
    beginning with the median (i.e. the middle element) and subsequently the elements right and left of it, in
    increasing distance from the median.

    Parameters
    ----------
    psort: 1D array_like
        The list of elements to reoder.

    Examples
    --------
    >>> median_sorted_by_power([1,2,3,4,5])
    [3, 4, 2, 5, 1]

    In the example above, the middle element is 3. Therefore, the resulting array starts with 3. From there the
    algorithm takes the first element right (4) and left (2) of it. Then it takes the second element right (5) and
    left (1). This continues until all elements have been added to the output list.
    """
    lpsort = len(psort)
    if lpsort % 2 == 0:
        index = int(lpsort / 2) - 1
    else:
        index = int(lpsort / 2)

    modifier = 0
    out_psort = []
    start_index = index
    for i in range(0, lpsort):
        out_psort.append(psort[index])
        if modifier == 0:
            modifier = 1
        elif modifier > 0:
            modifier = -modifier
        elif modifier < 0:
            modifier = -(modifier - 1)
        index = start_index + modifier

    return out_psort


def FindRFI_LOFAR(
        tbb_filename,
        metadata_dir,
        target_trace_length=65536,
        rfi_cleaning_trace_length=8192,
):
    """
    A code that basically reads given LOFAR TBB H5 file and returns an array of dirty channels.
    Some values are hard coded based on LOFAR Experience.

    Parameters
    ----------
    tbb_filename : Path-like str
        The path to the TBB file to be analysed.
    metadata_dir : Path-like str
        The path to the directory containing the LOFAR metadata (required to open TBB file correctly).
    target_trace_length : int
        Size of total block of trace to be evaluated for finding dirty rfi channels.
    rfi_cleaning_trace_length: int
        Size of one chunk of trace to be evaluated at a time for calculating spectrum from.

    Raises
    ------
    ValueError
        If the `target_trace_length` is not a multiple of the `rfi_cleaning_trace_length`.
    """
    # Hardcoded values for LOFAR
    # TODO: fix units with utilities module
    lower_frequency_bound_Hz = 0.0
    upper_frequency_bound_Hz = 100e6
    initial_block = 0

    # Some checks to make sure variables are correctly matched with each other
    if target_trace_length % rfi_cleaning_trace_length != 0:
        logger.error(
            "The target total block size has to be multiple of single RFI block size."
        )
        raise ValueError

    if (rfi_cleaning_trace_length < 4096) or (rfi_cleaning_trace_length > 16384):
        logger.warning(
            "RFI cleaning may not work optimally at block sizes < 4096 or > 16384"
        )

    # Open the TBB file and pass it to FindRFI()
    tbb_file = lofar_io.open_TBB(tbb_filename, metadata_dir=metadata_dir)

    num_blocks = np.median(tbb_file.get_nominal_data_lengths() // rfi_cleaning_trace_length)  # should all be the same
    num_blocks -= initial_block  # initial block is hardcoded to 0?

    # TODO: what if one bad antenna in Station? Currently FindRFI crashes

    logger.info(f"Running find RFI with {num_blocks} blocks")
    output = FindRFI(tbb_file, rfi_cleaning_trace_length, initial_block, int(num_blocks),
                     lower_frequency=lower_frequency_bound_Hz, upper_frequency=upper_frequency_bound_Hz,
                     num_dbl_z=1000)

    tbb_file.close_file()

    # Calculate the required output variables
    avg_power_spectrum = np.sum(output["ave_spectrum_magnitude"], axis=0)
    avg_antenna_power = output["ave_spectrum_magnitude"]

    dirty_channels = output["dirty_channels"][0]
    multiplied_channels = []
    multiplied_blocks = target_trace_length // rfi_cleaning_trace_length
    for ch in dirty_channels:  # TODO: could be done more efficiently...?
        this_channel_list = np.arange(multiplied_blocks * ch, multiplied_blocks * ch + multiplied_blocks, 1)
        this_channel_list = list(this_channel_list)
        multiplied_channels.extend(this_channel_list)

    dirty_channels = np.sort(np.array(multiplied_channels))
    dirty_channels_block_size = target_trace_length

    return avg_power_spectrum, dirty_channels, dirty_channels_block_size, avg_antenna_power


# TODO: add description of algorithm to notes section
def FindRFI(
        tbb_file,
        block_size,
        initial_block,
        num_blocks,
        max_blocks=None,
        lower_frequency=10e6,
        upper_frequency=90e6,
        num_dbl_z=100,
):
    """
    A function to find RFI in data using phase-variance.

    Parameters
    ----------
    tbb_file : MultiFile_Dal1
        File pointer to TBB encompassing the data for one station.
    block_size : int
        The size of a single block of which to calculate the spectrum. Should be around 65536 (2^16).
    initial_block : int
        Initial block should be such that there is no lightning in the max_blocks number of blocks.
    num_blocks : int
        Number of blocks to use for phase-variance detection. Should be at least 20.
    max_blocks : int, default=None
        Sometimes a block needs to be skipped, so max_blocks shows the maximum number of blocks used
        (after initial block) used to find num_blocks number of good blocks.  If max_blocks is None (default),
        it is set to `num_blocks`.
    lower_frequency : float, default=10e6
        The lower end of the frequency band to consider.
    upper_frequency : float, default=90e6
        The higher end of the frequency band to consider.
    num_dbl_z : int, default=100
        The number of double zeros allowed in a block, if there are too many, then there could be data loss.

    Returns
    -------
    output_dict : dict
        A dictionary with the following key-value pairs:
        * "ave_spectrum_magnitude": array that contains the average of the magnitude of the frequency spectrum
        * "ave_spectrum_phase": array containing the average of the phase of the frequency spectrum
        * "phase_variance": array containing the phase variance of each frequency channel
        * "dirty_channels": array of indices indicating the channels that are contaminated with RFI

    Notes
    -----
    The algorithm compares the phase stability of each frequency channel between a reference antenna and every
    other antenna in the station. If the phase is stable, this indicates a constant source contaminating the data.
    More information can be found in Section 3.2.2 of `this paper <https://arxiv.org/pdf/1311.1399.pdf>`_ .
    """
    num_blocks = int(num_blocks)  # make sure the number of blocks in an integer (as its used as a shape parameter)

    if max_blocks is None:
        max_blocks = num_blocks

    # TODO: can this replaced by "standard" NuRadioReco implementations?
    window_function = half_hann_window(block_size, 0.1)
    num_antennas = len(tbb_file.get_antenna_names())

    # step one: find which blocks are good, and find average power
    oneAnt_data = np.empty(block_size, dtype=np.double)

    logger.info("finding good blocks")
    blocks_good = np.zeros((num_antennas, max_blocks), dtype=bool)
    num_good_blocks = np.zeros(num_antennas, dtype=int)
    average_power = np.zeros(num_antennas, dtype=np.double)
    for block_i in range(max_blocks):
        block = block_i + initial_block

        for ant_i in range(num_antennas):
            oneAnt_data[:] = tbb_file.get_data(
                block_size * block, block_size, antenna_index=ant_i
            )
            if (
                    num_double_zeros(oneAnt_data) < num_dbl_z
            ):  # this antenna on this block is good
                blocks_good[ant_i, block_i] = True
                num_good_blocks[ant_i] += 1

                oneAnt_data *= window_function

                FFT_data = np.fft.fft(oneAnt_data)
                np.abs(FFT_data, out=FFT_data)
                magnitude = FFT_data
                magnitude *= magnitude
                average_power[ant_i] += np.real(np.sum(magnitude))

    average_power[num_good_blocks != 0] /= num_good_blocks[num_good_blocks != 0]

    # Now we try to find the best reference antenna, require that antenna allows for maximum number of good antennas,
    # and has **best** average received power
    allowed_num_antennas = np.empty(
        num_antennas, dtype=int
    )
    # If ant_i is chosen to be your reference antenna, then allowed_num_antennas[ ant_i ] is the number of
    # antennas with num_blocks good blocks
    for ant_i in range(num_antennas):  # fill allowed_num_antennas
        blocks_can_use = np.where(blocks_good[ant_i])[0]
        num_good_blocks_per_antenna = np.sum(blocks_good[:, blocks_can_use], axis=1)
        allowed_num_antennas[ant_i] = np.sum(num_good_blocks_per_antenna >= num_blocks)

    max_allowed_antennas = np.max(allowed_num_antennas)

    if max_allowed_antennas < 2:
        logger.error("ERROR: station", tbb_file.get_station_name(), "cannot find RFI")
        return

    # Pick a reference antenna that allows max number of antennas, and has most median amount of power
    can_be_ref_antenna = allowed_num_antennas == max_allowed_antennas

    sorted_by_power = np.argsort(average_power)
    mps = median_sorted_by_power(sorted_by_power)

    for ant_i in mps:
        if can_be_ref_antenna[ant_i]:
            ref_antenna = ant_i
            break

    logger.info("Taking channel %d as reference antenna" % ref_antenna)  # this will fail if ref_antenna not found

    # Define some helping variables
    good_blocks = np.where(blocks_good[ref_antenna])[0]

    num_good_blocks = np.sum(blocks_good[:, good_blocks], axis=1)
    antenna_is_good = num_good_blocks >= (num_blocks - 1)

    blocks_good[np.logical_not(antenna_is_good), :] = False

    # Process data
    num_processed_blocks = np.zeros(num_antennas, dtype=int)
    frequencies = np.fft.fftfreq(block_size, 1.0 / tbb_file.get_sample_frequency())
    lower_frequency_index = np.searchsorted(
        frequencies[: int(len(frequencies) / 2)], lower_frequency
    )
    upper_frequency_index = np.searchsorted(
        frequencies[: int(len(frequencies) / 2)], upper_frequency
    )

    phase_mean = np.zeros(
        (num_antennas, upper_frequency_index - lower_frequency_index), dtype=complex
    )
    spectrum_mean = np.zeros(
        (num_antennas, upper_frequency_index - lower_frequency_index), dtype=np.double
    )

    data = np.empty((num_antennas, len(frequencies)), dtype=complex)
    temp_mag_spectrum = np.empty((num_antennas, len(frequencies)), dtype=np.double)
    temp_phase_spectrum = np.empty((num_antennas, len(frequencies)), dtype=complex)
    for block_i in good_blocks:
        logger.info("Doing block %d" % block_i)
        block = block_i + initial_block

        for ant_i in range(num_antennas):
            if (
                    num_processed_blocks[ant_i] == num_blocks
                    or not blocks_good[ant_i, block_i]
            ):
                continue
            oneAnt_data[:] = tbb_file.get_data(
                block_size * block, block_size, antenna_index=ant_i
            )

            # Window the data
            # Note: No hanning window if we want to measure power accurately from spectrum in the same units
            # as power from timeseries. Applying a window gives (at least) a scale factor difference!
            # But no window makes the cleaning less effective... :(
            oneAnt_data *= window_function
            data[ant_i] = np.fft.fft(oneAnt_data)

        np.abs(data, out=temp_mag_spectrum)
        temp_phase_spectrum[:] = data
        temp_phase_spectrum /= temp_mag_spectrum + 1.0e-15
        temp_phase_spectrum[:, :] /= temp_phase_spectrum[ref_antenna, :]

        temp_mag_spectrum *= temp_mag_spectrum

        for ant_i in range(num_antennas):
            if (
                    num_processed_blocks[ant_i] == num_blocks
                    or not blocks_good[ant_i, block_i]
            ):
                continue

            phase_mean[ant_i, :] += temp_phase_spectrum[ant_i][
                                    lower_frequency_index:upper_frequency_index
                                    ]
            spectrum_mean[ant_i, :] += temp_mag_spectrum[ant_i][
                                       lower_frequency_index:upper_frequency_index
                                       ]

            num_processed_blocks[ant_i] += 1

        if np.min(num_processed_blocks[antenna_is_good]) == num_blocks:
            break

    logger.info(
        num_blocks,
        "analyzed blocks",
        np.sum(antenna_is_good),
        "analyzed antennas out of",
        len(antenna_is_good),
    )

    # Get only good antennas
    antenna_is_good[
        ref_antenna
    ] = False  # we don't want to analyze the phase stability of the reference antenna

    # Get mean and phase stability
    spectrum_mean /= num_blocks

    phase_stability = np.abs(phase_mean)
    phase_stability *= -1.0 / num_blocks
    phase_stability += 1.0

    # Get median of stability by channel, across each antenna
    median_phase_spread_byChannel = np.median(phase_stability[antenna_is_good], axis=0)

    # Get median across all channels
    median_spread = np.median(median_phase_spread_byChannel)
    # Create a noise cutoff
    sorted_phase_spreads = np.sort(median_phase_spread_byChannel)
    N = len(median_phase_spread_byChannel)
    noise = sorted_phase_spreads[int(N * 0.95)] - sorted_phase_spreads[int(N / 2)]

    # Get channels contaminated by RFI, where phase stability is smaller than noise
    dirty_channels = np.where(
        median_phase_spread_byChannel < (median_spread - 3 * noise)
    )[0]

    # Extend dirty channels by some size, in order to account for shoulders
    extend_dirty_channels = np.zeros(N, dtype=bool)
    half_flagwidth = int(block_size / 8192)
    for i in dirty_channels:
        flag_min = i - half_flagwidth
        flag_max = i + half_flagwidth
        if flag_min < 0:
            flag_min = 0
        if flag_max >= N:
            flag_max = N - 1
        extend_dirty_channels[flag_min:flag_max] = True

    dirty_channels = np.where(extend_dirty_channels)

    antenna_is_good[ref_antenna] = True  # cause'.... ya know.... it is
    # plot and return data
    frequencies = frequencies[lower_frequency_index:upper_frequency_index]

    output_dict = {
        "ave_spectrum_magnitude": spectrum_mean,
        "ave_spectrum_phase": np.angle(phase_mean, deg=False),
        "phase_variance": phase_stability,
        "dirty_channels": dirty_channels + lower_frequency_index,
        "blocksize": block_size,
    }

    cleaned_spectrum = np.array(spectrum_mean)
    cleaned_spectrum[:, dirty_channels] = 0.0
    output_dict["cleaned_spectrum_magnitude"] = cleaned_spectrum
    output_dict["cleaned_power"] = 2 * np.sum(cleaned_spectrum, axis=1)

    output_dict["antenna_names"] = tbb_file.get_antenna_names()
    output_dict["timestamp"] = tbb_file.get_timestamp()
    output_dict["antennas_good"] = antenna_is_good
    output_dict["frequency"] = frequencies

    return output_dict


# TODO: make stationRFIFilter take keyword to only process certain station
class stationRFIFilter:
    """
    Remove the RFI from all stations in an Event, by using the phase-variance method described in
    :py:func:`.FindRFI`. This function returns the frequency channels which are contaminated, which are
    subsequently put to zero in the traces.

    **Note**: currently the class uses hardcoded values for LOFAR, this needs to be improved later.
    """
    def __init__(self):
        self.logger = logging.getLogger('NuRadioReco.channelRFIFilter')

        self.__rfi_trace_length = None

    def begin(self, rfi_cleaning_trace_length=65536):
        """
        Set the variables used for RFI detection.

        Parameters
        ----------
        rfi_cleaning_trace_length : int
            The number of samples to use per block to construct the frequency spectrum.
        """
        self.__rfi_trace_length = rfi_cleaning_trace_length

    @register_run()
    def run(self, event, reader):
        """
        Run the filter on the `event`. The `reader` object is required to retrieve the filenames associated with
        the loaded stations. The method currently uses :py:func:`.FindRFI_LOFAR` to find the contaminated channels
        and then puts the corresponding frequency bands to zero in every channel (in place).

        Parameters
        ----------
        event : Event object
            The event on which to run the filter.
        reader : readLOFARData object
            The reader used to read in the data of the event.
        """
        stations_dict = reader.get_stations()

        for station in event.get_stations():
            station_name = f'CS{station.get_id():03}'
            station_files = stations_dict[station_name]['files']

            # Find the length of a trace in the station (assume all channels have been loaded with same length)
            station_trace_length = len(station.get_channel(station.get_channel_ids()[0]).get_trace())
            # TODO: when time_trace is set, can replace this with channel.get_number_of_samples()

            # Do some checks
            if len(station_files) < 1:
                self.logger.warning(f'No files in reader dict for station {station_name}, skipping...')
                continue
            if (station_trace_length < self.__rfi_trace_length) or \
                    (station_trace_length % self.__rfi_trace_length != 0):
                self.logger.error(f'Station trace length ({station_trace_length}) has to be greater than RFI trace '
                                  f'length ({self.__rfi_trace_length}) as well as a multiple of it.')
                raise ValueError

            # TODO: replace this with FindRFI() as to allow other experiments to use the same code
            packet = FindRFI_LOFAR(station_files,
                                   reader.meta_dir,
                                   station_trace_length,
                                   self.__rfi_trace_length)

            # Extract the necessary information from FindRFI
            avg_power_spectrum = packet[0]
            dirty_channels = packet[1]
            dirty_channels_block_size = packet[2]

            # TODO: implement outlier detection in cleaned power

            # Remove flagged channels from traces
            for channel in station.iter_channels():
                trace_fft = channel.get_frequency_spectrum()
                sample_rate = channel.get_sampling_rate()

                trace_fft[dirty_channels] *= 0.0

                channel.set_frequency_spectrum(trace_fft, sample_rate)

    def end(self):
        pass

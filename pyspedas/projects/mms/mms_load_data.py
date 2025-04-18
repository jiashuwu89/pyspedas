import os
import requests
import logging
import warnings
from importlib.metadata import version, PackageNotFoundError
import numpy as np
from pytplot import cdf_to_tplot
from pytplot import time_clip as tclip
from pytplot import time_double, time_string
from dateutil.parser import parse
from datetime import timedelta, datetime
from shutil import copyfileobj, copy
from tempfile import NamedTemporaryFile
from .mms_config import CONFIG
from .mms_get_local_files import mms_get_local_files
from .mms_files_in_interval import mms_files_in_interval
from .mms_login_lasp import mms_login_lasp
from .mms_file_filter import mms_file_filter
from .mms_load_data_spdf import mms_load_data_spdf

from pyspedas.utilities.download import is_fsspec_uri
import fsspec

def mms_load_data(trange=['2015-10-16', '2015-10-17'], probe='1', data_rate='srvy', level='l2', 
    instrument='fgm', datatype='', varformat=None, exclude_format=None, prefix='', suffix='', get_support_data=False, time_clip=False,
    no_update=False, center_measurement=False, available=False, notplot=False, latest_version=False, 
    major_version=False, min_version=None, cdf_version=None, spdf=False, always_prompt=False, varnames=[]):
    """
    This function loads MMS data into tplot variables

    This function is not meant to be called directly. Please see the individual load routines for documentation and use.
    """
    if not isinstance(probe, list): probe = [probe]
    if not isinstance(data_rate, list): data_rate = [data_rate]
    if not isinstance(level, list): level = [level]
    if not isinstance(datatype, list): datatype = [datatype]
    
    probe = [str(p) for p in probe]

    # allows the user to pass in trange as list of datetime objects
    if type(trange[0]) == datetime and type(trange[1]) == datetime:
        trange = [time_string(trange[0].timestamp()), time_string(trange[1].timestamp())]

    # allows the user to pass in trange as a list of floats (unix times)
    if isinstance(trange[0], float):
        trange[0] = time_string(trange[0])
    if isinstance(trange[1], float):
        trange[1] = time_string(trange[1])

    download_only = CONFIG['download_only']

    no_download = False
    if no_update or CONFIG['no_download']: no_download = True

    if spdf:
        return mms_load_data_spdf(trange=trange, probe=probe, data_rate=data_rate, level=level, 
                                  instrument=instrument, datatype=datatype, varformat=varformat, exclude_format=exclude_format,
                                  suffix=suffix, get_support_data=get_support_data, time_clip=time_clip, 
                                  no_update=no_update, center_measurement=center_measurement, notplot=notplot, 
                                  latest_version=latest_version, major_version=major_version, 
                                  min_version=min_version, cdf_version=cdf_version, varnames=varnames)

    headers = {}
    try:
        release_version = version("pyspedas")
    except PackageNotFoundError:
        release_version = "bleeding edge"
    headers['User-Agent'] = 'pySPEDAS ' + release_version

    user = None
    if not no_download:
        sdc_session, user = mms_login_lasp(always_prompt=always_prompt, headers=headers)

    out_files = []
    available_files = []

    # We want to load CDFs by groups (probe, level, datatype, data rate) rather than
    # all together in one giant call to cdf_to_tplot.  We'll use a dictionary, with keys
    # derived from each combination of attributes, and maintain separate lists of files to
    # load together for each key.

    out_file_groupings = {}

    for prb in probe:
        for drate in data_rate:
            start_date = parse(trange[0]).strftime('%Y-%m-%d') # need to request full day, then parse out later
            end_date = parse(time_string(time_double(trange[1])-0.1)).strftime('%Y-%m-%d-%H-%M-%S') # -1 second to avoid getting data for the next day
            # kludge to fix issue for burst mode data in files from the previous day
            if drate == 'brst':
                sec_from_start_of_day = time_double(trange[0])-time_double(start_date)

                # check if we're within 10 minutes of the start of the day
                # and if so, grab 10 minutes of data from the end of the
                # previous day
                if sec_from_start_of_day <= 600.0:
                    start_date = time_string(time_double(start_date)-600.0, fmt='%Y-%m-%d-%H-%M-%S')

            for lvl in level:
                for dtype in datatype:

                    grouping_key = f"probe: {prb}, drate: {drate}, level: {lvl}, datatype: {dtype}"
                    out_file_groupings[grouping_key] = []

                    file_found = False

                    if user is None:
                        url = 'https://lasp.colorado.edu/mms/sdc/public/files/api/v1/file_info/science?start_date=' + start_date + '&end_date=' + end_date + '&sc_id=mms' + prb + '&instrument_id=' + instrument + '&data_rate_mode=' + drate + '&data_level=' + lvl
                    else:
                        url = 'https://lasp.colorado.edu/mms/sdc/sitl/files/api/v1/file_info/science?start_date=' + start_date + '&end_date=' + end_date + '&sc_id=mms' + prb + '&instrument_id=' + instrument + '&data_rate_mode=' + drate + '&data_level=' + lvl
                    
                    if dtype != '':
                        url = url + '&descriptor=' + dtype

                    if CONFIG['debug_mode']: logging.info('Fetching: ' + url)

                    if not no_download:
                        # query list of available files
                        try:
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore", category=ResourceWarning)
                                http_request = sdc_session.get(url, verify=True, headers=headers)
                                if http_request.status_code != 200:
                                    logging.warning("Request to MMS SDC returned HTTP status code %d", http_request.status_code)
                                    logging.warning("Text: %s", http_request.text)
                                    logging.warning("URL: %s", url)
                                    continue
                                else:
                                    http_json = http_request.json()

                            if CONFIG['debug_mode']: logging.info('Filtering the results down to your trange')

                            files_in_interval = mms_files_in_interval(http_json['files'], trange)

                            if available:
                                for file in files_in_interval:
                                    logging.info(file['file_name'] + ' (' + str(np.round(file['file_size']/(1024.*1024), decimals=1)) + ' MB)')
                                    available_files.append(file['file_name'])
                                continue

                            for file in files_in_interval:
                                file_date = parse(file['timetag'])
                                sep = "/" if is_fsspec_uri(CONFIG["local_data_dir"]) else os.path.sep
                                if dtype == '':
                                    out_dir = sep.join([CONFIG['local_data_dir'], 'mms'+prb, instrument, drate, lvl, file_date.strftime('%Y'), file_date.strftime('%m')])
                                else:
                                    out_dir = sep.join([CONFIG['local_data_dir'], 'mms'+prb, instrument, drate, lvl, dtype, file_date.strftime('%Y'), file_date.strftime('%m')])

                                if drate.lower() == 'brst':
                                    out_dir = sep.join([out_dir, file_date.strftime('%d')])

                                out_file = sep.join([out_dir, file['file_name']])

                                if CONFIG['debug_mode']: logging.info('File: ' + file['file_name'] + ' / ' + file['timetag'])

                                if is_fsspec_uri(CONFIG["local_data_dir"]):
                                    protocol, path = out_file.split("://")
                                    fs = fsspec.filesystem(protocol)

                                    if fs.exists(out_file) and str(fs.size(out_file)) == str(file["file_size"]):
                                        if not download_only: logging.info('Streaming ' + out_file)
                                        out_files.append(out_file)
                                        out_file_groupings[grouping_key].append(out_file)
                                        file_found = True
                                        continue
                                else:
                                    if os.path.exists(out_file) and str(os.stat(out_file).st_size) == str(file['file_size']):
                                        if not download_only: logging.debug('Loading ' + out_file)
                                        out_files.append(out_file)
                                        out_file_groupings[grouping_key].append(out_file)
                                        file_found = True
                                        continue

                                if user is None:
                                    download_url = 'https://lasp.colorado.edu/mms/sdc/public/files/api/v1/download/science?file=' + file['file_name']
                                else:
                                    download_url = 'https://lasp.colorado.edu/mms/sdc/sitl/files/api/v1/download/science?file=' + file['file_name']

                                logging.info('Downloading ' + file['file_name'] + ' to ' + out_dir)

                                with warnings.catch_warnings():
                                    warnings.simplefilter("ignore", category=ResourceWarning)
                                    fsrc = sdc_session.get(download_url, stream=True, verify=True, headers=headers)
                                ftmp = NamedTemporaryFile(delete=False)

                                with open(ftmp.name, 'wb') as f:
                                    copyfileobj(fsrc.raw, f)

                                if is_fsspec_uri(CONFIG["local_data_dir"]):
                                    protocol, path = out_dir.split("://")
                                    fs = fsspec.filesystem(protocol)

                                    fs.makedirs(out_dir, exist_ok=True)

                                    # if the download was successful, put at URI specified
                                    fs.put(ftmp.name, out_file)
                                else:
                                    if not os.path.exists(out_dir):
                                        os.makedirs(out_dir)

                                    # if the download was successful, copy to data directory
                                    copy(ftmp.name, out_file)

                                out_files.append(out_file)
                                out_file_groupings[grouping_key].extend([out_file])
                                file_found = True
                                fsrc.close()
                                ftmp.close()
                                os.unlink(ftmp.name)  # delete the temporary file
                        except requests.exceptions.ConnectionError as e:
                            # No/bad internet connection; try loading the files locally
                            print(e)
                            logging.error('No internet connection!')

                    if not file_found:
                        added_local_files = False
                        if not download_only:
                            logging.info('Searching for local files...')
                            local_files = mms_get_local_files(prb, instrument, drate, lvl, dtype, trange)
                            out_files.extend(local_files)
                            out_file_groupings[grouping_key].extend(local_files)
                            added_local_files = True

                        if added_local_files and CONFIG['mirror_data_dir'] is not None:
                            # check for network mirror; note: network mirrors are assumed to be read-only
                            # and we always copy the files from the mirror to the local data directory
                            # before trying to load into tplot variables 
                            logging.info('No local files found; checking network mirror...')
                            local_files = mms_get_local_files(prb, instrument, drate, lvl, dtype, trange, mirror=True)
                            out_files.extend(local_files)
                            out_file_groupings[grouping_key].extend(local_files)

    if not no_download:
        sdc_session.close()

    if available:
        return available_files

    if not download_only:
        out_files = sorted(out_files)

        # We could be returning a dict or a list, depending on whether notplot is set.
        # In either case, we probably want to eliminate duplicates.  So depending on
        # notplot, we create an empty dict or set, update() it with each returned dictionary (notplot)
        # or list (default), then if we're doing tplot variables, convert it back to a list
        # after processing all the groups.

        if notplot:
            return_value = {}
        else:
            return_value = set()

        for key in out_file_groupings.keys():
            group_list = out_file_groupings[key]
            if len(group_list) > 0:
                sorted_group_list = sorted(group_list)
                filtered_group_list = mms_file_filter(sorted_group_list, latest_version=latest_version, major_version=major_version, min_version=min_version, version=cdf_version)
                if not filtered_group_list:
                    logging.info(f"No matching CDF versions found for group: {key}, after sorting and filtering.")
                else:
                    logging.info(f"Loading files for group: {key}, after sorting and filtering:")
                    for f in filtered_group_list:
                        logging.info(f)
                    these_variables = cdf_to_tplot(filtered_group_list, varformat=varformat,exclude_format=exclude_format, varnames=varnames, get_support_data=get_support_data, prefix=prefix, suffix=suffix, center_measurement=center_measurement, notplot=notplot)
                    return_value.update(these_variables)

        filtered_out_files = mms_file_filter(out_files, latest_version=latest_version, major_version=major_version, min_version=min_version, version=cdf_version)

        if not filtered_out_files:
            logging.info('No matching CDF versions found.')
            return

        # new_variables = cdf_to_tplot(filtered_out_files, varformat=varformat,exclude_format=exclude_format, varnames=varnames, get_support_data=get_support_data, prefix=prefix, suffix=suffix, center_measurement=center_measurement, notplot=notplot)

        if notplot:
            return return_value

        new_variables = list(return_value)
        if not new_variables:
            logging.warning('No data loaded.')
            return

        if time_clip:
            for new_var in new_variables:
                tclip(new_var, trange[0], trange[1], suffix='')

        return new_variables
    else:
        return out_files

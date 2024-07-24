from .load import load
import numpy as np
import pandas as pd
from pytplot import store_data, options
from pytplot import time_double
from pyspedas.cotrans.xyz_to_polar import xyz_to_polar


def rdm(trange=['2012-10-01', '2012-10-02'],
        suffix='',  
        get_support_data=False, 
        varformat=None,
        varnames=[],
        downloadonly=False,
        notplot=False,
        no_update=False,
        time_clip=False,
        force_download=False):
    """
    This function loads data from the ACE Radiation Moniter (RDM)
    
    Parameters
    ----------
        trange : list of str
            time range of interest [starttime, endtime] with the format 
            'YYYY-MM-DD','YYYY-MM-DD'] or to specify more or less than a day 
            ['YYYY-MM-DD/hh:mm:ss','YYYY-MM-DD/hh:mm:ss']
            Default: ['2012-10-01', '2012-10-02']

        suffix: str
            The tplot variable names will be given this suffix.  By default, 
            no suffix is added.
            Default: ''

        get_support_data: bool
            Data with an attribute "VAR_TYPE" with a value of "support_data"
            will be loaded into tplot.  By default, only loads in data with a 
            "VAR_TYPE" attribute of "data".
            Default: False

        varformat: str
            The file variable formats to load into tplot.  Wildcard character
            "*" is accepted.  By default, all variables are loaded in.
            Default: None

        varnames: list of str
            List of variable names to load (if not specified,
            all data variables are loaded)
            Default: []

        downloadonly: bool
            Set this flag to download the CDF files, but not load them into 
            tplot variables
            Default: False

        notplot: bool
            Return the data in hash tables instead of creating tplot variables
            Default: False

        no_update: bool
            If set, only load data from your local cache
            Default: False

        time_clip: bool
            Time clip the variables to exactly the range specified in the trange keyword
            Default: False

        force_download: bool
            Download file even if local version is more recent than server version
            Default: False


    Returns
    ----------
        List of tplot variables created.

    Example:
    ---------- 
        >>> import pyspedas
        >>> from pytplot import tplot  
        >>> rdm_vars = pyspedas.akebono.rdm(trange=['2012-10-01', '2012-10-02'])
        >>> tplot('akb_rdm_FEIO')

    """
    files = load(instrument='rdm', trange=trange, suffix=suffix, get_support_data=get_support_data, varformat=varformat, varnames=varnames, downloadonly=downloadonly, notplot=notplot, time_clip=time_clip, no_update=no_update, force_download=force_download)

    if files is None or notplot or downloadonly:
        return files

    return rdm_postprocessing(files)



"""
created matt_dumont 
on: 14/09/23
"""
import itertools
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm, mstats
from copy import deepcopy
import warnings
import matplotlib.pyplot as plt
from matplotlib.cm import get_cmap
from matplotlib.transforms import blended_transform_factory
from matplotlib.lines import Line2D
from pyhomogeneity import pettitt_test


# todo add this to ksl tools or own repo for easy internal use

def _make_s_array(x):
    """
    make the s array for the mann kendall test
    :param x:
    :return:
    """
    n = len(x)
    k_array = np.repeat(x[:, np.newaxis], n, axis=1)
    j_array = k_array.transpose()

    s_stat_array = np.sign(k_array - j_array)
    s_stat_array = np.tril(s_stat_array, -1)  # remove the diagonal and upper triangle
    return s_stat_array


def _seasonal_mann_kendall_from_sarray(x, season_data, alpha=0.05, sarray=None,
                                       freq_limit=0.05):
    """
    calculate the seasonal mann kendall test for a time series
    after: https://doi.org/10.1029/WR020i006p00727
    :param x: the data
    :param season_data: the season data, will be converted to integers
    :param alpha: significance level
    :param sarray: the s array, if None will be calculated from _make_s_array
    :param freq_limit: the maximum difference in frequency between seasons (as a fraction),
                       if greater than this will raise a warning
    :return:
    """
    # calculate the unique data
    x = np.atleast_1d(x)
    season_data = np.atleast_1d(season_data)
    assert np.issubdtype(season_data.dtype, int) or np.issubdtype(season_data.dtype, np.string_), (
        'season data must be a string, or integer to avoid errors associated with float precision'
    )
    # get unique values convert to integers
    unique_seasons, season_data = np.unique(season_data, return_inverse=True)

    # get unique integer values
    unique_season_ints, counts = np.unique(season_data, return_counts=True)

    relaive_freq = np.abs(counts - counts.mean()) / counts.mean()
    if (relaive_freq > freq_limit).any():
        warnings.warn(f'the discrepancy of frequency of seasons is greater than the limit({freq_limit})'
                      f' this may affect the test'
                      f' the frequency of seasons are {counts}')
    assert season_data.shape == x.shape, 'season data and x must be the same shape'
    assert x.ndim == 1
    n = len(x)
    assert n >= 3, 'need at least 3 data points'

    # calculate s
    if sarray is None:
        sarray = _make_s_array(x)
    assert sarray.shape == (n, n)

    # make the season array
    season_k_array = np.repeat(season_data[:, np.newaxis], n, axis=1)
    season_j_array = season_k_array.transpose()

    s = 0
    var_s = 0
    # run the mann kendall for each season
    for season in unique_season_ints:
        season_idx = (season_k_array == season) & (season_j_array == season)
        temp_s = sarray[season_idx].sum()
        temp_x = x[season_data == season]
        n0 = len(temp_x)

        # calculate the var(s)
        unique_x, unique_counts = np.unique(temp_x, return_counts=True)
        unique_mod = (unique_counts * (unique_counts - 1) * (2 * unique_counts + 5)).sum() * (unique_counts > 1).sum()
        temp_var_s = (n0 * (n0 - 1) * (2 * n0 + 5) + unique_mod) / 18

        s += temp_s
        var_s += temp_var_s

    # calculate the z value
    z = np.abs(np.sign(s)) * (s - np.sign(s)) / np.sqrt(var_s)
    p = 2 * (1 - norm.cdf(abs(z)))  # two tail test
    h = abs(z) > norm.ppf(1 - alpha / 2)

    trend = np.sign(z) * h
    # -1 decreasing, 0 no trend, 1 increasing
    return trend, h, p, z, s, var_s


def _mann_kendall_from_sarray(x, alpha=0.05, sarray=None):
    """
    code optimised mann kendall
    :param x:
    :param alpha:
    :param sarray:
    :return:
    """

    # calculate the unique data
    x = np.atleast_1d(x)
    assert x.ndim == 1
    n = len(x)
    assert n >= 3, 'need at least 3 data points'

    # calculate s
    if sarray is None:
        sarray = _make_s_array(x)
    assert sarray.shape == (n, n)
    s = sarray.sum()

    # calculate the var(s)
    unique_x, unique_counts = np.unique(x, return_counts=True)
    unique_mod = (unique_counts * (unique_counts - 1) * (2 * unique_counts + 5)).sum() * (unique_counts > 1).sum()
    var_s = (n * (n - 1) * (2 * n + 5) + unique_mod) / 18

    z = np.abs(np.sign(s)) * (s - np.sign(s)) / np.sqrt(var_s)

    # calculate the p_value
    p = 2 * (1 - norm.cdf(abs(z)))  # two tail test
    h = abs(z) > norm.ppf(1 - alpha / 2)

    trend = np.sign(z) * h
    # -1 decreasing, 0 no trend, 1 increasing

    return trend, h, p, z, s, var_s


def _mann_kendall_old(x, alpha=0.05):
    """
    the duplicate from above is to return more parameters and put into the mann kendall class
    retrieved from https://mail.scipy.org/pipermail/scipy-dev/2016-July/021413.html
    this was depreciated as _mann_kendall_from_sarray is MUCH faster
    Input:
        x:   a vector of data
        alpha: significance level (0.05 default)
    Output:
        trend: tells the trend (increasing, decreasing or no trend)
        h: True (if trend is present) or False (if trend is absence)
        p: p value of the significance test
        z: normalized test statistics
    """
    warnings.warn('this function is depreciated, use _mann_kendall_from_sarray', DeprecationWarning)
    x = np.array(x)
    n = len(x)

    # calculate S
    s = 0
    for k in range(n - 1):
        for j in range(k + 1, n):
            s += np.sign(x[j] - x[k])

    # calculate the unique data
    unique_x = np.unique(x)
    g = len(unique_x)

    # calculate the var(s)
    if n == g:  # there is no tie
        var_s = (n * (n - 1) * (2 * n + 5)) / 18
    else:  # there are some ties in data
        tp = np.zeros(unique_x.shape)
        for i in range(len(unique_x)):
            tp[i] = sum(unique_x[i] == x)
        var_s = (n * (n - 1) * (2 * n + 5) + np.sum(tp * (tp - 1) * (2 * tp + 5))) / 18

    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s == 0:
        z = 0
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        raise ValueError('shouldnt get here')

    # calculate the p_value
    p = 2 * (1 - norm.cdf(abs(z)))  # two tail test
    h = abs(z) > norm.ppf(1 - alpha / 2)

    if (z < 0) and h:
        trend = -1
    elif (z > 0) and h:
        trend = 1
    else:
        trend = 0

    return trend, h, p, z, s, var_s


def _generate_startpoints(n, min_size, nparts, test=False):
    all_start_points = []
    for part in range(nparts - 1):
        start_points = np.arange(min_size + min_size * part, n - (min_size + min_size * part))
        all_start_points.append(start_points)

    all_start_points_out = np.array(list(itertools.product(*all_start_points)))
    all_start_points_out = all_start_points_out[np.all(
        [all_start_points_out[:, i] < all_start_points_out[:, i + 1] for i in range(nparts - 2)],
        axis=0)]
    temp = np.concatenate((
        np.array(all_start_points_out),
        np.full((len(all_start_points_out), 1), n)

    ), axis=1)
    sizes = np.diff(temp, axis=1)
    all_start_points_out = all_start_points_out[np.all(sizes >= min_size, axis=1)]
    if test:
        temp = np.concatenate((
            np.array(all_start_points_out),
            np.full((len(all_start_points_out), 1), n)

        ), axis=1)
        sizes = np.diff(temp, axis=1)
        assert np.all(sizes >= min_size)

    return all_start_points_out


def _old_smk(df, data_col, season_col, alpha=0.05, rm_na=True):
    warnings.warn('this function is depreciated, use _mann_kendall_from_sarray', DeprecationWarning)
    if rm_na:
        data = df.dropna(subset=[data_col, season_col])
    else:
        data = df.copy(deep=True)
    data_col = data_col
    season_col = season_col
    alpha = alpha

    # get list of seasons
    season_vals = np.unique(data[season_col])

    # calulate the seasonal MK values
    _season_outputs = {}
    s = 0
    var_s = 0
    for season in season_vals:
        tempdata = data[data_col][data[season_col] == season].sort_index()
        _season_outputs[season] = MannKendall(data=tempdata, alpha=alpha, rm_na=rm_na)
        temp = _season_outputs[season].var_s
        var_s += _season_outputs[season].var_s
        s += _season_outputs[season].s

    # calculate the z value
    z = np.abs(np.sign(s)) * (s - np.sign(s)) / np.sqrt(var_s)

    h = abs(z) > norm.ppf(1 - alpha / 2)
    p = 2 * (1 - norm.cdf(abs(z)))  # two tail test
    trend = np.sign(z) * h
    # -1 decreasing, 0 no trend, 1 increasing
    return trend, h, p, z, s, var_s


class MannKendall(object):  # todo write tests
    """
    an object to hold and calculate kendall trends

    :ivar trend: the trend of the data, -1 decreasing, 0 no trend, 1 increasing
    :ivar h: boolean, True if the trend is significant
    :ivar p: the p value of the trend
    :ivar z: the z value of the trend
    :ivar s: the s value of the trend
    :ivar var_s: the variance of the s value
    :ivar alpha: the alpha value used to calculate the trend
    :ivar data: the data used to calculate the trend
    :ivar data_col: the column of the data used to calculate the trend
    """
    "assumes a pandas dataframe or series with a time index"

    def __init__(self, data, alpha=0.05, data_col=None, rm_na=True):
        self.alpha = alpha

        if data_col is not None:
            test_data = data[data_col]
        else:
            test_data = data
        if rm_na:
            test_data = test_data.dropna(how='any')
        test_data = test_data.sort_index()
        self.data = test_data
        self.data_col = data_col
        self.trend, self.h, self.p, self.z, self.s, self.var_s = _mann_kendall_from_sarray(test_data, alpha=alpha)


class SeasonalKendall(object):  # todo write tests
    """
    an object to hold and calculate seasonal kendall trends

    :ivar trend: the trend of the data, -1 decreasing, 0 no trend, 1 increasing
    :ivar h: boolean, True if the trend is significant
    :ivar p: the p value of the trend
    :ivar z: the z value of the trend
    :ivar s: the s value of the trend
    :ivar var_s: the variance of the s value
    :ivar alpha: the alpha value used to calculate the trend
    :ivar data: the data used to calculate the trend
    :ivar data_col: the column of the data used to calculate the trend
    :ivar season_col: the column of the season data used to calculate the trend
    :ivar freq_limit: the maximum difference in frequency between seasons (as a fraction),
                        if greater than this will raise a warning
    """

    def __init__(self, df, data_col, season_col, alpha=0.05, rm_na=True,
                 freq_limit=0.05):
        """
        intis and calculate the seasonal mann kendall
        outputs are held by

        :param df: pd.DataFrame holding the season and data columns, expect the index to be the time index
                    e.g. sort_index will sort the data by time
        :param data_col: name of the data column
        :param season_col: name of the season column
        :param alpha: the alpha limit for the p value
        :param rm_na: boolean dropna
        :param freq_limit: the maximum difference in frequency between seasons (as a fraction),
                       if greater than this will raise a warning
        """

        self.freq_limit = freq_limit
        if rm_na:
            self.data = df.dropna(subset=[data_col, season_col])
        else:
            self.data = df.copy(deep=True)
        self.data_col = data_col
        self.season_col = season_col
        self.alpha = alpha

        x = self.data[data_col].sort_index()
        season_data = self.data[season_col].sort_index()

        trend, h, p, z, s, var_s = _seasonal_mann_kendall_from_sarray(x, season_data, alpha=self.alpha, sarray=None,
                                                                      freq_limit=self.freq_limit)
        self.trend = trend
        self.h = h
        self.p = p
        self.z = z
        self.s = s
        self.var_s = var_s
        # -1 decreasing, 0 no trend, 1 increasing


class MultiPartKendall():  # todo test
    """
    multi part mann kendall test to indentify a change point(s) in a time series
    after Frollini et al., 2020, DOI: 10.1007/s11356-020-11998-0
    :ivar acceptable_matches: (boolean index) the acceptable matches for the trend, i.e. the trend is the expected trend
    :ivar all_start_points: all the start points for the mann kendall tests
    :ivar alpha: the alpha value used to calculate the trend
    :ivar data: the data used to calculate the trend
    :ivar data_col: the column of the data used to calculate the trend
    :ivar datasets: a dictionary of the datasets {f'p{i}':pd.DataFrame for i in range(nparts)}
                    each dataset contains the mann kendall results for each part of the time series
                    (trend (1=increasing, -1=decreasing, 0=no trend), h, p, z, s, var_s)
    :ivar expect_part: the expected trend in each part of the time series (1 increasing, -1 decreasing, 0 no trend)
    :ivar idx_values: the index values of the data used to calculate the trend used in internal plotting
    :ivar min_size: the minimum size for all parts of the timeseries
    :ivar n: number of data points
    :ivar nparts: number of parts to split the time series into
    :ivar rm_na: boolean dropna
    :ivar s_array: the s array used to calculate the trend
    :ivar season_col: the column of the season data used to calculate the trend (not used for this class)
    :ivar season_data: the season data used to calculate the trend (not used for this class)
    :ivar serialise: boolean, True if the class is serialised
    :ivar serialise_path: path to the serialised file
    :ivar x: the data
    """

    def __init__(self, data, nparts=2, expect_part=(1, -1), min_size=10, alpha=0.05, data_col=None, rm_na=True,
                 serialise_path=None, recalc=False, initalize=True):
        """
        multi part mann kendall test to indentify a change point(s) in a time series
        after Frollini et al., 2020, DOI: 10.1007/s11356-020-11998-0
        note where the expected trend is zero the lack of a trend is considered significant if p > 1-alpha
        :param data: time series data, if DataFrame or Series, expects the index to be sample order (will sort on index)
                     if np.array or list expects the data to be in sample order
        :param nparts: number of parts to split the time series into
        :param expect_part: expected trend in each part of the time series (1 increasing, -1 decreasing, 0 no trend)
        :param min_size: minimum size for the first and last section of the time series
        :param alpha: significance level
        :param data_col: if data is a DataFrame or Series, the column to use
        :param rm_na: remove na values from the data
        :param serialise_path: path to serialised file (as hdf), if None will not serialise
        :param recalc: if True will recalculate the mann kendall even if the serialised file exists
        :param initalize: if True will initalize the class from the data, only set to False used in self.from_file
        :return:
        """
        self.expect_dict = {1: 'increasing', -1: 'decreasing', 0: 'no trend'}

        if not initalize:
            assert all([e is None for e in
                        [data, nparts, expect_part, min_size, alpha, data_col, rm_na, serialise_path, recalc]])
        else:
            loaded = False
            if serialise_path is not None:
                serialise_path = Path(serialise_path)
                self.serialise_path = serialise_path
                self.serialise = True
                if Path(serialise_path).exists() and not recalc:
                    loaded = True
                    self._set_from_file(
                        data=data,
                        nparts=nparts,
                        expect_part=expect_part,
                        min_size=min_size,
                        alpha=alpha,
                        data_col=data_col,
                        rm_na=rm_na,
                        season_col=None)
            else:
                self.serialise = False
                self.serialise_path = None

            if not loaded:
                self._set_from_data(data=data,
                                    nparts=nparts,
                                    expect_part=expect_part,
                                    min_size=min_size,
                                    alpha=alpha,
                                    data_col=data_col,
                                    rm_na=rm_na,
                                    season_col=None)

            if self.serialise and not loaded:
                self._to_file()

    def get_acceptable_matches(self):
        outdata = self.datasets['p0'].loc[self.acceptable_matches]
        outdata = outdata.set_index([f'split_point_{i}' for i in range(1, self.nparts)])
        outdata.rename(columns={f'{e}': f'{e}_p0' for e in ['trend', 'h', 'p', 'z', 's', 'var_s']}, inplace=True)
        for i in range(1, self.nparts):
            next_data = self.datasets[f'p{i}'].loc[self.acceptable_matches]
            next_data = next_data.set_index([f'split_point_{j}' for j in range(1, self.nparts)])
            next_data.rename(columns={f'{e}': f'{e}_p{i}' for e in ['trend', 'h', 'p', 'z', 's', 'var_s']},
                             inplace=True)
            outdata = pd.merge(outdata, next_data, left_index=True, right_index=True)

        return outdata

    def get_data_from_breakpoints(self, breakpoints):
        """

        :param breakpoints: beakpoints to split the data, e.g. from self.get_acceptable_matches
        :return: outdata: list of dataframes for each part of the time series
                 senslopes: list of senslopes for each part of the time series
                 senintercepts: list of senintercepts for each part of the time series
                 kendal_stats: dataframe of kendal stats for each part of the time series
        """
        assert len(breakpoints) == self.nparts - 1
        outdata = []
        kendal_stats = pd.DataFrame(index=[f'p{i}' for i in range(self.nparts)],
                                    columns=['trend', 'h', 'p', 'z', 's', 'var_s', 'senslope',
                                             'senintercept'])
        for p, ds in enumerate(self.datasets):
            temp = ds.set_index([f'split_point_{i}' for i in range(1, self.nparts)])
            outcols = ['trend', 'h', 'p', 'z', 's', 'var_s']
            kendal_stats.loc[f'p{p}', outcols] = temp.loc[breakpoints, outcols].values

        start = 0
        for i, bp in enumerate(breakpoints):
            if i == self.nparts - 1:
                end = self.n
            else:
                end = bp
            if isinstance(self.data, pd.DataFrame):
                outdata.append(self.data.loc[self.idx_values[start:end]])
            else:
                outdata.append(deepcopy(
                    pd.Series(index=self.idx_values[start:end], data=self.data[self.idx_values[start:end]])))
            start = end

        # calculate the senslope stats
        for i, ds in enumerate(outdata):
            senslope, senintercept = self._calc_senslope(ds)
            kendal_stats.loc[f'p{i}', 'sen_slope'] = senslope
            kendal_stats.locf[f'p{i}', 'sen_intercept'] = senintercept

        return outdata, kendal_stats

    def plot_data_from_breakpoints(self, breakpoints, ax=None):  # todo test
        """
        plot the data from the breakpoints including the senslope fits
        :param breakpoints:
        :param ax: ax to plot on if None then create the ax
        :return:
        """

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 8))
        else:
            fig = ax.figure()

        data, kendal_stats = self.get_data_from_breakpoints(breakpoints)
        trans = blended_transform_factory(ax.transData, ax.transAxes)

        # axhlines at breakpoints
        prev_bp = 0
        for i, bp in enumerate(np.concatenate((breakpoints, [self.n]))):
            if not bp == self.n:
                ax.axhline(self.idx_values[bp], color='k', ls=':')
            sslope = kendal_stats.loc[f"p{i}", "sen_slope"]
            sintercept = kendal_stats.loc[f"p{i}", "sen_intercept"]
            ax.text((prev_bp + bp) / 2, 0.9,
                    f'expected: {self.expect_dict[self.expect_part[i]]}\n'
                    f'got: slope: {sslope:.3e}, '
                    f'pval:{round(kendal_stats.loc[f"p{i}", "p"], 3)}',
                    transform=trans)

            # plot the senslope fit and intercept
            x = self.idx_values[prev_bp:bp]
            y = x * sslope + sintercept
            ax.plot(x, y, color='k', ls='--')
            prev_bp = bp

        colors = get_colors(data)
        for i, ds, c in enumerate(zip(data, colors)):
            if isinstance(self.data, pd.DataFrame):
                ax.scatter(ds.index, ds[self.data_col], c=c, label=f'part {i}')
            else:
                ax.scatter(ds.index, ds, c=c, label=f'part {i}')

        legend_handles = [Line2D([0], [0], color='k', ls=':'),
                          Line2D([0], [0], color='k', ls='--')]

        legend_labels = ['breakpoint', 'sen slope fit', ]

        nhandls, nlabels = ax.get_legend_handles_labels()
        legend_handles.extend(nhandls)
        legend_labels.extend(nlabels)
        ax.legend(legend_handles, legend_labels, loc='best')
        return fig, ax

    def _set_from_file(self, data, nparts, expect_part, min_size, alpha, data_col, rm_na,
                       season_col=None, check_inputs=True):
        """
        setup the class data from a serialised file, values are passed to ensure they are consistent
        :param serialise_path:
        :param data:
        :param nparts:
        :param expect_part:
        :param min_size:
        :param alpha:
        :param data_col:
        :param rm_na:
        :return:
        """
        assert self.serialise_path is not None, 'serialise path not set, should not get here'
        params = pd.read_hdf(self.serialise_path, 'params')
        assert isinstance(params, pd.Series)
        # other parameters
        self.alpha = params['alpha']
        self.nparts = params['nparts']
        self.min_size = params['min_size']
        self.data_col = params['data_col']
        self.rm_na = params['rm_na']
        self.season_col = params['season_col']
        self.n = params['n']
        self.expect_part = [params[f'expect_part{i}'] for i in range(self.nparts)]
        datatype = params['datatype']

        # d1 data
        d1_data = pd.read_hdf(self.serialise_path, 'd1_data')
        self.x = d1_data['x'].values
        self.idx_values = d1_data['idx_values'].values
        self.acceptable_matches = d1_data['acceptable_matches'].values
        if self.season_col is not None:
            self.season_data = d1_data['season_data'].values
        else:
            self.season_data = None

        if datatype == 'pd.DataFrame':
            self.data = pd.read_hdf(self.serialise_path, 'data')
            assert isinstance(self.data, pd.DataFrame)
        elif datatype == 'pd.Series':
            self.data = pd.read_hdf(self.serialise_path, 'data')
            assert isinstance(self.data, pd.Series)
        elif datatype == 'np.array':
            self.data = pd.read_hdf(self.serialise_path, 'data').values
            assert isinstance(self.data, np.ndarray)
            assert self.data.ndim == 1
        else:
            raise ValueError('unknown datatype, thou shall not pass')

        # s array
        self.s_array = pd.read_hdf(self.serialise_path, 's_array').values
        assert self.s_array.shape == (self.n, self.n)

        # all start points
        self.all_start_points = pd.read_hdf(self.serialise_path, 'all_start_points').values
        assert self.all_start_points.shape == (len(self.all_start_points), self.nparts - 1)

        # datasets
        self.datasets = {}
        for part in range(self.nparts):
            self.datasets[f'p{part}'] = pd.read_hdf(self.serialise_path, f'part{part}')

        if check_inputs:
            # check parameters have not changed
            assert self.data_col == data_col, 'data_col does not match'
            assert self.rm_na == rm_na, 'rm_na does not match'
            assert self.season_col == season_col, 'season_col does not match'
            assert self.nparts == nparts, 'nparts does not match'
            assert self.min_size == min_size, 'min_size does not match'
            assert self.alpha == alpha, 'alpha does not match'
            assert all(np.atleast_1d(self.expect_part) == np.atleast_1d(expect_part)), 'expect_part does not match'

            # check datasets
            if datatype == 'pd.DataFrame':
                pd.testing.assert_frame_equal(self.data, data, check_dtype=False, check_like=True)
            elif datatype == 'pd.Series':
                pd.testing.assert_series_equal(self.data, data, check_dtype=False, check_like=True)
            elif datatype == 'np.array':
                np.allclose(self.data, data)

    def _set_from_data(self, data, nparts, expect_part, min_size, alpha, data_col, rm_na,
                       season_col=None):
        """
        set up the class data from the input data
        :param data:
        :param nparts:
        :param expect_part:
        :param min_size:
        :param alpha:
        :param data_col:
        :param rm_na:
        :param season_col:
        :return:
        """
        self.data = deepcopy(data)
        self.alpha = alpha
        self.nparts = nparts
        self.min_size = min_size
        self.expect_part = expect_part
        self.data_col = data_col
        self.rm_na = rm_na

        assert len(expect_part) == nparts

        # handle data (including options for season)
        self.season_col = season_col
        if season_col is not None:
            assert isinstance(data, pd.DataFrame) or isinstance(data, dict), ('season_col passed but data is not a '
                                                                              'DataFrame or dictionary')
            assert season_col in data.keys(), 'season_col not in data'
            assert data_col is not None, 'data_col must be passed if season_col is passed'
            assert data_col in data.keys(), 'data_col not in data'
            if rm_na:
                data = data.dropna(subset=[data_col, season_col])
            data = data.sort_index()
            self.season_data = data[season_col]
            self.idx_values = data.index.values
            x = np.array(data[data_col])
            self.x = x
        else:
            self.season_data = None
            if data_col is not None:
                x = pd.Series(data[data_col])
            else:
                x = pd.Series(data)
            if rm_na:
                x = x.dropna(how='any')
            x = x.sort_index()
            self.idx_values = x.index.values
            x = np.array(x)
            self.x = x
        assert x.ndim == 1, 'data must be 1d or multi d but with col_name passed'

        n = len(x)
        self.n = n
        if n / self.nparts < min_size:
            raise ValueError('the time series is too short for the minimum size')
        self.s_array = _make_s_array(x)

        all_start_points = _generate_startpoints(n, self.min_size, self.nparts)
        datasets = {f'p{i}': [] for i in range(nparts)}
        self.all_start_points = all_start_points
        self.datasets = datasets

        self._calc_mann_kendall()

        # find all acceptable matches
        idx = np.ones(len(self.all_start_points), bool)
        for part, expect in enumerate(self.expect_part):
            if expect == 0:
                use_alpha = 1 - self.alpha
                idx = (idx
                       & (self.datasets[f'p{part}'].trend == expect)
                       & (self.datasets[f'p{part}'].p > use_alpha)
                       )
            else:
                use_alpha = self.alpha
                idx = (idx
                       & (self.datasets[f'p{part}'].trend == expect)
                       & (self.datasets[f'p{part}'].p < use_alpha)
                       )
        self.acceptable_matches = idx

    def _calc_senslope(self, data):

        if isinstance(self.data, pd.DataFrame):
            senslope, senintercept, lo_slope, up_slope = mstats.theilslopes(data[self.data_col], data.index)
        else:
            senslope, senintercept, lo_slope, up_slope = mstats.theilslopes(data, data.index)
        return senslope, senintercept

    def _calc_mann_kendall(self):
        """
        acutually calculate the mann kendall from the sarray, this should be the only thing that needs
        to be updated for the seasonal kendall
        :return:
        """
        for sp in self.all_start_points:
            start = 0
            for i in range(self.nparts):
                if i == self.nparts - 1:
                    end = self.n
                else:
                    end = sp + sp * i
                data = (*sp,
                        *_mann_kendall_from_sarray(self.x[start:end], alpha=self.alpha,
                                                   sarray=self.s_array[start:end, start:end]))
                self.datasets[f'p{i}'].append(data)
                start = end
        for part in range(self.nparts):
            self.datasets[f'p{part}'] = pd.DataFrame(self.datasets[f'p{part}'],
                                                     columns=[f'split_point_{i}' for i in range(1, self.nparts)]
                                                             + ['trend', 'h', 'p', 'z', 's', 'var_s'])

    def _to_file(self):
        assert self.serialise_path is not None, 'serialise path not set, should not get here'
        with pd.HDFStore(self.serialise_path, 'w') as hdf:
            # setup single value parameters
            params = pd.Series()

            # should be 1d+ of same length
            d1_data = pd.DataFrame(index=range(len(self.x)))
            d1_data['x'] = self.x
            d1_data['idx_values'] = self.idx_values
            d1_data['acceptable_matches'] = self.acceptable_matches
            if self.season_col is not None:
                d1_data['season_data'] = self.season_data
            d1_data.to_hdf(hdf, 'd1_data')

            # save as own datasets
            if isinstance(self.data, pd.DataFrame):
                self.data.to_hdf(hdf, 'data')
                params['datatype'] = 'pd.DataFrame'
            elif isinstance(self.data, pd.Series):
                self.data.to_hdf(hdf, 'data')
                params['datatype'] = 'pd.Series'
            else:
                params['datatype'] = 'np.array'
                pd.Series(self.data).to_hdf(hdf, 'data')

            assert isinstance(self.s_array, np.ndarray)
            pd.DataFrame(self.s_array).to_hdf(hdf, 's_array')
            assert isinstance(self.all_start_points, np.ndarray)
            pd.DataFrame(self.all_start_points).to_hdf(hdf, 'all_start_points')

            for part in range(self.nparts):
                self.datasets[f'p{part}'].to_hdf(hdf, f'part{part}')

            # other parameters
            params['alpha'] = self.alpha
            params['nparts'] = self.nparts
            params['min_size'] = self.min_size
            params['data_col'] = self.data_col
            params['rm_na'] = self.rm_na
            params['season_col'] = self.season_col
            params['n'] = self.n
            for i in range(self.nparts):
                params[f'expect_part{i}'] = self.expect_part[i]

        params.to_hdf(hdf, 'params')

    @classmethod
    @staticmethod
    def from_file(path):
        """
        load the class from a serialised file
        :param path:
        :return:
        """
        mpk = MultiPartKendall(data=None, nparts=None, expect_part=None, min_size=None, alpha=None, data_col=None,
                               rm_na=None, season_col=None)
        mpk.serialise_path = Path(path)
        mpk.serialise = True
        mpk._set_from_file(data=None, nparts=None, expect_part=None, min_size=None, alpha=None, data_col=None,
                           rm_na=None, season_col=None, check_inputs=False)
        return mpk


class SeasonalMultiPartKendall(MultiPartKendall):  # todo test
    """
    multi part mann kendall test to indentify a change point(s) in a time series
    after Frollini et al., 2020, DOI: 10.1007/s11356-020-11998-0
    :ivar acceptable_matches: (boolean index) the acceptable matches for the trend, i.e. the trend is the expected trend
    :ivar all_start_points: all the start points for the mann kendall tests
    :ivar alpha: the alpha value used to calculate the trend
    :ivar data: the data used to calculate the trend
    :ivar data_col: the column of the data used to calculate the trend
    :ivar datasets: a dictionary of the datasets {f'p{i}':pd.DataFrame for i in range(nparts)}
                    each dataset contains the mann kendall results for each part of the time series
                    (trend (1=increasing, -1=decreasing, 0=no trend), h, p, z, s, var_s)
    :ivar expect_part: the expected trend in each part of the time series (1 increasing, -1 decreasing, 0 no trend)
    :ivar idx_values: the index values of the data used to calculate the trend used in internal plotting
    :ivar min_size: the minimum size for all parts of the timeseries
    :ivar n: number of data points
    :ivar nparts: number of parts to split the time series into
    :ivar rm_na: boolean dropna
    :ivar s_array: the s array used to calculate the trend
    :ivar season_col: the column of the season data used to calculate the trend
    :ivar season_data: the season data used to calculate the trend
    :ivar serialise: boolean, True if the class is serialised
    :ivar serialise_path: path to the serialised file
    :ivar x: the data
    """

    def __init__(self, data, data_col, season_col, nparts=2, expect_part=(1, -1), min_size=10, alpha=0.05, rm_na=True,
                 serialise_path=None, recalc=False, initalize=True):
        """
        multi part seasonal mann kendall test to indentify a change point(s) in a time series
        after Frollini et al., 2020, DOI: 10.1007/s11356-020-11998-0
        :param data: time series data, if DataFrame or Series, expects the index to be sample order (will sort on index)
                     if np.array or list expects the data to be in sample order
        :param data_col: if data is a DataFrame or Series, the column to use
        :param season_col: the column to use for the season
        :param nparts: number of parts to split the time series into
        :param expect_part: expected trend in each part of the time series (1 increasing, -1 decreasing, 0 no trend)
        :param min_size: minimum size for the first and last section of the time series
        :param alpha: significance level
        :param rm_na: remove na values from the data
        :param serialise_path: path to serialised file (as hdf), if None will not serialise
        :param recalc: if True will recalculate the mann kendall even if the serialised file exists
        :param initalize: if True will initalize the class from the data, only set to False used in self.from_file
        :return:
        """
        if not initalize:
            assert all([e is None for e in
                        [data, nparts, expect_part, min_size, alpha, data_col, rm_na, serialise_path, recalc]])
        else:
            loaded = False
            if serialise_path is not None:
                serialise_path = Path(serialise_path)
                self.serialise_path = serialise_path
                self.serialise = True
                if Path(serialise_path).exists() and not recalc:
                    loaded = True
                    self._set_from_file(
                        data=data,
                        nparts=nparts,
                        expect_part=expect_part,
                        min_size=min_size,
                        alpha=alpha,
                        data_col=data_col,
                        rm_na=rm_na,
                        season_col=season_col)
            else:
                self.serialise = False
                self.serialise_path = None

            if not loaded:
                self._set_from_data(data=data,
                                    nparts=nparts,
                                    expect_part=expect_part,
                                    min_size=min_size,
                                    alpha=alpha,
                                    data_col=data_col,
                                    rm_na=rm_na,
                                    season_col=season_col)

            if self.serialise and not loaded:
                self._to_file()

    def _calc_mann_kendall(self):
        """
        acutually calculate the mann kendall from the sarray, this should be the only thing that needs
        to be updated for the seasonal kendall
        :return:
        """

        for sp in self.all_start_points:
            start = 0
            for i in range(self.nparts):
                if i == self.nparts - 1:
                    end = self.n
                else:
                    end = sp + sp * i
                data = (*sp,
                        *_seasonal_mann_kendall_from_sarray(self.x[start:end], alpha=self.alpha,
                                                            season_data=self.season_data[start:end],
                                                            sarray=self.s_array[start:end,
                                                                   start:end]))  # and passing the s array
                self.datasets[f'p{i}'].append(data)
                start = end
        for part in range(self.nparts):
            self.datasets[f'p{part}'] = pd.DataFrame(self.datasets[f'p{part}'],
                                                     columns=[f'split_point_{i}' for i in range(1, self.nparts)]
                                                             + ['trend', 'h', 'p', 'z', 's', 'var_s'])

    def _calc_senslope(self, data):
        slopes = []
        intercepts = []
        for season in np.unique(self.season_data.unique()):
            temp = data.loc[self.season_data == season]

            senslope, senintercept, lo_slope, up_slope = mstats.theilslopes(temp[self.data_col], temp.index)
            slopes.append(senslope)
            intercepts.append(senintercept)
        return np.mean(senslope), np.mean(senintercept)


def get_colors(vals, cmap='tab10'):
    n_scens = len(vals)
    if n_scens < 20:
        cmap = get_cmap(cmap)
        colors = [cmap(e / (n_scens + 1)) for e in range(n_scens)]
    else:
        colors = []
        i = 0
        cmap = get_cmap(cmap)
        for v in vals:
            colors.append(cmap(i / 20))
            i += 1
            if i == 20:
                i = 0
    return colors


if __name__ == '__main__':
    _generate_startpoints(100, 10, 3, test=True)
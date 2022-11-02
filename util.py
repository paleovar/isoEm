import os.path
import numpy as np


def flatten(l):
    """
    flatten a 2d list into a 1d list
    """
    return [item for sublist in l for item in sublist]


def check_dict_conditions(dic, conditions, use_prints=False):
    """
    Test whether dict "dic" fullfills the given conditions "conditions".
    The latter are given as a array of key-value pairs, values may be lists/tuples.
    If prints==True, information on mismatche can be printed.
    """
    for key, value in conditions.items():
        if key in dic.keys():
            if not dic[key] == value:
                if use_prints:
                    print("Difference:", key, "Original:", dic[key], "Condition:", value)
                return False
        else:
            if use_prints:
                print("Key not contained in dataset:", key)
            return False
    return True


def test_if_folder_exists(dir_name):
    """
    Test if a given filename already exists. Because files are named by hashes this
    implies that we already created a file for the given configuration
    """
    if os.path.exists(dir_name):
        return True
    else:
        return False


def create_hash_from_description(description):
    """
    Create a hash value that can than be used to identify duplicates of folders.
    """
    # to be able to hash, we need tuples instead of lists and frozensets instead of dicts.
    res_dict = {}
    for key, value in description.items():
        if type(value) == dict:
            res_dict[key] = frozenset(value)
        elif type(value) == list:
            res_dict[key] = tuple(value)
        else:
            res_dict[key] = value
    return str(hex(hash(frozenset(res_dict.items()))))


def get_years_months(t, units, calendar):
    """
    The data sets come with different time units and calendars.
    We write a function that returns the 'true' time steps.
    @param t: Timesteps to be converted
    @param units: String containing a description of the time units used. Can be extracted via netCDF4.
    @param calendar: String containing a description of the calendar used. Can be extracted via netCDF4.
    @return: 
    """
    if units == "months since 801-1-15 00:00:00":
        years = 801 + t // 12
        months = 0 + t % 12
    elif units == "month as %Y%m.%f":
        timesteps = [t_.split(".")[0] for t_ in t.astype(str)]
        years = [int(t_[:-2]) for t_ in timesteps]
        months = [int(t_[-2:])-1 for t_ in timesteps]  # want months to start with zero instead of one
    elif units == "day as %Y%m%d.%f":
        timesteps = [t_.split(".")[0] for t_ in t.astype(str)]
        years = [int(t_[:-4]) for t_ in timesteps]
        months = [int(t_[-4:-2])-1 for t_ in timesteps]  # want months to start with zero instead of one
    elif units == "months since 850-1-15 00:00:00":
        years = 850 + t // 12
        months = 0 + t % 12
    elif units == "days since 0850-01-01 00:00:00":
        if calendar == "365_day":
            years = 850 + t // 365
            ds = [31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 0]
            months = [np.argmin(np.abs(ds - t_ % 365)) for t_ in t]
    elif units == "days since 2350-12-01 00:00:00":
        if calendar == "360_day":
            y_ref = 654
            m_ref = 11
            years = - y_ref + 850 + (t // 360)  # in the dataset the year (2954) corresponds to year 850
            months = (t+m_ref*30) % 360 // 30
    elif units == "days since 0000-01-01 00:00:00":
        return None, None
    return years, months


def get_year_mon_day_from_timesteps(time_steps, ref_date):
    """
    Extract the month (0: January,..., 11: December) of given timesteps, assuming the time is given as days
    since the reference date and a 360 day calendar with month length 30.

    @param time_steps: Array of timesteps
    @param ref_date: Reference date
    @return: Array containing month of each timestep.
    """
    ref_year = ref_date.year
    ref_month = ref_date.month - 1  # months in calendar 1-12, we want 0-11
    ref_day = ref_date.day

    ref_n_days = ref_year*360 + ref_month*30 + ref_day

    total_days = ref_n_days + time_steps

    year = total_days // 360
    month = (total_days - year * 360) // 30
    day = (total_days - year * 360 - month * 30) // 1
    return year, month, day


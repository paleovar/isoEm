from evaluate import get_rescaled_predictions_and_gt, load_compatible_available_runs
from train import find_and_load_dataset
import util
import netCDF4 as nc
import numpy as np
import os

import copy

import gzip
import pickle

from icosahedron import Icosahedron

from subprocess import call


def interpolate_predictions(
    descriptions,
    predictions,
    output_folder,
    script_folder="Scripts/",
    resolution=5,
    interpolation="cons1",
    do_scaling=True,
):
    """
    Provide functions to interpolate between grids.
    Ideally the function would proceed in the following steps:
    1) load predictions, undo the standardization
    2) create netcdf4 (temporary)
    3) do the interpolation by calling the script files
    4) create a gz file from the interpolated file.
    @param descriptions: Descriptions of model and dataset
    @param predictions: Predictions to be interpolated
    @param output_folder: Folder to store the results in
    @param script_folder: Folder in which the interpolation shell scripts must be stored in (+grid description files)
    @param resolution: Resolution of the icosahedron used in the interpolation
    @param interpolation: Type of interpolation used (cons1 or NN)
    @param do_scaling: Whether or not we want to rescale the data before saving
    @return:
    """
    assert len(descriptions["DATASET_DESCRIPTION"]
               ["TARGET_VARIABLES"].keys()) == 1
    assert descriptions["DATASET_DESCRIPTION"]["TIMESCALE"] == "YEARLY"
    # load the predictions, undo the scaling
    if do_scaling:
        if descriptions["DATASET_DESCRIPTION"]["GRID_TYPE"] == "Flat":
            rescaled_predictions, _, _ = get_rescaled_predictions_and_gt(
                descriptions, predictions
            )
        elif descriptions["DATASET_DESCRIPTION"]["GRID_TYPE"] == "Ico":
            rescaled_predictions, _ = get_rescaled_predictions_and_gt(
                descriptions, predictions
            )
        else:
            raise NotImplementedError("Invalid grid type")
    else:
        rescaled_predictions = predictions

    netcdf_from_rescaled_predictions(
        descriptions,
        rescaled_predictions,
        descriptions["DATASET_DESCRIPTION"]["TIMESTEPS_TEST"],
        script_folder,
    )
    if do_scaling:
        dataset_description = dict(
            {"RESULTS_INTERPOLATED": True, "RESULTS_RESCALED": True}, **descriptions["DATASET_DESCRIPTION"]
        )
    else:
        dataset_description = dict(
            {"RESULTS_INTERPOLATED": True, "RESULTS_RESCALED": False}, **descriptions["DATASET_DESCRIPTION"]
        )
    if descriptions["DATASET_DESCRIPTION"]["GRID_TYPE"] == "Flat":
        run_script(
            descriptions,
            script_folder,
            resolution=resolution,
            interpolation_type=interpolation,
        )
        ds_5_nbs = nc.Dataset(
            os.path.join(
                script_folder, "tmp_r_{}_nbs_5_{}.nc".format(
                    resolution, interpolation)
            )
        )
        ds_6_nbs = nc.Dataset(
            os.path.join(
                script_folder, "tmp_r_{}_nbs_6_{}.nc".format(
                    resolution, interpolation)
            )
        )

        ico = Icosahedron(r=resolution)
        regions, vertices = ico.get_voronoi_regions_vertices()
        indices_six_nb = []
        indices_five_nb = []
        for i in range(len(regions)):
            if len(regions[i]) > 5:
                indices_six_nb.append(i)
            else:
                indices_five_nb.append(i)
        # create numpy arrays
        indices_6_nbs = np.array(indices_six_nb)
        indices_5_nbs = np.array(indices_five_nb)

        res = np.zeros(
            (
                ds_6_nbs.variables[
                    list(
                        descriptions["DATASET_DESCRIPTION"]["TARGET_VARIABLES"].values(
                        )
                    )[0][0]
                ][:].data.shape[:-1]
                + (len(indices_6_nbs) + 10,)
            )
        )
        res[..., indices_6_nbs] = ds_6_nbs.variables[
            list(descriptions["DATASET_DESCRIPTION"]
                 ["TARGET_VARIABLES"].values())[0][0]
        ][:].data
        res[..., indices_5_nbs] = ds_5_nbs.variables[
            list(descriptions["DATASET_DESCRIPTION"]
                 ["TARGET_VARIABLES"].values())[0][0]
        ][:].data

        charts = Icosahedron(r=resolution).get_charts_cut()
        res = res.reshape(res.shape[0], 1, charts.shape[0]
                          * charts.shape[1], charts.shape[2])
        dataset_description["GRID_TYPE"] = "Ico"
        dataset_description["RESOLUTION"] = resolution
        dataset_description["INTERPOLATION"] = interpolation
        model_training_description = descriptions["MODEL_TRAINING_DESCRIPTION"]

        new_descriptions = {
            "MODEL_TRAINING_DESCRIPTION": model_training_description,
            "DATASET_DESCRIPTION": dataset_description,
        }

    elif descriptions["DATASET_DESCRIPTION"]["GRID_TYPE"] == "Ico":
        run_script(
            descriptions,
            script_folder,
            resolution=descriptions["DATASET_DESCRIPTION"]["RESOLUTION"],
            interpolation_type=interpolation,
        )
        ds_6_nbs = nc.Dataset(
            os.path.join(
                script_folder,
                "tmp_6_nbs_r_{}_nbs_6_{}.nc".format(
                    descriptions["DATASET_DESCRIPTION"]["RESOLUTION"], interpolation
                ),
            )
        )
        res = ds_6_nbs.variables[
            list(descriptions["DATASET_DESCRIPTION"]
                 ["TARGET_VARIABLES"].values())[0][0]
        ][:].data

        res = res[:, np.newaxis, ...]

        print(
            "When interpolating back to flat grid, only the 6nbs file is used, "
            "because otherwise we have wrong results due to overlap."
        )
        dataset_description["GRID_TYPE"] = "Flat"
        model_training_description = descriptions["MODEL_TRAINING_DESCRIPTION"]

        new_descriptions = {
            "MODEL_TRAINING_DESCRIPTION": model_training_description,
            "DATASET_DESCRIPTION": dataset_description,
        }

    else:
        raise NotImplementedError("Invalid grid type")

    s1 = util.create_hash_from_description(
        new_descriptions["DATASET_DESCRIPTION"])
    s2 = util.create_hash_from_description(
        new_descriptions["MODEL_TRAINING_DESCRIPTION"]
    )
    folder_name = os.path.join(output_folder, s1 + s2)
    predictions_file = os.path.join(folder_name, "predictions.gz")
    descriptions_file = os.path.join(folder_name, "descriptions.gz")

    if util.test_if_folder_exists(folder_name):
        raise FileExistsError(
            "Specified configuration of dataset, model and training configuration already exists."
        )
    else:
        os.makedirs(folder_name)

    print("writing predictions")
    with gzip.open(predictions_file, "wb") as f:
        pickle.dump(res, f)

    print("writing descriptions")
    with gzip.open(descriptions_file, "wb") as f:
        pickle.dump(new_descriptions, f)
    print("done")


def netcdf_from_rescaled_predictions(
    descriptions, rescaled_predictions, t_test, output_folder
):
    dataset_description = descriptions["DATASET_DESCRIPTION"]
    model_training_description = descriptions["MODEL_TRAINING_DESCRIPTION"]
    assert (
        len(dataset_description["TARGET_VARIABLES"].keys()) == 1
    ), "Interpolation only implemented for single target variable"

    if dataset_description["GRID_TYPE"] == "Flat":
        tocopy = []
        dimscopy = []
        output_file = os.path.join(output_folder, "tmp.nc")

        if dataset_description["TIMESCALE"] == "YEARLY":
            filename = os.path.join(
                "Datasets",
                dataset_description["CLIMATE_MODEL"],
                "Original",
                "{}_yearly.nc".format(
                    list(dataset_description["TARGET_VARIABLES"].keys())[0]
                ),
            )
        elif dataset_description["TIMESCALE"] == "MONTHLY":
            filename = os.path.join(
                "Datasets",
                dataset_description["CLIMATE_MODEL"],
                "Original",
                "{}.nc".format(
                    list(dataset_description["TARGET_VARIABLES"].keys())[0]),
            )
        else:
            raise NotImplementedError("Invalid timescale")
        original_dimensions = (
            nc.Dataset(filename)
            .variables[
                "{}".format(
                    list(dataset_description["TARGET_VARIABLES"].values())[
                        0][0]
                )
            ]
            .dimensions
        )
        necessary_dimensions = (
            original_dimensions[0],
            original_dimensions[2],
            original_dimensions[3],
        )
        original_dataype = (
            nc.Dataset(filename)
            .variables[
                "{}".format(
                    list(dataset_description["TARGET_VARIABLES"].values())[
                        0][0]
                )
            ]
            .datatype
        )

        src = nc.Dataset(filename)
        if "t" in src.dimensions:
            dimscopy.append("t")
        elif "time" in src.dimensions:
            dimscopy.append("time")
        else:
            raise KeyError("Time dimension not found")
        if "latitude" in src.dimensions:
            dimscopy.append("latitude")
            tocopy.append("latitude")
        elif "lat" in src.dimensions:
            dimscopy.append("lat")
            tocopy.append("lat")
        if "longitude" in src.dimensions:
            dimscopy.append("longitude")
            tocopy.append("longitude")
        elif "lon" in src.dimensions:
            dimscopy.append("lon")
            tocopy.append("lon")

        dst = nc.Dataset(output_file, "w")
        dst.setncatts(src.__dict__)
        # copy dimensions
        for name, dimension in src.dimensions.items():
            if name in dimscopy:
                dst.createDimension(
                    name, (len(dimension) if not dimension.isunlimited() else None)
                )
        # copy all file data except for the excluded
        for name, variable in src.variables.items():
            if name in tocopy:
                x = dst.createVariable(
                    name, variable.datatype, variable.dimensions)
                dst[name][:] = src[name][:]
                # copy variable attributes all at once via dictionary
                dst[name].setncatts(src[name].__dict__)
        target_var_attribute_dict = (
            nc.Dataset(filename)
            .variables[
                "{}".format(
                    list(dataset_description["TARGET_VARIABLES"].values())[
                        0][0]
                )
            ]
            .__dict__
        )
        dst.createVariable(
            "{}".format(
                list(dataset_description["TARGET_VARIABLES"].values())[0][0]),
            original_dataype,
            necessary_dimensions,
        )
        dst.variables[
            "{}".format(
                list(dataset_description["TARGET_VARIABLES"].values())[0][0])
        ].setncatts(target_var_attribute_dict)
        try:
            src["t"]
            dst.createVariable("t", "float64", "t")
            dst["t"].setncatts(src["t"].__dict__)
            dst.variables["t"][:] = list(t_test)
        except IndexError:
            src["time"]
            dst.createVariable("time", "float64", "time")
            dst["time"].setncatts(src["time"].__dict__)
            dst.variables["time"][:] = list(t_test)

        # pad the numpy by the amount the we trimmed of when loading the data
        tmp = np.pad(
            np.squeeze(rescaled_predictions),
            (
                (0, 0),
                (
                    dataset_description["LATITUDES_SLICE"][0],
                    -dataset_description["LATITUDES_SLICE"][1],
                ),
                (0, 0),
            ),
            "constant",
            constant_values=target_var_attribute_dict["missing_value"],
        )
        dst.variables["d18O"][:] = tmp

        dst.close()
        src.close()

    elif dataset_description["GRID_TYPE"] == "Ico":
        assert dataset_description["TIMESCALE"] == "YEARLY"
        tocopy = ["lon", "lon_bnds", "lat", "lat_bnds"]
        dimscopy = ["bnds", "ncells", "vertices"]
        output_file_5_nbs = os.path.join(output_folder, "tmp_5_nbs.nc")
        output_file_6_nbs = os.path.join(output_folder, "tmp_6_nbs.nc")

        filename_5_nbs = os.path.join(
            "Datasets",
            dataset_description["CLIMATE_MODEL"],
            "Interpolated",
            "{}_yearly_r_{}_nbs_5_{}.nc".format(
                list(dataset_description["TARGET_VARIABLES"].keys())[0],
                dataset_description["RESOLUTION"],
                dataset_description["INTERPOLATION"],
            ),
        )
        filename_6_nbs = os.path.join(
            "Datasets",
            dataset_description["CLIMATE_MODEL"],
            "Interpolated",
            "{}_yearly_r_{}_nbs_6_{}.nc".format(
                list(dataset_description["TARGET_VARIABLES"].keys())[0],
                dataset_description["RESOLUTION"],
                dataset_description["INTERPOLATION"],
            ),
        )

        original_dimensions_5_nbs = (
            nc.Dataset(filename_5_nbs)
            .variables[
                "{}".format(
                    list(dataset_description["TARGET_VARIABLES"].values())[
                        0][0]
                )
            ]
            .dimensions
        )
        original_dimensions_6_nbs = (
            nc.Dataset(filename_6_nbs)
            .variables[
                "{}".format(
                    list(dataset_description["TARGET_VARIABLES"].values())[
                        0][0]
                )
            ]
            .dimensions
        )
        necessary_dimensions_5_nbs = (
            original_dimensions_5_nbs[0],
            original_dimensions_5_nbs[2],
        )
        necessary_dimensions_6_nbs = (
            original_dimensions_6_nbs[0],
            original_dimensions_6_nbs[2],
        )
        original_datatype_5_nbs = (
            nc.Dataset(filename_5_nbs)
            .variables[
                "{}".format(
                    list(dataset_description["TARGET_VARIABLES"].values())[
                        0][0]
                )
            ]
            .datatype
        )
        original_datatype_6_nbs = (
            nc.Dataset(filename_6_nbs)
            .variables[
                "{}".format(
                    list(dataset_description["TARGET_VARIABLES"].values())[
                        0][0]
                )
            ]
            .datatype
        )

        src_5_nbs = nc.Dataset(filename_5_nbs)
        src_6_nbs = nc.Dataset(filename_6_nbs)
        dst_5_nbs = nc.Dataset(output_file_5_nbs, "w")
        dst_6_nbs = nc.Dataset(output_file_6_nbs, "w")
        dst_5_nbs.setncatts(src_5_nbs.__dict__)
        dst_6_nbs.setncatts(src_6_nbs.__dict__)

        if "t" in src_6_nbs.dimensions:
            dimscopy.append("t")
        elif "time" in src_6_nbs.dimensions:
            dimscopy.append("time")
        else:
            raise KeyError("Time dimension not found")

        for name, dimension in src_5_nbs.dimensions.items():
            if name in dimscopy:
                dst_5_nbs.createDimension(
                    name, (len(dimension) if not dimension.isunlimited() else None)
                )
        for name, dimension in src_6_nbs.dimensions.items():
            if name in dimscopy:
                dst_6_nbs.createDimension(
                    name, (len(dimension) if not dimension.isunlimited() else None)
                )

        # copy all file data except for the excluded
        for name, variable in src_5_nbs.variables.items():
            if name in tocopy:
                x = dst_5_nbs.createVariable(
                    name, variable.datatype, variable.dimensions
                )
                dst_5_nbs[name][:] = src_5_nbs[name][:]
                # copy variable attributes all at once via dictionary
                dst_5_nbs[name].setncatts(src_5_nbs[name].__dict__)
        for name, variable in src_6_nbs.variables.items():
            if name in tocopy:
                x = dst_6_nbs.createVariable(
                    name, variable.datatype, variable.dimensions
                )
                dst_6_nbs[name][:] = src_6_nbs[name][:]
                # copy variable attributes all at once via dictionary
                dst_6_nbs[name].setncatts(src_6_nbs[name].__dict__)
        target_var_attribute_dict_6_nbs = (
            nc.Dataset(filename_6_nbs)
            .variables[
                "{}".format(
                    list(dataset_description["TARGET_VARIABLES"].values())[
                        0][0]
                )
            ]
            .__dict__
        )
        dst_6_nbs.createVariable(
            "{}".format(
                list(dataset_description["TARGET_VARIABLES"].values())[0][0]),
            original_datatype_6_nbs,
            necessary_dimensions_6_nbs,
        )
        dst_6_nbs.variables[
            "{}".format(
                list(dataset_description["TARGET_VARIABLES"].values())[0][0])
        ].setncatts(target_var_attribute_dict_6_nbs)
        dst_6_nbs.createVariable("t", "float64", "t")
        dst_6_nbs.createVariable("t_bnds", "float64", ("t", "bnds"))
        dst_6_nbs.variables["t"][:] = t_test

        target_var_attribute_dict_5_nbs = (
            nc.Dataset(filename_5_nbs)
            .variables[
                "{}".format(
                    list(dataset_description["TARGET_VARIABLES"].values())[
                        0][0]
                )
            ]
            .__dict__
        )
        dst_5_nbs.createVariable(
            "{}".format(
                list(dataset_description["TARGET_VARIABLES"].values())[0][0]),
            original_datatype_5_nbs,
            necessary_dimensions_5_nbs,
        )
        dst_5_nbs.variables[
            "{}".format(
                list(dataset_description["TARGET_VARIABLES"].values())[0][0])
        ].setncatts(target_var_attribute_dict_5_nbs)
        dst_5_nbs.createVariable("t", "float64", "t")
        dst_5_nbs.createVariable("t_bnds", "float64", ("t", "bnds"))
        dst_5_nbs.variables["t"][:] = t_test

        rescaled_predictions_5_nbs, rescaled_predictions_6_nbs = split_5_nbs_6_nbs(
            rescaled_predictions, dataset_description
        )

        dst_6_nbs.variables["d18O"][:] = rescaled_predictions_6_nbs
        dst_6_nbs.close()
        src_6_nbs.close()

        dst_5_nbs.variables["d18O"][:] = rescaled_predictions_5_nbs
        dst_5_nbs.close()
        src_5_nbs.close()
    else:
        raise NotImplementedError("Invalid grid type")


def split_5_nbs_6_nbs(rescaled_predictions, dataset_description):
    assert dataset_description["GRID_TYPE"] == "Ico"
    ico = Icosahedron(r=dataset_description["RESOLUTION"])
    regions, vertices = ico.get_voronoi_regions_vertices()
    charts = ico.get_charts_cut()
    indices_six_nb = []
    indices_five_nb = []
    for i in range(len(regions)):
        if len(regions[i]) > 5:
            indices_six_nb.append(i)
        else:
            indices_five_nb.append(i)
    # create numpy arrays
    indices_6_nbs = np.array(indices_six_nb)
    indices_5_nbs = np.array(indices_five_nb)
    rescaled_predictions_5_nbs = np.squeeze(
        rescaled_predictions.reshape(rescaled_predictions.shape[0], -1)[
            ..., indices_5_nbs
        ]
    )
    rescaled_predictions_6_nbs = np.squeeze(
        rescaled_predictions.reshape(rescaled_predictions.shape[0], -1)[
            ..., indices_6_nbs
        ]
    )
    return rescaled_predictions_5_nbs, rescaled_predictions_6_nbs


def run_script(descriptions, script_folder, interpolation_type="cons1", resolution=5):
    """
    @param descriptions: Descriptions of dataset and (model and training)
    @param script_folder: Should contain the two scripts: ico_to_model.sh and model_to_ico.sh as
    well as grid description files for the icosahedral grid and model grids.
    @param interpolation_type: The type of interpolation used.
    @param resolution: Resolution of the icosahedron.
    @return:
    """
    if descriptions["DATASET_DESCRIPTION"]["GRID_TYPE"] == "Flat":
        script = os.path.join(script_folder, "model_to_ico.sh")
        files = os.path.join(script_folder, "tmp.nc")
        i_arg = interpolation_type
        f_arg = files
        g_arg = "{}grid_description_r_{}_nbs_6_ico.txt {}grid_description_r_{}_nbs_5_ico.txt".format(
            script_folder, resolution, script_folder, resolution
        )
        call([script, "-f", f_arg, "-g", g_arg, "-i", i_arg])

    elif descriptions["DATASET_DESCRIPTION"]["GRID_TYPE"] == "Ico":
        assert (
            descriptions["DATASET_DESCRIPTION"]["CLIMATE_MODEL"] == "iHadCM3"
        ), "original grid description files missing for this models."
        files_5_nb = os.path.join(script_folder, "tmp_5_nbs.nc")
        files_6_nb = os.path.join(script_folder, "tmp_6_nbs.nc")
        script = os.path.join(script_folder, "ico_to_model.sh")
        o_arg = os.path.join(script_folder, "default_grid.txt")
        i_arg = interpolation_type

        g_arg = "{}grid_description_r_{}_nbs_6_ico.txt".format(
            script_folder, descriptions["DATASET_DESCRIPTION"]["RESOLUTION"]
        )
        call([script, "-f", files_6_nb, "-g", g_arg, "-o", o_arg, "-i", i_arg])

        g_arg = "{}grid_description_r_{}_nbs_5_ico.txt".format(
            script_folder, descriptions["DATASET_DESCRIPTION"]["RESOLUTION"]
        )
        call([script, "-f", files_5_nb, "-g", g_arg, "-o", o_arg, "-i", i_arg])

    else:
        raise NotImplementedError("Invalid grid type")


def get_interpolated_data_and_gt(
    descriptions,
    data,
    output_folder,
    script_folder="Scripts/",
    resolution=5,
    interpolation="cons1",
    do_scaling=True,
    latitude_slice=[1, -1],
    print_folder_names=False
):
    """
    @param descriptions: Descriptions of dataset and {model and training}
    @param data: Data to be interpolated
    @param output_folder: Directory to store the interpolated data in.
    @param script_folder: Should contain the two scripts: ico_to_model.sh and model_to_ico.sh as
    well as grid description files for the icosahedral grid and model grids.
    @param resolution: Resolution of the icosahedron that determines the resolution of the icosahedral grid we interpolate to
    @param interpolation: Type of interpolation used. Supported are cons1 and NN   
    @param latitude_slice: Ignore latitudes outside the given slice (important because iHadCM3 has no valid data there)
    @param print_folder_names: Print the foldernames when loading the interpolated data. Diagnostic tool.
    @return: Interpolated data and ground truth.
    """
    try:
        interpolate_predictions(copy.deepcopy(descriptions), data, output_folder=output_folder, script_folder=script_folder,
                                resolution=resolution, interpolation=interpolation, do_scaling=do_scaling)
    except FileExistsError:
        print("Interpolated file already exists, use existing version.")
    except OSError:
        print("OSError: Probably CDO is not installed. Test if we have exiting interpolated results.")

    descriptions_interpolated = copy.deepcopy(descriptions)
    if descriptions["DATASET_DESCRIPTION"]["GRID_TYPE"] == "Flat":
        descriptions_interpolated["DATASET_DESCRIPTION"]["GRID_TYPE"] = "Ico"
    else:
        descriptions_interpolated["DATASET_DESCRIPTION"]["GRID_TYPE"] = "Flat"
    descriptions_interpolated["DATASET_DESCRIPTION"]["RESULTS_INTERPOLATED"] = True

    # Load the interpolated predictions
    predictions_list, descriptions_list = load_compatible_available_runs(
        output_folder, descriptions_interpolated, print_folder_names=print_folder_names)

    if len(predictions_list) > 1 or len(predictions_list) == 0:
        raise RuntimeError("There should be exactly one stored version of the interpolated data, but {} were found".format(
            len(predictions_list)))

    # Get the corresponding ground truth
    ignore_vars = ["RESULTS_INTERPOLATED", "LATITUDES_SLICE", "LATITUDES", "RESULTS_RESCALED",
                   "LONGITUDES", "GRID_SHAPE", "RESOLUTION", "INTERPOLATE_CORNERS", "INTERPOLATION"]
    d_reduced = descriptions_list[0]["DATASET_DESCRIPTION"]
    for l in ignore_vars:
        d_reduced.pop(l, None)
    ds = find_and_load_dataset(
        descriptions_list[0]["MODEL_TRAINING_DESCRIPTION"]["DATASET_FOLDER"], d_reduced)

    if descriptions["DATASET_DESCRIPTION"]["GRID_TYPE"] == "Ico":
        print("When interpolating to model grid, currently the iHadCM3 specifics are used.")
        return predictions_list[0][..., latitude_slice[0]:latitude_slice[1], :], ds["test"]["targets"].reshape(predictions_list[0][..., latitude_slice[0]:latitude_slice[1], :].shape)
    else:
        return predictions_list[0], ds["test"]["targets"].reshape(predictions_list[0].shape)


def interpolate_climate_model_data_to_ico_grid(
    model_name,
    variable_name,
    script_folder="Scripts/",
    dataset_folder="Datasets/",
    resolution=5,
    interpolation="cons1",
):
    """
    Interpolate raw data from one grid to another. This is only implemented for yearly files.
    @param dataset_folder: File in which the climate model datasets are stored
    @param script_folder: File in which the scripts are stored
    @param model_name: Name of the climate model whose data we want to interpolate
    @param variable_name: Name of the variable (and dataset) that we want to interpolate
    @param resolution: Resolution level of the used icosahedron
    @param interpolation: Type of interpolation used by CDO, inplemented are cons1 and NN
    @return:
    """
    path = os.path.join(
        dataset_folder, model_name, "Original", "{}_yearly.nc".format(
            variable_name)
    )

    tmp_path_5_nbs = os.path.join(
        dataset_folder,
        model_name,
        "Original",
        "{}_yearly_r_{}_nbs_5_{}.nc".format(
            variable_name, resolution, interpolation),
    )
    tmp_path_6_nbs = os.path.join(
        dataset_folder,
        model_name,
        "Original",
        "{}_yearly_r_{}_nbs_6_{}.nc".format(
            variable_name, resolution, interpolation),
    )

    new_path_5_nbs = os.path.join(
        dataset_folder,
        model_name,
        "Interpolated",
        "{}_yearly_r_{}_nbs_5_{}.nc".format(
            variable_name, resolution, interpolation),
    )
    new_path_6_nbs = os.path.join(
        dataset_folder,
        model_name,
        "Interpolated",
        "{}_yearly_r_{}_nbs_6_{}.nc".format(
            variable_name, resolution, interpolation),
    )

    script = os.path.join(script_folder, "model_to_ico.sh")
    files = path
    i_arg = interpolation
    f_arg = files
    g_arg = "{}grid_description_r_{}_nbs_6_ico.txt {}grid_description_r_{}_nbs_5_ico.txt".format(
        script_folder, resolution, script_folder, resolution
    )
    call([script, "-f", f_arg, "-g", g_arg, "-i", i_arg])

    os.rename(tmp_path_5_nbs, new_path_5_nbs)
    os.rename(tmp_path_6_nbs, new_path_6_nbs)

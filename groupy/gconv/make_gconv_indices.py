
# Code for generating indices used in G-convolutions for various groups G.
# The indices created by these functions are used to rotate and flip filters on the plane or on a group.
# These indices depend only on the filter size, so they are created only once at the beginning of training.

import numpy as np

from groupy.garray.C4_array import C4
from groupy.garray.D4_array import D4
from groupy.garray.p4_array import C4_halfshift
from groupy.gfunc.z2func_array import Z2FuncArray
from groupy.gfunc.p4func_array import P4FuncArray
from groupy.gfunc.p4mfunc_array import P4MFuncArray

import numpy as np

from groupy.garray.C4_array import C4
from groupy.garray.D4_array import D4
from groupy.garray.p4_array import C4_halfshift
from groupy.gfunc.z2func_array import Z2FuncArray
from groupy.gfunc.p4func_array import P4FuncArray
from groupy.gfunc.p4mfunc_array import P4MFuncArray


def make_c4_z2_indices(ksize):
    x = np.random.randn(1, ksize, ksize)
    f = Z2FuncArray(v=x)

    if ksize % 2 == 0:
        uv = f.left_translation_indices(C4_halfshift[:, None, None, None])
    else:
        uv = f.left_translation_indices(C4[:, None, None, None])
    r = np.zeros(uv.shape[:-1] + (1,))
    ruv = np.c_[r, uv]
    return ruv.astype('int32')


def make_c4_p4_indices(ksize):
    x = np.random.randn(4, ksize, ksize)
    f = P4FuncArray(v=x)

    if ksize % 2 == 0:
        li = f.left_translation_indices(C4_halfshift[:, None, None, None])
    else:
        li = f.left_translation_indices(C4[:, None, None, None])
    return li.astype('int32')


def make_d4_z2_indices(ksize):
    assert ksize % 2 == 1  # TODO
    x = np.random.randn(1, ksize, ksize)
    f = Z2FuncArray(v=x)
    uv = f.left_translation_indices(D4.flatten()[:, None, None, None])
    mr = np.zeros(uv.shape[:-1] + (1,))
    mruv = np.c_[mr, uv]
    return mruv.astype('int32')


def make_d4_p4m_indices(ksize):
    assert ksize % 2 == 1  # TODO
    x = np.random.randn(8, ksize, ksize)
    f = P4MFuncArray(v=x)
    li = f.left_translation_indices(D4.flatten()[:, None, None, None])
    return li.astype('int32')


def make_c6_p6_indices(ksize):
    assert ksize % 2 == 1  # TODO

    from groupy.gfunc.p6_axial_func_array import P6FuncArray
    import groupy.garray.p6_array as p6a
    import groupy.garray.C6_array as c6a

    x = np.random.randn(6, ksize, ksize)

    f = P6FuncArray(v=x)

    li = f.left_translation_indices(c6a.C6.flatten()[:, None, None, None])
    # Set invalid indices to the weight which is known to be zero.
    li[np.min(li[..., -2:], axis=-1) < 0, :] = np.zeros(li.shape[-1])
    li[np.max(li[..., -2:], axis=-1) >= ksize, :] = np.zeros(li.shape[-1])

    return li.astype('int32')


def make_d6_p6m_indices(ksize):
    assert ksize % 2 == 1  # TODO

    from groupy.gfunc.p6m_axial_func_array import P6MFuncArray
    import groupy.garray.p6m_array as p6ma
    import groupy.garray.D6_array as d6a

    x = np.random.randn(12, ksize, ksize)

    f = P6MFuncArray(v=x)

    li = f.left_translation_indices(d6a.D6.flatten()[:, None, None, None])

    # Set invalid indices to the weight which is known to be zero.
    li[np.min(li[..., -2:], axis=-1) < 0, :] = np.zeros(li.shape[-1])
    li[np.max(li[..., -2:], axis=-1) >= ksize, :] = np.zeros(li.shape[-1])

    return li.astype('int32')


def make_c6_z2_indices(ksize):
    import groupy.garray.p6_array as p6a
    import groupy.garray.C6_array as c6a

    assert ksize % 2 == 1, "Only uneven filters are supported"

    x = np.random.randn(1, ksize, ksize)
    f = Z2FuncArray(v=x)

    uv = f.left_translation_indices(c6a.C6.flatten()[:, None, None, None])

    r = np.zeros(uv.shape[:-1] + (1,))
    ruv = np.c_[r, uv]

    # When rotating upon change of basis some of the points that are NOT on initial hex (u,v) = (1,1) or (-1,-1)
    # may get transformed to values with abs()>1. This is not important though, because we will mask them out anyway.
    # Set invalid indices to the weight which is known to be zero.
    ruv[np.min(ruv[..., -2:], axis=-1) < 0, :] = np.zeros(ruv.shape[-1])
    ruv[np.max(ruv[..., -2:], axis=-1) >= ksize, :] = np.zeros(ruv.shape[-1])

    return ruv.astype('int32')


def make_d6_z2_indices(ksize):
    assert ksize % 2 == 1, "Only uneven filters are supported"

    import groupy.garray.p6m_array as p6ma
    import groupy.garray.D6_array as d6a
    x = np.random.randn(1, ksize, ksize)

    f = Z2FuncArray(v=x)
    uv = f.left_translation_indices(d6a.D6.flatten()[:, None, None, None])

    mr = np.zeros(uv.shape[:-1] + (1,))
    mruv = np.c_[mr, uv]

    # Set invalid indices to the weight which is known to be zero.
    mruv[np.min(mruv[..., -2:], axis=-1) < 0, :] = np.zeros(mruv.shape[-1])
    mruv[np.max(mruv[..., -2:], axis=-1) >= ksize, :] = np.zeros(mruv.shape[-1])

    return mruv.astype('int32')


def flatten_indices(inds):
    """
    The Chainer implementation of G-Conv uses indices into a 5D filter tensor (with an additional axis for the
    transformations H. For the tensorflow implementation it was more convenient to flatten the filter tensor into
    a 3D tensor with shape (output channels, input channels, transformations * width * height).

    This function takes indices in the format required for Chainer and turns them into indices into the flat array
    used by tensorflow.

    :param inds: np.ndarray of shape (output transformations, input transformations, n, n, 3), as output by
    the functions like make_d4_p4m_indices(n).
    :return: np.ndarray of shape (output transformations, input transformations, n, n)
    """
    n = inds.shape[-2]
    nti = inds.shape[1]
    T = inds[..., 0]  # shape (nto, nti, n, n)
    U = inds[..., 1]  # shape (nto, nti, n, n)
    V = inds[..., 2]  # shape (nto, nti, n, n)
    # inds_flat = T * n * n + U * n + V
    inds_flat = U * n * nti + V * nti + T
    return inds_flat
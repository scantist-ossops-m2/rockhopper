# -*- coding: utf-8 -*-
"""
"""

import numpy as np
from cslug import CSlug, ptr, anchor, Header

endians_header = Header(*anchor("src/endians.h", "src/endians.c"),
                        includes=["<stdbool.h>", '"_endian_typedefs.h"'])
slug = CSlug(anchor(
    "_slugs/ragged_array",
    "src/ragged_array.c",
    "src/ragged_array.h",
    "src/endians.c",
), headers=endians_header)  # yapf: disable


class RaggedArray(object):
    """A 2D array with rows of mixed lengths.

    A ragged array consists of three 1D arrays.

    *   :attr:`flat` contains the flattened contents. i.e. each row joined end
        end without any delimiters or information describing the shape.
    *   :attr:`starts` and :attr:`ends` determine the shape. Each integer value
        in these arrays is the start and stop of a :class:`slice` of
        :attr:`flat`. Each slice is a :class:`RaggedArray` row.

    A :class:`RaggedArray` is considered *packed* if the end of each row
    is the same as the start of the next row.

    """
    flat: np.ndarray
    starts: np.ndarray
    ends: np.ndarray

    def __init__(self, flat, starts, ends=None, dtype=None):
        """The default way to construct a :class:`RaggedArray` is explicitly
        from a :attr:`flat` contents array and either row :attr:`starts` and
        :attr:`ends` arrays or, more commonly, a *bounds* array.

        Args:
            flat:
                The contents of the array with no structure.
            starts:
                The index of **flat** where each row starts.
                Or if **ends** is unspecified, the start of each row and the
                end of the previous row.
            ends:
                The index of **flat** where each row ends.

        """
        self.flat = np.asarray(flat, dtype=dtype, order="C")
        if ends is None:
            bounds = np.asarray(starts, dtype=np.intc, order="C")
            self.starts = bounds[:-1]
            self.ends = bounds[1:]
        else:
            self.starts = np.asarray(starts, dtype=np.intc, order="C")
            self.ends = np.asarray(ends, dtype=np.intc, order="C")

        self._c_struct = slug.dll.RaggedArray(
            ptr(self.flat),
            self.flat.dtype.itemsize,
            len(self),
            ptr(self.starts),
            ptr(self.ends),
        )

    @property
    def dtype(self):
        """The data type of the contents of this array.

        Returns:
            numpy.dtype: :py:`self.flat.dtype`.

        """
        return self.flat.dtype

    def astype(self, dtype):
        """Cast the contents to a given **dtype**. Analogous to
        :meth:`numpy.ndarray.astype`.

        Args:
            dtype (numpy.dtype):
                Desired data type for the :attr:`flat` attribute.

        Returns:
            RaggedArray: A modified copy with :py:`copy.flat.dtype == dtype`.

        Only the :attr:`flat` property is cast - :attr:`starts` and :attr:`ends`
        remain unchanged.

        The :attr:`flat` attribute is a copy if :meth:`numpy.ndarray.astype`
        chooses to copy it. The :attr:`starts` and :attr:`ends` are never
        copied.

            >>> ragged = RaggedArray.from_nested([[1, 2], [3]], dtype=np.int32)
            >>> ragged.astype(np.int32).flat is ragged.flat
            False
            >>> ragged.astype(np.int16).starts is ragged.starts
            True

        """
        return type(self)(self.flat.astype(dtype), self.starts, self.ends)

    @classmethod
    def from_lengths(cls, flat, lengths, dtype=None):
        bounds = np.empty(len(lengths) + 1, dtype=np.intc)
        bounds[0] = 0
        np.cumsum(lengths, out=bounds[1:])
        return cls(flat, bounds, dtype=dtype)

    @classmethod
    def from_nested(cls, nested, dtype=None):
        flat = np.concatenate(nested)
        lengths = [len(i) for i in nested]
        return cls.from_lengths(flat, lengths, dtype=dtype)

    def __getitem__(self, item):
        if np.isscalar(item):
            return self.flat[self.starts[item]:self.ends[item]]
        return type(self)(self.flat, self.starts[item], self.ends[item])

    def __len__(self):
        return len(self.starts)

    def __iter__(self):
        return (self[i] for i in range(len(self)))

    def repacked(self):
        length = (self.ends - self.starts).sum()
        flat = np.empty((length,) + self.flat.shape[1:], self.flat.dtype)
        bounds = np.empty(len(self.starts) + 1, np.intc)
        new = type(self)(flat, bounds[:-1], bounds[1:])
        slug.dll.repack(self._c_struct._ptr, new._c_struct._ptr)
        return new

def _2_power(x):
    from numbers import Integral
    if isinstance(x, Integral):
        return x
    itemsize = np.dtype(x).itemsize
    return next(i for i in range(8) if (1 << i) == itemsize)  # pragma: no branch

# -*- coding: utf-8 -*-

"""Implementation of the IAU 1980 Earth orientation model
"""

from pathlib import Path

import numpy as np

from ..utils.matrix import rot1, rot2, rot3
from ..utils.memoize import memoize
from ..dates.eop import get_eop

@memoize
def _tab(max_i=None):
    """Extraction and caching of IAU1980 nutation coefficients
    """

    filepath = Path(__file__).parent / "data" / "tab5.1.txt"

    result = []
    with filepath.open() as fhd:
        i = 0
        for line in fhd.read().splitlines():
            if line.startswith("#") or not line.strip():
                continue

            fields = line.split()
            result.append(([int(x) for x in fields[:5]], [float(x) for x in fields[6:]]))

            i += 1
            if max_i and i >= max_i:
                break

    return result


def rate(date):
    """Return the rotation rate vector of the earth for a given date
    """
    lod = get_eop(date.mjd).lod / 1000.
    return np.array([0, 0, 7.292115146706979e-5 * (1 - lod / 86400.)])


def _earth_orientation(date):
    """Earth Orientation Parameters in degrees
    """
    eop = get_eop(date.mjd)
    return eop.x / 3600., eop.y / 3600.


def earth_orientation(date):  # pragma: no cover
    """Earth Orientation as a rotation matrix
    """
    x_p, y_p = np.deg2rad(_earth_orientation(date))
    return rot1(y_p) @ rot2(x_p)


def _precesion(date):
    """Precesion in degrees
    """

    t = date.change_scale('TT').julian_century

    zeta = (2306.2181 * t + 0.30188 * t ** 2 + 0.017998 * t ** 3) / 3600.
    theta = (2004.3109 * t - 0.42665 * t ** 2 - 0.041833 * t ** 3) / 3600.
    z = (2306.2181 * t + 1.09468 * t ** 2 + 0.018203 * t ** 3) / 3600.

    # print("zeta = {}\ntheta = {}\nz = {}\n".format(zeta, theta, z))
    return zeta, theta, z


def precesion(date):  # pragma: no cover
    """Precesion as a rotation matrix
    """
    zeta, theta, z = np.deg2rad(_precesion(date))
    return rot3(zeta) @ rot2(-theta) @ rot3(z)


@memoize
def _nutation(date, eop_correction=True, terms=106):
    """Model 1980 of nutation as described in Vallado p. 224

    Args:
        date (beyond.utils.date.Date)
        eop_correction (bool): set to ``True`` to include model correction
            from 'finals' files.
        terms (int)
    Return:
        tuple : 3-elements, all floats in degrees
            1. ̄ε
            2. Δψ
            3. Δε

    Warning:
        The good version of the nutation model can be found in the **errata**
        of the 4th edition of *Fundamentals of Astrodynamics and Applications*
        by Vallado.
    """

    ttt = date.change_scale('TT').julian_century

    r = 360.

    # in arcsecond
    epsilon_bar = 84381.448 - 46.8150 * ttt - 5.9e-4 * ttt ** 2\
        + 1.813e-3 * ttt ** 3

    # Conversion to degrees
    epsilon_bar /= 3600.

    # mean anomaly of the moon
    m_m = 134.96298139 + (1325 * r + 198.8673981) * ttt\
        + 0.0086972 * ttt ** 2 + 1.78e-5 * ttt ** 3

    # mean anomaly of the sun
    m_s = 357.52772333 + (99 * r + 359.0503400) * ttt\
        - 0.0001603 * ttt ** 2 - 3.3e-6 * ttt ** 3

    # L - Omega
    u_m_m = 93.27191028 + (1342 * r + 82.0175381) * ttt\
        - 0.0036825 * ttt ** 2 + 3.1e-6 * ttt ** 3

    # Mean elongation of the moon from the sun
    d_s = 297.85036306 + (1236 * r + 307.11148) * ttt\
        - 0.0019142 * ttt ** 2 + 5.3e-6 * ttt ** 3

    # Mean longitude of the ascending node of the moon
    om_m = 125.04452222 - (5 * r + 134.1362608) * ttt\
        + 0.0020708 * ttt ** 2 + 2.2e-6 * ttt ** 3

    delta_psi = 0.
    delta_eps = 0.
    for integers, reals in _tab(terms):
        a1, a2, a3, a4, a5 = integers
        # Conversion from 0.1 mas to mas
        A, B, C, D = np.array(list(reals)) / 36000000.
        a_p = a1 * m_m + a2 * m_s + a3 * u_m_m + a4 * d_s + a5 * om_m
        # a_p %= 360.
        delta_psi += (A + B * ttt) * np.sin(np.deg2rad(a_p))
        delta_eps += (C + D * ttt) * np.cos(np.deg2rad(a_p))

    if eop_correction:
        eop = get_eop(date.mjd)
        delta_eps += eop.deps / 3600000.
        delta_psi += eop.dpsi / 3600000.

    return epsilon_bar, delta_psi, delta_eps


def nutation(date, eop_correction=True, terms=106):  # pragma: no cover
    """Nutation as a rotation matrix
    """
    epsilon_bar, delta_psi, delta_eps = np.deg2rad(_nutation(date, eop_correction, terms))
    epsilon = epsilon_bar + delta_eps

    return rot1(-epsilon_bar) @ rot3(delta_psi) @ rot1(epsilon)


def equinox(date, eop_correction=True, terms=106, kinematic=True):
    """Equinox equation in degrees
    """
    epsilon_bar, delta_psi, delta_eps = _nutation(date, eop_correction, terms)

    equin = delta_psi * 3600. * np.cos(np.deg2rad(epsilon_bar))

    if date.d >= 50506 and kinematic:
        # Starting 1992-02-27, we apply the effect of the moon
        ttt = date.change_scale('TT').julian_century
        om_m = 125.04455501 - (5 * 360. + 134.1361851) * ttt\
            + 0.0020756 * ttt ** 2 + 2.139e-6 * ttt ** 3

        equin += 0.00264 * np.sin(np.deg2rad(om_m)) + 6.3e-5 * np.sin(np.deg2rad(2 * om_m))

    # print("esquinox = {}\n".format(equin / 3600))
    return equin / 3600.


def _sideral(date, longitude=0., model='mean', eop_correction=True, terms=106):
    """Get the sideral time at a defined date

    Args:
        date (Date):
        longitude (float): Longitude of the observer (in degrees)
            East positive/West negative.
        model (str): 'mean' or 'apparent' for GMST and GAST respectively
    Return:
        float: Sideral time in degrees

    GMST: Greenwich Mean Sideral Time
    LST: Local Sideral Time (Mean)
    GAST: Greenwich Apparent Sideral Time
    """

    t = date.change_scale('UT1').julian_century

    # Compute GMST in seconds
    theta = 67310.54841 + (876600 * 3600 + 8640184.812866) * t + 0.093104 * t ** 2\
        - 6.2e-6 * t ** 3

    # Conversion from second (time) to degrees (angle)
    theta /= 240.

    if model == 'apparent':
        theta += equinox(date, eop_correction, terms)

    # Add local longitude to the sideral time
    theta += longitude
    # Force to 0-360 degrees range
    theta %= 360.

    return theta


def sideral(date, longitude=0., model='mean', eop_correction=True, terms=106):  # pragma: no cover
    """Sideral time as a rotation matrix
    """
    theta = _sideral(date, longitude, model, eop_correction, terms)
    return rot3(np.deg2rad(-theta))
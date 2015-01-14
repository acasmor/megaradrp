#
# Copyright 2011-2014 Universidad Complutense de Madrid
#
# This file is part of Megara DRP
#
# Megara DRP is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Megara DRP is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Megara DRP.  If not, see <http://www.gnu.org/licenses/>.
#

'''Calibration Recipes for Megara'''

import logging

import numpy

from scipy.interpolate import interp1d

from astropy.io import fits
from astropy import wcs

from numina.core import BaseRecipe, RecipeRequirements
from numina.core import Product, DataProductRequirement, Requirement
from numina.core import define_requirements, define_result
from numina.core.products import ArrayType
from numina.core.requirements import ObservationResultRequirement
from numina.core import RecipeError
from numina.array.combine import median as c_median
from numina.flow import SerialFlow
from numina.flow.processing import BiasCorrector

from megaradrp.core import OverscanCorrector, TrimImage
from megaradrp.core import ApertureExtractor, FiberFlatCorrector
from megaradrp.core import peakdet
# from numina.logger import log_to_history

from megaradrp.core import RecipeResult
from megaradrp.products import MasterBias, MasterDark, MasterFiberFlat
from megaradrp.products import TraceMapType, MasterSensitivity

from .flat import FiberFlatRecipe, TraceMapRecipe, TwiligthFiberFlatRecipe


_logger = logging.getLogger('numina.recipes.megara')


class BiasRecipeRequirements(RecipeRequirements):
    obresult = ObservationResultRequirement()


class BiasRecipeResult(RecipeResult):
    biasframe = Product(MasterBias)


@define_requirements(BiasRecipeRequirements)
@define_result(BiasRecipeResult)
class BiasRecipe(BaseRecipe):

    '''Process BIAS images and create MASTER_BIAS.'''

    def __init__(self):
        super(BiasRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    def run(self, rinput):
        return self.process(rinput.obresult)

    def process(self, obresult):
        _logger.info('starting bias reduction')

        if not obresult.frames:
            raise RecipeError('Frame list is empty')

        cdata = []

        o_c = OverscanCorrector()
        t_i = TrimImage()

        basicflow = SerialFlow([o_c, t_i])

        try:
            for frame in obresult.frames:
                hdulist = frame.open()
                hdulist = basicflow(hdulist)
                cdata.append(hdulist)

            _logger.info('stacking %d images using median', len(cdata))

            data = c_median([d[0].data for d in cdata], dtype='float32')
            template_header = cdata[0][0].header
            hdu = fits.PrimaryHDU(data[0], header=template_header)
        finally:
            for hdulist in cdata:
                hdulist.close()

        hdr = hdu.header
        hdr = self.set_base_headers(hdr)
        hdr['IMGTYP'] = ('BIAS', 'Image type')
        hdr['NUMTYP'] = ('MASTER_BIAS', 'Data product type')
        hdr['CCDMEAN'] = data[0].mean()

        varhdu = fits.ImageHDU(data[1], name='VARIANCE')
        num = fits.ImageHDU(data[2], name='MAP')
        hdulist = fits.HDUList([hdu, varhdu, num])
        _logger.info('bias reduction ended')

        result = self.create_result(biasframe=hdu)
        return result


class DarkRecipeRequirements(BiasRecipeRequirements):
    master_bias = DataProductRequirement(MasterBias, 'Master bias calibration')


class DarkRecipeResult(RecipeResult):
    darkframe = Product(MasterDark)


@define_requirements(DarkRecipeRequirements)
@define_result(DarkRecipeResult)
class DarkRecipe(BaseRecipe):

    '''Process DARK images and provide MASTER_DARK. '''

    def __init__(self):
        super(DarkRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    # FIXME find a better way of doing this automatically
    # @log_to_history(_logger)
    def run(self, rinput):

        _logger.info('starting dark reduction')

        _logger.info('dark reduction ended')

        result = self.create_result(darkframe=None)
        return result




class PseudoFluxCalibrationRecipeRequirements(RecipeRequirements):
    obresult = ObservationResultRequirement()
    master_bias = DataProductRequirement(MasterBias, 'Master bias calibration')
    master_fiber_flat = DataProductRequirement(
        MasterFiberFlat, 'Master fiber flat calibration')
    traces = Requirement(TraceMapType, 'Trace information of the Apertures')
    reference_spectrum = DataProductRequirement(
        MasterFiberFlat, 'Reference spectrum')


class PseudoFluxCalibrationRecipeResult(RecipeResult):
    calibration = Product(MasterSensitivity)
    calibration_rss = Product(MasterSensitivity)


@define_requirements(PseudoFluxCalibrationRecipeRequirements)
@define_result(PseudoFluxCalibrationRecipeResult)
class PseudoFluxCalibrationRecipe(BaseRecipe):

    def __init__(self):
        super(PseudoFluxCalibrationRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    def run(self, rinput):
        _logger.info('starting pseudo flux calibration')

        o_c = OverscanCorrector()
        t_i = TrimImage()

        with rinput.master_bias.open() as hdul:
            mbias = hdul[0].data.copy()
            b_c = BiasCorrector(mbias)

        a_e = ApertureExtractor(rinput.traces)

        with rinput.master_fiber_flat.open() as hdul:
            f_f_c = FiberFlatCorrector(hdul)

        basicflow = SerialFlow([o_c, t_i, b_c, a_e, f_f_c])

        t_data = []

        try:
            for frame in rinput.obresult.frames:
                hdulist = frame.open()
                hdulist = basicflow(hdulist)
                t_data.append(hdulist)

            data_t = c_median([d[0].data for d in t_data], dtype='float32')
            template_header = t_data[0][0].header
            hdu_t = fits.PrimaryHDU(data_t[0], header=template_header)
        finally:
            for hdulist in t_data:
                hdulist.close()

        hdr = hdu_t.header
        hdr = self.set_base_headers(hdr)
        hdr['CCDMEAN'] = data_t[0].mean()
        hdr['NUMTYP'] = ('SCIENCE_TARGET', 'Data product type')

        # FIXME: hardcoded calibration
        # Polynomial that translates pixels to wl
        _logger.warning('using hardcoded LR-U spectral calibration')
        wlcal = [7.12175997e-10, -9.36387541e-06,
                 2.13624855e-01, 3.64665269e+03]
        plin = numpy.poly1d(wlcal)
        wl_n_r = plin(range(1, hdu_t.data.shape[1] + 1))  # Non-regular WL

        _logger.info('resampling reference spectrum')

        wlr = [3673.12731884058, 4417.497427536232]
        size = hdu_t.data.shape[1]
        delt = (wlr[1] - wlr[0]) / (size - 1)

        def add_wcs(hdr):
            hdr['CRPIX1'] = 1
            hdr['CRVAL1'] = wlr[0]
            hdr['CDELT1'] = delt
            hdr['CTYPE1'] = 'WAVELENGTH'
            hdr['CRPIX2'] = 1
            hdr['CRVAL2'] = 1
            hdr['CDELT2'] = 1
            hdr['CTYPE2'] = 'PIXEL'
            return hdr

        with rinput.reference_spectrum.open() as hdul:
            # Needs resampling
            data = hdul[0].data
            w_ref = wcs.WCS(hdul[0].header)
            # FIXME: Hardcoded values
            # because we do not have WL calibration
            pix = range(1, len(data) + 1)
            wl = w_ref.wcs_pix2world(pix, 1)
            # The 0 mean 0-based
            si = interp1d(wl, data)
            # Reference spectrum evaluated in the irregular WL grid
            final = si(wl_n_r)

        sens_data = final / hdu_t.data
        hdu_sens = fits.PrimaryHDU(sens_data, header=hdu_t.header)

        # Very simple wl calibration
        # add_wcs(hdu_sens.header)

        # add_wcs(hdu_t.header)

        _logger.info('pseudo flux calibration reduction ended')

        result = PseudoFluxCalibrationRecipeResult(
            calibration=hdu_sens, calibration_rss=hdu_t)
        return result


class ArcRecipeRequirements(RecipeRequirements):
    master_bias = DataProductRequirement(MasterBias, 'Master bias calibration')
    obresult = ObservationResultRequirement()


class ArcRecipeResult(RecipeResult):
    fiberflat_frame = Product(MasterFiberFlat)
    fiberflat_rss = Product(MasterFiberFlat)
    traces = Product(ArrayType)


@define_requirements(ArcRecipeRequirements)
@define_result(ArcRecipeResult)
class ArcRecipe(BaseRecipe):

    def __init__(self):
        super(ArcRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    def run(self, rinput):
        pass


class LCB_IFU_StdStarRecipeRequirements(RecipeRequirements):
    master_bias = DataProductRequirement(MasterBias, 'Master bias calibration')
    obresult = ObservationResultRequirement()


class LCB_IFU_StdStarRecipeResult(RecipeResult):
    fiberflat_frame = Product(MasterFiberFlat)
    fiberflat_rss = Product(MasterFiberFlat)
    traces = Product(ArrayType)


@define_requirements(LCB_IFU_StdStarRecipeRequirements)
@define_result(LCB_IFU_StdStarRecipeResult)
class LCB_IFU_StdStarRecipe(BaseRecipe):

    def __init__(self):
        super(LCB_IFU_StdStarRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    def run(self, rinput):
        pass


class FiberMOS_StdStarRecipeRequirements(RecipeRequirements):
    master_bias = DataProductRequirement(MasterBias, 'Master bias calibration')
    obresult = ObservationResultRequirement()


class FiberMOS_StdStarRecipeResult(RecipeResult):
    fiberflat_frame = Product(MasterFiberFlat)
    fiberflat_rss = Product(MasterFiberFlat)
    traces = Product(ArrayType)


@define_requirements(FiberMOS_StdStarRecipeRequirements)
@define_result(FiberMOS_StdStarRecipeResult)
class FiberMOS_StdStarRecipe(BaseRecipe):

    def __init__(self):
        super(FiberMOS_StdStarRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    def run(self, rinput):
        pass


class SensitivityFromStdStarRecipeRequirements(RecipeRequirements):
    master_bias = DataProductRequirement(MasterBias, 'Master bias calibration')
    obresult = ObservationResultRequirement()


class SensitivityFromStdStarRecipeResult(RecipeResult):
    fiberflat_frame = Product(MasterFiberFlat)
    fiberflat_rss = Product(MasterFiberFlat)
    traces = Product(ArrayType)


@define_requirements(SensitivityFromStdStarRecipeRequirements)
@define_result(SensitivityFromStdStarRecipeResult)
class SensitivityFromStdStarRecipe(BaseRecipe):

    def __init__(self):
        super(SensitivityFromStdStarRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    def run(self, rinput):
        pass


class S_And_E_FromStdStarsRecipeRequirements(RecipeRequirements):
    master_bias = DataProductRequirement(MasterBias, 'Master bias calibration')
    obresult = ObservationResultRequirement()


class S_And_E_FromStdStarsRecipeResult(RecipeResult):
    fiberflat_frame = Product(MasterFiberFlat)
    fiberflat_rss = Product(MasterFiberFlat)
    traces = Product(ArrayType)


@define_requirements(S_And_E_FromStdStarsRecipeRequirements)
@define_result(S_And_E_FromStdStarsRecipeResult)
class S_And_E_FromStdStarsRecipe(BaseRecipe):

    def __init__(self):
        super(SensitivityFromStdStarRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    def run(self, rinput):
        pass


class BadPixelsMaskRecipeRequirements(RecipeRequirements):
    obresult = ObservationResultRequirement()


class BadPixelsMaskRecipeResult(RecipeResult):
    biasframe = Product(MasterBias)


@define_requirements(BadPixelsMaskRecipeRequirements)
@define_result(BadPixelsMaskRecipeResult)
class BadPixelsMaskRecipe(BaseRecipe):

    '''Process BIAS images and create MASTER_BIAS.'''

    def __init__(self):
        super(BadPixelsMaskRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    def run(self, rinput):
        pass


class LinearityTestRecipeRequirements(RecipeRequirements):
    obresult = ObservationResultRequirement()


class LinearityTestRecipeResult(RecipeResult):
    biasframe = Product(MasterBias)


@define_requirements(LinearityTestRecipeRequirements)
@define_result(LinearityTestRecipeResult)
class LinearityTestRecipe(BaseRecipe):

    '''Process BIAS images and create MASTER_BIAS.'''

    def __init__(self):
        super(LinearityTestRecipe, self).__init__(
            author="Sergio Pascual <sergiopr@fis.ucm.es>",
            version="0.1.0"
        )

    def run(self, rinput):
        pass
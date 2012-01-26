#
# Copyright 2011-2012 Universidad Complutense de Madrid
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

__all__ = ['find_recipe']

# equivalence
_equiv = {'bias': 'calibration:BiasRecipe',
          'dark': 'calibration:DarkRecipe',
        'mosaic': 'recipe2:Recipe'}

def find_recipe(mode):
    return _equiv[mode]

class MegaraPipeline(object):

    def find_recipe(self, mode):
        return _equiv[mode]

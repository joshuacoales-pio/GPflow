# Copyright 2016 alexggmatthews, James Hensman
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# flake8: noqa


import tensorflow as tf

tf.enable_eager_execution()

from ._version import __version__
from ._settings import SETTINGS as settings


from . import kernels

# from . import misc
# from . import conditionals
# from . import logdensities
# from . import likelihoods
# from . import models
# from . import test_util
# from . import training as train
# from . import features
# from . import expectations
# from . import probability_distributions
# from . import multioutput

from .base import Parameter
from .base import positive, triangular

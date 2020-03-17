# ---
# jupyter:
#   jupytext:
#     formats: ipynb,.pct.py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.3.3
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Natural gradients
#
# This notebook shows some basic usage of the natural gradient optimizer, both on its own and in combination with Adam optimizer.

# %%
import warnings
import numpy as np
import gpflow
import tensorflow as tf

from gpflow.ci_utils import ci_niter, ci_range
from gpflow.models import VGP, GPR, SGPR, SVGP
from gpflow.optimizers import NaturalGradient
from gpflow.optimizers.natgrad import XiSqrtMeanVar

# %matplotlib inline
# %precision 4

np.random.seed(0)
tf.random.set_seed(0)

N, D = 100, 2
batch_size = 50

# inducing points
M = 10

x = np.random.uniform(size=(N, D))
y = np.sin(10 * x)

data = (x, y)
inducing_variable = tf.random.uniform((M, D))
adam_learning_rate = 0.01
iterations = ci_niter(5)

# %% [markdown]
# ### VGP is a GPR

# %% [markdown]
# The following section demonstrates how natural gradients can turn VGP into GPR *in a single step, if the likelihood is Gaussian*.

# %% [markdown]
# Let's start by first creating a standard GPR model with Gaussian likelihood:

# %%
gpr = GPR(data, kernel=gpflow.kernels.Matern52())

# %% [markdown]
# The likelihood of the exact GP model is:

# %%
gpr.log_likelihood().numpy()

# %% [markdown]
# Now we will create an approximate model which approximates the true posterior via a variational Gaussian distribution.<br>We initialize the distribution to be zero mean and unit variance.

# %%
vgp = VGP(data, kernel=gpflow.kernels.Matern52(), likelihood=gpflow.likelihoods.Gaussian())

# %% [markdown]
# The likelihood of the approximate GP model is:

# %%
vgp.log_likelihood().numpy()

# %% [markdown]
# Obviously, our initial guess for the variational distribution is not correct, which results in a lower bound to the likelihood of the exact GPR model. We can optimize the variational parameters in order to get a tighter bound. 

# %% [markdown]
# In fact, we only need to take **one step** in the natural gradient direction to recover the exact posterior:

# %%
natgrad_opt = NaturalGradient(gamma=1.0)
variational_params = [(vgp.q_mu, vgp.q_sqrt)]
natgrad_opt.minimize(lambda: - vgp.log_marginal_likelihood(), var_list=variational_params)

# %% [markdown]
# The likelihood of the approximate GP model after a single NatGrad step:

# %%
vgp.log_likelihood().numpy()

# %% [markdown]
# ### Optimize both variational parameters and kernel hyperparameters together
#
# In the Gaussian likelihood case we can iterate between an Adam update for the hyperparameters and a NatGrad update for the variational parameters. That way, we achieve optimization of hyperparameters as if the model were a GPR.

# %% [markdown]
# The trick is to forbid Adam from updating the variational parameters by setting them to not trainable.

# %%
# Stop Adam from optimizing the variational parameters
vgp.q_mu.trainable = False
vgp.q_sqrt.trainable = False

adam_opt_for_vgp = tf.optimizers.Adam(adam_learning_rate)
adam_opt_for_gpr = tf.optimizers.Adam(adam_learning_rate)

# %%
for i in range(iterations):
    adam_opt_for_gpr.minimize(
        lambda: - gpr.log_marginal_likelihood(), 
        var_list=gpr.trainable_variables)
    likelihood = gpr.log_likelihood()
    tf.print(f'GPR with Adam: iteration {i + 1} likelihood {likelihood:.04f}')

# %%
for i in range(iterations):
    adam_opt_for_vgp.minimize(
        lambda: - vgp.log_marginal_likelihood(),
        var_list=vgp.trainable_variables)
    natgrad_opt.minimize(
        lambda: - vgp.log_marginal_likelihood(),
        var_list=variational_params)
    likelihood = vgp.log_likelihood()
    tf.print(f'VGP with NaturalGradient and Adam: iteration {i + 1} likelihood {likelihood:.04f}')

# %% [markdown]
# Compare GPR and VGP lengthscales after optimization:

# %%
print(f'GPR lengthscales = {gpr.kernel.lengthscales.numpy():.04f}')
print(f'VGP lengthscales = {vgp.kernel.lengthscales.numpy():.04f}')

# %% [markdown]
# ### Natural gradients also work for the sparse model
# Similarly, natural gradients turn SVGP into SGPR in the Gaussian likelihood case. <br>
# We can again combine natural gradients with Adam to update both variational parameters and hyperparameters too.<br>
# Here we'll just do a single natural step demonstration.

# %%
svgp = SVGP(kernel=gpflow.kernels.Matern52(), likelihood=gpflow.likelihoods.Gaussian(), inducing_variable=inducing_variable)
sgpr = SGPR(data, kernel=gpflow.kernels.Matern52(), inducing_variable=inducing_variable)

for model in svgp, sgpr:
    model.likelihood.variance.assign(0.1)

# %% [markdown]
# Analytically optimal sparse model likelihood:

# %%
sgpr.log_likelihood().numpy()

# %% [markdown]
# SVGP likelihood before natural gradient step:

# %%
svgp.log_likelihood(data).numpy()

# %%
variational_params = [(svgp.q_mu, svgp.q_sqrt)]

def svgp_loss_cb():
    return - svgp.log_marginal_likelihood(data)

natgrad_opt = NaturalGradient(gamma=1.0)
natgrad_opt.minimize(svgp_loss_cb, var_list=variational_params)

# %% [markdown]
# SVGP likelihood after a single natural gradient step:

# %%
svgp.log_likelihood(data).numpy()

# %% [markdown]
# ### Minibatches
# A crucial property of the natural gradient method is that it still works with minibatches.
# In practice though, we need to use a smaller gamma.

# %%
natgrad_opt = NaturalGradient(gamma=0.1)

data_minibatch = tf.data.Dataset.from_tensor_slices(data).prefetch(N).repeat().shuffle(N).batch(batch_size)
data_minibatch_it = iter(data_minibatch)

def svgp_stochastic_loss_cb() -> tf.Tensor:
    batch = next(data_minibatch_it)
    return - svgp.log_marginal_likelihood(batch)

for _ in range(ci_niter(100)):
    natgrad_opt.minimize(svgp_stochastic_loss_cb, var_list=variational_params)

# %% [markdown]
# Minibatch SVGP likelihood after NatGrad optimization:

# %%
np.average([svgp.log_likelihood(next(data_minibatch_it)) for _ in ci_range(100)])

# %% [markdown]
# ### Comparison with ordinary gradients in the conjugate case
#
# ##### (Take home message: natural gradients are always better)
#
# Compared to SVGP with ordinary gradients with minibatches, the natural gradient optimizer is much faster in the Gaussian case. 
#
# Here we'll do hyperparameter learning together with optimization of the variational parameters, comparing the interleaved natural gradient approach and the one using ordinary gradients for the hyperparameters and variational parameters jointly.
#
# **NOTE:** Again we need to compromise for smaller gamma value, which we'll keep *fixed* during the optimization.

# %%
svgp_ordinary = SVGP(kernel=gpflow.kernels.Matern52(), likelihood=gpflow.likelihoods.Gaussian(), inducing_variable=inducing_variable)
svgp_natgrad = SVGP(kernel=gpflow.kernels.Matern52(), likelihood=gpflow.likelihoods.Gaussian(), inducing_variable=inducing_variable)

# ordinary gradients with Adam for SVGP
ordinary_adam_opt = tf.optimizers.Adam(adam_learning_rate)

# NatGrads and Adam for SVGP
# Stop Adam from optimizing the variational parameters
svgp_natgrad.q_mu.trainable = False
svgp_natgrad.q_sqrt.trainable = False

# Create the optimize_tensors for SVGP
natgrad_adam_opt = tf.optimizers.Adam(adam_learning_rate)

natgrad_opt = NaturalGradient(gamma=0.1)
variational_params = [(svgp_natgrad.q_mu, svgp_natgrad.q_sqrt)]

# %% [markdown]
# Let's optimize the models:

# %%
data_minibatch = tf.data.Dataset.from_tensor_slices(data).prefetch(N).repeat().shuffle(N).batch(batch_size)
data_minibatch_it = iter(data_minibatch)


def svgp_ordinary_loss_cb() -> tf.Tensor:
    batch = next(data_minibatch_it)
    return - svgp_ordinary.log_marginal_likelihood(batch)


def svgp_natgrad_loss_cb() -> tf.Tensor:
    batch = next(data_minibatch_it)
    return - svgp_natgrad.log_marginal_likelihood(batch)


for _ in range(ci_niter(100)):
    ordinary_adam_opt.minimize(svgp_ordinary_loss_cb, var_list=svgp_ordinary.trainable_variables)


for _ in range(ci_niter(100)):
    natgrad_adam_opt.minimize(svgp_natgrad_loss_cb, var_list=svgp_natgrad.trainable_variables)
    natgrad_opt.minimize(svgp_natgrad_loss_cb, var_list=variational_params)

# %% [markdown]
# SVGP likelihood after ordinary `Adam` optimization:

# %%
np.average([svgp_ordinary.log_likelihood(next(data_minibatch_it)) for _ in ci_range(100)])

# %% [markdown]
# SVGP likelihood after `NaturalGradient` and `Adam` optimization:

# %%
np.average([svgp_natgrad.log_likelihood(next(data_minibatch_it)) for _ in ci_range(100)])

# %% [markdown]
# ### Comparison with ordinary gradients in the non-conjugate case
# #### Binary classification
#
# ##### (Take home message: natural gradients are usually better)
#
# We can use natural gradients even when the likelihood isn't Gaussian. It isn't guaranteed to be better, but it usually is better in practical situations.

# %%
y_binary = np.random.choice([1., -1], size=x.shape)
vgp_data = (x, y_binary)

vgp_bernoulli = VGP(vgp_data, kernel=gpflow.kernels.Matern52(), likelihood=gpflow.likelihoods.Bernoulli())
vgp_bernoulli_natgrad = VGP(vgp_data, kernel=gpflow.kernels.Matern52(), likelihood=gpflow.likelihoods.Bernoulli())

# ordinary gradients with Adam for VGP with Bernoulli likelihood
adam_opt = tf.optimizers.Adam(adam_learning_rate)

# NatGrads and Adam for VGP with Bernoulli likelihood
# Stop Adam from optimizing the variational parameters
vgp_bernoulli_natgrad.q_mu.trainable = False
vgp_bernoulli_natgrad.q_sqrt.trainable = False

# Create the optimize_tensors for VGP with natural gradients
natgrad_adam_opt = tf.optimizers.Adam(adam_learning_rate)
natgrad_opt = NaturalGradient(gamma=0.1)
variational_params = [(vgp_bernoulli_natgrad.q_mu, vgp_bernoulli_natgrad.q_sqrt)]

# %%
# Optimize vgp_bernoulli
for _ in range(ci_niter(100)):
    adam_opt.minimize(
        lambda: - vgp_bernoulli.log_marginal_likelihood(),
        var_list=vgp_bernoulli.trainable_variables)

# Optimize vgp_bernoulli_natgrad
for _ in range(ci_niter(100)):
    adam_opt.minimize(
        lambda: - vgp_bernoulli_natgrad.log_marginal_likelihood(),  
        var_list=vgp_bernoulli_natgrad.trainable_variables)
    natgrad_opt.minimize(
            lambda: - vgp_bernoulli_natgrad.log_marginal_likelihood(),
            var_list=variational_params)

# %% [markdown]
# VGP likelihood after ordinary `Adam` optimization:

# %%
vgp_bernoulli.log_likelihood().numpy()

# %% [markdown]
# VGP likelihood after `NaturalGradient` + `Adam` optimization:

# %%
vgp_bernoulli_natgrad.log_likelihood().numpy()

# %% [markdown]
# We can also choose to run natural gradients in another parameterization.<br>
# The sensible choice is the model parameters (q_mu, q_sqrt), which is already in GPflow.

# %%
vgp_bernoulli_natgrads_xi = VGP(vgp_data, kernel=gpflow.kernels.Matern52(), likelihood=gpflow.likelihoods.Bernoulli())

# Stop Adam from optimizing the variational parameters
vgp_bernoulli_natgrads_xi.q_mu.trainable = False
vgp_bernoulli_natgrads_xi.q_sqrt.trainable = False

# Create the optimize_tensors for VGP with Bernoulli likelihood
adam_opt = tf.optimizers.Adam(adam_learning_rate)
natgrad_opt = NaturalGradient(gamma=0.01)

variational_params = [(vgp_bernoulli_natgrads_xi.q_mu, vgp_bernoulli_natgrads_xi.q_sqrt, XiSqrtMeanVar())]

# %%
# Optimize vgp_bernoulli_natgrads_xi
for _ in range(ci_niter(100)):
    adam_opt.minimize(
        lambda: - vgp_bernoulli_natgrads_xi.log_marginal_likelihood(),                
        var_list=vgp_bernoulli_natgrads_xi.trainable_variables)

    natgrad_opt.minimize(
        lambda: - vgp_bernoulli_natgrads_xi.log_marginal_likelihood(),
        var_list=variational_params)

# %% [markdown]
# VGP likelihood after `NaturalGradient` with `XiSqrtMeanVar` + `Adam` optimization:

# %%
vgp_bernoulli_natgrads_xi.log_likelihood().numpy()

# %% [markdown]
# With sufficiently small steps, it shouldn't make a difference which transform is used, but for large 
# steps this can make a difference in practice.

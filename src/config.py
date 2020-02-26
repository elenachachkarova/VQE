import scipy
import numpy

vqe_params = {'chemical_accuracy': 1e-3, 'max_n_iterations': 2000}

multithread = {'n_cpus': 6}

adaptive_ansatz_params = {'energy_threshold': 1e-6, 'max_ansatz_elements': 10}

# <<<<<<<CLASSICAL OPTIMIZER>>>>>>>>>>>>
optimizer = 'L-BFGS-B'
optimizer_tol = 1e-5
optimizer_bounds = scipy.optimize.Bounds(-numpy.pi/2, numpy.pi/2)
# optimizer_bounds = None
optimizer_options = {'maxcor': 15, 'ftol': 1e-9, 'gtol': 1e-7, 'eps': 1e-02, 'maxfun': 1000, 'maxiter': 1000,
                     'iprint': -1, 'maxls': 20}

# this settings worked for the adapt_vqe when using the UCCSD elements. However they fail for ESD
# optimizer_options={'maxcor': 10, 'ftol': 1e-06, 'gtol': 1e-04, 'eps': 1e-04, 'maxfun': 1500, 'maxiter': 1000,
#                    'iprint': -1, 'maxls': 5}


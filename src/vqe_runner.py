from openfermion.transforms import get_fermion_operator, jordan_wigner, get_sparse_operator
from openfermionpsi4 import run_psi4
from openfermion.hamiltonians import MolecularData
from openfermion.utils import freeze_orbitals

import src.backends as backends
from src.utils import QasmUtils, LogUtils
from src import config

import scipy
import numpy
import time
from functools import partial

import logging

from src.ansatz_element_lists import UCCSD
import ray


class VQERunner:
    # Works for a single geometry
    def __init__(self, q_system, ansatz=None, backend_type=backends.QiskitSim, optimizer=config.optimizer,
                 optimizer_options=config.optimizer_options, print_var_parameters=False, use_ansatz_gradient=False):

        self.backend_type = backend_type
        self.optimizer = optimizer
        self.optimizer_options = optimizer_options
        self.use_ansatz_gradient = use_ansatz_gradient
        self.print_var_parameters = print_var_parameters

        self.q_system = q_system

        self.previous_energy = self.q_system.hf_energy
        self.new_energy = None

        self.iteration = 0
        self.t_previous_iter = 0

        LogUtils.vqe_info(q_system, ansatz_elements=ansatz, basis=q_system.basis,
                          molecule_geometry_params=q_system.get_geometry, backend=backend_type)
        logging.info('Optimizer: {}. Optimizer options: {}'.format(optimizer, optimizer_options))

    def get_energy(self, var_parameters, ansatz, backend, multithread=False, multithread_iteration=None,
                   init_state_qasm=None):

        if multithread is False:
            iteration_duration = time.time() - self.t_previous_iter
            self.t_previous_iter = time.time()

        energy = backend.get_expectation_value(var_parameters=var_parameters, ansatz=ansatz,
                                               init_state_qasm=init_state_qasm)

        # TODO: the code below is a mess .. FIX
        # if we run in parallel process don't print and update info
        if multithread:
            if multithread_iteration is not None:
                try:
                    multithread_iteration[0] += 1
                except TypeError as te:
                    logging.warning(te)

            # # TODO this logging does not work when running in parallel
            # logging.info('Parallel process. Energy {}. Iteration duration: {}'.format(energy, time.time() - t_start))
        else:

            # print info
            self.new_energy = energy
            delta_e = self.new_energy - self.previous_energy
            self.previous_energy = self.new_energy

            message = 'Iteration: {}. Energy {}.  Energy change {} , Iteration dutation: {}' \
                .format(self.iteration, self.new_energy, '{:.3e}'.format(delta_e), iteration_duration)
            if self.print_var_parameters:
                message += ' Params: ' + str(var_parameters)
            logging.info(message)
            print(message)

            self.iteration += 1

        return energy

    def get_ansatz_gradient(self, var_parameters, ansatz, backend, init_state_qasm=None):
        return backend.get_ansatz_gradient(var_parameters, ansatz=ansatz, init_state_qasm=init_state_qasm)

    def vqe_run(self, ansatz, initial_var_parameters=None, init_state_qasm=None):

        assert len(ansatz) > 0
        if initial_var_parameters is None:
            var_parameters = numpy.zeros(sum([element.n_var_parameters for element in ansatz]))
        else:
            assert len(initial_var_parameters) == sum([element.n_var_parameters for element in ansatz])
            var_parameters = initial_var_parameters

        backend = self.backend_type(self.q_system)

        message = ''
        message += '-----Running VQE for: {}-----\n'.format(self.q_system.name)
        message += '-----Number of electrons: {}-----\n'.format(self.q_system.n_electrons)
        message += '-----Number of orbitals: {}-----\n'.format(self.q_system.n_orbitals)
        message += '-----Numeber of ansatz elements: {}-----\n'.format(len(ansatz))
        if len(ansatz) == 1:
            message += '-----Ansatz type {}------\n'.format(ansatz[0].element)
        message += '-----Statevector and energy calculated using {}------\n'.format(backend)
        message += '-----Optimizer {}------\n'.format(self.optimizer)
        print(message)
        logging.info(message)

        self.iteration = 1
        self.t_previous_iter = time.time()

        # precompute frequently used quantities
        if self.use_ansatz_gradient:
            for element in ansatz:
                element.compute_excitation_mtrx()  # the excitation matrices are now computed and stored in each element

        get_energy = partial(self.get_energy, ansatz=ansatz, backend=backend, init_state_qasm=init_state_qasm)

        get_gradient = partial(self.get_ansatz_gradient, ansatz=ansatz, backend=backend, init_state_qasm=init_state_qasm)

        if self.use_ansatz_gradient:

            opt_energy = scipy.optimize.minimize(get_energy, var_parameters, jac=get_gradient, method=self.optimizer,
                                                 options=self.optimizer_options, tol=config.optimizer_tol,
                                                 bounds=config.optimizer_bounds)
        else:

            opt_energy = scipy.optimize.minimize(get_energy, var_parameters, method=self.optimizer,
                                                 options=self.optimizer_options, tol=config.optimizer_tol,
                                                 bounds=config.optimizer_bounds)

        # Prevents memory overflow with ray
        for element in ansatz:
            element.delete_excitation_mtrx()

        print(opt_energy)
        logging.info(opt_energy)

        opt_energy['n_iters'] = self.iteration  # cheating
        return opt_energy

    @ray.remote
    def vqe_run_multithread(self, ansatz, initial_var_parameters=None, initial_statevector_qasm=None):

        if initial_var_parameters is None or initial_var_parameters == []:
            var_parameters = numpy.zeros(sum([element.n_var_parameters for element in ansatz]))
        else:
            assert len(initial_var_parameters) == sum([element.n_var_parameters for element in ansatz])
            var_parameters = initial_var_parameters

        # create it as a list so we can pass it by reference
        local_iteration = [0]

        # partial function to be used in the optimizer
        H_sparse_matrix = get_sparse_operator(self.q_system.jw_qubit_ham)
        if self.use_ansatz_gradient:
            for element in ansatz:
                element.compute_excitation_mtrx()  # the excitation matrices are now computed and stored in each element

        get_energy = partial(self.get_energy, ansatz=ansatz, multithread=True,
                             multithread_iteration=local_iteration, H_sparse_matrix=H_sparse_matrix)

        # if no ansatz elements supplied, calculate the energy without using the optimizer
        if len(ansatz) == 0:
            return get_energy(var_parameters)

        if self.use_ansatz_gradient:
            statevector_ref = [[]]
            var_parameters_ref = [[]]

            get_energy = partial(self.get_energy, ansatz=ansatz,
                                 initial_statevector_qasm=initial_statevector_qasm, ham_sparse_matrix=H_sparse_matrix,
                                 precomputed_statevector=statevector_ref, previous_var_parameters=var_parameters_ref,
                                 multithread=True, multithread_iteration=local_iteration)

            get_gradient = partial(self.get_ansatz_gradient, ansatz=ansatz,
                                   ham_sparse_matrix=H_sparse_matrix,
                                   initial_statevector_qasm=initial_statevector_qasm,
                                   precomputed_statevector=statevector_ref, previous_var_parameters=var_parameters_ref)

            opt_energy = scipy.optimize.minimize(get_energy, var_parameters, method=self.optimizer, jac=get_gradient,
                                                 options=self.optimizer_options, tol=config.optimizer_tol,
                                                 bounds=config.optimizer_bounds)
        else:
            opt_energy = scipy.optimize.minimize(get_energy, var_parameters, method=self.optimizer,
                                                 options=self.optimizer_options, tol=config.optimizer_tol,
                                                 bounds=config.optimizer_bounds)

        if len(ansatz) == 1:
            message = 'Ran VQE for element {}. Energy {}. Iterations {}'.format(ansatz[0].element,
                                                                                opt_energy.fun, local_iteration[0])
            logging.info(message)
            print(message)
        else:
            message = 'Ran VQE. Energy {}. Iterations {}'.format(opt_energy.fun, local_iteration[0])
            logging.info(message)
            print(message)

        # Prevents memory overflow with ray
        for element in ansatz:
            element.delete_excitation_mtrx()

        opt_energy['n_iters'] = local_iteration[0]  # cheating
        return opt_energy

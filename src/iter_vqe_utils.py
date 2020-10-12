from openfermion import get_sparse_operator, QubitOperator
from src import config
from src import backends
from src.ansatz_elements import *

import time
import ray
import ast


class IterVQEQasmUtils:
    @staticmethod
    def gate_count_from_ansatz(ansatz, n_qubits, var_parameters=None):
        n_var_parameters = sum([x.n_var_parameters for x in ansatz])
        if var_parameters is None:
            var_parameters = numpy.zeros(n_var_parameters)
        else:
            assert n_var_parameters == len(var_parameters)
        qasm = backends.QiskitSim.qasm_from_ansatz(ansatz, var_parameters)
        return QasmUtils.gate_count_from_qasm(qasm, n_qubits)


class IterVQEEnergyUtils:
    # finds the VQE energy contribution of a single ansatz element added to (optionally) an initial ansatz
    @staticmethod
    def get_ansatz_elements_energy_reductions(vqe_runner, ansatz_elements, initial_var_parameters=None,
                                              initial_ansatz=None, multithread=False):
        if initial_ansatz is None:
            initial_ansatz = []
        if multithread:
            ray.init(num_cpus=config.multithread['n_cpus'])
            elements_ray_ids = [
                [element,
                 vqe_runner.vqe_run_multithread.remote(self=vqe_runner, ansatz=initial_ansatz + [element],
                                                       initial_var_parameters=initial_var_parameters + [0])]
                # TODO this will work only if the ansatz element has 1 var. par.
                for element in ansatz_elements
            ]
            elements_results = [[element_ray_id[0], ray.get(element_ray_id[1])] for element_ray_id in elements_ray_ids]
            ray.shutdown()
        else:
            elements_results = [
                [element, vqe_runner.vqe_run(ansatz=initial_ansatz + [element],
                                             initial_var_parameters=initial_var_parameters+[0])]
                for element in ansatz_elements
            ]

        return elements_results

    # returns the ansatz element that achieves lowest energy (together with the energy value)
    @staticmethod
    def get_largest_energy_reduction_ansatz_element(vqe_runner, ansatz_elements, initial_var_parameters=None,
                                                    ansatz=None, multithread=False):
        elements_results = IterVQEEnergyUtils.get_ansatz_elements_energy_reductions(vqe_runner, ansatz_elements,
                                                                                    initial_var_parameters=initial_var_parameters,
                                                                                    initial_ansatz=ansatz,
                                                                                    multithread=multithread)
        return min(elements_results, key=lambda x: x[1].fun)

    # NOT used
    # get ansatz elements that contribute to energy decrease below(above) some threshold value
    @staticmethod
    def get_ansatz_elements_below_threshold(vqe_runner, ansatz_elements, threshold, initial_var_parameters=[],
                                            initial_ansatz=[], multithread=False):
        elements_results = IterVQEEnergyUtils.get_ansatz_elements_energy_reductions(vqe_runner, ansatz_elements,
                                                                                    initial_var_parameters=initial_var_parameters,
                                                                                    initial_ansatz=initial_ansatz,
                                                                                    multithread=multithread)
        return [element_result for element_result in elements_results if element_result[1].fun <= threshold]


class IterVQEGradientUtils:

    # calculate commutators the commutators of H, with the excitation generators of the ansatz_elements
    @staticmethod
    def calculate_commutators(H_qubit_operator, ansatz_elements, n_system_qubits, multithread=False):
        commutators = {}
        if multithread:
            ray.init(num_cpus=config.multithread['n_cpus'])
            elements_ray_ids = [
                [
                    element, IterVQEGradientUtils.get_commutator_matrix_multithread.
                    remote(QubitOperator(str(element.excitation_generator)),
                           # H_qubit_operator and excitation_generator are passed by values, and deleted in
                           # get_commutator_matrix_multithread.Otherwise ray.threads keep local copies that fill the RAM
                           H_qubit_operator=QubitOperator(str(H_qubit_operator)), n_qubits=n_system_qubits)
                ]
                for element in ansatz_elements
            ]
            for element_ray_id in elements_ray_ids:
                key = str(element_ray_id[0].excitation_generator)
                commutators[key] = ray.get(element_ray_id[1])

            del elements_ray_ids
            ray.shutdown()
        else:
            for i, element in enumerate(ansatz_elements):
                excitation_generator = element.excitation_generator
                key = str(excitation_generator)
                print('Calculated commutator ', key)
                commutator = H_qubit_operator * excitation_generator - excitation_generator * H_qubit_operator
                commutator_sparse_matrix = get_sparse_operator(commutator, n_qubits=n_system_qubits)
                commutators[key] = commutator_sparse_matrix

        return commutators

    @staticmethod
    @ray.remote
    def get_commutator_matrix_multithread(excitation_generator, H_qubit_operator, n_qubits):
        t0 = time.time()
        commutator_qubit_operator = H_qubit_operator * excitation_generator - excitation_generator * H_qubit_operator
        commutator_sparse_matrix = get_sparse_operator(commutator_qubit_operator,  n_qubits=n_qubits)
        print('Calculated commutator ', str(excitation_generator), 'time ', time.time() - t0)
        del commutator_qubit_operator
        del t0
        del excitation_generator
        del H_qubit_operator
        return commutator_sparse_matrix

    @staticmethod
    @ray.remote
    def get_excitation_gradient_multithread(excitation_element, ansatz, var_parameters, backend,
                                            commutator_sparse_matrix=None):
        t0 = time.time()
        gradient = backend.excitation_gradient(excitation_element, ansatz, var_parameters,
                                               commutator_sparse_matrix=commutator_sparse_matrix,
                                               update_statevector=False)  # experiment with true

        message = 'Excitation {}. Excitation grad {}. Time {}'.format(excitation_element.element, gradient,
                                                                      time.time() - t0)
        # TODO check if required
        del commutator_sparse_matrix
        print(message)  # keep this since logging does not work well in multithreading
        return gradient

    # finds energy gradient of <H> w.r.t. to the ansatz_elements variationa parameters
    @staticmethod
    def get_ansatz_elements_gradients(ansatz_elements, q_system, var_parameters=None, ansatz=None, multithread=False,
                                      dynamic_commutator_matrices=None, backend_type=backends.QiskitSim):

        if ansatz is None:
            ansatz = []
            var_parameters = []

        backend = backend_type(q_system)
        # initialize the statevector once, and use it to calculate all gradients
        backend.update_statevector(ansatz, var_parameters)

        # use this function to supply precomputed commutators to the gradient evaluation function
        def get_commutator_matrix(element):
            if dynamic_commutator_matrices is None:
                return None
            else:
                try:
                    return dynamic_commutator_matrices[str(element.excitation_generator)].copy()
                except KeyError:
                    t0 = time.time()
                    commutator = q_system.jw_qubit_ham * element.excitation_generator - element.excitation_generator * q_system.jw_qubit_ham
                    commutator_matrix = get_sparse_operator(commutator)
                    dynamic_commutator_matrices[str(element.excitation_generator)] = commutator_matrix
                    print('Calculating commutator for ', element.excitation_generator, 'time ', time.time() - t0)
                    return commutator_matrix.copy()

        if multithread:
            ray.init(num_cpus=config.multithread['n_cpus'])
            elements_ray_ids = [
                [
                    element, IterVQEGradientUtils.get_excitation_gradient_multithread.
                    remote(element, ansatz, var_parameters, backend, commutator_sparse_matrix=get_commutator_matrix(element))
                 ]
                for element in ansatz_elements
            ]
            elements_results = [[element_ray_id[0], ray.get(element_ray_id[1])] for element_ray_id in
                                elements_ray_ids]
            ray.shutdown()
        else:
            elements_results = [
                [
                    element, backend.excitation_gradient(element, ansatz, var_parameters,
                                                         commutator_sparse_matrix=get_commutator_matrix(element))]
                for element in ansatz_elements
            ]
        return elements_results

    # returns the n ansatz elements that with largest energy gradients
    @staticmethod
    def get_largest_gradient_ansatz_elements(ansatz_elements, q_system, backend_type=backends.QiskitSim, var_parameters=None
                                             , ansatz=None, n=1, multithread=False, dynamic_commutators=None):

        elements_results = IterVQEGradientUtils.get_ansatz_elements_gradients(ansatz_elements, q_system,
                                                                              var_parameters=var_parameters,
                                                                              ansatz=ansatz,
                                                                              multithread=multithread,
                                                                              dynamic_commutator_matrices=dynamic_commutators,
                                                                              backend_type=backend_type)
        elements_results.sort(key=lambda x: abs(x[1]))
        return elements_results[-n:]


class IterVQEDataUtils:
    @staticmethod
    def save_data(data_frame, molecule, time_stamp, ansatz_element_type=None, frozen_els=None, iter_vqe_type='iqeb'):
        filename = '{}_{}_{}_{}_{}.csv'.format(molecule.name, iter_vqe_type, ansatz_element_type, frozen_els, time_stamp)
        try:
            data_frame.to_csv('../../results/iter_vqe_results/'+filename)
        except FileNotFoundError:
            try:
                data_frame.to_csv('results/iter_vqe_results/'+filename)
            except FileNotFoundError as fnf:
                print(fnf)

    # TODO: make this less ugly and more general
    @staticmethod
    def get_ansatz_from_data_frame(data_frame, q_system):
        ansatz = []
        for i in range(len(data_frame)):
            element = data_frame.loc[i]['element']
            element_qubits = data_frame.loc[i]['element_qubits']
            if element[0] == 'e' and element[4] == 's':
                ansatz.append(EffSFExc(*ast.literal_eval(element_qubits), system_n_qubits=q_system.n_qubits))
            elif element[0] == 'e' and element[4] == 'd':
                ansatz.append(EffDFExc(*ast.literal_eval(element_qubits), system_n_qubits=q_system.n_qubits))
            elif element[0] == 's' and element[2] == 'q':
                ansatz.append(SQExc(*ast.literal_eval(element_qubits), system_n_qubits=q_system.n_qubits))
            elif element[0] == 'd' and element[2] == 'q':
                ansatz.append(DQExc(*ast.literal_eval(element_qubits), system_n_qubits=q_system.n_qubits))
            elif element[:2] == '1j':
                ansatz.append(PauliStringExc(QubitOperator(element), system_n_qubits=q_system.n_qubits))
            elif element[:8] == 'spin_s_f':
                ansatz.append(SpinCompSFExc(*ast.literal_eval(element_qubits), system_n_qubits=q_system.n_qubits))
            elif element[:8] == 'spin_d_f':
                ansatz.append(SpinCompDFExc(*ast.literal_eval(element_qubits), system_n_qubits=q_system.n_qubits))
            elif element[:8] == 'spin_s_q':
                ansatz.append(SpinCompSQExc(*ast.literal_eval(element_qubits), system_n_qubits=q_system.n_qubits))
            elif element[:8] == 'spin_d_q':
                ansatz.append(SpinCompDQExc(*ast.literal_eval(element_qubits), system_n_qubits=q_system.n_qubits))
            else:
                print(element, element_qubits)
                raise Exception('Unrecognized ansatz element.')

        var_pars = list(data_frame['var_parameters'])

        return ansatz, var_pars

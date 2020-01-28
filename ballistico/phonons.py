"""
Ballistico
Anharmonic Lattice Dynamics
"""
from ballistico.helpers.tools import is_calculated
from ballistico.helpers.tools import lazy_property
from ballistico.helpers.tools import q_vec_from_q_index
from ballistico.controllers.harmonic import *
import numpy as np
import ase.units as units

KELVINTOTHZ = units.kB / units.J / (2 * np.pi * units._hbar) * 1e-12
KELVINTOJOULE = units.kB / units.J
THZTOMEV = units.J * units._hbar * 2 * np.pi * 1e15
EVTOTENJOVERMOL = units.mol / (10 * units.J)

DELTA_DOS = 1
NUM_DOS = 100
FOLDER_NAME = 'ald-output'


class Phonons:
    def __init__(self, **kwargs):
        """The phonons object exposes all the phononic properties of a system,

        Parameters
        ----------
        finite_difference : FiniteDifference
            contains all the information about the system and the derivatives of the potential.
        is_classic : bool
            specifies if the system is classic, `True` or quantum, `False`
        temperature : float
            defines the temperature of the simulation.
        folder (optional) : string
            specifies where to store the data files. Default is `output`.
        kpts (optional) : (3) tuple
            defines the number of k points to use to create the k mesh. Default is [1, 1, 1].
        min_frequency (optional) : float
            ignores all phonons with frequency below `min_frequency` THz, Default is None..
        max_frequency (optional) : float
            ignores all phonons with frequency above `max_frequency` THz, Default is None.
        sigma_in (optional) : float or None
            defines the width of the energy conservation smearing in the phonons scattering calculation.
            If `None` the width is calculated dynamically. Otherwise the input value corresponds to the
            width in THz. Default is None.
        broadening_shape (optional) : string
            defines the algorithm to use to calculate the broadening. Available broadenings are `gauss` and `triangle`.
            Default is `gauss`.
        is_tf_backend (optional) : bool
            defines if the third order phonons scattering calculations should be performed on tensorflow (True) or
            numpy (False). Default is True.
        Returns
        -------
        Phonons
            An instance of the `Phonons` class.

        """
        self.finite_difference = kwargs.pop('finite_difference')
        if 'is_classic' in kwargs:
            self.is_classic = bool(kwargs['is_classic'])
        if 'temperature' in kwargs:
            self.temperature = float(kwargs['temperature'])
        self.folder = kwargs.pop('folder', FOLDER_NAME)
        self.kpts = kwargs.pop('kpts', (1, 1, 1))
        self.kpts = np.array(self.kpts)
        self.min_frequency = kwargs.pop('min_frequency', None)
        self.max_frequency = kwargs.pop('max_frequency', None)
        self.sigma_in = kwargs.pop('sigma_in', None)
        self.broadening_shape = kwargs.pop('broadening_shape', 'gauss')
        self.is_tf_backend = kwargs.pop('is_tf_backend', False)
        self.is_nw = kwargs.pop('is_nw', False)
        self.atoms = self.finite_difference.atoms
        self.supercell = np.array(self.finite_difference.supercell)
        self.n_k_points = int(np.prod(self.kpts))
        self.n_atoms = self.finite_difference.n_atoms
        self.n_modes = self.finite_difference.n_modes
        self.n_phonons = self.n_k_points * self.n_modes
        self.is_able_to_calculate = True


    @lazy_property(is_storing=True, is_reduced_path=True)
    def physical_modes(self):
        """
        Calculate physical modes. Non physical modes are the first 3 modes of q=(0, 0, 0) and, if defined, all the
        modes outside the frequency range min_frequency and max_frequency.
        Returns
        -------
        physical_modes : np array
            (n_k_points, n_modes) bool
        """
        physical_modes = calculate_physical_modes(self)
        return physical_modes


    @lazy_property(is_storing=True, is_reduced_path=True)
    def frequency(self):
        """
        Calculate phonons frequencies
        Returns
        -------
        frequencies : np array
            (n_k_points, n_modes) frequencies in THz
        """
        frequencies = calculate_frequencies(self)
        return frequencies


    @lazy_property(is_storing=True, is_reduced_path=True)
    def velocity(self):
        """Calculates the velocities using Hellmann-Feynman theorem.
        Returns
        -------
        velocities : np array
            (n_k_points, n_unit_cell * 3, 3) velocities in 100m/s or A/ps
        """
        velocities = calculate_velocities(self)
        return velocities


    @lazy_property(is_storing=True, is_reduced_path=False)
    def heat_capacity(self):
        """Calculate the heat capacity for each k point in k_points and each mode.
        If classical, it returns the Boltzmann constant in W/m/K. If quantum it returns the derivative of the
        Bose-Einstein weighted by each phonons energy.
        .. math::

            c_\\mu = k_B \\frac{\\nu_\\mu^2}{ \\tilde T^2} n_\\mu (n_\\mu + 1)

        where the frequency :math:`\\nu` and the temperature :math:`\\tilde T` are in THz.

        Returns
        -------
        c_v : np.array(n_k_points, n_modes)
            heat capacity in W/m/K for each k point and each mode
        """
        c_v = calculate_heat_capacity(self)
        return c_v


    @lazy_property(is_storing=True, is_reduced_path=False)
    def population(self):
        """Calculate the phonons population for each k point in k_points and each mode.
        If classical, it returns the temperature divided by each frequency, using equipartition theorem.
        If quantum it returns the Bose-Einstein distribution

        Returns
        -------
        population : np.array(n_k_points, n_modes)
            population for each k point and each mode
        """
        occupations =  calculate_occupations(self)
        return occupations


    @property
    def bandwidth(self):
        """Calculate the phonons bandwidth, the inverse of the lifetime, for each k point in k_points and each mode.

        Returns
        -------
        bandwidth : np.array(n_k_points, n_modes)
            bandwidth for each k point and each mode
        """
        gamma = self._ps_and_gamma[:, 1]
        return gamma


    @property
    def phase_space(self):
        """Calculate the 3-phonons-processes phase_space, for each k point in k_points and each mode.

        Returns
        -------
        phase_space : np.array(n_k_points, n_modes)
            phase_space for each k point and each mode
        """
        ps = self._ps_and_gamma[:, 0]
        return ps


    @lazy_property(is_storing=False, is_reduced_path=False)
    def rescaled_eigenvectors(self):
        n_atoms = self.n_atoms
        n_modes = self.n_modes
        masses = self.atoms.get_masses()
        rescaled_eigenvectors = self.eigenvectors[:, :, :].reshape(
            (self.n_k_points, n_atoms, 3, n_modes), order='C') / np.sqrt(
            masses[np.newaxis, :, np.newaxis, np.newaxis])
        rescaled_eigenvectors = rescaled_eigenvectors.reshape((self.n_k_points, n_modes, n_modes), order='C')
        return rescaled_eigenvectors


    @lazy_property(is_storing=False, is_reduced_path=False)
    def _main_q_mesh(self):
        q_mesh = q_vec_from_q_index(np.arange(self.n_k_points), self.kpts)
        return q_mesh


    @lazy_property(is_storing=True, is_reduced_path=True)
    def _dynmat_derivatives(self):
        dynmat_derivatives = calculate_dynmat_derivatives(self)
        return dynmat_derivatives


    @lazy_property(is_storing=True, is_reduced_path=True)
    def _eigensystem(self):
        eigensystem = calculate_eigensystem(self)
        return eigensystem


    @lazy_property(is_storing=False, is_reduced_path=True)
    def _chi_k(self):
        chi = np.zeros((self.n_k_points, self.finite_difference.n_replicas), dtype=np.complex)
        for index_q in range(self.n_k_points):
            k_point = q_vec_from_q_index(index_q, self.kpts)
            chi[index_q] = self._chi(k_point)
        return chi


    @lazy_property(is_storing=False, is_reduced_path=True)
    def _omegas(self):
        return self.frequency * 2 * np.pi


    @lazy_property(is_storing=True, is_reduced_path=True)
    def _velocities_af(self):
        velocities_AF = calculate_velocities_af(self)
        return velocities_AF


    @lazy_property(is_storing=True, is_reduced_path=True)
    def _sij(self):
        sij = calculate_sij(self)
        return sij


    @lazy_property(is_storing=True, is_reduced_path=False)
    def _ps_and_gamma(self):
        if is_calculated('ps_gamma_and_gamma_tensor', self):
            ps_and_gamma = self._ps_gamma_and_gamma_tensor[:, :2]
        else:
            ps_and_gamma = self.calculate_ps_and_gamma(is_gamma_tensor_enabled=False)
        return ps_and_gamma


    @lazy_property(is_storing=True, is_reduced_path=False)
    def _ps_gamma_and_gamma_tensor(self):
        ps_gamma_and_gamma_tensor = self.calculate_ps_and_gamma(is_gamma_tensor_enabled=True)
        return ps_gamma_and_gamma_tensor


    @lazy_property(is_storing=False, is_reduced_path=False)
    def _scattering_matrix_without_diagonal(self):
        frequencies = self._keep_only_physical(self.frequency.reshape((self.n_phonons), order='C'))
        gamma_tensor = self._keep_only_physical(self._ps_gamma_and_gamma_tensor[:, 2:])
        scattering_matrix_without_diagonal = contract('a,ab,b->ab', 1 / frequencies, gamma_tensor, frequencies)
        return scattering_matrix_without_diagonal


    @lazy_property(is_storing=False, is_reduced_path=False)
    def _scattering_matrix(self):
        scattering_matrix = -1 * self._scattering_matrix_without_diagonal
        gamma = self._keep_only_physical(self.bandwidth.reshape((self.n_phonons), order='C'))
        scattering_matrix = scattering_matrix + np.diag(gamma)
        return scattering_matrix


    @property
    def _is_amorphous(self):
        is_amorphous = (self.kpts == (1, 1, 1)).all()
        return is_amorphous


    @property
    def eigenvalues(self):
        """Calculates the eigenvalues of the dynamical matrix in Thz^2.

        Returns
        -------
        eigenvalues : np array
            (n_phonons) Eigenvalues of the dynamical matrix
        """
        eigenvalues = self._eigensystem[:, 0, :]
        return eigenvalues


    @property
    def eigenvectors(self):
        """Calculates the eigenvectors of the dynamical matrix.

        Returns
        -------
        eigenvectors : np array
            (n_phonons, n_phonons) Eigenvectors of the dynamical matrix
        """
        eigenvectors = self._eigensystem[:, 1:, :]
        return eigenvectors


    def _keep_only_physical(self, operator):
        physical_modes = self.physical_modes
        if operator.shape == (self.n_phonons, self.n_phonons):
            index = np.outer(physical_modes, physical_modes)
            return operator[index].reshape((physical_modes.sum(), physical_modes.sum()), order='C')
        else:
            return operator[physical_modes, ...]


    def _chi(self, qvec):
        dxij = self.finite_difference.list_of_replicas
        cell_inv = self.finite_difference.cell_inv
        chi_k = np.exp(1j * 2 * np.pi * dxij.dot(cell_inv.dot(qvec)))
        return chi_k


    def calculate_ps_and_gamma(self, is_gamma_tensor_enabled=True):
        print('Projection started')
        if self.is_tf_backend:
            try:
                from ballistico.anharmonic_tf import Anharmonic
            except ModuleNotFoundError as err:
                print(err)
                print('tensorflow>=2.0 is required to run accelerated routines. Please consider installing tensorflow>=2.0. More info here: https://www.tensorflow.org/install/pip')
                print('Using numpy engine instead.')
                from ballistico.anharmonic import Anharmonic
        else:
            from ballistico.anharmonic import Anharmonic

        anharmonic = Anharmonic(finite_difference=self.finite_difference,
                                frequencies=self.frequency,
                                kpts=self.kpts,
                                rescaled_eigenvectors=self.rescaled_eigenvectors,
                                is_gamma_tensor_enabled=is_gamma_tensor_enabled,
                                chi_k=self._chi_k,
                                velocities=self.velocity,
                                physical_modes=self.physical_modes,
                                occupations=self.population,
                                sigma_in=self.sigma_in,
                                broadening_shape=self.broadening_shape
                                )
        if self._is_amorphous:
            ps_and_gamma = anharmonic.project_amorphous()
        else:
            ps_and_gamma = anharmonic.project_crystal()
        return ps_and_gamma


    def chi(phonons, qvec):
        dxij = phonons.finite_difference.list_of_replicas
        cell_inv = phonons.finite_difference.cell_inv
        chi_k = np.exp(1j * 2 * np.pi * dxij.dot(cell_inv.dot(qvec)))
        return chi_k


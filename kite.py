"""       
        ##############################################################################      
        #                        KITE | Pre-Release version 0.1                      #      
        #                                                                            #      
        #                        Kite home: quantum-kite.com                         #           
        #                                                                            #      
        #  Developed by: Simao M. Joao, Joao V. Lopes, Tatiana G. Rappoport,         #       
        #  Misa Andelkovic, Lucian Covaci, Aires Ferreira, 2018                      #      
        #                                                                            #      
        ##############################################################################      
"""


import numpy as np
import h5py as hp
import pybinding as pb

from scipy.sparse import coo_matrix
from scipy.spatial import cKDTree


# Class that introduces Structural Disorder into the initially built lattice.
# The exported dataset StructuralDisorder has the following groups:
# - Concentration: concentration of disorder,
# - NumBondDisorder: number of bond changes,
# - NumOnsiteDisorder: number of onsite energy,
# The disorder is represented through nodes, where each node represents and maps a single orbital.
# - NumNodes: total number of orbitals included in the disorded,
# - NodePosition: orbital associated with the node,
# - NodeFrom, and NodeTo: bond from and to with 2 columns and NumBondDisorder rows, where the second column is complex
# conjugated hopping,
# - Hopping: values of the new hopping, with 2 columns and NumBondDisorder rows where the hoppings in different
# columns are conjugated values,
# - NodeOnsite: array of nodes that have onsite disorder,
# - U0: value of the onsite disorder.
class StructuralDisorder:
    def __init__(self, lattice, concentration):

        self._concentration = concentration
        self._num_bond_disorder_per_type = 0
        self._num_onsite_disorder_per_type = 0

        self._orbital_from = []
        self._orbital_to = []
        self._orbital_onsite = []

        self._idx_node = 0
        self._disorder_hopping = []
        self._disorder_onsite = []

        self._nodes_from = []
        self._nodes_to = []
        self._nodes_onsite = []

        # only used for scaling
        self._sub_from = []
        self._sub_to = []
        self._sub_onsite = []
        self._rel_idx_onsite = []
        self._rel_idx_to = []
        self._rel_idx_from = []
        self._onsite = []
        self._hopping = []

        self._orbital_vacancy = []
        self._vacancy_sub = []

        self._num_nodes = 0
        self._nodes_map = dict()
        self._node_orbital = []
        num_orbitals = np.zeros(lattice.nsub, dtype=np.uint64)
        for name, sub in lattice.sublattices.items():
            # num of orbitals at each sublattice is equal to size of onsite energy
            num_energies = np.asarray(sub.energy).shape[0]
            num_orbitals[sub.alias_id] = num_energies
        self._num_orbitals_total = np.sum(np.asarray(num_orbitals))
        self._num_orbitals = np.asarray(num_orbitals)
        self._num_orbitals_before = np.cumsum(np.asarray(num_orbitals)) - num_orbitals
        self._lattice = lattice

    def add_vacancy(self, *disorder):
        if len(disorder) == 1:
            num_vacancy_disorder = 0
            for dis in disorder:
                # check if it's just concentration or sublatt
                num_vacancy_disorder += 1
                self.add_local_vacancy_disorder(dis)

        else:
            raise SystemExit('Vacancy disorder should be added in a form:'
                             '\n sublattice name,'
                             '\n or in a form of disorder onsite energy:'
                             '\n ([rel. unit cell], sublattice_name, '
                             'onsite energy)')

    def add_structural_disorder(self, *disorder):
        self._nodes_map = dict()

        num_bond_disorder_per_type = 0
        num_onsite_disorder_per_type = 0
        for dis in disorder:
            if len(dis) == 5:
                num_bond_disorder_per_type += 1
                self.add_local_bond_disorder(*dis)
            else:
                if len(dis) == 3:
                    num_onsite_disorder_per_type += 1
                    self.add_local_onsite_disorder(*dis)
                else:
                    raise SystemExit('Disorder should be added in a form of bond disorder:'
                                     '\n([rel. unit cell from], sublattice_from, [rel. unit cell to], sublattice_to, '
                                     'value),'
                                     '\n or in a form of disorder onsite energy:'
                                     '\n ([rel. unit cell], sublattice_name, '
                                     'onsite energy)')

        self._num_bond_disorder_per_type = num_bond_disorder_per_type
        self._num_onsite_disorder_per_type = num_onsite_disorder_per_type
        sorted_node_orb = sorted(self._nodes_map, key=lambda x: self._nodes_map[x])
        sorted_nodes = [self._nodes_map[x] for x in sorted_node_orb]

        sorted_dict = dict(zip(sorted_node_orb, sorted_nodes))
        self._nodes_map = sorted_dict
        self._node_orbital = sorted_node_orb

    def map_the_orbital(self, orb, nodes_map):
        idx_node = len(nodes_map)
        if not (orb in nodes_map):
            nodes_map[orb] = idx_node
            idx_node += 1
        self._nodes_map = nodes_map

        return idx_node

    def add_local_vacancy_disorder(self, sub):
        orbital_vacancy = []

        names, sublattices = zip(*self._lattice.sublattices.items())

        if sub not in names:
            raise SystemExit('Desired initial sublattice doesn\'t exist in the chosen lattice! ')

        indx = names.index(sub)
        lattice_sub = sublattices[indx]

        sub_id = lattice_sub.alias_id

        it = np.nditer(lattice_sub.energy, flags=['multi_index'])
        while not it.finished:
            orbit = self._num_orbitals_before[sub_id] + it.multi_index[0]
            if orbit not in orbital_vacancy:
                orbital_vacancy.append(orbit)
            it.iternext()

        self._orbital_vacancy.append(orbital_vacancy)
        self._vacancy_sub.append(sub)

    def add_local_bond_disorder(self, relative_index_from, from_sub, relative_index_to, to_sub, hoppings):

        # save the info used for manual scaling
        self._sub_from.append(from_sub)
        self._sub_to.append(to_sub)
        self._rel_idx_to.append(relative_index_to)
        self._rel_idx_from.append(relative_index_from)
        self._hopping.append(np.atleast_1d(hoppings))

        orbital_from = []
        orbital_to = []
        orbital_hop = []

        vectors = np.asarray(self._lattice.vectors)
        space_size = vectors.shape[0]

        distance_relative = np.asarray(relative_index_from) - np.asarray(relative_index_to)

        if np.linalg.norm(distance_relative) > space_size:
            raise SystemExit('Currently only the next nearest distances are supported, make the bond of the bond '
                             'disorder shorter! ')

        names, sublattices = zip(*self._lattice.sublattices.items())

        if from_sub not in names:
            raise SystemExit('Desired initial sublattice doesnt exist in the chosen lattice! ')
        if to_sub not in names:
            raise SystemExit('Desired final sublattice doesnt exist in the chosen lattice! ')

        indx_from = names.index(from_sub)
        lattice_sub_from = sublattices[indx_from]

        indx_to = names.index(to_sub)
        lattice_sub_to = sublattices[indx_to]

        from_sub_id = lattice_sub_from.alias_id
        to_sub_id = lattice_sub_to.alias_id

        nodes_map = self._nodes_map

        nodes_from = []
        nodes_to = []

        h = np.nditer(hoppings, flags=['multi_index'])
        while not h.finished:
            relative_move_from = np.dot(np.asarray(relative_index_from) + 1,
                                        3 ** np.linspace(0, space_size - 1, space_size, dtype=np.int32))
            relative_move_to = np.dot(np.asarray(relative_index_to) + 1,
                                      3 ** np.linspace(0, space_size - 1, space_size, dtype=np.int32))

            if isinstance(hoppings, np.ndarray):
                orb_from = int(relative_move_from +
                               (self._num_orbitals_before[from_sub_id] + h.multi_index[0]) * 3 ** space_size)
                orb_to = int(relative_move_to +
                             (self._num_orbitals_before[to_sub_id] + h.multi_index[1]) * 3 ** space_size)

                self.map_the_orbital(orb_from, nodes_map)
                self.map_the_orbital(orb_to, nodes_map)

                orbital_from.append(orb_from)
                orbital_to.append(orb_to)

                nodes_from.append(nodes_map[orb_from])
                nodes_to.append(nodes_map[orb_to])

                # conjugate
                orbital_from.append(orb_to)
                orbital_to.append(orb_from)

                nodes_from.append(nodes_map[orb_to])
                nodes_to.append(nodes_map[orb_from])

                orbital_hop.append(h[0])
                orbital_hop.append(np.conj(h[0]))

            else:
                orb_from = int(relative_move_from + self._num_orbitals_before[from_sub_id] * 3 ** space_size)
                orb_to = int(relative_move_to + self._num_orbitals_before[to_sub_id] * 3 ** space_size)

                self.map_the_orbital(orb_from, nodes_map)
                self.map_the_orbital(orb_to, nodes_map)

                orbital_from.append(orb_from)
                orbital_to.append(orb_to)

                nodes_from.append(nodes_map[orb_from])
                nodes_to.append(nodes_map[orb_to])

                # conjugate
                orbital_from.append(orb_to)
                orbital_to.append(orb_from)

                nodes_from.append(nodes_map[orb_to])
                nodes_to.append(nodes_map[orb_from])

                orbital_hop.append(h[0])
                orbital_hop.append((h[0].conjugate()))

            h.iternext()

        self._orbital_from.append(orbital_from)
        self._orbital_to.append(orbital_to)

        self._disorder_hopping.append(orbital_hop)

        self._nodes_from.append(nodes_from)
        self._nodes_to.append(nodes_to)

        if len(nodes_map) > self._num_nodes:
            self._num_nodes = len(nodes_map)

    def add_local_onsite_disorder(self, relative_index, sub, value):

        # save the info used for manual scaling
        self._sub_onsite.append(sub)
        self._rel_idx_onsite.append(relative_index)
        self._onsite.append(np.atleast_1d(value))

        orbital_onsite = []
        orbital_onsite_en = []

        nodes_map = self._nodes_map

        vectors = np.asarray(self._lattice.vectors)
        space_size = vectors.shape[0]

        names, sublattices = zip(*self._lattice.sublattices.items())

        if sub not in names:
            raise SystemExit('Desired initial sublattice doesnt exist in the chosen lattice! ')

        indx_sub = names.index(sub)
        lattice_sub = sublattices[indx_sub]

        sub_id = lattice_sub.alias_id

        nodes_onsite = []

        h = np.nditer(value, flags=['multi_index'])
        while not h.finished:
            relative_move = np.dot(np.asarray(relative_index) + 1,
                                   3 ** np.linspace(0, space_size - 1, space_size, dtype=np.int32))

            if isinstance(value, np.ndarray):
                orb = int(relative_move + (self._num_orbitals_before[sub_id] + h.multi_index[0]) * 3 ** space_size)

                self.map_the_orbital(orb, nodes_map)

                orbital_onsite_en.append(h[0])

                nodes_onsite.append(nodes_map[orb])
                orbital_onsite.append(orb)
            else:
                orb = int(relative_move + self._num_orbitals_before[sub_id] * 3 ** space_size)

                self.map_the_orbital(orb, nodes_map)

                orbital_onsite_en.append(h[0])
                nodes_onsite.append(nodes_map[orb])
                orbital_onsite.append(orb)
            h.iternext()

        self._orbital_onsite.append(orbital_onsite)

        self._disorder_onsite.append(orbital_onsite_en)

        self._nodes_onsite.append(nodes_onsite)

        if len(nodes_map) > self._num_nodes:
            self._num_nodes = len(nodes_map)


# Class that introduces Disorder into the initially built lattice.
# The informations about the disorder are the type, mean value, and standard deviation. The function that you could use
# in the bulding of the lattice is add_disorder. The class method takes care of the shape of the disorder chosen (it
# needs to be same as the number of orbitals at a given atom), and takes care of the conversion to the c++ orbital-only
# format.
class Disorder:
    def __init__(self, lattice):
        # type of the disorder, can be 'Gaussian', 'Uniform' and 'Deterministic'.
        self._type = []
        # type_id of the disorder, can be 'Gaussian': 1, 'Uniform': 2 and 'Deterministic': 3.
        self._type_id = []
        # mean value of the disorder.
        self._mean = []
        # standard deviation of the disorder.
        self._stdv = []
        # orbital that has the chosen disorder.
        self._orbital = []
        # sublattice that has the chosen disorder.
        self._sub_name = []

        num_orbitals = np.zeros(lattice.nsub, dtype=np.uint64)
        for name, sub in lattice.sublattices.items():
            # num of orbitals at each sublattice is equal to size of onsite energy
            num_energies = np.asarray(sub.energy).shape[0]
            num_orbitals[sub.alias_id] = num_energies
        self._num_orbitals_total = np.sum(np.asarray(num_orbitals))
        self._num_orbitals = np.asarray(num_orbitals)
        self._num_orbitals_before = np.cumsum(np.asarray(num_orbitals)) - num_orbitals
        self._lattice = lattice

    # class method that introduces the disorder to the lattice
    def add_disorder(self, sublattice, dis_type, mean_value, standard_deviation=0.):
        if isinstance(dis_type, list):
            if isinstance(sublattice, list):
                for indx, name in enumerate(sublattice):
                    self.add_local_disorder(name, dis_type[indx], mean_value[indx], standard_deviation[indx])
            else:
                self.add_local_disorder(sublattice, dis_type, mean_value, standard_deviation)

        else:
            self.add_local_disorder(sublattice, [dis_type], [mean_value], [standard_deviation])

    def add_local_disorder(self, sublattice_name, dis_type, mean_value, standard_deviation):

        vectors = np.asarray(self._lattice.vectors)
        space_size = vectors.shape[0]

        names, sublattices = zip(*self._lattice.sublattices.items())

        if sublattice_name not in names:
            raise SystemExit('Desired sublattice doesnt exist in the chosen lattice! ')
        indx = names.index(sublattice_name)
        lattice_sub = sublattices[indx]
        size_orb = self._num_orbitals[lattice_sub.alias_id]

        hopping = {'relative_index': np.zeros(space_size, dtype=np.int32), 'from_id': lattice_sub.alias_id,
                   'to_id': lattice_sub.alias_id, 'mean_value': lattice_sub.energy}

        # number of orbitals before i-th sublattice, where is is the array index
        orbitals_before = self._num_orbitals_before

        orbital_from = self._orbital
        orbital_to = []
        orbital_dis_mean = self._mean
        orbital_dis_stdv = self._stdv
        orbital_dis_type = self._type
        orbital_dis_type_id = self._type_id

        dis_number = {'Gaussian': 1, 'Uniform': 2, 'Deterministic': 3, 'gaussian': 1, 'uniform': 2, 'deterministic': 3}
        for index, it in enumerate(mean_value):
            relative_move = np.dot(hopping['relative_index'] + 1,
                                   3 ** np.linspace(0, space_size - 1, space_size, dtype=np.int32))
            if len(mean_value) > 1:
                orbital_from.append(orbitals_before[hopping['from_id']] + index)
                orbital_to.append(relative_move + (orbitals_before[hopping['to_id']] + index) * 3 ** space_size)
            else:
                orbital_from.append(hopping['from_id'])
                orbital_to.append(relative_move + hopping['to_id'] * 3 ** space_size)
            orbital_dis_mean.append(it)
            orbital_dis_stdv.append(standard_deviation[index])
            orbital_dis_type.append(dis_type[index])
            if dis_type[index] in dis_number:
                orbital_dis_type_id.append(dis_number[dis_type[index]])
                if dis_type[index] == 'Deterministic' or dis_type[index] == 'deterministic':
                    if standard_deviation[index] != 0:
                        raise SystemExit(
                            'Standard deviation of deterministic disorder must be 0.')
            else:
                raise SystemExit(
                    'Disorder not present! Try between Gaussian, Deterministic, and Uniform case insensitive ')

        if not (all(np.asarray(i).shape == size_orb for i in [dis_type, mean_value, standard_deviation])):
            print('Shape of disorder', len(dis_type), len(mean_value), len(standard_deviation),
                  'is different than the number of orbitals at sublattice ', sublattice_name, 'which is', size_orb,
                  '\n')
            raise SystemExit('All parameters should have the same length! ')

        self._sub_name.append(sublattice_name * len(mean_value))
        self._type = orbital_dis_type
        self._type_id = orbital_dis_type_id
        self._mean = orbital_dis_mean
        self._stdv = orbital_dis_stdv
        self._orbital = orbital_from


class Calculation:

    @property
    def get_dos(self):
        """Returns the requested DOS functions."""
        return self._dos

    @property
    def get_conductivity_dc(self):
        """Returns the requested DC conductivity functions."""
        return self._conductivity_dc

    @property
    def get_conductivity_optical(self):
        """Returns the requested optical conductivity functions."""
        return self._conductivity_optical

    @property
    def get_conductivity_optical_nonlinear(self):
        """Returns the requested nonlinear optical conductivity functions."""
        return self._conductivity_optical_nonlinear

    @property
    def get_singleshot_conductivity_dc(self):
        """Returns the requested singleshot DC conductivity functions."""
        return self._singleshot_conductivity_dc

    def __init__(self, configuration=None):

        if configuration is not None and not isinstance(configuration, Configuration):
            raise TypeError("You're forwarding a wrong type!")

        self._scaling_factor = configuration.energy_scale
        self._energy_shift = configuration.energy_shift
        self._dos = []
        self._conductivity_dc = []
        self._conductivity_optical = []
        self._conductivity_optical_nonlinear = []
        self._singleshot_conductivity_dc = []

        self._avail_dir_full = {'xx': 0, 'yy': 1, 'zz': 2, 'xy': 3, 'xz': 4, 'yx': 5, 'yz': 6, 'zx': 7, 'zy': 8}
        self._avail_dir_nonl = {'xxx': 0, 'xxy': 1, 'xxz': 2, 'xyx': 3, 'xyy': 4, 'xyz': 5, 'xzx': 6, 'xzy': 7,
                                'xzz': 8, 'yxx': 9, 'yxy': 10, 'yxz': 11, 'yyx': 12, 'yyy': 13, 'yyz': 14, 'yzx': 15,
                                'yzy': 16, 'yzz': 17, 'zxx': 18, 'zxy': 19, 'zxz': 20, 'zyx': 21, 'zyy': 22, 'zyz': 23,
                                'zzx': 24, 'zzy': 25, 'zzz': 26}
        self._avail_dir_sngl = {'xx': 0, 'yy': 1, 'zz': 2}

    def dos(self, num_points, num_moments, num_random, num_disorder=1):
        """Calculate the density of states as a function of energy

        Parameters
        ----------
        num_points : int
            Number of energy point inside the spectrum at which the DOS will be calculated.
        num_moments : int
            Number of polynomials in the Chebyshev expansion.
        num_random : int
            Number of random vectors to use for the stochastic evaluation of trace.
        num_disorder : int
            Number of different disorder realisations.
        """

        self._dos.append({'num_points': num_points, 'num_moments': num_moments, 'num_random': num_random,
                          'num_disorder': num_disorder})

    def conductivity_dc(self, direction, num_points, num_moments, num_random, num_disorder=1, temperature=0):
        """Calculate the density of states as a function of energy

        Parameters
        ----------
        direction : string
            direction in xyz coordinates along which the conductivity is calculated.
            Supports 'xx', 'yy', 'zz', 'xy', 'xz', 'yx', 'yz', 'zx', 'zy'.
        num_points : int
            Number of energy point inside the spectrum at which the DOS will be calculated.
        num_moments : int
            Number of polynomials in the Chebyshev expansion.
        num_random : int
            Number of random vectors to use for the stochastic evaluation of trace.
        num_disorder : int
            Number of different disorder realisations.
        temperature : float
            Value of the temperature at which we calculate the response.
        """
        if direction not in self._avail_dir_full:
            print('The desired direction is not available. Choose from a following set: \n',
                  self._avail_dir_full.keys())
            raise SystemExit('Invalid direction!')
        else:
            self._conductivity_dc.append(
                {'direction': self._avail_dir_full[direction], 'num_points': num_points, 'num_moments': num_moments,
                 'num_random': num_random, 'num_disorder': num_disorder,
                 'temperature': temperature})

    def conductivity_optical(self, direction, num_points, num_moments, num_random, num_disorder=1, temperature=0):
        """Calculate the density of states as a function of energy

        Parameters
        ----------
        direction : string
            direction in xyz coordinates along which the conductivity is calculated.
            Supports 'xx', 'yy', 'zz', 'xy', 'xz', 'yx', 'yz', 'zx', 'zy'.
        num_points : int
            Number of energy point inside the spectrum at which the DOS will be calculated.
        num_moments : int
            Number of polynomials in the Chebyshev expansion.
        num_random : int
            Number of random vectors to use for the stochastic evaluation of trace.
        num_disorder : int
            Number of different disorder realisations.
        temperature : float
            Value of the temperature at which we calculate the response.
        """
        if direction not in self._avail_dir_full:
            print('The desired direction is not available. Choose from a following set: \n',
                  self._avail_dir_full.keys())
            raise SystemExit('Invalid direction!')
        else:
            self._conductivity_optical.append(
                {'direction': self._avail_dir_full[direction], 'num_points': num_points, 'num_moments': num_moments,
                 'num_random': num_random, 'num_disorder': num_disorder,
                 'temperature': temperature})

    def conductivity_optical_nonlinear(self, direction, num_points, num_moments, num_random, num_disorder=1,
                                       temperature=0, **kwargs):
        """Calculate the density of states as a function of energy

        Parameters
        ----------
        direction : string
            direction in xyz coordinates along which the conductivity is calculated.
            Supports all the combinations of the direction x, y and z with length 3 like 'xxx','zzz', 'xxy', 'xxz' etc.
        num_points : int
            Number of energy point inside the spectrum at which the DOS will be calculated.
        num_moments : int
            Number of polynomials in the Chebyshev expansion.
        num_random : int
            Number of random vectors to use for the stochastic evaluation of trace.
        num_disorder : int
            Number of different disorder realisations.
        temperature : float
            Value of the temperature at which we calculate the response.

            Optional parameters, forward special, a parameter that can simplify the calculation for some materials.
        """

        if direction not in self._avail_dir_nonl:
            print('The desired direction is not available. Choose from a following set: \n',
                  self._avail_dir_nonl.keys())
            raise SystemExit('Invalid direction!')
        else:
            special = kwargs.get('special', 0)

            self._conductivity_optical_nonlinear.append(
                {'direction': self._avail_dir_nonl[direction], 'num_points': num_points,
                 'num_moments': num_moments, 'num_random': num_random, 'num_disorder': num_disorder,
                 'temperature': temperature, 'special': special})

    def singleshot_conductivity_dc(self, energy, direction, eta, num_moments, num_random, num_disorder=1, **kwargs):
        """Calculate the density of states as a function of energy

        Parameters
        ----------
        energy : ndarray or float
            Array or a single value of energies at which singleshot_conductivity_dc will be calculated.
        direction : string
            direction in xyz coordinates along which the conductivity is calculated.
            Supports 'xx', 'yy', 'zz'.
        eta : Float
            Parameter that affects the broadening of the kernel function.
        num_moments : int
            Number of polynomials in the Chebyshev expansion.
        num_random : int
            Number of random vectors to use for the stochastic evaluation of trace.
        num_disorder : int
            Number of different disorder realisations.
        **kwargs: Optional arguments preserve_disorder.

        """

        preserve_disorder = kwargs.get('preserve_disorder', False)
        if direction not in self._avail_dir_sngl:
            print('The desired direction is not available. Choose from a following set: \n',
                  self._avail_dir_sngl.keys())
            raise SystemExit('Invalid direction!')
        else:
            self._singleshot_conductivity_dc.append(
                {'energy': (np.atleast_1d(energy)),
                 'direction': self._avail_dir_sngl[direction],
                 'eta': np.atleast_1d(eta), 'num_moments': np.atleast_1d(num_moments),
                 'num_random': num_random, 'num_disorder': num_disorder,
                 'preserve_disorder': np.atleast_1d(preserve_disorder)})


class Configuration:

    def __init__(self, divisions=(1, 1), length=(1, 1), boundaries=(False, False), is_complex=False, precision=1,
                 spectrum_range=None):
        """Define basic parameters used in the calculation

       Parameters
       ----------
       divisions : int, tuple(int, int), tuple(int, int, int)
           Number of decomposition parts of the system.
       length : int, tuple(int, int), tuple(int, int, int)
           Number of unit cells in each direction.
       boundaries : int, tuple(int, int), tuple(int, int, int)
           Periodic boundary conditions each direction.
       is_complex : bool
           Boolean that reflects whether the type of Hamiltonian is complex or not.
       precision : int
            Integer which defines the precision of the number used in the calculation. Float - 0, double - 1,
            long double - 2.
       spectrum_range : Optional[Tuple[float, float]]
            Energy scale which defines the scaling factor of all the energy related parameters. The scaling is done
            automatically in the background after this definition. If the term is not specified, a rough estimate of the
            bounds is found.
       """

        if spectrum_range:
            self._energy_scale = (spectrum_range[1] - spectrum_range[0]) / 2
            self._energy_shift = (spectrum_range[1] + spectrum_range[0]) / 2
        else:
            self._energy_scale = None
            self._energy_shift = None

        self._is_complex = int(is_complex)
        self._precision = precision
        self._divisions = divisions
        self._boundaries = np.asarray(boundaries).astype(int)

        self._length = length
        self._htype = np.float32
        self.set_type()

    def set_type(self, ):
        if self._is_complex == 0:
            if self._precision == 0:
                self._htype = np.float32
            elif self._precision == 1:
                self._htype = np.float64
            elif self._precision == 2:
                self._htype = np.float128
            else:
                raise SystemExit('Precision should be 0, 1 or 2')
        else:
            if self._precision == 0:
                self._htype = np.complex64
            elif self._precision == 1:
                self._htype = np.complex128
            elif self._precision == 2:
                self._htype = np.complex256

    @property
    def energy_scale(self):
        """Returns the energy scale of the hopping parameters."""
        return self._energy_scale

    @property
    def energy_shift(self):
        """Returns the energy shift of the hopping parameters around which the spectrum is centered."""
        return self._energy_shift

    @property
    def comp(self):  # -> is_complex:
        """Returns 0 if hamiltonian is real and 1 elsewise."""
        return self._is_complex

    @property
    def prec(self):  # -> precision:
        """Returns 0, 1, 2 if precision if float, double, and long double respectively."""
        return self._precision

    @property
    def div(self):  # -> divisions:
        """Returns the number of decomposed elements of matrix in x, y and/or z direction. Their product gives the total
        number of threads spawn."""
        return self._divisions

    @property
    def bound(self):  # -> boundaries:
        """Returns the boundary conditions in each direction, 0 - no boundary condtions, 1 - peridoc bc. """
        return self._boundaries

    @property
    def leng(self):  # -> length:
        """Return the number of unit cell repetitions in each direction. """
        return self._length

    @property
    def type(self):  # -> type:
        """Return the type of the Hamiltonian complex or real, and float, double or long double. """
        return self._htype


def make_pybinding_model(lattice, disorder=None, disorder_structural=None, **kwargs):
    """Build a Pybinding model with disorder used in Kite. Bond disorder is not currently supported.

    Parameters
    ----------
    lattice : pb.Lattice
        Pybinding lattice object that carries the info about the unit cell vectors, unit cell cites, hopping terms and
        onsite energies.
    disorder : Disorder
        Class that introduces Disorder into the initially built lattice. For more info check the Disorder class.
    disorder_structural : StructuralDisorder
        Class that introduces StructuralDisorder into the initially built lattice. For more info check the
        StructuralDisorder class.
    **kwargs: Optional arguments like shape .

    """

    shape = kwargs.get('shape', None)
    if disorder_structural:
        # check if there's a bond disorder term
        # return an error if so
        disorder_struc_list = disorder_structural
        if not isinstance(disorder_structural, list):
            disorder_struc_list = [disorder_structural]

        for idx_struc, dis_struc in enumerate(disorder_struc_list):
            if len(dis_struc._sub_from):
                raise SystemExit(
                    'Automatic scaling is not supported when bond disorder is specified. Please select the scaling '
                    'bounds manually.')

    def gaussian_disorder(sub, mean_value, stdv):
        """Add gaussian disorder with selected mean value and standard deviation to the pybinding model.

        Parameters
        ----------
        sub : str
            Select a sublattice where disorder should be added.
        mean_value : float
            Select a mean value of the disorder.
        stdv : float
            Select standard deviation of the disorder.
        """

        @pb.onsite_energy_modifier
        def modify_energy(energy, sub_id):
            rand_onsite = np.random.normal(loc=mean_value, scale=stdv, size=len(energy[sub_id == sub]))
            energy[sub_id == sub] += rand_onsite
            return energy

        return modify_energy

    def deterministic_disorder(sub, mean_value):
        """Add deterministic disorder with selected mean value to the Pybinding model.

        Parameters
        ----------
        sub : str
            Select a sublattice where disorder should be added.
        mean_value : float
            Select a mean value of the disorder.

        """

        @pb.onsite_energy_modifier
        def modify_energy(energy, sub_id):
            onsite = mean_value * np.ones(len(energy[sub_id == sub]))
            energy[sub_id == sub] += onsite
            return energy

        return modify_energy

    def uniform_disorder(sub, mean_value, stdv):
        """Add uniform disorder with selected mean value and standard deviation to the Pybinding model.

        Parameters
        ----------
        sub : str
            Select a sublattice where disorder should be added.
        mean_value : float
            Select a mean value of the disorder.
        stdv : float
            Select standard deviation of the disorder.
        """

        @pb.onsite_energy_modifier
        def modify_energy(energy, sub_id):
            a = mean_value - stdv * np.sqrt(3)
            b = mean_value + stdv * np.sqrt(3)

            rand_onsite = np.random.uniform(low=a, high=b, size=len(energy[sub_id == sub]))
            energy[sub_id == sub] += rand_onsite

            return energy

        return modify_energy

    def vacancy_disorder(sub, concentration):
        """Add vacancy disorder with selected concentration to the Pybinding model.

        Parameters
        ----------
        sub : str
            Select a sublattice where disorder should be added.
        concentration : float
            Concentration of the vacancy disorder.
        """

        @pb.site_state_modifier(min_neighbors=2)
        def modifier(state, sub_id):
            rand_vec = np.random.rand(len(state))
            vacant_sublattice = np.logical_and(sub_id == sub, rand_vec < concentration)

            state[vacant_sublattice] = False
            return state

        return modifier

    def local_onsite_disorder(positions, value):
        """Add onsite disorder as a part of StructuralDisorder class to the Pybinding model.

        Parameters
        ----------
        positions : np.ndarray
            Select positions where disorder should appear
        value : np.ndarray
            Value of the disordered onsite term.
        """
        space_size = np.array(positions).shape[1]

        @pb.onsite_energy_modifier
        def modify_energy(x, y, z, energy):
            # all_positions = np.column_stack((x, y, z))[0:space_size, :]
            all_positions = np.stack([x, y, z], axis=1)[:, 0:space_size]

            kdtree1 = cKDTree(positions)
            kdtree2 = cKDTree(all_positions)

            d_max = 0.05
            # find the closest elements between two trees, with d < d_max. Finds the desired elements from the
            # parameters x, y, z being used inside the modifier function.
            coo = kdtree1.sparse_distance_matrix(kdtree2, d_max, output_type='coo_matrix')

            energy[coo.col] += value

            return energy

        return modify_energy

    if not shape:
        referent_size = 100
        a1, a2 = lattice.vectors
        norm_a1 = np.linalg.norm(a1)
        norm_a2 = np.linalg.norm(a2)
        num_a1 = referent_size / norm_a1
        num_a2 = referent_size / norm_a2
        shape = pb.rectangle(4 * num_a1 * norm_a1, 4 * num_a2 * norm_a2)
        trans_symm = pb.translational_symmetry(a1=num_a1 * norm_a1, a2=num_a2 * norm_a2)
        param = [shape, trans_symm]
    else:
        param = [shape]

    model = pb.Model(lattice, *param)

    if disorder:
        disorder_list = disorder
        if not isinstance(disorder, list):
            disorder_list = [disorder]
        for dis in disorder_list:
            for idx in range(len(dis._type)):
                if dis._type[idx].lower() == 'uniform':
                    model.add(
                        uniform_disorder(dis._sub_name[idx], dis._mean[idx], dis._stdv[idx]))
                if dis._type[idx].lower() == 'gaussian':
                    model.add(
                        gaussian_disorder(dis._sub_name[idx], dis._mean[idx], dis._stdv[idx]))
                if dis._type[idx].lower() == 'deterministic':
                    model.add(deterministic_disorder(dis._sub_name[idx], dis._mean[idx]))

    if disorder_structural:

        disorder_struc_list = disorder_structural
        if not isinstance(disorder_structural, list):
            disorder_struc_list = [disorder_structural]

        for idx_struc, dis_struc in enumerate(disorder_struc_list):
            num_sites = model.system.num_sites
            rand_vec = np.random.rand(num_sites)
            space_size = np.array(lattice.vectors).shape[0]

            for vac in dis_struc._vacancy_sub:
                model.add(vacancy_disorder(sub=vac, concentration=dis_struc._concentration))

            for idx in range(len(dis_struc._sub_onsite)):
                names, sublattices = zip(*model.lattice.sublattices.items())

                sublattice_alias = names.index(dis_struc._sub_onsite[idx])

                select_sublattice = model.system.sublattices == sublattice_alias
                sub_and_rand = np.logical_and(select_sublattice, rand_vec < dis_struc._concentration)

                # generates a set of random positions that will be added to the nodes in structural disorder, problem
                # because when only one sublattice is selected, effective concentration will be lower
                positions = np.stack([model.system.positions.x[sub_and_rand],
                                      model.system.positions.y[sub_and_rand],
                                      model.system.positions.z[sub_and_rand]], axis=1)[:, 0:space_size]

                # ref_pos = np.stack([model.system.positions.x[def_site_idx], model.system.positions.y[def_site_idx],
                #                     model.system.positions.z[def_site_idx]], axis=1)[:, 0:space_size]

                # get the position of onsite disordered sublattice
                vectors = np.array(lattice.vectors)[:, 0:space_size]
                pos_sub = lattice.sublattices[dis_struc._sub_onsite[idx]].position[0:space_size]

                # make an array of positions of sites where the onsite disorder will be added
                pos = pos_sub + np.dot(vectors.T, np.array(dis_struc._rel_idx_onsite[idx]))
                select_pos = positions + pos

                # add the onsite with value dis_struc._onsite[idx]
                model.add(local_onsite_disorder(select_pos, dis_struc._onsite[idx]))

    return model


def estimate_bounds(lattice, disorder=None, disorder_structural=None):
    model = make_pybinding_model(lattice, disorder, disorder_structural)
    kpm = pb.kpm(model)
    a, b = kpm.scaling_factors
    return -a + b, a + b


def config_system(lattice, config, calculation, **kwargs):
    """Export the lattice and related parameters to the *.h5 file

    Parameters
    ----------
    lattice : pb.Lattice
        Pybinding lattice object that carries the info about the unit cell vectors, unit cell cites, hopping terms and
        onsite energies.
    config : Configuration
        Configuration object, basic parameters defining size, precision, energy scale and number of decomposition parts
        in the calculation.
    calculation : Calculation
        Calculation object that defines the requested functions for the calculation.
    **kwargs: Optional arguments like filename, Disorder or Disorder_structural.

    """

    print('##############################################################################')
    print('#                        KITE | Pre-Release Beta 0.1                         #')
    print('#                                                                            #')
    print('#                        Kite home: quantum-kite.com                         #')
    print('#                                                                            #')
    print('#                                                                            #')
    print('#                                                                            #')
    print('#  Developed by: Simao M. Joao, Joao V. Lopes, Tatiana G. Rappoport,         #')
    print('#                                                                            #')
    print('#  Misa Andelkovic, Lucian Covaci, Aires Ferreira, 2018                      #')
    print('#                                                                            #')
    print('#                                                                            #')
    print('##############################################################################')

    # hamiltonian is complex 1 or real 0
    complx = int(config.comp)

    # check if there are complex hoppings but identifier is_complex is 0
    imag_part = 0
    # loop through all hoppings
    for name, hop in lattice.hoppings.items():
        imag_part += np.linalg.norm(np.asarray(hop.energy).imag)
    if imag_part > 0 and complx == 0:
        print('Complex hoppings are added but is_complex identifier is 0. Automatically turning is_complex to 1!')
        config._is_complex = 1
        config.set_type()

    # hamiltonian is complex 1 or real 0
    complx = int(config.comp)

    filename = kwargs.get('filename', 'kite_config.h5')

    disorder = kwargs.get('disorder', None)
    disorder_structural = kwargs.get('disorder_structural', None)
    print('\n##############################################################################\n')
    print('SCALING:\n')
    # if bounds are not specified, find a rough estimate
    if not config.energy_scale:
        print('\nAutomatic scaling is being done. If unexpected results are produced, consider '
              '\nselecting the bounds manually. '
              '\nEstimate of the spectrum bounds with a safety factor is: ')
        e_min, e_max = estimate_bounds(lattice, disorder, disorder_structural)
        print('({:.2f}, {:.2f} eV)\n'.format(e_min, e_max))
        # add a safety factor for a scaling factor
        config._energy_scale = (e_max - e_min) / (2 * 0.9)
        config._energy_shift = (e_max + e_min) / 2
    else:
        print('\nManual scaling is chosen. \n')
    print('\n##############################################################################\n')
    print('BOUNDARY CONDITIONS:\n')

    vectors = np.asarray(lattice.vectors)
    space_size = vectors.shape[0]
    vectors = vectors[:, 0:space_size]

    # iterate through all the sublattices and add onsite energies to hoppings list
    # count num of orbitals and read the atom positions.
    hoppings = []
    # get number of orbitals at each atom.
    num_orbitals = np.zeros(lattice.nsub, dtype=np.int64)
    # get all atom positions to the position array.
    position_atoms = np.zeros([lattice.nsub, space_size], dtype=np.float64)
    for name, sub in lattice.sublattices.items():
        # num of orbitals at each sublattice is equal to size of onsite energy
        num_energies = np.asarray(sub.energy).shape[0]
        num_orbitals[sub.alias_id] = num_energies
        # position_atoms is a list of vectors of size space_size
        position_atoms[sub.alias_id, :] = sub.position[0:space_size]
        # define hopping dict from relative hopping index from and to id (relative number of sublattice in relative
        # index lattice) and onsite
        # energy shift is substracted from onsite potential, this is later added to the hopping dictionary,
        # hopping terms shouldn't be substracted
        hopping = {'relative_index': np.zeros(space_size, dtype=np.int32), 'from_id': sub.alias_id,
                   'to_id': sub.alias_id, 'hopping_energy': sub.energy - config.energy_shift}
        hoppings.append(hopping)

    # num_orbitals = np.asarray(num_orbitals)
    position_atoms = np.array(position_atoms)
    # repeats the positions of atoms based on the number of orbitals
    position = np.repeat(position_atoms, num_orbitals, axis=0)

    # iterate through all the hoppings and add hopping energies to hoppings list
    for name, hop in lattice.hoppings.items():
        hopping_energy = hop.energy
        for term in hop.terms:
            hopping = {'relative_index': term.relative_index[0:space_size], 'from_id': term.from_id,
                       'to_id': term.to_id, 'hopping_energy': hopping_energy}
            hoppings.append(hopping)
            # if the unit cell is [0, 0]
            if np.linalg.norm(term.relative_index[0:space_size]) == 0:
                hopping = {'relative_index': term.relative_index[0:space_size], 'from_id': term.to_id,
                           'to_id': term.from_id, 'hopping_energy': np.conj(hopping_energy)}
                hoppings.append(hopping)
            # if the unit cell [i, j] is different than [0, 0] and also -[i, j] hoppings with opposite direction
            if np.linalg.norm(term.relative_index[0:space_size]):
                hopping = {'relative_index': -term.relative_index[0:space_size], 'from_id': term.to_id,
                           'to_id': term.from_id, 'hopping_energy': np.conj(hopping_energy)}
                hoppings.append(hopping)

    orbital_from = []
    orbital_to = []
    orbital_hop = []
    # number of orbitals before i-th sublattice, where is is the array index
    orbitals_before = np.cumsum(num_orbitals) - num_orbitals
    # iterate through all hoppings, and define unique orbital hoppings
    # orbital_to in unit cell [i, j] is defined  as [i, j] x [1, 3] + relative_orbital_num*3**2 2D
    # orbital_to in unit cell [i, j, k] is defined  as [i, j, k] x [1, 3, 9] + relative_orbital_num*3**3 3D
    # relative index of orbital_from is unique as only hoppings from the orbitals in the initial unit cell are exported
    for h in hoppings:
        hopping_energy = h['hopping_energy']
        it = np.nditer(hopping_energy, flags=['multi_index'])
        while not it.finished:
            relative_move = np.dot(h['relative_index'] + 1,
                                   3 ** np.linspace(0, space_size - 1, space_size, dtype=np.int32))
            # if hopping_energy.size > 1:
            orbital_from.append(orbitals_before[h['from_id']] + it.multi_index[0])
            orbital_to.append(relative_move + (orbitals_before[h['to_id']] + it.multi_index[1]) * 3 ** space_size)
            # else:
            #     orbital_from.append(h['from_id'])
            #     orbital_to.append(relative_move + h['to_id'] * 3 ** space_size)

            orbital_hop.append(it[0] if complx else np.real(it[0]))

            it.iternext()

    # extract t - hoppings where each row corresponds to hopping from row number orbital and d - for each hopping it's
    # unique identifier
    t_list = []
    d_list = []
    # make a sparse matrix from orbital_hop, and (orbital_from, orbital_to) as it's easier to take nonzero hoppings from
    # sparse matrix
    matrix = coo_matrix((orbital_hop, (orbital_from, orbital_to)),
                        shape=(np.max(orbital_from) + 1, np.max(orbital_to) + 1))
    # num_hoppings is a vector where each value corresponds to num of hoppings from orbital equal to it's index
    num_hoppings = np.zeros(matrix.shape[0])
    # iterate through all rows of matrix, number of row = number of orbital from

    for i in range(matrix.shape[0]):
        # all hoppings from orbital i
        row_mat = matrix.getrow(i)
        # number of hoppings from orbital i
        num_hoppings[i] = row_mat.size

        t_list.append(row_mat.data)
        d_list.append(row_mat.indices)

    # fix the size of hopping and distance matrices, where the number of columns is max number of hoppings
    max_hop = int(np.max(num_hoppings))
    d = np.zeros((matrix.shape[0], max_hop))
    t = np.zeros((matrix.shape[0], max_hop), dtype=matrix.data.dtype)
    for i_row, d_row in enumerate(d_list):
        t_row = t_list[i_row]
        d[i_row, :len(d_row)] = d_row
        t[i_row, :len(t_row)] = t_row

    f = hp.File(filename, 'w')

    f.create_dataset('IS_COMPLEX', data=complx, dtype='u4')
    # precision of hamiltonian float, double, long double
    f.create_dataset('PRECISION', data=config.prec, dtype='u4')
    # number of repetitions in each of the directions
    f.create_dataset('L', data=config.leng, dtype='u4')
    # periodic boundary conditions, 0 - no, 1 - yes.
    bound = config.bound
    print('\nPeriodic boundary conditions along the direction of lattice vectors \n'
          'respectively are set to: ', bool(bound[0]), 'and ', bool(bound[1]), '\n')
    f.create_dataset('Boundaries', data=bound, dtype='u4')
    print('\n##############################################################################\n')
    print('DECOMPOSITION:\n')

    # number of divisions of the in each direction of hamiltonian. nx x ny = num_threads
    print('\nChosen number of decomposition parts is:', config.div[0], 'x', config.div[1], '.'
                                                                                           '\nINFO: this product will correspond to the total number of threads. '
                                                                                           '\nYou should choose at most the number of processor cores you have.'
                                                                                           '\nWARNING: System size need\'s to be an integer multiple of \n'
                                                                                           '[STRIDE * ', config.div[0],
          ' and STRIDE * ', config.div[1], '] '
                                           '\nwhere STRIDE is selected when compiling the C++ code. \n')

    f.create_dataset('Divisions', data=config.div, dtype='u4')
    # space dimension of the lattice 1D, 2D, 3D
    f.create_dataset('DIM', data=space_size, dtype='u4')
    # lattice vectors. Size is same as DIM
    f.create_dataset('LattVectors', data=vectors, dtype=np.float64)
    # position for each atom
    f.create_dataset('OrbPositions', data=position, dtype=np.float64)
    # total number of orbitals
    f.create_dataset('NOrbitals', data=np.sum(num_orbitals), dtype='u4')
    # scaling factor for the hopping parameters
    f.create_dataset('EnergyScale', data=config.energy_scale, dtype=np.float64)
    # shift factor for the hopping parameters
    f.create_dataset('EnergyShift', data=config.energy_shift, dtype=np.float64)
    # Hamiltonian group
    grp = f.create_group('Hamiltonian')
    # Hamiltonian group
    grp.create_dataset('NHoppings', data=num_hoppings, dtype='u4')
    # distance
    grp.create_dataset('d', data=d, dtype='i4')

    if complx:
        # hoppings
        grp.create_dataset('Hoppings', data=(t.astype(config.type)) / config.energy_scale)
    else:
        # hoppings
        grp.create_dataset('Hoppings', data=(t.real.astype(config.type)) / config.energy_scale)

    grp_dis = grp.create_group('Disorder')

    if disorder:
        grp_dis.create_dataset('OnsiteDisorderModelType', data=disorder._type_id, dtype=np.int32)
        grp_dis.create_dataset('OrbitalNum', data=disorder._orbital, dtype=np.int32)
        # no need to substract config.energy_scale from mean value as it's already subtracted once from onsite energy
        grp_dis.create_dataset('OnsiteDisorderMeanValue',
                               data=(np.array(disorder._mean)) / config.energy_scale,
                               dtype=np.float64)
        grp_dis.create_dataset('OnsiteDisorderMeanStdv', data=np.array(disorder._stdv) / config.energy_scale,
                               dtype=np.float64)
    else:
        grp_dis.create_dataset('OnsiteDisorderModelType', (1, 0))
        grp_dis.create_dataset('OrbitalNum', (1, 0))
        grp_dis.create_dataset('OnsiteDisorderMeanValue', (1, 0))
        grp_dis.create_dataset('OnsiteDisorderMeanStdv', (1, 0))

    grp_dis_vac = grp.create_group('Vacancy')
    idx_vacancy = 0
    grp_dis = grp.create_group('StructuralDisorder')
    if disorder_structural:

        if isinstance(disorder_structural, list):
            num_dis = len(disorder_structural)
        else:
            num_dis = 1
            disorder_structural = [disorder_structural]

        for idx in range(num_dis):

            disorder_struct = disorder_structural[idx]

            num_orb_vac = len(disorder_struct._orbital_vacancy)
            if num_orb_vac > 0:
                grp_dis_type = grp_dis_vac.create_group('Type{val}'.format(val=idx_vacancy))
                grp_dis_type.create_dataset('Orbitals', data=np.asarray(disorder_struct._orbital_vacancy),
                                            dtype=np.int32)
                grp_dis_type.create_dataset('Concentration', data=disorder_struct._concentration,
                                            dtype=np.float64)
                grp_dis_type.create_dataset('NumOrbitals', data=num_orb_vac, dtype=np.int32)
                idx_vacancy += 1

            if disorder_struct._num_bond_disorder_per_type or disorder_struct._num_onsite_disorder_per_type:
                # Type idx
                grp_dis_type = grp_dis.create_group('Type{val}'.format(val=idx))
                # Concentration of this type
                grp_dis_type.create_dataset('Concentration', data=np.asarray(disorder_struct._concentration),
                                            dtype=np.float64)
                # Number of bond disorder
                grp_dis_type.create_dataset('NumBondDisorder',
                                            data=2 * np.asarray(disorder_struct._num_bond_disorder_per_type),
                                            dtype=np.int32)
                # Number of onsite disorder
                grp_dis_type.create_dataset('NumOnsiteDisorder',
                                            data=np.asarray(disorder_struct._num_onsite_disorder_per_type),
                                            dtype=np.int32)

                # Node of the bond disorder from
                grp_dis_type.create_dataset('NodeFrom', data=np.asarray(disorder_struct._nodes_from).flatten(),
                                            dtype=np.int32)
                # Node of the bond disorder to
                grp_dis_type.create_dataset('NodeTo', data=np.asarray(disorder_struct._nodes_to).flatten(),
                                            dtype=np.int32)
                # Node of the onsite disorder
                grp_dis_type.create_dataset('NodeOnsite', data=np.asarray(disorder_struct._nodes_onsite),
                                            dtype=np.int32)

                # Num nodes
                grp_dis_type.create_dataset('NumNodes', data=disorder_struct._num_nodes, dtype=np.int32)
                # Orbital mapped for this node
                grp_dis_type.create_dataset('NodePosition', data=np.asarray(disorder_struct._node_orbital),
                                            dtype=np.uint32)

                # Onsite disorder energy
                grp_dis_type.create_dataset('U0',
                                            data=(np.asarray(disorder_struct._disorder_onsite).real.astype(
                                                config.type)) / config.energy_scale)
                # Bond disorder hopping
                disorder_hopping = disorder_struct._disorder_hopping
                if complx:
                    # hoppings
                    grp_dis_type.create_dataset('Hopping',
                                                data=(np.asarray(disorder_hopping).astype(
                                                    config.type).flatten()) / config.energy_scale)
                else:
                    # hoppings
                    grp_dis_type.create_dataset('Hopping',
                                                data=(np.asarray(disorder_hopping).real.astype(
                                                    config.type).flatten()) / config.energy_scale)

    # Calculation function defined with num_moments, num_random vectors, and num_disorder etc. realisations
    grpc = f.create_group('Calculation')
    if calculation.get_dos:
        grpc_p = grpc.create_group('dos')

        moments, random, point, dis, temp, direction = [], [], [], [], [], []
        for single_dos in calculation.get_dos:
            moments.append(single_dos['num_moments'])
            random.append(single_dos['num_random'])
            point.append(single_dos['num_points'])
            dis.append(single_dos['num_disorder'])

        if len(calculation.get_dos) > 1:
            raise SystemExit('Only a single function request of each type is currently allowed. Please use another '
                             'configuration file for the same functionality.')
        grpc_p.create_dataset('NumMoments', data=moments, dtype=np.int32)
        grpc_p.create_dataset('NumRandoms', data=random, dtype=np.int32)
        grpc_p.create_dataset('NumPoints', data=point, dtype=np.int32)
        grpc_p.create_dataset('NumDisorder', data=dis, dtype=np.int32)

    if calculation.get_conductivity_dc:
        grpc_p = grpc.create_group('conductivity_dc')

        moments, random, point, dis, temp, direction = [], [], [], [], [], []
        for single_cond_dc in calculation.get_conductivity_dc:
            moments.append(single_cond_dc['num_moments'])
            random.append(single_cond_dc['num_random'])
            point.append(single_cond_dc['num_points'])
            dis.append(single_cond_dc['num_disorder'])
            temp.append(single_cond_dc['temperature'])
            direction.append(single_cond_dc['direction'])

        if len(calculation.get_conductivity_dc) > 1:
            raise SystemExit('Only a single function request of each type is currently allowed. Please use another '
                             'configuration file for the same functionality.')
        grpc_p.create_dataset('NumMoments', data=np.asarray(moments), dtype=np.int32)
        grpc_p.create_dataset('NumRandoms', data=np.asarray(random), dtype=np.int32)
        grpc_p.create_dataset('NumPoints', data=np.asarray(point), dtype=np.int32)
        grpc_p.create_dataset('NumDisorder', data=np.asarray(dis), dtype=np.int32)
        grpc_p.create_dataset('Temperature', data=np.asarray(temp) / config.energy_scale, dtype=np.float64)
        grpc_p.create_dataset('Direction', data=np.asarray(direction), dtype=np.int32)

    if calculation.get_conductivity_optical:
        grpc_p = grpc.create_group('conductivity_optical')

        moments, random, point, dis, temp, direction = [], [], [], [], [], []
        for single_cond_opt in calculation.get_conductivity_optical:
            moments.append(single_cond_opt['num_moments'])
            random.append(single_cond_opt['num_random'])
            point.append(single_cond_opt['num_points'])
            dis.append(single_cond_opt['num_disorder'])
            temp.append(single_cond_opt['temperature'])
            direction.append(single_cond_opt['direction'])

        if len(calculation.get_conductivity_optical) > 1:
            raise SystemExit('Only a single function request of each type is currently allowed. Please use another '
                             'configuration file for the same functionality.')
        grpc_p.create_dataset('NumMoments', data=np.asarray(moments), dtype=np.int32)
        grpc_p.create_dataset('NumRandoms', data=np.asarray(random), dtype=np.int32)
        grpc_p.create_dataset('NumPoints', data=np.asarray(point), dtype=np.int32)
        grpc_p.create_dataset('NumDisorder', data=np.asarray(dis), dtype=np.int32)
        grpc_p.create_dataset('Temperature', data=np.asarray(temp) / config.energy_scale, dtype=np.float64)
        grpc_p.create_dataset('Direction', data=np.asarray(direction), dtype=np.int32)

    if calculation.get_conductivity_optical_nonlinear:
        grpc_p = grpc.create_group('conductivity_optical_nonlinear')

        moments, random, point, dis, temp, direction, special = [], [], [], [], [], [], []
        for single_cond_opt_non in calculation.get_conductivity_optical_nonlinear:
            moments.append(single_cond_opt_non['num_moments'])
            random.append(single_cond_opt_non['num_random'])
            point.append(single_cond_opt_non['num_points'])
            dis.append(single_cond_opt_non['num_disorder'])
            temp.append(single_cond_opt_non['temperature'])
            direction.append(single_cond_opt_non['direction'])
            special.append(single_cond_opt_non['special'])

        if len(calculation.get_conductivity_optical_nonlinear) > 1:
            raise SystemExit('Only a single function request of each type is currently allowed. Please use another '
                             'configuration file for the same functionality.')
        grpc_p.create_dataset('NumMoments', data=np.asarray(moments), dtype=np.int32)
        grpc_p.create_dataset('NumRandoms', data=np.asarray(random), dtype=np.int32)
        grpc_p.create_dataset('NumPoints', data=np.asarray(point), dtype=np.int32)
        grpc_p.create_dataset('NumDisorder', data=np.asarray(dis), dtype=np.int32)
        grpc_p.create_dataset('Temperature', data=np.asarray(temp) / config.energy_scale, dtype=np.float64)
        grpc_p.create_dataset('Direction', data=np.asarray(direction), dtype=np.int32)
        grpc_p.create_dataset('Special', data=np.asarray(special), dtype=np.int32)

    if calculation.get_singleshot_conductivity_dc:
        grpc_p = grpc.create_group('singleshot_conductivity_dc')

        moments, random, dis, energies, eta, direction, preserve_disorder = [], [], [], [], [], [], []

        for single_singlshot_cond in calculation.get_singleshot_conductivity_dc:

            energy_ = single_singlshot_cond['energy']
            eta_ = single_singlshot_cond['eta']
            preserve_disorder_ = single_singlshot_cond['preserve_disorder']
            moments_ = single_singlshot_cond['num_moments']

            # get the lengts
            len_en = energy_.size
            len_eta = eta_.size
            len_preserve_dis = preserve_disorder_.size
            len_moments = moments_.size

            lengths = np.array([len_en, len_eta, len_preserve_dis, len_moments])

            # find the max length
            max_length = np.max(lengths)

            # check if lenghts are consistent
            if (len_en != max_length and len_en != 1) or (len_eta != max_length and len_eta != 1) or \
                    (len_preserve_dis != max_length and len_preserve_dis != 1) or \
                    (len_moments != max_length and len_moments != 1):
                raise SystemExit('Number of moments, eta, energy and preserve_disorder should either have the same '
                                 'length or specified as a single value! Choose them accordingly.')

            # make all lists equal in length
            if len_en == 1:
                energy_ = np.repeat(energy_, max_length)
            if len_eta == 1:
                eta_ = np.repeat(eta_, max_length)
            if len_preserve_dis == 1:
                preserve_disorder_ = np.repeat(preserve_disorder_, max_length)
            if len_moments == 1:
                moments_ = np.repeat(moments_, max_length)

            moments.append(moments_)
            energies.append(energy_)
            eta.append(eta_)
            random.append(single_singlshot_cond['num_random'])
            dis.append(single_singlshot_cond['num_disorder'])
            direction.append(single_singlshot_cond['direction'])
            preserve_disorder.append(preserve_disorder_)

        if len(calculation.get_singleshot_conductivity_dc) > 1:
            raise SystemExit('Only a single function request of each type is currently allowed. Please use another '
                             'configuration file for the same functionality.')
        grpc_p.create_dataset('NumMoments', data=np.asarray(moments), dtype=np.int32)
        grpc_p.create_dataset('NumRandoms', data=np.asarray(random), dtype=np.int32)
        grpc_p.create_dataset('NumDisorder', data=np.asarray(dis), dtype=np.int32)
        grpc_p.create_dataset('Energy', data=(np.asarray(energies) - config.energy_shift) / config.energy_scale,
                              dtype=np.float64)
        grpc_p.create_dataset('Gamma', data=np.asarray(eta) / config.energy_scale, dtype=np.float64)
        grpc_p.create_dataset('Direction', data=np.asarray(direction), dtype=np.int32)
        grpc_p.create_dataset('PreserveDisorder', data=np.asarray(preserve_disorder).astype(int), dtype=np.int32)

    print('\n##############################################################################\n')
    print('OUTPUT:\n')
    print('\nExporting of KITE configuration to {} finished.\n'.format(filename))
    print('\n##############################################################################\n')
    f.close()

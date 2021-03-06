from collections import Counter
import itertools as it
from mesohops.dynamics.hops_aux import AuxiliaryVector as AuxVec
from mesohops.util.dynamic_dict import Dict_wDefaults
from mesohops.dynamics.hierarchy_functions import (
    filter_aux_triangular,
    filter_aux_longedge,
    filter_markovian,
)
from mesohops.util.exceptions import AuxError, UnsupportedRequest

__title__ = "Hierarchy Class"
__author__ = "D. I. G. Bennett, Leo Varvelo"
__version__ = "1.0"


HIERARCHY_DICT_DEFAULT = {"MAXHIER": int(3), "TERMINATOR": False, "STATIC_FILTERS": []}

HIERARCHY_DICT_TYPES = dict(
    MAXHIER=[type(int())],
    TERMINATOR=[type(False), type(str())],
    STATIC_FILTERS=[type([])],
)


class HopsHierarchy(Dict_wDefaults):
    """
    HopsHierarchy defines the representation of the hierarchy in the HOPS
    calculation. It contains the user parameters, helper functions, and
    the list of all nodes contained in the hierarchy.
    """

    def __init__(self, hierarchy_param, system_param):
        """
        INPUTS
        ------
        1. hierarchy_param :
            [see hops_basis]
            a. MAXHIER : int                    [Allowed: >0]
                         The maximum depth in the hierarchy that will be kept
                         in the calculation.
            b. TERMINATOR : boolean             [Allowed: False]
                            The name of the terminator condition to be used.
            c. STATIC_FILTERS :                 [Allowed: Triangular, LongEdge, Domain]
                              The total set of nodes defined by MAXHIER can
                              be further filtered. This is a list of filters
                              [(filter_name1, [filter_param_1]), ...]

        2. system_param :
            [see hops_system]
            a. N_HMODES : int
                          number of modes that appear in hierarchy

        RETURNS
        -------
        None

        NOTE: This class is only well defined within the context of a specific
        calculation where the system parameters and hierarchy parameters have
        been set. YOU SHOULDN'T INSTANTIATE ONE OF THESE CLASSES YOURSELF.
        IF YOU FEEL THE NEED TO, YOU ARE PROBABLY DOING SOMETHING STRANGE.
        """
        self._default_param = HIERARCHY_DICT_DEFAULT
        self._param_types = HIERARCHY_DICT_TYPES

        self.param = hierarchy_param
        self.n_hmodes = system_param["N_HMODES"]
        self._auxiliary_list = []

    def initialize(self, flag_adaptive):
        """
        This function will initialize the hierarchy.

        PARAMETERS
        ----------
        1. flag_adaptive : boolean
                           boolean describing whether the calculation is adaptive or not

        RETURNS
        -------
        None
        """
        # Prepare the hierarchy
        # ---------------------
        if not flag_adaptive:
            self.auxiliary_list = self.define_triangular_hierarchy(
                self.n_hmodes, self.param["MAXHIER"]
            )
            self.auxiliary_list = self.filter_aux_list(self.auxiliary_list)

        else:
            # Initialize Guess for the hierarchy
            # NOTE: The first thing a hierarchy does is start expanding from the
            #       zero index. It might, at some point, be more efficient to
            #       initialize the hierarchy with an explicit guess (in combination
            #       with a restriction that no auxiliary nodes are removed until after
            #       Nsteps). At the moment, though, I'm skipping this and allowing
            #       the hierarchy to control its own growth.
            self.auxiliary_list = [AuxVec([], self.n_hmodes)]

    def filter_aux_list(self, list_aux):
        """
        A function that applies all of the filters defined for the hierarchy
        in "STATIC_FILTERS"

        PARAMETERS
        ----------
        1. list_aux : list
                      the list of auxiliaries that is to be filtered

        RETURNS
        -------
        1. list_aux : list
                      the filtered list of auxiliaries

        """
        for (filter_i, param_i) in self.param["STATIC_FILTERS"]:
            list_aux = self.apply_filter(list_aux, filter_i, param_i)

        return list_aux

    def apply_filter(self, list_aux, filter_name, params):
        """
        This is a function that implements a variety of different hierarchy filtering
        methods. In all cases, this filtering begins with the current list of auxiliaries
        and then prunes down from that list according to a set of rules.

        PARAMETERS
        ----------
        1. list_aux : list
                      the list of auxiliaries that needs to be filtered
        2. filter_name : str
                         name of filter
        3. params : list
                    the list of parameters for the filter

        RETURNS
        -------
        1. list_aux : list
                      a list of filtered auxiliaries


        ALLOWED LIST OF FILTERS:
        - Triangular: bolean_by_mode, [kmax, kdepth]
             If the mode has a non-zero value, then it is kept only if
             the value is less than kmax and the total auxillary is less
             than kdepth. This essentially truncates some modes at a lower
             order than the other modes.
        - LongEdge: bolean_by_mode, [kmax, kdepth]
             Beyond kdepth, only keep the edge terms upto kmax.
        """
        if filter_name == "Triangular":
            list_aux = filter_aux_triangular(
                list_aux=list_aux,
                list_boolean_by_mode=params[0],
                kmax=params[1][0],
                kdepth=params[1][1],
            )
        elif filter_name == "LongEdge":
            list_aux = filter_aux_longedge(
                list_aux=list_aux,
                list_boolean_by_mode=params[0],
                kmax=params[1][0],
                kdepth=params[1][1],
            )
        elif filter_name == "Markovian":
            list_aux = filter_markovian(list_aux=list_aux, list_boolean=params)
        else:
            raise UnsupportedRequest(filter_name, "hierarchy_static_filter")

        # Update STATIC_FILTERS parameters if needed
        # ------------------------------------------
        if not (
            [filter_name, params] in self.param["STATIC_FILTERS"]
            or (filter_name, params) in self.param["STATIC_FILTERS"]
        ):
            self.param["STATIC_FILTERS"].append((filter_name, params))

        return list_aux

    def _aux_index(self, aux, absolute=False):
        """
        This function will return the index value for a given auxiliary. The
        important thing is that this function is aware of whether or not the
        calculation should be using an 'absolute' index or a 'relative' index. 
        
        Absolute index: no matter what auxiliaries are in the hierarchy, the index
                        value does not change. This is a useful approach when trying
                        to do things like dynamic filtering. 
        
        Relative index: This is the more intuitive indexing scheme which only keeps
                        track of the auxiliary vectors that are actually in the
                        hierarchy.

        PARAMETERS
        ----------
        1. aux : Auxiliary object
                 a hops_aux auxiliary object
        2. absolute : boolean
                      describes whether the indexing should be relative or absolute
                      the default value is False

        RETURNS
        -------
        1. aux_index : int
                       aux_index is the relative or absolute index of a single
                       auxiliary
        """
        if absolute:
            return aux.absolute_index
        else:
            return self.auxiliary_list.index(aux)

    @staticmethod
    def _const_aux_edge(absindex_mode, depth, n_hmodes):
        """
        This function creates an auxiliary object for an edge node at
        a particular depth along a given mode. 

        PARAMETERS
        ----------
        1. absindex_mode : int
                           absolute index of the edge mode
        2. depth : int
                   the depth of the edge auxiliary
        3. n_hmodes : int
                      number of modes that appear in the hierarchy

        RETURNS
        -------
        1 aux : Auxiliary object
                the auxiliary at the the edge node

        """
        return AuxVec([(absindex_mode, depth)], n_hmodes)

    @staticmethod
    def define_triangular_hierarchy(n_hmodes, maxhier):
        """
        This function creates a triangular hierarchy

        PARAMETERS
        ----------
        1. n_hmodes : int
                      number of modes that appear in the hierarchy
        2. maxhier : int
                     the max single value of the hierarchy

        RETURNS
        -------
        1. list_aux : list
                      list of auxiliaries in the new triangular hierarchy
        """
        list_aux = []
        # first loop over hierarchy depth
        for k in range(maxhier + 1):
            # Second loop over
            for aux_raw in it.combinations_with_replacement(range(n_hmodes), k):
                count = Counter(aux_raw)
                list_aux.append(
                    AuxVec([(key, count[key]) for key in count.keys()], n_hmodes)
                )
        return list_aux

    @property
    def size(self):
        return len(self.auxiliary_list)

    @property
    def auxiliary_list(self):
        return self._auxiliary_list

    @auxiliary_list.setter
    def auxiliary_list(self, aux_list):
        aux_list.sort()
        if aux_list[0].absolute_index == 0:
            self._auxiliary_list = aux_list
        else:
            raise AuxError("Zero Vector not contained in list_aux!")

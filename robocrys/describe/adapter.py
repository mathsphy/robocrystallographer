"""
This module implements a class to resolve the symbolic references in condensed
structure data.
"""

from collections import namedtuple, defaultdict
from typing import Dict, Any, List, Union

from pymatgen.core.periodic_table import get_el_sp

ComponentDetails = namedtuple('ComponentDetails',
                              ['formula', 'count', 'dimensionality',
                               'molecule_name', 'orientation', 'index'])

ComponentGroup = namedtuple('ComponentGroup',
                            ['formula', 'dimensionality', 'count', 'components',
                             'molecule_name'])

SiteGroup = namedtuple('SiteGroup', ['element', 'count', 'sites'])

NeighborSiteDetails = namedtuple('NeighborSiteDetails',
                                 ['element', 'count', 'sites', 'sym_label'])


class DescriptionAdapter(object):
    """Class to facilitate pulling data from the condensed structure dictionary.

    Attributes:
        elements: The site elements.
        sym_labels: The symmetry labels as strings.
        use_iupac_ordering (bool, optional): Whether to order formulas
            by the iupac "electronegativity" series, defined in
            Table VI of "Nomenclature of Inorganic Chemistry (IUPAC
            Recommendations 2005)". This ordering effectively follows
            the groups and rows of the periodic table, except the
            Lanthanides, Actanides and hydrogen. If set to ``False``, the
            elements will be ordered according to the electronegativity values.

    Args:
        condensed_structure: The condensed structure data, formatted as produced
            by :meth:`robocrys.condense.StructureCondenser.condense_structure`.
    """

    def __init__(self, condensed_structure: Dict[str, Any],
                 use_iupac_ordering: bool = True):
        self._condensed_structure = condensed_structure
        self.use_iupac_ordering = use_iupac_ordering

        self.elements = {site_index: site_data['element']
                         for site_index, site_data in self.sites.items()}

        # convert the sym_labels tuple into a str. E.g. (1, 2, ) -> "(1,2)"
        self.sym_labels = {site_index: self.get_sym_label(site_index)
                           for site_index in self.sites.keys()}

    def get_nearest_neighbor_details(self, site_index: int,
                                     group_by_element: bool = False
                                     ) -> List[NeighborSiteDetails]:
        """Gets a summary of all the nearest neighbors to a site.

        Args:
            site_index: An inequivalent site index.
            group_by_element: Whether to group all nearest neighbor sites
                with the same element together.

        Returns:
            A :obj:`list` of ``ComponentDetails`` objects, each with the
            attributes:

            - ``element`` (``str``): The element of the nearest neighbor site.
            - ``count`` (``int``): The number of sites of this type.
            - ``sym_label`` (``str``): The symmetry label.
            - ``sites`` (``list[int]``): The site indices representing this
                nearest neighbor. Can be more than one site if
                ``group_by_element=True``.
        """
        nn_sites = self.sites[site_index]['nn']

        nn_dict = defaultdict(list)
        for nn_site in set(nn_sites):
            element = self.sites[nn_site]['element']
            all_labels = self.sites[nn_site]['sym_labels']
            identity = (element,) if group_by_element else (element, all_labels)

            count = nn_sites.count(nn_site)
            nn_dict[identity].append(
                {'count': count,
                 'labels': all_labels,
                 'site': nn_site})

        nn_details = []
        for identity, nn_group in nn_dict.items():
            # convert the sym_labels tuple into a str. E.g. (1, 2, ) -> "(1,2)"
            sites = [nn_site['site'] for nn_site in nn_group]
            nn_details.append(NeighborSiteDetails(
                element=identity[0],
                sites=sites,
                count=sum([nn_site['count'] for nn_site in nn_group]),
                sym_label=self.get_sym_label(sites)))

        return sorted(nn_details, key=self._site_order)

    def get_distance_details(self, from_site: int,
                             to_sites: Union[int, List[int]]) -> List[float]:
        """

        Args:
            from_site: An inequivalent site index.
            to_sites: One ore more inequivalent site indices.

        Returns:
            The distances between the sites.
        """
        if isinstance(to_sites, int):
            # If only one to_site is provided turn it into a list
            to_sites = [to_sites]

        return [distance for to_site in to_sites
                for distance in self.distances[from_site][to_site]]

    def get_component_details(self) -> List[ComponentDetails]:
        """Gets a summary of all components.

        Returns:
            A :obj:`list` of ``ComponentDetails`` objects, each with the
            attributes:

            - ``count`` (``int``): The number of these components in the
                structure.
            - ``formula`` (``str``): The component formula.
            - ``dimensionality`` (``int``): The component dimensionality.
            - ``molecule_name`` (``str`` or ``None``): The molecule name if
                applicable, else ``None``.
            - ``orientation`` (``tuple[int]``): The component orientation.
            - ``index`` (``list[int]``): The component inequivalent index.
        """
        component_details = []

        for index in set(self.component_makeup):
            component_details.append(ComponentDetails(
                count=self.component_makeup.count(index),
                formula=self.components[index]['formula'],
                dimensionality=self.components[index]['dimensionality'],
                molecule_name=self.components[index]['molecule_name'],
                orientation=self.components[index]['orientation'],
                index=index))

        return sorted(component_details, key=_component_order)

    def get_component_groups(self) -> List[ComponentGroup]:
        """Gets a summary of all components groups.

        Returns:
            The components, grouped together by formula, dimensionality and
            molecule name. The data will be returned as a :obj:`list` of
            ``ComponentGroup`` objects, each with the attributes:

            - ``count`` (``int``): The total number of components in this group.
            - ``formula`` (``str``): The formula of the components..
            - ``dimensionality`` (``int``): The dimensionality of the
                components.
            - ``molecule_name`` (``str`` or ``None``): The molecule name if
                applicable, else ``None``.
            - ``components`` (``list[ComponentDetails]``): The components
                in the group.
        """
        component_details = self.get_component_details()

        grouped_components = defaultdict(list)
        for component in component_details:
            identity = (component.dimensionality, component.formula,
                        component.molecule_name)
            grouped_components[identity].append(component)

        component_group_details = []
        for identity, group in grouped_components.items():
            component_group_details.append(ComponentGroup(
                count=sum(component.count for component in group),
                dimensionality=identity[0],
                formula=identity[1],
                molecule_name=identity[2],
                components=sorted(group, key=_component_order)))

        return sorted(component_group_details, key=_component_order)

    def get_component_site_groups(self, component_index: int
                                  ) -> List[SiteGroup]:
        """Gets a summary of the sites in a component.

        Returns:
            The sites, grouped together by element. The data will be returned
            as a :obj:`list` of ``SiteGroup`` objects, each with the attributes:

            - ``count`` (``int``): The total number of sites in this group.
            - ``element`` (``str``): The site element.
            - ``sites`` (``list[int]``): A list of site indices in this group.
        """
        sites = self.components[component_index]['sites']

        grouped_sites = defaultdict(list)
        for site_index in sites:
            grouped_sites[self.elements[site_index]].append(site_index)

        site_groups = []
        for element, group in grouped_sites.items():
            site_groups.append(SiteGroup(
                count=sum(sites.count(site_index) for site_index in group),
                element=element,
                sites=group))

        return sorted(site_groups, key=self._site_order)

    def get_sym_label(self, site_indices: Union[int, List[int]]) -> str:
        """Utility function to convert site indices into a sym label string."""
        # convert the sym_labels tuple into a str. E.g. (1, 2, ) -> "(1,2)"
        if isinstance(site_indices, int):
            site_indices = [site_indices]

        all_labels = sorted([label for site_index in site_indices for label in
                             self.sites[site_index]['sym_labels']])
        return "({})".format(",".join(map(str, sorted(all_labels))))

    @property
    def mineral(self) -> Dict[str, Union[str, int, bool]]:
        """The mineral data.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['mineral']

    @property
    def formula(self) -> str:
        """The structure formula.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['formula']

    @property
    def spg_symbol(self) -> str:
        """The space group symbol.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['spg_symbol']

    @property
    def crystal_system(self) -> str:
        """The crystal system.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['crystal_system']

    @property
    def dimensionality(self) -> int:
        """The overall dimensionality.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['dimensionality']

    @property
    def sites(self) -> Dict[int, Dict[str, Any]]:
        """The site data.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['sites']

    @property
    def distances(self) -> Dict[int, Dict[int, List[float]]]:
        """The distance data.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['distances']

    @property
    def angles(self) -> Dict[int, Dict[int, Dict[str, List[float]]]]:
        """The angle data.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['angles']

    @property
    def components(self) -> Dict[int, Dict[str, Any]]:
        """The component data.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['components']

    @property
    def component_makeup(self) -> List[int]:
        """The component makeup of the structure.

        See :meth:`robocrys.condense.StructureCondenser.condense_structure` for
        more details.
        """
        return self._condensed_structure['component_makeup']

    def _site_order(self, s):
        """Utility function to help sort NeighborSiteDetails and SiteGroups."""
        specie = get_el_sp(s.element)
        x = specie.iupac_ordering if self.use_iupac_ordering else specie.X

        if isinstance(s, NeighborSiteDetails):
            return [x, s.count, s.sym_label, s.sites]
        else:
            return [x, s.count, s.sites]



def _component_order(c):
    """Utility function to help sort ComponentDetails and ComponentGroups."""
    mn = c.molecule_name if c.molecule_name else 'z'

    if isinstance(c, ComponentDetails):
        ori = c.orientation if c.orientation else (0, 0, 0)
        return [mn, c.dimensionality, c.formula, ori, c.count]
    else:
        return [mn, c.dimensionality, c.formula, c.count]

# def get_next_nearest_neighbor_data(self, site_index: int
#                                    ) -> Dict[str, Any]:
#     """Gets a summary of the next nearest neighbor connectivity.
#
#     Args:
#         site_index: The site index (zero based).
#
#     Returns:
#         A summary of the next nearest neighbor information as a dict.
#         Formatted as::
#
#             {
#                 'Sn': {
#                     'octahedral': {
#                         'corner-sharing': {
#                             'n_sites': 8,
#                             'angles': [180, 180, 180, ...]
#                         }
#                     }
#                 }
#             }
#
#     """
#     nnn_info = self.get_next_nearest_neighbors(site_index)
#
#     # group next nearest neighbors by element, connectivity and geometry
#     # e.g. grouped_nnn looks like {el: {connectivity: {geometry: [sites]}}}
#     grouped_nnn = defaultdict(
#         lambda: defaultdict(lambda: defaultdict(list)))
#
#     for site in nnn_info:
#         grouped_nnn[site['element']][
#             site['geometry']['type']][site['connectivity']].append(site)
#
#     nnn_data = {}
#     for element, geom_data in grouped_nnn.items():
#         nnn_el_data = {}
#         for geometry, con_data in geom_data.items():
#             nnn_geom_data = {}
#             for connectivity, sites in con_data.items():
#                 nnn_geom_data[connectivity] = {
#                     'n_sites': len(sites),
#                     'angles': [angle for site in sites
#                                for angle in site['angles']]}
#             nnn_el_data[geometry] = nnn_geom_data
#         nnn_data[element] = nnn_el_data
#     return nnn_data

# def merge_similar_sites(sites: List[Dict[str, Any]]):
#     """Merges sites with the same properties except bond angles and distances.
#
#     Args:
#         sites: A list of sites. Each site is formatted as a :ob:`dict` with
#           the keys:
#
#             - ``'element'`` (``str``): The element of the site.
#             - ``'geometry'`` (``dict``): The geometry, as output by
#                 :meth:`SiteAnalyzer.get_site_geometry`.
#             - ``'nn_data'`` (``dict``): The nearest neighbor data, as output
#             by :meth:`SiteAnalyzer.get_nearest_neighbor_data`.
#             - ``'nnn_data'`` (``dict``): The next nearest neighbor data, as
#                 given by :meth:`SiteAnalyzer.get_next_nearest_neighbor_data`.
#
#     Returns:
#         A list of merged sites with the same format as above. Merged sites
#         have a different ``nn_data`` format than unmerged sites. For example,
#         ``nn_data`` in unmerged sites is formatted as::
#
#             {
#                 'Sn': {
#                     'n_sites': 6,
#                     'inequiv_groups': [
#                         {
#                             'n_sites': 4,
#                             'inequiv_id': 0,
#                             'dists': [1, 1, 2, 2]
#                         },
#                         {
#                             'n_sites': 2,
#                             'inequiv_id': 1,
#                             'dists': [3, 3]
#                         }
#                     ]
#                 }
#             }
#
#         Merged sites do not contain an ``inequiv_groups`` key and are instead
#         formatted as::
#
#             {
#                 'n_sites': 6
#                 'dists': [1, 1, 1, 2, 2, 2, 2, 3, 3]
#                 )
#             }
#
#         Note that there are now more distances than there are number of sites.
#         This is because n_sites gives the number of bonds to a specific site,
#         whereas the distances are for the complete set of distances for all
#         similar (merged) sites. Similarly, merged next nearest neighbor
#         data can contain more angles than number of sites, however, the
#         general format of the ``nnn_data`` dict is unaltered.
#     """
#     sites = copy.deepcopy(sites)
#     new_sites = []
#
#     for site in sites:
#
#         matched = False
#         for new_site in new_sites:
#             elem_match = site['element'] == new_site['element']
#             geom_match = geometries_match(
#                 site['geometry'], new_site['geometry'], likeness_tol=1)
#             nn_match = nn_summaries_match(
#                 site['nn_data'], new_site['nn_data'],
#                 match_bond_dists=False)
#             nnn_match = nnn_summaries_match(
#                 site['nnn_data'], new_site['nnn_data'],
#                 match_bond_angles=False)
#
#             if elem_match and geom_match and nn_match and nnn_match:
#                 new_site['nn_data'] = _merge_nn_data(site['nn_data'],
#                                                      new_site['nn_data'])
#                 new_site['nnn_data'] = _merge_nnn_data(site['nnn_data'],
#                                                        new_site['nnn_data'])
#                 matched = True
#                 break
#
#         if not matched:
#             # no matches therefore store original site id
#             new_sites.append(site)
#
#     return new_sites
#
#
# def _merge_nn_data(site_nn_data, new_site_nn_data):
#     """Utility function to merge nearest neighbor data.
#
#     See the ``merge_similar_sites`` docstring for information on the format of
#     the merged data.
#
#     Note an error will be thrown if this function is called on two sites that
#     not have matching nearest neighbor summaries (ignoring bond distances).
#     """
#
#     for el in site_nn_data:
#         site_dists = [dist for group in
#                       site_nn_data[el]['inequiv_groups']
#                       for dist in group['dists']]
#
#         if 'inequiv_groups' in new_site_nn_data[el]:
#             # remove inequiv_groups key and group all distances
#             # together
#             groups = new_site_nn_data[el].pop('inequiv_groups')
#             dists = [dist for dist_set in groups
#                      for dist in dist_set['dists']]
#             new_site_nn_data[el]['dists'] = dists + site_dists
#         else:
#             new_site_nn_data[el]['dists'] += site_dists
#
#     return new_site_nn_data
#
#
# def _merge_nnn_data(site_nnn_data, new_site_nnn_data):
#     """Utility function to merge next nearest neighbor data.
#
#     See the ``merge_similar_sites`` docstring for information on the format of
#     the merged data.
#
#     Note an error will be thrown if this function is called on two sites that
#     not have matching next nearest neighbor summaries (ignoring bond angles).
#     """
#     for el in site_nnn_data:
#         for geometry in site_nnn_data[el]:
#             for connectivity in site_nnn_data[el][geometry]:
#                 new_site_nnn_data[el][geometry][connectivity]['angles'].extend(
#                     site_nnn_data[el][geometry][connectivity]['angles'])
#
#     return new_site_nnn_data

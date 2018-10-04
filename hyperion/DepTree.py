import sys

class CircularReferenceException(Exception):
    def __init__(self, node1, node2):
        self.node1 = node1
        self.node2 = node2

class Node(object):
    pass

    def __init__(self, comp):
        self.component = comp
        self.depends_on = []
        self.comp_name = comp['name']

    def addEdge(self, node):
        self.depends_on.append(node)


def dep_resolve(node, resolved, unresolved):
    unresolved.append(node)
    for edge in node.depends_on:
        if edge not in resolved:
            if edge in unresolved:
                raise CircularReferenceException(node.comp_name, edge.comp_name)
            dep_resolve(edge, resolved, unresolved)
    resolved.append(node)
    unresolved.remove(node)
from copy import deepcopy

def corroborate(notes, supporters, tolerance=.1):
    """Experimental filter, NOT correctness proof. Match once per supporter run."""
    supported = set()
    for run in supporters:
        pairs = sorted((abs(a['start']-b['start']), i, j)
                       for i, a in enumerate(notes) for j, b in enumerate(run)
                       if a['pitch'] == b['pitch'] and abs(a['start']-b['start']) <= tolerance)
        used_a, used_b = set(), set()
        for _, i, j in pairs:
            if i not in used_a and j not in used_b:
                supported.add(i)
                used_a.add(i)
                used_b.add(j)
    return (deepcopy([n for i,n in enumerate(notes) if i in supported]),
            deepcopy([n for i,n in enumerate(notes) if i not in supported]))

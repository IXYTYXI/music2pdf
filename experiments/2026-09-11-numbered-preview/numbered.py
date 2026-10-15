def symbol(pitch):
    if int(pitch)!=pitch or not 0<=pitch<=127: raise ValueError('Invalid MIDI pitch')
    return (['1','♯1','2','♯2','3','4','♯4','5','♯5','6','♯6','7'][int(pitch)%12],int(pitch)//12-5)

def group_onsets(notes):
    groups=[]
    for n in sorted(notes,key=lambda n:(n['start'],-n['pitch'])):
        if not groups or n['start']-groups[-1][0]['start']>.06: groups.append([])
        groups[-1].append(n)
    return groups

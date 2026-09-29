from decode import decode, load_mag


def is_adsb(m):
    return len(m) == 28 and int(m[:2], 16) >> 3 ==17

if __name__ == "__main__":

    with open("../dump1090/truth_modes1.txt", "r") as f:
        data = f.read()
        lines = data.splitlines()
        key = set([line[1:-1].upper() for line in lines if is_adsb(line[1:-1])])

    found = decode(load_mag("../dump1090/testfiles/modes1.bin"))
    mine = { m for _, m in found if is_adsb(m)}

    print("dump1090:", len(key))
    print("yours:   ", len(mine))
    print("both:    ", len(key & mine))
    print("missed:  ", len(key - mine))
    print("extra:   ", len(mine - key))
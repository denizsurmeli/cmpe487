import random 


def fill_file(filepath: str, size: int):
    """
    Fills the `filepath` with `size` random bytes.
    """

    with open(filepath, 'w') as f:
        for i in range(size):
            f.write(str(chr(random.randint(33, 126))))


if __name__ == '__main__':
    two_mb = 2 * 1024 * 1024 # 2 MB
    fill_file('file.txt', 10000)
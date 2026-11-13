import sys
from .tasks import run

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], int(sys.argv[3]))

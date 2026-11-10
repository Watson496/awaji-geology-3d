"""Build present-day native-unit fields and condition them on finite fault surfaces."""
from gempy_fields import main
from fault_model import main as condition_faults

if __name__ == '__main__':
    main()
    # A single-unit/debug run does not produce a complete volume.
    import sys
    if not any(a.startswith(('--unit','--surface-only')) for a in sys.argv[1:]):
        condition_faults()

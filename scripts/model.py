"""現在の原地質単元の場を作り、有限断層面による条件を適用する。"""
from gempy_fields import main
from fault_model import main as condition_faults

if __name__ == '__main__':
    main()
    # 単一単元のデバッグ実行では、完全なボリュームは得られない。
    import sys
    if not any(a.startswith(('--unit','--surface-only')) for a in sys.argv[1:]):
        condition_faults()

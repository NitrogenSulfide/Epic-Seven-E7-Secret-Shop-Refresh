"""Offline preparation of private reference crops; no ADB, clicks or game access."""
import argparse
from e7_shop_navigation import prepare_references

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', required=True)
    parser.add_argument('--shop', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    prepare_references(args.home, args.shop, args.output)
    print('Private references created. Validate both screenshots offline before live use.')

#!/usr/bin/env python3
"""Install a nationwide reference core or download one verified deep dataset."""
import argparse
import json

from observatory.atlas import core_install, dataset_catalog, load_dataset, state_catalog
from observatory.db import Database
from observatory.settings import get_settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--core", action="store_true")
parser.add_argument("--dataset")
parser.add_argument("--state")
parser.add_argument("--catalog", action="store_true")
parser.add_argument("--offline", action="store_true")
args = parser.parse_args()
database = Database(get_settings())
if args.core:
    result = core_install(database, progress=lambda p: print(json.dumps(p), flush=True))
elif args.dataset:
    result = load_dataset(database, args.dataset, args.state, offline=args.offline,
        progress=lambda p: print(json.dumps(p), flush=True))
elif args.catalog:
    result = dataset_catalog(database, args.state)
else:
    result = state_catalog(database)
print(json.dumps(result, indent=2))

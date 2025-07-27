import argparse
from .indexer import index_project
from .finder import find_usages
from config import USAGES_INDEX_FILE


def main():
    """
    Command-line interface for find_usages package.
    """
    parser = argparse.ArgumentParser(
        prog="findusages", description="Index and find usages using Jedi"
    )
    parser.add_argument("--make-index", action="store_true", help="Build index.json")
    parser.add_argument(
        "--index-file", default=USAGES_INDEX_FILE, help="Path to index JSON"
    )
    parser.add_argument("root", nargs="?", default=".", help="Project root directory")
    parser.add_argument("target", nargs="?", help="Target name or FQN to find usages")
    args = parser.parse_args()

    if args.make_index:
        index_project(args.root, args.index_file)
    else:
        if not args.target:
            parser.error("Target required when not building index")
        try:
            results = find_usages(args.target, args.root, args.index_file)
            if not results:
                print(f"No usages found for '{args.target}'")
            else:
                for result in results:
                    print(
                        f"{result.get('path')}:{result.get('line')}:{result.get('column')}  -> {result.get('fqn')}"
                    )
        except FileNotFoundError as e:
            print(str(e))


if __name__ == "__main__":
    main()

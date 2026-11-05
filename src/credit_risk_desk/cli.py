import argparse
import json

from .db import get_engine


def main():
    parser = argparse.ArgumentParser(description="Credit Risk Desk data and model commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed-demo")
    fetch = sub.add_parser("download-berka")
    fetch.add_argument("--directory", default="data/raw/berka")
    imp = sub.add_parser("import-berka")
    imp.add_argument("--directory", default="data/raw/berka")
    train_parser = sub.add_parser("train")
    train_parser.add_argument("--output", default="artifacts")
    args = parser.parse_args()
    from .ingest import demo_frames, download, load_dataset, read_berka
    if args.command == "download-berka":
        result = download(args.directory)
    elif args.command == "seed-demo":
        result = load_dataset(get_engine(), demo_frames(), "demo", {"generator": "demo_frames-v1", "seed": 42})
    elif args.command == "import-berka":
        frames, manifest = read_berka(args.directory)
        result = load_dataset(get_engine(), frames, "berka", manifest)
    else:
        from .ml import train
        report = train(get_engine(), args.output)
        result = {"model_version": report["model_version"], "split_counts": report["split_counts"], "test": report["test"]}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

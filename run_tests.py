#!/usr/bin/env python3
"""Build the real Salam programs, then exercise BOMCheck as a separate process."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=os.environ.get("SALAM", "salam"))
    args = parser.parse_args()
    compiler = shutil.which(args.compiler) or str(Path(args.compiler).resolve())
    root = Path(__file__).resolve().parent
    build = root / "build"
    build.mkdir(exist_ok=True)
    sources = ["test_references", "test_csv", "test_bom", "test_report", "main"]
    for source in sources:
        target = "bomcheck" if source == "main" else source
        result = subprocess.run(
            [compiler, "build", source + ".salam", "--output=" + str(build / target)],
            cwd=root, capture_output=True, text=True, timeout=120,
        )
        (build / (source + ".log")).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise AssertionError(source + " build failed:\n" + result.stderr[-5000:])
        if source != "main":
            subprocess.run([str(build / target)], check=True, timeout=20)

    binary = str(build / "bomcheck")
    header = "references,quantity,value,footprint\n"
    cases = []

    def case(name, data, exit_code=0, error=None, quantity=None, groups=None):
        cases.append((name, data, exit_code, error, quantity, groups))

    case("single", header + "R1,1,10k,0402\n", quantity=1, groups=1)
    case("range", header + "r1-r3,3,10k,0402\nR4,1,10k,0402\n", quantity=4, groups=1)
    case("separators", header + '"R1,R2; R3\tR4",4,10k,0402\n', quantity=4)
    case("unicode", header + 'R1,1,"10kΩ, ±1% 🔧",0402\n', quantity=1)
    case("escaped", header + 'R1,1,"10k ""quote"" \\ path",0402\n', quantity=1)
    case("reordered", "footprint,value,quantity,references\n0402,10k,1,R1\n", quantity=1)
    case("trimmed", " references , quantity , value , footprint \n R1 , 1 , 10k , 0402 \n", quantity=1)
    case("bom-crlf", "\ufeff" + header.replace("\n", "\r\n") + "\r\nR1,1,10k,0402\r\n", quantity=1)
    case("no-final-newline", header + "R1,1,10k,0402", quantity=1)
    case("empty", "", 1, "header")
    case("only-header", header, 1, "empty")
    case("duplicate-header", "references,quantity,value,value\n", 1, "header")
    case("unknown-header", "references,quantity,value,package\n", 1, "header")
    case("extra-header", header.strip() + ",extra\n", 1, "header")
    case("missing-column", header + "R1,1,10k\n", 1, "columns")
    case("extra-column", header + "R1,1,10k,0402,x\n", 1, "columns")
    case("blank-value", header + "R1,1,,0402\n", 1, "value")
    case("blank-footprint", header + "R1,1,10k,\n", 1, "footprint")
    for value in ["0", "-1", "+1", "1.0", "1e0", "10001", "9" * 100, "", "１"]:
        case("bad-quantity-" + value[:12], header + "R1," + value + ",10k,0402\n", 1, "quantity")
    for refs in ["R0", "R01", "R1000001", "1R", "R", "Ω1", "R1-R0", "R2-R1", "R1-C2", "R1-", "R1-R2-R3", "", "R1/R2"]:
        case("bad-ref-" + refs, header + refs + ",1,10k,0402\n", 1, "references")
    case("quantity-mismatch", header + "R1-R3,2,10k,0402\n", 1, "quantity_mismatch")
    case("duplicate-row", header + "R1 R1,2,10k,0402\n", 1, "duplicate_reference")
    case("duplicate-cross-row", header + "R1-R3,3,10k,0402\nr2,1,22k,0603\n", 1, "duplicate_reference")
    case("quote-in-unquoted", header + 'R1,1,10"k,0402\n', 1, "csv")
    case("trailing-after-quote", header + 'R1,1,"10k"x,0402\n', 1, "csv")
    case("unclosed-quote", header + 'R1,1,"10k,0402\n', 1, "csv")
    case("multiline-field", header + 'R1,1,"10k\npart",0402\n', 1, "csv")
    case("ref-row-limit", header + "R1-R10001,10000,10k,0402\n", 1, "references")
    case("ref-total-limit", header + "R1-R6000,6000,10k,0402\nC1-C5000,5000,10nF,0603\n", 1, "limit")
    case("ref-total-boundary", header + "R1-R10000,10000,10k,0402\n", quantity=10000, groups=1)
    case("field-boundary", header + "R1,1," + "a" * 4096 + ",0402\n", quantity=1)
    case("field-limit", header + "R1,1," + "a" * 4097 + ",0402\n", 1, "csv")
    case("row-boundary", header + "".join(f"R{i},1,10k,0402\n" for i in range(1, 2001)), quantity=2000)
    case("row-limit", header + "".join(f"R{i},1,10k,0402\n" for i in range(1, 2002)), 1, "csv")
    case("file-limit", b"x" * 1048577, 2, "input")
    case("nul-tail", (header + "R1,1,10k,0402\n").encode() + b"\0unvalidated", 2, "input")
    for raw in [b"\xff", b"\xc0\x80", b"\xed\xa0\x80", b"\xf4\x90\x80\x80", b"\xe2\x82"]:
        case("invalid-utf8-" + raw.hex(), header.encode() + b"R1,1," + raw + b",0402\n", 2, "input")
    case("escape-control", header + "R1,1,\x1b[31m10k,0402\n", 2, "input")
    case("bare-cr", header + "R1,1,10k,0402\r", 2, "input")

    results = []
    with tempfile.TemporaryDirectory(prefix="bomcheck-tests-") as directory:
        folder = Path(directory)
        for index, (name, data, code, error, quantity, groups) in enumerate(cases):
            path = folder / (str(index) + "-input.csv")
            content = data.encode("utf-8") if isinstance(data, str) else data
            path.write_bytes(content)
            before = hashlib.sha256(content).hexdigest()
            run = subprocess.run([binary, "--json", str(path)], capture_output=True, timeout=20)
            assert run.returncode == code, (name, run.returncode, run.stderr)
            output = json.loads(run.stdout)
            assert output["valid"] == (code == 0), (name, output)
            if error:
                assert error in [e["code"] for e in output["errors"]], (name, output)
                assert output["total_quantity"] is None and output["groups"] == [], (name, output)
            if quantity is not None:
                assert output["total_quantity"] == quantity, (name, output)
            if groups is not None:
                assert len(output["groups"]) == groups, (name, output)
            assert hashlib.sha256(path.read_bytes()).hexdigest() == before, name + " mutated input"
            results.append({"case": name, "exit": code, "passed": True})

        for name, argv, code in [
            ("missing-path", [], 2), ("unknown-option", ["--wat"], 2),
            ("extra-path", ["a", "b"], 2), ("help", ["--help"], 0),
            ("unreadable-missing", ["--json", str(folder / "missing.csv")], 2),
            ("directory", ["--json", str(folder)], 2),
        ]:
            run = subprocess.run([binary] + argv, capture_output=True, timeout=20)
            assert run.returncode == code, (name, run.stderr)
            results.append({"case": name, "exit": code, "passed": True})

        path = folder / "-input.csv"
        path.write_text(header + "R1,1,10k,0402\n")
        run = subprocess.run([binary, "--json", "--", "-input.csv"], cwd=folder, capture_output=True, timeout=20)
        assert run.returncode == 0 and json.loads(run.stdout)["total_quantity"] == 1
        results.append({"case": "option-terminator", "exit": 0, "passed": True})

    valid_example = subprocess.run([binary, "example-valid.csv"], cwd=root, capture_output=True, text=True, timeout=20)
    assert valid_example.returncode == 0 and "4 x 10kΩ" in valid_example.stdout
    results.append({"case": "text-report", "exit": 0, "passed": True})
    (build / "test-results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"{len(results)} CLI cases passed; all file inputs unchanged")


if __name__ == "__main__":
    main()

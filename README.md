# Salam BOMCheck

BOMCheck is an offline bill-of-materials validator **built with the [Salam Programming Language](https://github.com/SalamLang/Salam)**. It catches duplicate component references, invalid reference ranges and quantity mismatches before you share a BOM with an assembler. It reads one CSV and prints either a readable report or JSON; it never modifies the input or contacts a service.

## Build and run

Use the official **Salam 0.5.0** release. Native execution is tested on macOS arm64; other platforms have not been verified. Download the matching release archive and verify its accompanying SHA-256 before extracting it. Keep the bundled `std` directory beside the compiler. No global installation is required.

```sh
mkdir -p build
/path/to/salam build main.salam --output=build/bomcheck
./build/bomcheck example-valid.csv
./build/bomcheck --json example-invalid.csv
```

The valid example contains seven components, including four identical resistors:

```text
VALID BOM: 4 row(s), 7 unique reference(s)
Total quantity: 7
4 x 10kΩ | Resistor_SMD:R_0402
2 x 100nF, 10% | Capacitor_SMD:C_0603
1 x Green | LED_SMD:LED_0805
```

`--help` explains usage. Use `--` before a filename beginning with a hyphen. Exit codes are **0** for a valid BOM, **1** for CSV/schema/BOM errors and **2** for usage or file-input failures. `--json` returns an object with `valid`, `rows`, `unique_references`, `total_quantity`, `groups` and `errors`. File-input errors use line `0`; BOM diagnostics use physical, one-based lines.

**Invalid input never produces a partial purchasing summary:** `total_quantity` is `null` and `groups` is empty. Row/reference counts on invalid BOMs reflect only processing completed before the error, not a complete inventory.

## CSV contract

The header must contain these four unique column names, in any order:

```csv
references,quantity,value,footprint
R1-R3,3,10k,Resistor_SMD:R_0402
"C1,C2",2,"100nF, 10%",Capacitor_SMD:C_0603
```

- References contain ASCII letters followed by an integer from `1` through `1000000`, with no leading zeros. Letter case is normalized (`r1` and `R1` are the same component). Multi-letter prefixes such as `LED1` are supported.
- Spaces, tabs, commas and semicolons separate references. A range such as `R1-R4` includes both endpoints and requires matching prefixes in ascending order. Spaces inside a range are not supported.
- Quantity is a positive decimal integer and must equal the number of expanded references on that row. Duplicate references are errors within a row or across the whole BOM, even when the rows have different values or footprints.
- Value and footprint must be nonempty. Whitespace around headers and fields is trimmed. Valid rows with equal trimmed value and footprint are grouped in first-appearance order; these strings are case-sensitive.
- UTF-8, an optional leading UTF-8 BOM, LF/CRLF endings, quoted commas and doubled quotes are supported. Empty physical lines are ignored. Quoted fields must fit on one physical line; malformed quoting is rejected rather than repaired.
- Limits: **1 MiB per file, 2000 data rows, 10000 expanded references in total, 4096 bytes per field, 65536 bytes per physical line**. NUL, malformed UTF-8, other ASCII control bytes (except tab/newline/CRLF) and bare CR endings are rejected. Supply ordinary files, not pipes/devices.

This is a structural check of the supplied table. It does not inspect schematics, verify component availability, validate footprint-library names, compare prices, or determine electrical correctness.

## Tests

Python 3.9+ is used only as a test driver. The application itself is Salam. The test runner builds the real programs, runs four native unit programs, then executes black-box CLI cases covering normal input, malformed data, resource boundaries, UTF-8, JSON parsing, exit codes and unchanged input-file hashes:

```sh
python3 run_tests.py --compiler /path/to/salam
/path/to/salam format --check *.salam
```

The runner writes native build logs and `test-results.json` under ignored `build/`. It requires no Python packages or network access. It fails if a build or assertion fails. `example-invalid.csv` intentionally contains a quantity mismatch, a duplicate reference, a leading-zero reference and a blank value.

## Source layout

| File | Responsibility |
| --- | --- |
| `numbers.salam` | Bounded decimal conversion without integer overflow |
| `references.salam` | Reference grammar, normalization and range expansion |
| `csv_input.salam` | Strict CSV parsing and physical line tracking |
| `bom.salam` | Header, quantity, duplicate and required-field validation |
| `summary.salam` | Complete quantity grouping for valid BOMs |
| `report.salam` | Text and JSON diagnostics/reports |
| `input.salam` | Bounded read-only file loading and UTF-8 validation |
| `options.salam` | Command-line arguments and help |
| `main.salam` | Application flow and exit status |
| `test_*.salam`, `run_tests.py` | Native unit checks and process-level regressions |

## Development and license

Development, documentation and tests were produced with OpenAI Codex on behalf of the repository owner. The native tests and CLI checks were actually executed; no independent human review is claimed. The project was built incrementally, with working parsing, validation, reporting and CLI milestones recorded separately.

GPL-3.0; see [LICENSE](LICENSE). Salam's compiler and standard library are distributed separately under their own notices. This repository does not bundle a compiler or generated binary.

# Native fuzz tests

`decoder` exercises valid and malformed RF frames, rejected-output preservation and learned button mappings. `transmit` checks binary widths, invalid characters, protocol/repeat limits and signed Dooya fields.

Run with Clang and its libFuzzer runtime:

```sh
bash fuzz/run.sh 60
```

The argument is seconds per target (default 60). On macOS, select a Clang installation with libFuzzer, for example `CXX=/opt/homebrew/opt/llvm/bin/clang++ bash fuzz/run.sh 60`. AddressSanitizer and UndefinedBehaviorSanitizer instrument the production headers. Inputs are limited to 4096 bytes, individual runs to 5 seconds, and resident memory to 512 MiB. The synthetic corpus contains no device captures or credentials; no device or network access occurs.

The runner copies seeds and builds into a fresh temporary directory. Successful runs remove it; failures print its location and retain the executable, corpus and crash input for reproduction. Checked-in seeds are never modified. CI runs a 15-second smoke campaign per target.

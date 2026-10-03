#!/bin/sh
# Use the pinned toolchain even when Homebrew's cargo/rustc precede rustup on PATH.
set -eu
KWR_TOOLCHAIN=1.96.0
RUSTC="$(rustup which --toolchain "$KWR_TOOLCHAIN" rustc)"
RUSTDOC="$(rustup which --toolchain "$KWR_TOOLCHAIN" rustdoc)"
export RUSTC RUSTDOC
PATH="${RUSTC%/*}:$PATH"
export PATH
exec cargo "$@"

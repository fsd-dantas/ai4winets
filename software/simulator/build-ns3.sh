#!/usr/bin/env bash
# Reproducible ns-3 build for the ECoRA simulator, from the declaration in ns3-build.json.
#
#   software/simulator/build-ns3.sh [ROOT]
#
# ROOT defaults to $ECORA_NS3_ROOT, then to ~/ecora-ns3. The script downloads the pinned
# archive if it is absent, refuses one whose SHA-256 differs, extracts it into a fresh tree,
# configures and builds the declared modules under the declared profile, and writes two
# files to ROOT/out: the attribute registry dump and the build facts. The model manifest is
# assembled from those by `python -m ecora simulator-manifest`, so it is hashed with the
# same canonical encoding as every other record.
#
# An existing source tree is reused only if this script created it. A tree extracted or
# edited by anything else is not evidence of what the pinned release contains.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
declaration="$here/ns3-build.json"
root="${1:-${ECORA_NS3_ROOT:-$HOME/ecora-ns3}}"

field() { python3 -c "import json,sys; v=json.load(open(sys.argv[1]))[sys.argv[2]]; print(v if isinstance(v,str) else '\n'.join(v) if isinstance(v,list) else '\n'.join(f'-D{k}={x}' for k,x in v.items()))" "$declaration" "$1"; }

release="$(field release)"
archive="$(field archive)"
url="$(field url)"
sha256="$(field sha256)"
source_dir="$root/$(field source_dir)"
profile="$(field build_profile)"
modules="$(field modules | paste -sd ';')"
mapfile -t flags < <(field configure_flags)
mapfile -t defines < <(field cmake_defines)
mapfile -t programs < <(field programs)

mkdir -p "$root/out"
cd "$root"

if [[ ! -f "$archive" ]]; then
    echo "downloading $url"
    curl -sSfL -o "$archive.part" "$url"
    mv "$archive.part" "$archive"
fi
actual="$(sha256sum "$archive" | cut -d' ' -f1)"
if [[ "$actual" != "$sha256" ]]; then
    echo "refused: $archive has SHA-256 $actual, declared $sha256" >&2
    exit 1
fi
echo "verified $archive $actual"

stamp="$source_dir/.ecora-extracted"
if [[ -d "$source_dir" && ! -f "$stamp" ]]; then
    echo "refused: $source_dir exists and was not extracted by this script" >&2
    exit 1
fi
if [[ ! -d "$source_dir" ]]; then
    tar -xjf "$archive"
    echo "$actual" > "$stamp"
fi
if [[ "$(cat "$stamp")" != "$sha256" ]]; then
    echo "refused: $source_dir was extracted from a different archive" >&2
    exit 1
fi

for program in "${programs[@]}"; do
    cp "$here/src/$program.cc" "$source_dir/scratch/$program.cc"
done

cd "$source_dir"
./ns3 clean >/dev/null 2>&1 || true
./ns3 configure --build-profile="$profile" --enable-modules="$modules" "${flags[@]}" -- "${defines[@]}"
./ns3 build "${programs[@]}"

# Profiles other than release and default carry a suffix, as in ns3.48-name-debug.
binary() { find "$source_dir/build/scratch" -maxdepth 1 -type f \( -name "ns${release}-$1" -o -name "ns${release}-$1-*" \) -perm -u+x | head -1; }
attributes="$(binary ecora-attributes)"
[[ -n "$attributes" ]] || { echo "refused: ecora-attributes was not built" >&2; exit 1; }
"$attributes" > "$root/out/ns3-attributes.json"

# What configure actually enabled, dependencies included, as ns-3 recorded it.
resolved="$(python3 -c "import ast,glob,re,sys; t=open(glob.glob(sys.argv[1]+'/.lock-ns3_*')[0]).read(); m=re.search(r'^NS3_ENABLED_MODULES = (\[.*\])', t, re.M); print(';'.join(sorted(x[4:] for x in ast.literal_eval(m.group(1)))))" "$source_dir")"
cache="$source_dir/cmake-cache/CMakeCache.txt"
cachevalue() { grep -E "^$1:" "$cache" | head -1 | cut -d= -f2-; }
python3 - "$root/out/build-facts.json" <<EOF
import json, platform, subprocess, sys
def first(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()[0]
facts = {
    "release": "$release", "archive_sha256": "$actual", "build_profile": "$profile",
    "enabled_modules": "$modules".split(";"),
    "resolved_modules": "$resolved".split(";"),
    "configure_flags": $(python3 -c "import json,sys; print(json.dumps(sys.argv[1:]))" "${flags[@]}"),
    "cmake_defines": $(python3 -c "import json,sys; print(json.dumps(sys.argv[1:]))" "${defines[@]}"),
    "cmake_build_type": "$(cachevalue CMAKE_BUILD_TYPE)",
    "cxx_compiler": first(["$(cachevalue CMAKE_CXX_COMPILER)", "--version"]),
    "cxx_flags_release": "$(cachevalue CMAKE_CXX_FLAGS_RELEASE)",
    "cmake": first(["cmake", "--version"]),
    "generator": "$(cachevalue CMAKE_GENERATOR)",
    "native_optimizations": "$(cachevalue NS3_NATIVE_OPTIMIZATIONS)",
    "asserts": "$(cachevalue NS3_ASSERT)",
    "logs": "$(cachevalue NS3_LOG)",
    "platform": platform.platform(),
    "machine": platform.machine(),
}
json.dump(facts, open(sys.argv[1], "w"), indent=2, sort_keys=True)
EOF
echo "wrote $root/out/ns3-attributes.json and $root/out/build-facts.json"

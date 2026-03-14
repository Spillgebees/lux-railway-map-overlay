#!/usr/bin/env bash
set -euo pipefail

output_dir="${1:-/glyphs/output}"
font_maker_bin="${2:-/tmp/font-maker/build/font-maker}"
plex_ref="${IBM_PLEX_REF:-d9eb8cf4ea24ed0a670bcf7b5bbd4434a17e3b53}"
plex_base_url="https://raw.githubusercontent.com/googlefonts/plex/${plex_ref}/packages/plex-sans/fonts/complete/ttf"
plex_cache_dir="/tmp/ibm-plex-sans"
noto_font_dir="/usr/share/fonts/truetype/noto"

plex_regular_font="${plex_cache_dir}/IBMPlexSans-Regular.ttf"
plex_bold_font="${plex_cache_dir}/IBMPlexSans-Bold.ttf"
noto_regular_font="${noto_font_dir}/NotoSans-Regular.ttf"
noto_italic_font="${noto_font_dir}/NotoSans-Italic.ttf"
noto_bold_font="${noto_font_dir}/NotoSans-Bold.ttf"

if [ ! -x "$font_maker_bin" ]; then
    echo "Missing font-maker binary: $font_maker_bin" >&2
    exit 1
fi

mkdir -p "$plex_cache_dir" "$output_dir"

curl -fsSL "${plex_base_url}/IBMPlexSans-Regular.ttf" -o "$plex_regular_font"
curl -fsSL "${plex_base_url}/IBMPlexSans-Bold.ttf" -o "$plex_bold_font"

for font_path in "$plex_regular_font" "$plex_bold_font" "$noto_regular_font" "$noto_italic_font" "$noto_bold_font"; do
    if [ ! -f "$font_path" ]; then
        echo "Missing font file: $font_path" >&2
        exit 1
    fi
done

temp_root="$(mktemp -d)"
plex_regular_output_dir="${temp_root}/plex-regular"
plex_bold_output_dir="${temp_root}/plex-bold"
noto_regular_output_dir="${temp_root}/noto-regular"
noto_italic_output_dir="${temp_root}/noto-italic"
noto_bold_output_dir="${temp_root}/noto-bold"

trap 'rm -rf "$temp_root"' EXIT

"$font_maker_bin" --name "IBM Plex Sans Regular" "$plex_regular_output_dir" "$plex_regular_font"
"$font_maker_bin" --name "IBM Plex Sans Bold" "$plex_bold_output_dir" "$plex_bold_font"
"$font_maker_bin" --name "Noto Sans Regular" "$noto_regular_output_dir" "$noto_regular_font"
"$font_maker_bin" --name "Noto Sans Italic" "$noto_italic_output_dir" "$noto_italic_font"
"$font_maker_bin" --name "Noto Sans Bold" "$noto_bold_output_dir" "$noto_bold_font"

cp -R "$plex_regular_output_dir"/. "$output_dir"/
cp -R "$plex_bold_output_dir"/. "$output_dir"/
cp -R "$noto_regular_output_dir"/. "$output_dir"/
cp -R "$noto_italic_output_dir"/. "$output_dir"/
cp -R "$noto_bold_output_dir"/. "$output_dir"/
